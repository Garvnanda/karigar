"""Parametric jewellery geometry in Blender (bpy + bmesh). Units: millimetres.

Every builder produces closed (manifold) solids, unions all gold parts into
one castable body, and reports its volume. Orientation convention for the
finished piece: rings and bangles stand upright in the XZ plane (axis = Y),
pendants face the camera (-Y); +Z is up.
"""
from __future__ import annotations

import math
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
        parts.append(sphere((0, 0, 0), (R, R, th / 2), "coin", 64, 24))
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


def build(spec: DesignSpec, scale: float) -> Built:
    return BUILDERS[spec.piece_type](spec, scale)


def gold_volume(spec: DesignSpec, scale: float) -> float:
    """Solver probe: build, measure, discard."""
    clear_scene()
    v = build(spec, scale).volume_mm3
    clear_scene()
    return v
