"""Shared parts for the ring / pendant / coin families (rings.py, pendants.py, coin.py).

Private module (leading underscore: families/__init__ does not import it as a family).
Everything here needs Blender, so it is only imported inside builders. Units: mm.

Parts are separate closed solids; a family unions them with `geometry.union`.
Stones are `geometry.gem` proxies (girdle at z=0 in their own frame) placed with a
Matrix; a seat's metal is built in the same local frame and moved with the same
Matrix, so stone and seat always stay together.
"""
from __future__ import annotations

import math

import bpy  # noqa: F401  (must precede bmesh)
import bmesh
from mathutils import Matrix, Vector

from .. import geometry as g

WIRE_MIN_D = 0.6        # mm: thinnest wire / filigree we let the solver go to (lost-wax)


# ------------------------------------------------------------------ curves
def catmull(ctrl, per: int, closed: bool = True) -> list[Vector]:
    """Centripetal-free (uniform) Catmull-Rom through the control points; `per` samples
    per span. Closed: the last point is not repeated."""
    P = [Vector(p) if len(p) == 3 else Vector((p[0], p[1], 0.0)) for p in ctrl]
    n = len(P)
    out = []
    spans = n if closed else n - 1
    for i in range(spans):
        p0 = P[(i - 1) % n] if closed else P[max(i - 1, 0)]
        p1, p2 = P[i % n], P[(i + 1) % n]
        p3 = P[(i + 2) % n] if closed else P[min(i + 2, n - 1)]
        for k in range(per):
            t = k / per
            t2, t3 = t * t, t * t * t
            out.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2
                              + (-p0 + 3 * p1 - 3 * p2 + p3) * t3))
    if not closed:
        out.append(P[-1].copy())
    return out


def _circumradius(a, b, c) -> float:
    A, B, C = (b - c).length, (a - c).length, (a - b).length
    s = (A + B + C) / 2
    ar = max(s * (s - A) * (s - B) * (s - C), 0.0) ** 0.5
    return A * B * C / (4 * ar) if ar > 1e-12 else math.inf


def relax(pts, r_min: float, closed: bool = True, iters: int = 400) -> list[Vector]:
    """Round off every bend of a polyline tighter than radius r_min (a tube of radius r
    folds into itself where the path bends tighter than r): vertices at such bends are
    pulled towards their neighbours' midpoint until none is left. Open ends stay put."""
    P = [Vector(p) if len(p) == 3 else Vector((p[0], p[1], 0.0)) for p in pts]
    n = len(P)
    idx = range(n) if closed else range(1, n - 1)
    for _ in range(iters):
        moved = False
        for i in idx:
            a, b, c = P[i - 1], P[i], P[(i + 1) % n]
            if _circumradius(a, b, c) < r_min:
                P[i] = b.lerp((a + c) / 2, 0.5)
                moved = True
        if not moved:
            break
    return P


# ------------------------------------------------------------------ solids
def tube(pts, r: float, name: str, closed: bool = False, segs: int = 12, up=(0, 0, 1)):
    """Round wire swept along a polyline (rotation-minimising frames). Open tubes get
    flat caps; callers add `g.sphere` beads at the ends for a rounded tip."""
    P = [Vector(p) for p in pts]
    n = len(P)
    T = []
    for i in range(n):
        if closed:
            d = P[(i + 1) % n] - P[i - 1]
        else:
            d = P[min(i + 1, n - 1)] - P[max(i - 1, 0)]
        T.append(d.normalized())
    upv = Vector(up)
    N0 = upv - upv.dot(T[0]) * T[0]
    if N0.length < 1e-6:
        N0 = T[0].orthogonal()
    N = [N0.normalized()]
    for i in range(1, n):
        v = N[-1] - N[-1].dot(T[i]) * T[i]
        N.append(v.normalized() if v.length > 1e-9 else T[i].orthogonal().normalized())
    if closed:   # spread the seam twist evenly so the last ring lines up with the first
        v = N[-1] - N[-1].dot(T[0]) * T[0]
        tw = math.atan2(T[0].dot(v.cross(N[0])), v.dot(N[0]))
        N = [Matrix.Rotation(tw * i / n, 3, T[i]) @ N[i] for i in range(n)]
    bm = bmesh.new()
    rings = []
    for i in range(n):
        B = T[i].cross(N[i])
        # half-step phase: no vertex row sits level with the centreline, so a wire laid
        # centred on a plate's face has no edges lying in that face (coplanar booleans
        # leave crossing slivers)
        rings.append([bm.verts.new(P[i] + r * (math.cos(2 * math.pi * (k + 0.5) / segs) * N[i]
                                                 + math.sin(2 * math.pi * (k + 0.5) / segs) * B))
                      for k in range(segs)])
    last = n if closed else n - 1
    for i in range(last):
        a, b = rings[i], rings[(i + 1) % n]
        for k in range(segs):
            bm.faces.new((a[k], a[(k + 1) % segs], b[(k + 1) % segs], b[k]))
    if not closed:
        bm.faces.new(list(reversed(rings[0])))
        bm.faces.new(rings[-1])
    return g._obj_from_bm(bm, name)


def wire(pts, r: float, name: str, segs: int = 12, up=(0, 0, 1)):
    """Open tube with bead-rounded ends (list of parts)."""
    P = [Vector(p) for p in pts]
    # odd ring count: the end beads have no equator ring level with the wire's centre
    return [tube(P, r, name, False, segs, up),
            g.sphere(P[0], (r * 1.12,) * 3, name + "_a", 14, 9),
            g.sphere(P[-1], (r * 1.12,) * 3, name + "_b", 14, 9)]


# Largest edge on a flat face / dome. A flat ngon triangulated without interior points
# gives slivers as long as the part, and collinear outline points give zero-area
# triangles; booleans against those left crossing slivers on every plate top (measured
# on the first pendant builds). Flat faces and domes are therefore filled with concentric
# loops of short edges (_cap) instead.
FACE_EDGE_MM = 0.4


# Rise of a "flat" face at its centre. An exactly planar face crossed by other parts puts
# every seam vertex exactly in that plane, and the boolean output then has coplanar edges
# lying over neighbouring face triangles, which mesh_check counts as crossings (seen with
# both the MANIFOLD and EXACT solvers). A slight crown (invisible: 0.05 mm over a plate)
# removes the coplanarity; curved shanks and the original domed pendant never hit it.
CROWN_MM = 0.05
RIPPLE_MM = 0.006       # and a smooth sub-micron-slope ripple so no loop of a fill is planar


def ripple(x: float, y: float) -> float:
    return RIPPLE_MM * math.sin(0.9 * x + 1.3 * y + 0.5) * math.cos(0.7 * x - 1.1 * y)


def prism(contour, z0: float, z1: float, name: str, centre=(0.0, 0.0), edge: float = FACE_EDGE_MM,
          crown: float = CROWN_MM):
    """Plate: a CCW polygon in XY, star-shaped about `centre`, from z0 to z1, both faces
    crowned by `crown` at the centre. Faces are concentric-loop fills (no slivers); the
    sides are quads."""
    bm = bmesh.new()
    c = (centre[0], centre[1])
    hi = _cap(bm, contour, c, lambda f: z1 + crown * (1 - f * f), edge, flip=False)
    lo = _cap(bm, contour, c, lambda f: z0 - crown * (1 - f * f), edge, flip=True)
    n = len(contour)
    for i in range(n):
        j = (i + 1) % n
        bm.faces.new((lo[i], lo[j], hi[j], hi[i]))
    return g._obj_from_bm(bm, name)


def disc(r: float, z0: float, z1: float, name: str, segs: int = 96, edge: float = FACE_EDGE_MM):
    """Flat round plate (a cylinder whose caps are meshed finely, not as a fan)."""
    return prism([(r * math.cos(2 * math.pi * i / segs), r * math.sin(2 * math.pi * i / segs))
                  for i in range(segs)], z0, z1, name, (0.0, 0.0), edge)


def resample(pts, m: int) -> list[tuple]:
    """m points evenly spaced by arc length along a closed 2-D polyline, from pts[0]."""
    P = [Vector((p[0], p[1])) for p in pts]
    n = len(P)
    seg = [(P[i] - P[i - 1]).length for i in range(1, n)] + [(P[0] - P[-1]).length]
    L = sum(seg)
    out, acc, i = [], 0.0, 0
    for k in range(m):
        t = L * k / m
        while acc + seg[i] < t and i < n - 1:
            acc += seg[i]
            i += 1
        u = (t - acc) / seg[i] if seg[i] else 0.0
        q = P[i].lerp(P[(i + 1) % n], u)
        out.append((q.x, q.y))
    return out


def _arc_frac(vs) -> list[float]:
    d = [0.0]
    for a, b in zip(vs, vs[1:]):
        d.append(d[-1] + (b.co - a.co).length)
    L = d[-1] + (vs[0].co - vs[-1].co).length
    return [x / L for x in d] + [1.0]


def _zip(bm, A, B, flip: bool) -> None:
    """Triangle strip between closed vertex loops A (outer) and B (inner), both CCW in XY
    and starting at the same angle; vertex counts may differ."""
    fa, fb = _arc_frac(A), _arc_frac(B)
    n, m = len(A), len(B)
    i = j = 0
    while i < n or j < m:
        if j >= m or (i < n and fa[i + 1] <= fb[j + 1]):
            tri = (A[i % n], A[(i + 1) % n], B[j % m])
            i += 1
        else:
            tri = (A[i % n], B[(j + 1) % m], B[j % m])
            j += 1
        bm.faces.new(tuple(reversed(tri)) if flip else tri)


def _cap(bm, contour, c, zf, edge, flip, outer=None, extra_fs=()):
    """Concentric-loop fill of a star-shaped contour about c: loops at scale f (outer
    first) at height zf(f), resampled to ~`edge` spacing, closed with an apex at f = 0.
    `outer` reuses existing outer-loop vertices; `extra_fs` adds loops (e.g. where a dome
    is steep). Returns the outer loop's vertices."""
    R = max(math.hypot(p[0] - c[0], p[1] - c[1]) for p in contour)
    perim = sum(math.dist(contour[i], contour[i - 1]) for i in range(len(contour)))
    k = max(2, math.ceil(R / edge))
    extra = {round(f, 6) for f in extra_fs if 0.02 < f < 0.995}
    even = {round(1 - i / k, 6) for i in range(1, k)}
    # an even loop right next to an extra one would make a strip of slivers between them
    fs = sorted(extra | {f for f in even if all(abs(f - e) > 0.4 / k for e in extra)}, reverse=True)
    loops = [outer or [bm.verts.new((p[0], p[1], zf(1.0) + ripple(p[0], p[1]))) for p in contour]]
    for f in fs:
        m = max(6, round(perim * f / edge))
        pts = resample([(c[0] + (p[0] - c[0]) * f, c[1] + (p[1] - c[1]) * f) for p in contour], m)
        loops.append([bm.verts.new((x, y, zf(f) + ripple(x, y))) for x, y in pts])
    apex = bm.verts.new((c[0], c[1], zf(0.0) + ripple(c[0], c[1])))
    for A, B in zip(loops, loops[1:]):
        _zip(bm, A, B, flip)
    L = loops[-1]
    for i in range(len(L)):
        tri = (L[i], L[(i + 1) % len(L)], apex)
        bm.faces.new(tuple(reversed(tri)) if flip else tri)
    return loops[0]


def cushion(contour, centre, z0: float, z1: float, name: str, layers: int = 10, n: float = 3.0,
            edge: float = FACE_EDGE_MM):
    """Puffed plate: the contour (CCW, star-shaped about `centre`) with a flat back at z0 and
    a superellipse dome rising to z1 (a cushion / puffed heart). Both faces are concentric
    loops of short edges, the dome's height steps no coarser than (z1 - z0) / layers."""
    bm = bmesh.new()
    c = (centre[0], centre[1])
    R = max(math.hypot(p[0] - c[0], p[1] - c[1]) for p in contour)
    e_top = min(edge, R / max(layers, 2))

    def dome(f):
        return z0 + (z1 - z0) * (1 - min(f, 1.0) ** n) ** (1 / n)
    steps = max(layers, math.ceil((z1 - z0) / e_top))
    steep = [(1 - (j / steps) ** n) ** (1 / n) for j in range(1, steps)]   # even height steps
    rim = _cap(bm, contour, c, dome, e_top, flip=False, extra_fs=steep)
    _cap(bm, contour, c, lambda f: z0 - CROWN_MM * (1 - f * f), edge, flip=True, outer=rim)
    return g._obj_from_bm(bm, name)


def place(objs, M: Matrix):
    for o in objs:
        o.data.transform(M)
    return objs


# ------------------------------------------------------------------ settings
def stone(d: float, name: str):
    ob, pav, crown = g.gem(d, name)
    return ob, pav, crown


def bezel_seat(d: float, wall: float, name: str):
    """Cup + rubbed-over rim for a round stone of diameter d, girdle at z=0 (local frame).
    Returns (gold parts, stone, depth below the girdle)."""
    st, pav, _ = stone(d, name + "_stone")
    rim = g.torus(d / 2 + wall * 0.5, wall * 0.6, name + "_rim", 48, 10)
    rim.data.transform(Matrix.Translation((0, 0, 0.05)))
    rc = d / 2 + wall * 0.9
    z_wall = -0.55 * pav                    # straight bezel wall up to the girdle, crown left open
    rz = 0.95 * 0.55 * pav                  # bowl under the pavilion; its top stays below the girdle
    cup = g.cylinder((0, 0), rc, z_wall, -0.02, name + "_wall", 32)
    bowl = g.sphere((0, 0, z_wall), (rc, rc, rz), name + "_cup", 32, 12)
    return [rim, cup, bowl], st, -z_wall + rz


def claw_head(d: float, n: int, wire_r: float, z_bot: float, name: str, rails: int = 2):
    """n claws (+ gallery rails) for a round stone of diameter d, girdle at z=0, claws run
    from radius ~d/4 at z_bot (< 0) to tips over the crown. Returns (parts, stone)."""
    st, pav, crown = stone(d, name + "_stone")
    r_top = d / 2 + wire_r * 0.25
    r_bot = max(d * 0.24, wire_r * 1.6)
    z_tip = crown * 0.7
    parts = []
    for k in range(n):
        a = 2 * math.pi * (k + 0.5) / n
        parts += g.rod((r_bot * math.cos(a), r_bot * math.sin(a), z_bot),
                       (r_top * math.cos(a), r_top * math.sin(a), z_tip), wire_r, f"{name}_claw{k}", 12)
    zs = [-pav * 0.35] if rails == 1 else [-pav * 0.3, z_bot + (-pav * 0.3 - z_bot) * 0.35]
    for i, z in enumerate(zs):
        f = (z - z_bot) / (z_tip - z_bot)
        rr = r_bot + (r_top - r_bot) * f
        rail = g.torus(rr, wire_r * 0.85, f"{name}_rail{i}", 48, 10)
        rail.data.transform(Matrix.Translation((0, 0, z)))
        parts.append(rail)
    return parts, st


def pave_stone(d: float, bead_r: float, name: str, beads: int = 2):
    """A melee stone sunk to its girdle with `beads` grain prongs at its rim (local frame,
    girdle at z=0, beads at +-x). Returns (parts, stone)."""
    st, _, _ = stone(d, name + "_stone")
    parts = []
    for k in range(beads):
        a = math.pi * k if beads == 2 else 2 * math.pi * k / beads + math.pi / 4
        parts.append(g.sphere(((d / 2 + bead_r * 0.25) * math.cos(a), (d / 2 + bead_r * 0.25) * math.sin(a),
                               0.0), (bead_r,) * 3, f"{name}_bead{k}", 12, 8))
    return parts, st


# ------------------------------------------------------------------ ring shank
def shank_c(phi: float, p: float = 1.5) -> float:
    """1 at the top of the ring (phi = 0), 0 at the bottom: the taper weight."""
    return ((1 + math.cos(phi)) / 2) ** p


def tapered_shank(inner_d: float, w_top: float, w_bot: float, t_top: float, t_bot: float,
                  name: str = "shank", steps: int = 144, segs: int = 24, n_exp: float = 2.6):
    """Upright ring shank (axis Y, top at +Z) whose width and thickness taper from the top
    to the bottom. The finger hole is the inscribed circle of the `steps`-gon, exactly
    inner_d (vertices pushed out by 1/cos(pi/steps), as geometry.band(inscribed=True))."""
    r_v = inner_d / 2 / math.cos(math.pi / steps)
    bm = bmesh.new()
    rings = []
    for j in range(steps):
        phi = 2 * math.pi * j / steps
        c = shank_c(phi)
        a = (t_bot + (t_top - t_bot) * c) / 2
        b = (w_bot + (w_top - w_bot) * c) / 2
        prof = g._profile(r_v + a, a, b, n_exp, n_exp, segs)
        sp, cp = math.sin(phi), math.cos(phi)
        rings.append([bm.verts.new((x * sp, z, x * cp)) for x, z in prof])
    for j in range(steps):
        A, B = rings[j], rings[(j + 1) % steps]
        for k in range(segs):
            bm.faces.new((A[k], A[(k + 1) % segs], B[(k + 1) % segs], B[k]))
    return g._obj_from_bm(bm, name)


def shank_thickness(t_top: float, t_bot: float, phi: float) -> float:
    return t_bot + (t_top - t_bot) * shank_c(phi)


def on_shank(inner_d: float, r_out_extra: float, phi: float, y: float = 0.0) -> Matrix:
    """Frame on the ring at angle phi (0 = top, + towards +X): origin at radius
    inner_d/2 + r_out_extra, local +Z radial (out of the finger), local +X along the
    ring's circumference, local +Y along the finger (ring axis)."""
    r = inner_d / 2 + r_out_extra
    radial = Vector((math.sin(phi), 0, math.cos(phi)))
    tang = Vector((math.cos(phi), 0, -math.sin(phi)))
    ax = Vector((0, 1, 0))
    M = Matrix((tang, ax, radial)).transposed().to_4x4()
    M.translation = radial * r + Vector((0, y, 0))
    return M


# ------------------------------------------------------------------ pendant bail
BAIL_CLEAR_MM = 0.1     # free space between the hole's bottom and the pendant below it


def bail_tube(th: float) -> float:
    return max(0.6, th * 0.45)


def bail(top_y: float, th: float, name: str = "bail", bead: bool = False, x: float = 0.0,
         below=()):
    """Pendant bail in the build plane (face +Z, up +Y; geometry.ROT_UPRIGHT later):
    a loop standing in the YZ plane at x so a chain runs along X; its hole is
    dfm.MIN_BAIL_HOLE. `top_y` is the pendant's top edge there; the loop overlaps it by
    40% of its tube. `below` (the pendant's other parts) lifts the loop until its hole
    clears every one of them across the loop's width: a heart's lobes or a rim wire
    rising beside the attachment point must not block the chain. An optional bead sits
    at the joint, below the hole. Returns (parts, loop radius, tube radius)."""
    from .. import dfm
    t = bail_tube(th)
    r = dfm.MIN_BAIL_HOLE / 2 + t
    cy = top_y + r - t * 0.4
    ys = [v.co.y for o in below for v in o.data.vertices if abs(v.co.x - x) <= t + 0.3]
    if ys:
        cy = max(cy, max(ys) + BAIL_CLEAR_MM + r - t)
    loop = g.torus(r, t, name, 48, 12)
    loop.data.transform(Matrix.Translation((x, cy, th * 0.35)) @ Matrix.Rotation(math.radians(90), 4, "Y"))
    parts = [loop]
    if bead:
        hb = cy - (r - t)                               # bottom of the hole
        parts.append(g.sphere((x, hb - 0.08 - 1.3 * t, th * 0.4), (t * 1.5, t * 1.3, t * 1.3),
                              name + "_bead", 20, 12))
    return parts, r, t


# ------------------------------------------------------------------ boolean hygiene
JITTER_RAD = 1.5e-3     # ~0.015 mm at 10 mm: far below casting resolution (~0.025 mm)


def jitter(parts, keep: int = 1, seed: int = 0) -> None:
    """Tilt every part after the first `keep` by a tiny, deterministic, part-specific angle
    about its own centre. Parts built on a shared grid (a wire centred on a plate face, a
    vertex row level with a face, a quad's midline on a plane) make the boolean emit
    near-coincident edges that read as crossings after float32 rounding (measured on the
    first pendant builds). A generic tilt breaks such alignments; the base part (ring
    shank: the finger hole; pendant back plate) is never moved. `seed` picks another tilt."""
    axes = ((0.31, 0.83, 0.46), (0.77, -0.21, 0.6), (-0.42, 0.55, 0.72))
    for k, o in enumerate(parts[keep:]):
        me = o.data
        if not me.vertices:
            continue
        lo = Vector((min(v.co[i] for v in me.vertices) for i in range(3)))
        hi = Vector((max(v.co[i] for v in me.vertices) for i in range(3)))
        c = (lo + hi) / 2
        ang = JITTER_RAD * (1 + 0.37 * ((k + 3 * seed) % 5))
        R = Matrix.Rotation(ang, 4, Vector(axes[(k + seed) % 3]).normalized())
        me.transform(Matrix.Translation(c) @ R @ Matrix.Translation(-c))


UNION_TRIES = 4
DEBRIS_MM = 0.05        # a loose shard smaller than this across is boolean float debris


def drop_debris(ob) -> int:
    """Delete loose shards the boolean leaves behind: separate face islands whose bounding
    box is under DEBRIS_MM across (seen as 4-5 zero-volume faces, 0.01 mm big, on the temple
    lotus). They are not metal anyone could cast; real parts are hundreds of times larger.
    Returns how many were removed."""
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    seen, kill = set(), []
    for f in bm.faces:
        if f in seen:
            continue
        comp, stack = [], [f]
        seen.add(f)
        while stack:
            x = stack.pop()
            comp.append(x)
            for e in x.edges:
                for y in e.link_faces:
                    if y not in seen:
                        seen.add(y)
                        stack.append(y)
        vs = {v for x in comp for v in x.verts}
        span = max(max(v.co[i] for v in vs) - min(v.co[i] for v in vs) for i in range(3))
        if span < DEBRIS_MM:
            kill.append(vs)
    if kill:
        bmesh.ops.delete(bm, geom=[v for vs in kill for v in vs], context="VERTS")
        bm.to_mesh(ob.data)
    bm.free()
    return len(kill)


def union_clean(parts, name: str = "gold", keep: int = 1):
    """geometry.union with boolean hygiene: jitter the parts, union, and check the result
    with mesh_check; if the boolean left a defect (a stray float32 crossing), redo it from
    the saved parts with another jitter (up to UNION_TRIES). Returns the last union."""
    from .. import geometry as g, mesh_check as mc
    saved = [(o.name, o.data.copy()) for o in parts]
    gold = None
    try:
        for attempt in range(UNION_TRIES):
            if attempt:
                me = gold.data
                bpy.data.objects.remove(gold, do_unlink=True)
                bpy.data.meshes.remove(me)
                parts = []
                for nm, me in saved:
                    ob = bpy.data.objects.new(nm, me.copy())
                    bpy.context.scene.collection.objects.link(ob)
                    parts.append(ob)
            jitter(parts, keep, attempt)
            gold = g.union(parts, name)
            drop_debris(gold)
            if not mc.check(gold).problems():
                break
    finally:
        for _, me in saved:
            bpy.data.meshes.remove(me)
    return gold
