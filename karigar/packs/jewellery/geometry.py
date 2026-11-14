"""Parametric jewellery geometry in Blender (bpy + bmesh). Units: millimetres.

Every builder produces closed (manifold) solids, unions all gold parts into
one castable body, and reports its volume. Orientation convention for the
finished piece: rings and bangles stand upright in the XZ plane (axis = Y),
pendants face the camera (-Y); +Z is up.
"""
from __future__ import annotations

import hashlib
import json
import math
from collections import OrderedDict
from dataclasses import dataclass, field

import bpy  # must precede bmesh
import bmesh
from mathutils import Matrix, Vector

from . import dfm
from .schema import DesignSpec

ROT_UPRIGHT = Matrix.Rotation(math.radians(90), 4, "X")   # XY-plane build -> XZ plane


# ---------------------------------------------------------------- scene utils
def clear_scene() -> None:
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    for coll in (bpy.data.meshes, bpy.data.materials, bpy.data.cameras, bpy.data.lights,
                 bpy.data.collections, bpy.data.images):
        for d in list(coll):
            try:
                coll.remove(d)
            except (RuntimeError, ReferenceError):
                pass


def _obj_from_bm(bm: bmesh.types.BMesh, name: str, smooth: bool = True) -> bpy.types.Object:
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    me.polygons.foreach_set("use_smooth", [smooth] * len(me.polygons))
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def mesh_volume(ob: bpy.types.Object) -> float:
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    bm.transform(ob.matrix_world)
    v = bm.calc_volume(signed=False)
    bm.free()
    return v


def union(objs: list[bpy.types.Object], name: str) -> bpy.types.Object:
    """Boolean-union parts into one manifold body (what the casting unit receives)."""
    if len(objs) == 1:
        objs[0].name = name
        return objs[0]
    base, rest = objs[0], objs[1:]
    coll = bpy.data.collections.new(name + "_parts")
    bpy.context.scene.collection.children.link(coll)
    for o in rest:
        bpy.context.scene.collection.objects.unlink(o)
        coll.objects.link(o)
    mod = base.modifiers.new("union", "BOOLEAN")
    mod.operation = "UNION"
    mod.operand_type = "COLLECTION"
    mod.collection = coll
    mod.solver = "MANIFOLD"
    dg = bpy.context.evaluated_depsgraph_get()
    dg.update()
    me = bpy.data.meshes.new_from_object(base.evaluated_get(dg))
    if len(me.polygons) == 0:  # fall back to the slower exact solver
        bpy.data.meshes.remove(me)
        mod.solver = "EXACT"
        dg.update()
        me = bpy.data.meshes.new_from_object(base.evaluated_get(dg))
    out = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(out)
    for o in objs:
        bpy.data.objects.remove(o, do_unlink=True)
    bpy.data.collections.remove(coll)
    return out


# ------------------------------------------------------------- primitives
def _profile(cx: float, a: float, b: float, n_in: float, n_out: float, segs: int):
    """Closed cross-section in the (radial x, axial z) plane, centred at (cx, 0).
    a = half radial thickness, b = half axial width. Superellipse exponents:
    2 = oval, ~6 = flat/court, ~1.2 = knife edge. Innermost point sits exactly
    at x = cx - a (the finger/wrist surface)."""
    pts = []
    for i in range(segs):
        th = 2 * math.pi * i / segs
        c, s = math.cos(th), math.sin(th)
        n = n_out if c >= 0 else n_in
        x = cx + a * math.copysign(abs(c) ** (2 / n), c)
        z = b * math.copysign(abs(s) ** (2 / n), s)
        pts.append((x, z))
    return pts


def _revolve(profile, steps: int) -> bmesh.types.BMesh:
    bm = bmesh.new()
    vs = [bm.verts.new((x, 0.0, z)) for x, z in profile]
    es = [bm.edges.new((vs[i], vs[(i + 1) % len(vs)])) for i in range(len(vs))]
    bmesh.ops.spin(bm, geom=vs + es, cent=(0, 0, 0), axis=(0, 0, 1),
                   angle=2 * math.pi, steps=steps, use_merge=True)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
    return bm


PROFILE_EXP = {  # (inner, outer) superellipse exponents
    "comfort": (2.6, 2.6), "flat": (6.0, 6.0), "knife": (2.6, 1.25), "faceted": (2.0, 2.0),
}


def band(inner_d: float, width: float, thickness: float, profile: str, steps=160, segs=40, name="band",
         inscribed: bool = False):
    n_in, n_out = PROFILE_EXP[profile]
    if profile == "faceted":
        steps, segs = 36, 6
    a = thickness / 2
    # The revolve is a `steps`-gon, whose flat facets sit inside its vertices.
    # inscribed=True pushes the innermost vertex ring out so the inscribed
    # circle (what a ring mandrel measures) is exactly inner_d. Bangles keep
    # vertices on inner_d (their facet sag is < 0.005 mm and their golden
    # weight stays unchanged).
    r_in = inner_d / 2 / math.cos(math.pi / steps) if inscribed else inner_d / 2
    bm = _revolve(_profile(r_in + a, a, width / 2, n_in, n_out, segs), steps)
    return _obj_from_bm(bm, name, smooth=(profile != "faceted"))


def torus(major_r: float, minor_r: float, name="torus", steps=64, segs=16):
    return _obj_from_bm(_revolve(_profile(major_r, minor_r, minor_r, 2, 2, segs), steps), name)


def cylinder(center, radius: float, z_lo: float, z_hi: float, name="cylinder", segs=32):
    """Closed upright cylinder (axis Z) centred on (center.x, center.y)."""
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=True, segments=segs, radius1=radius,
                          radius2=radius, depth=z_hi - z_lo)
    bmesh.ops.translate(bm, vec=Vector((center[0], center[1], (z_lo + z_hi) / 2)), verts=bm.verts)
    return _obj_from_bm(bm, name)


def sphere(center, radii, name="sphere", u=24, v=16):
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=u, v_segments=v, radius=1.0)
    bmesh.ops.scale(bm, vec=Vector(radii), verts=bm.verts)
    bmesh.ops.translate(bm, vec=Vector(center), verts=bm.verts)
    return _obj_from_bm(bm, name)


def rod(p0, p1, radius: float, name="rod", segs=16):
    """Cylinder from p0 to p1 with rounded (spherical) tip at p1."""
    p0, p1 = Vector(p0), Vector(p1)
    d = p1 - p0
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=segs, radius1=radius, radius2=radius, depth=d.length)
    bmesh.ops.translate(bm, vec=Vector((0, 0, d.length / 2)), verts=bm.verts)
    rot = Vector((0, 0, 1)).rotation_difference(d.normalized()).to_matrix().to_4x4()
    bm.transform(Matrix.Translation(p0) @ rot)
    ob = _obj_from_bm(bm, name)
    tip = sphere(p1, (radius * 1.15,) * 3, name + "_tip", u=16, v=10)
    return [ob, tip]


def gem(d: float, name="gem", segs=16):
    """Faceted round-brilliant proxy as one closed mesh. Girdle at z=0."""
    r = d / 2
    pav, crown, girdle, table_r = 0.43 * d, 0.16 * d, 0.025 * d, 0.285 * d
    bm = bmesh.new()
    culet = bm.verts.new((0, 0, -pav))
    gb, gt, tb = [], [], []
    for i in range(segs):
        a = 2 * math.pi * i / segs
        a2 = a + math.pi / segs
        gb.append(bm.verts.new((r * math.cos(a), r * math.sin(a), 0)))
        gt.append(bm.verts.new((r * math.cos(a), r * math.sin(a), girdle)))
        tb.append(bm.verts.new((table_r * math.cos(a2), table_r * math.sin(a2), girdle + crown)))
    for i in range(segs):
        j = (i + 1) % segs
        bm.faces.new((culet, gb[j], gb[i]))
        bm.faces.new((gb[i], gb[j], gt[j], gt[i]))
        bm.faces.new((gt[i], gt[j], tb[i]))
        bm.faces.new((gt[j], tb[j], tb[i]))
    bm.faces.new(tb)
    return _obj_from_bm(bm, name, smooth=False), pav, girdle + crown


# ------------------------------------------------------------- pieces
@dataclass
class Built:
    gold: bpy.types.Object
    gems: list[bpy.types.Object] = field(default_factory=list)
    volume_mm3: float = 0.0
    dims: dict = field(default_factory=dict)
    # Earring pair: the mirrored second earring (display/GLB). `gold` stays ONE closed
    # solid (the casting model, cast twice); volume_mm3 counts both pieces.
    mirror: list[bpy.types.Object] = field(default_factory=list)
    # Metal removed by cutting the stone seats (mm^3, one piece). volume_mm3 is measured after it.
    seat_cut_mm3: float = 0.0
    seats_in_model: bool = True     # False: the casting body is uncut, the setter cuts the seats


def _place(obs, m: Matrix):
    for o in obs:
        o.data.transform(m)


FLORAL_PETAL_TILT = 12      # degrees the petal tips lift off the seat
FLORAL_MIN_PETAL_T = 0.8    # mm, petal thickness floor (pendant minimum in dfm)


def floral_top(inner_d: float, t: float, flower_d: float, petals: int, gem_d: float = 0.0):
    """Parametric flower fused onto the top of an upright ring (axis Y, +Z up).

    A round seat is sunk into the top of the shank; `petals` ellipsoid petals
    radiate from it to the flower diameter, tips lifted; a centre bead, or a
    bezel when there is a stone, caps it. Nothing goes below
    inner_d/2 + 0.45 t, and every point's distance from the ring axis is at
    least its height z, so the finger hole is untouched. Returns
    (gold parts, stone or None)."""
    top = inner_d / 2 + t
    seat_r = max(flower_d * 0.30, gem_d / 2 + 0.5 if gem_d else 0.0)
    z_lo = top - t * 0.55
    z_s = top + max(0.5, t * 0.35)          # seat top: the petals' base plane
    parts = [cylinder((0, 0), seat_r, z_lo, z_s, "seat", 32)]
    tp = max(FLORAL_MIN_PETAL_T, t * 0.55)
    r0 = seat_r * 0.35                      # petal root, well inside the seat
    L = max(flower_d / 2, seat_r + 0.6) - r0
    r_c = r0 + L / 2
    W = min(L * 0.62, 2 * r_c * math.sin(math.pi / petals) * 0.95)
    for k in range(petals):
        a = 2 * math.pi * k / petals
        p = sphere((0, 0, 0), (L / 2, W / 2, tp / 2), f"petal{k}", 24, 12)
        p.data.transform(Matrix.Translation((0, 0, z_s - tp * 0.2)) @ Matrix.Rotation(a, 4, "Z")
                         @ Matrix.Translation((r_c, 0, 0))
                         @ Matrix.Rotation(math.radians(-FLORAL_PETAL_TILT), 4, "Y"))
        parts.append(p)
    stone = None
    if gem_d > 0:
        bez = torus(gem_d / 2 + 0.35, 0.5, "bezel", 64, 12)
        bez.data.transform(Matrix.Translation((0, 0, z_s + 0.2)))
        parts.append(bez)
        stone, pav, _ = gem(gem_d, "stone")
        stone.data.transform(Matrix.Translation((0, 0, z_s + 0.3)))
    else:
        bead_r = max(0.6, seat_r * 0.55)
        parts.append(sphere((0, 0, z_s + tp * 0.3), (bead_r, bead_r, bead_r * 0.8), "bead", 24, 12))
    return parts, stone


def build_ring(spec: DesignSpec, s: float) -> Built:
    w, t = spec.width_mm * s, spec.thickness_mm * s
    parts = [band(spec.inner_d_mm, w, t, spec.profile, name="shank", inscribed=True)]
    _place(parts, ROT_UPRIGHT)
    gems = []
    dims = {"width_mm": round(w, 2), "thickness_mm": round(t, 2), "inner_d_mm": spec.inner_d_mm}
    if spec.motif == "floral":
        d = spec.gem_d_mm if spec.gem != "none" else 0.0
        flower, stone = floral_top(spec.inner_d_mm, t, spec.size_mm * s, spec.petals, d)
        parts += flower
        gems += [stone] if stone else []
        gold = union(parts, "gold")
        dims.update(flower_d_mm=round(spec.size_mm * s, 2), petals=spec.petals)
        return Built(gold, gems, mesh_volume(gold), dims)
    if spec.gem != "none" and spec.gem_d_mm > 0:
        d = spec.gem_d_mm
        top = spec.inner_d_mm / 2 + t
        g, pav, crown_h = gem(d, "stone")
        z_g = top + 0.35 + pav
        g.data.transform(Matrix.Translation((0, 0, z_g)))
        gems.append(g)
        n = spec.prongs
        r_top, r_bot = d / 2 + dfm.PRONG_D * 0.2, min(w / 2 * 0.8, d * 0.22)
        z_bot, z_tip = top - t * 0.45, z_g + crown_h * 0.75
        for k in range(n):
            a = 2 * math.pi * (k + 0.5) / n
            p0 = (r_bot * math.cos(a), r_bot * math.sin(a), z_bot)
            p1 = (r_top * math.cos(a), r_top * math.sin(a), z_tip)
            parts += rod(p0, p1, dfm.PRONG_D / 2, f"prong{k}")
        # gallery rail: ties the claws together under the girdle
        z_rail = z_g - pav * 0.55
        f = (z_rail - z_bot) / (z_tip - z_bot)
        rail = torus(r_bot + (r_top - r_bot) * f, dfm.PRONG_D * 0.42, "rail")
        rail.data.transform(Matrix.Translation((0, 0, z_rail)))
        parts.append(rail)
    gold = union(parts, "gold")
    return Built(gold, gems, mesh_volume(gold), dims)


def build_bangle(spec: DesignSpec, s: float) -> Built:
    w, t = spec.width_mm * s, spec.thickness_mm * s
    parts = [band(spec.inner_d_mm, w, t, spec.profile, steps=256, name="bangle")]
    if spec.motif == "beaded":
        r_out = spec.inner_d_mm / 2 + t * 0.85
        br = min(t * 0.8, w * 0.48)
        for k in range(spec.bead_count):
            a = 2 * math.pi * k / spec.bead_count
            parts.append(sphere((r_out * math.cos(a), r_out * math.sin(a), 0), (br,) * 3, f"bead{k}", 20, 12))
    _place(parts, ROT_UPRIGHT)
    gold = union(parts, "gold")
    return Built(gold, [], mesh_volume(gold), {"width_mm": round(w, 2), "thickness_mm": round(t, 2),
                                               "inner_d_mm": spec.inner_d_mm})


def build_pendant(spec: DesignSpec, s: float) -> Built:
    R, th = spec.size_mm * s / 2, spec.thickness_mm * s
    parts, gems = [], []
    if spec.shape == "disc":
        parts.append(sphere((0, 0, 0), (R, R, th / 2), "coin", 96, 36))
        parts.append(torus(R * 0.9, th * 0.32, "rim", 96, 12))
        center_r = R * 0.35
    else:
        n = spec.petals
        for layer, (scale_l, tilt, off) in enumerate(((1.0, 14, 0.0), (0.68, 30, 0.5))):
            L, W = R * 0.62 * scale_l, R * 0.30 * scale_l
            for k in range(n):
                a = 2 * math.pi * (k + off) / n
                p = sphere((0, 0, 0), (L, W, th / 2), f"petal{layer}_{k}", 24, 12)
                m = (Matrix.Rotation(a, 4, "Z") @ Matrix.Translation((R - L, 0, th * 0.25 * layer))
                     @ Matrix.Rotation(math.radians(-tilt), 4, "Y"))
                p.data.transform(m)
                parts.append(p)
        center_r = R * 0.30
    if spec.gem != "none" and spec.gem_d_mm > 0:
        d = spec.gem_d_mm
        bez = torus(d / 2 + 0.35, 0.55, "bezel", 64, 12)
        bez.data.transform(Matrix.Translation((0, 0, th * 0.55)))
        cup = sphere((0, 0, th * 0.2), (d / 2 + 0.3, d / 2 + 0.3, th * 0.45), "cup", 32, 12)
        parts += [bez, cup]
        g, pav, _ = gem(d, "stone")
        g.data.transform(Matrix.Translation((0, 0, th * 0.55 + 0.1)))
        gems.append(g)
    else:
        parts.append(sphere((0, 0, th * 0.25), (center_r, center_r, th * 0.7), "dome", 32, 16))
    # bail: chain runs along X through a ring standing in the YZ plane
    bail_tube = max(0.6, th * 0.45)
    bail_r = dfm.MIN_BAIL_HOLE / 2 + bail_tube
    bail = torus(bail_r, bail_tube, "bail", 48, 12)
    bail.data.transform(Matrix.Translation((0, R + bail_r - bail_tube * 0.6, 0))
                        @ Matrix.Rotation(math.radians(90), 4, "Y"))
    parts.append(bail)
    _place(parts + gems, ROT_UPRIGHT)
    gold = union(parts, "gold")
    return Built(gold, gems, mesh_volume(gold), {"size_mm": round(2 * R, 2), "thickness_mm": round(th, 2)})


BUILDERS = {"ring": build_ring, "bangle": build_bangle, "pendant": build_pendant}


PAIR_GAP_MM = 4.0           # display gap between the two earrings of a pair


def _mirror_copy(ob: bpy.types.Object, dx: float, name: str) -> bpy.types.Object:
    """Copy of `ob` mirrored across the YZ plane and moved `dx` along X; normals kept outward."""
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    bm.transform(Matrix.Translation((dx, 0, 0)) @ Matrix.Scale(-1, 4, (1, 0, 0)) @ ob.matrix_world)
    bmesh.ops.reverse_faces(bm, faces=bm.faces)       # a mirror flips the winding
    return _obj_from_bm(bm, name)


def make_pair(b: Built) -> Built:
    """Second earring as a mirror image beside the first; weight counts both."""
    xs = [(b.gold.matrix_world @ v.co).x for v in b.gold.data.vertices]
    dx = 2 * max(xs) + PAIR_GAP_MM          # mirror of x is -x; shift clear of the first
    b.mirror = [_mirror_copy(b.gold, dx, "gold_pair")] + [
        _mirror_copy(g, dx, g.name + "_pair") for g in b.gems]
    b.volume_mm3 *= 2
    b.dims = {**b.dims, "pieces": 2}
    return b


# ------------------------------------------------------------- stone seats
SEAT_NUDGE_MM = 0.002       # retry offset of a seat cutter (microns: no weighable change)
SEAT_GROW = 0.003           # retry: cutter 0.3% larger (a few microns of seat clearance)
SEAT_TURN = 0.0075          # retry: cutter turned ~0.43 deg about its axis (facets off the metal's)
# (grow, nudge, turn) attempts, first clean one wins. A pair (earrings) is triangulated after the
# cut so its mirror copy keeps the same triangles; a single piece tries untriangulated first
# (triangulating some boolean results splits a sliver into non-manifold edges).
SEAT_TRIES = ((0.0, 0.0, 0.0), (0.0, SEAT_NUDGE_MM, 0.0), (0.0, 0.0, SEAT_TURN),
              (0.0, SEAT_NUDGE_MM, -SEAT_TURN), (SEAT_GROW, 0.0, 0.0), (SEAT_GROW, SEAT_NUDGE_MM, SEAT_TURN),
              (0.0, 2 * SEAT_NUDGE_MM, 2 * SEAT_TURN), (2 * SEAT_GROW, 0.0, -2 * SEAT_TURN))


def _seat_try(gold, gems, grow: float, nudge: float, turn: float, tri: bool, name: str):
    coll = bpy.data.collections.new(name + "_seats")
    bpy.context.scene.collection.children.link(coll)
    for i, gm in enumerate(gems):
        me = gm.data.copy()
        me.transform(gm.matrix_world)
        if grow or nudge or turn:
            c = sum((v.co for v in me.vertices), Vector()) / max(len(me.vertices), 1)
            off = Vector((nudge * math.sin(1.7 * i + 1), nudge * math.cos(2.3 * i + 1), nudge * 0.5))
            me.transform(Matrix.Translation(c + off) @ Matrix.Rotation(turn, 4, "Z")
                         @ Matrix.Scale(1 + grow, 4) @ Matrix.Translation(-c))
        coll.objects.link(bpy.data.objects.new(f"{gm.name}_cutter", me))
    mod = gold.modifiers.new("seats", "BOOLEAN")
    mod.operation, mod.operand_type, mod.collection, mod.solver = "DIFFERENCE", "COLLECTION", coll, "MANIFOLD"
    dg = bpy.context.evaluated_depsgraph_get()
    dg.update()
    me = bpy.data.meshes.new_from_object(gold.evaluated_get(dg))
    gold.modifiers.remove(mod)
    for o in list(coll.objects):
        m = o.data
        bpy.data.objects.remove(o, do_unlink=True)
        bpy.data.meshes.remove(m)
    bpy.data.collections.remove(coll)
    if tri:
        bm = bmesh.new()
        bm.from_mesh(me)
        bmesh.ops.triangulate(bm, faces=bm.faces[:], quad_method="BEAUTY", ngon_method="BEAUTY")
        bm.to_mesh(me)
        bm.free()
    out = bpy.data.objects.new(name, me)
    out.matrix_world = gold.matrix_world.copy()
    bpy.context.scene.collection.objects.link(out)
    return out


def _pair_dx(ob) -> float:
    return 2 * max((ob.matrix_world @ v.co).x for v in ob.data.vertices) + PAIR_GAP_MM


def _seat_problems(ob, mirror: bool) -> list[str]:
    from . import mesh_check
    out = mesh_check.check(ob).problems()
    if mirror and not out:          # the mirror copy exactly as make_pair will place it
        cp = _mirror_copy(ob, _pair_dx(ob), ob.name + "_probe")
        out = ["mirror " + p for p in mesh_check.check(cp).problems()]
        bpy.data.objects.remove(cp, do_unlink=True)
    return out


def cut_seats(b: Built, mirror: bool = False) -> Built:
    """Cut every stone's seat out of the gold (gold minus the stones' solids), so the metal the
    solver weighs has no gold where a stone sits. volume_mm3 is always the seat-cut volume;
    seat_cut_mm3 is the metal removed.

    The cut is retried with the cutter nudged / turned / grown by microns until the cut body
    passes the mesh check (and, for an earring pair, so does its mirror copy). The first clean
    cut becomes the casting body. If no attempt is clean, the cut never degrades the casting:
    the original (uncut) body is kept for the STL with `seats_in_model = False` (the setter cuts
    the seats, as at a bench) while the weight is still the cut volume. If every boolean returns
    empty geometry, the gold under the stones is measured another way (gold_in_stones_mm3) and
    subtracted: gold under a stone is never weighed."""
    if not b.gems:
        return b
    before = mesh_volume(b.gold)
    name = b.gold.name
    cut_v = None
    # A pair is always triangulated (see SEAT_TRIES); a single piece tries untriangulated cuts
    # first, then triangulated ones (the earring/nose families' own unions are triangulated).
    tries = ([(t, True) for t in SEAT_TRIES] if mirror
             else [(t, False) for t in SEAT_TRIES[:4]] + [(t, True) for t in SEAT_TRIES])
    for k, ((grow, nudge, turn), tri) in enumerate(tries):
        ob = _seat_try(b.gold, b.gems, grow, nudge, turn, tri, f"{name}_seat{k}")
        if len(ob.data.polygons) == 0:          # boolean failed outright
            bpy.data.objects.remove(ob, do_unlink=True)
            continue
        v = mesh_volume(ob)
        cut_v = v if cut_v is None else cut_v
        if not _seat_problems(ob, mirror):
            bpy.data.objects.remove(b.gold, do_unlink=True)
            ob.name = name
            b.gold, b.volume_mm3 = ob, v
            b.seat_cut_mm3 = max(0.0, before - v)
            return b
        bpy.data.objects.remove(ob, do_unlink=True)
    if cut_v is None:
        # Every DIFFERENCE came back empty: the weight must still exclude the gold under the
        # stones, so it is measured another way (per-stone INTERSECT, else sampled).
        cut_v = max(0.0, before - gold_in_stones_mm3(b.gold, b.gems))
    b.volume_mm3 = cut_v                        # weight after the seats, body left uncut
    b.seat_cut_mm3 = max(0.0, before - cut_v)
    b.seats_in_model = False
    return b


OVERLAP_GRID = 28           # sampled overlap: points per axis over a stone's bounding box


def _intersect_mm3(gold, gem):
    """Volume of gold inside one stone (boolean INTERSECT), or None when the boolean returns
    empty geometry (failed, or the stone does not touch the metal)."""
    cp = bpy.data.objects.new(gold.name + "_ov", gold.data.copy())
    cp.matrix_world = gold.matrix_world.copy()
    bpy.context.scene.collection.objects.link(cp)
    mod = cp.modifiers.new("ov", "BOOLEAN")
    mod.operation, mod.object, mod.solver = "INTERSECT", gem, "MANIFOLD"
    dg = bpy.context.evaluated_depsgraph_get()
    dg.update()
    me = bpy.data.meshes.new_from_object(cp.evaluated_get(dg))
    ob = bpy.data.objects.new(gold.name + "_ovm", me)
    ob.matrix_world = gold.matrix_world.copy()
    bpy.context.scene.collection.objects.link(ob)
    v = mesh_volume(ob) if len(me.polygons) else None
    for o in (ob, cp):
        m = o.data
        bpy.data.objects.remove(o, do_unlink=True)
        bpy.data.meshes.remove(m)
    return v


def _bvh(ob):
    from mathutils.bvhtree import BVHTree
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    bm.transform(ob.matrix_world)
    t = BVHTree.FromBMesh(bm)
    bm.free()
    return t


_RAYS = (Vector((0.9134, 0.2721, 0.3027)), Vector((-0.2311, 0.9542, 0.1898)),
         Vector((0.1567, -0.3249, 0.9327)))


def _inside(tree, p: Vector) -> bool:
    """Point-in-closed-mesh by ray parity, majority of three skew rays (a ray grazing an edge
    is outvoted)."""
    votes = 0
    for d in _RAYS:
        n, o = 0, p.copy()
        while True:
            hit, _, _, dist = tree.ray_cast(o, d)
            if hit is None:
                break
            n += 1
            o = hit + d * 1e-5
        votes += n % 2
    return votes >= 2


def _sampled_overlap_mm3(gold, gem, n: int = OVERLAP_GRID) -> float:
    """Gold inside one stone by grid sampling the stone's bounding box (both meshes closed)."""
    tg, ts = _bvh(gold), _bvh(gem)
    pts = [gem.matrix_world @ v.co for v in gem.data.vertices]
    lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    step = (hi - lo) / n
    hits = 0
    for i in range(n):
        for j in range(n):
            for k in range(n):
                p = lo + Vector(((i + 0.5) * step.x, (j + 0.5) * step.y, (k + 0.5) * step.z))
                if _inside(ts, p) and _inside(tg, p):
                    hits += 1
    return hits * step.x * step.y * step.z


def gold_in_stones_mm3(gold, gems) -> float:
    """Gold volume inside the stones (stones do not overlap each other): per stone a boolean
    INTERSECT; when that returns empty geometry, a grid-sampled estimate (zero when the stone
    really sits clear of the metal)."""
    tot = 0.0
    for gm in gems:
        v = _intersect_mm3(gold, gm)
        tot += v if v is not None else _sampled_overlap_mm3(gold, gm)
    return tot


def build(spec: DesignSpec, scale: float) -> Built:
    """Registered family (spec.family) or the original per-piece builder, then the stone
    seats are cut out of the gold (`cut_seats`, every builder alike). An earring with
    spec.pair is mirrored into a pair after its family builder returns one earring."""
    if not spec.family:
        return cut_seats(BUILDERS[spec.piece_type](spec, scale))
    from . import families
    fam = families.get(spec.family)
    if fam.piece_type != spec.piece_type:
        raise ValueError(f"family {fam.name!r} builds a {fam.piece_type}, not a {spec.piece_type}")
    # An earring is cut as if it will be mirrored, pair or not, so one earring weighs exactly
    # half a pair (the same cut attempt is chosen either way).
    b = cut_seats(fam.builder(spec, scale), mirror=spec.piece_type == "earring")
    if spec.piece_type == "earring" and spec.pair:
        b = make_pair(b)
    return b


# ------------------------------------------------------------- weighing (cached)
SEAT_CUT_VERSION = 2        # bump when the weighed geometry changes, so no stale volume is reused
CACHE_MAX = 2048
_VOLUMES: "OrderedDict[str, float]" = OrderedDict()
CACHE_STATS = {"hits": 0, "builds": 0}


def spec_hash(spec: DesignSpec, scale: float) -> str:
    """Key of one build: the spec's canonical JSON, the scale and, for a family, which builder.
    Same key -> same geometry -> same metal volume."""
    builder = ""
    if spec.family:
        from . import families
        fb = families.get(spec.family).builder
        builder = f"{fb.__module__}.{fb.__qualname__}:{id(fb)}"
    blob = json.dumps({"spec": spec.model_dump(mode="json"), "scale": repr(float(scale)),
                       "builder": builder, "v": SEAT_CUT_VERSION}, sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()


def clear_volume_cache() -> None:
    _VOLUMES.clear()
    CACHE_STATS.update(hits=0, builds=0)


def gold_volume(spec: DesignSpec, scale: float) -> float:
    """Solver probe: metal volume (mm^3, stone seats cut; a pair counts both) of the spec at
    this scale. Cached by spec hash, so re-probing a scale (another variant, an edit, the
    minimum-weight search) never rebuilds; a miss builds, measures and discards."""
    key = spec_hash(spec, scale)
    if key in _VOLUMES:
        _VOLUMES.move_to_end(key)
        CACHE_STATS["hits"] += 1
        return _VOLUMES[key]
    clear_scene()
    v = build(spec, scale).volume_mm3
    clear_scene()
    CACHE_STATS["builds"] += 1
    _VOLUMES[key] = v
    if len(_VOLUMES) > CACHE_MAX:
        _VOLUMES.popitem(last=False)
    return v
