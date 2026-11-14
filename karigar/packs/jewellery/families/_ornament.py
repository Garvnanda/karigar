"""Ornament parts shared by the earring and nose families: lathe and sweep solids, a
layered flower with a bezel-set stone, ear posts (plain and threaded-look).

Underscore module: `families._load_all` skips it, and nothing here imports bpy /
bmesh / mathutils / geometry at module level (the brief and designer run without
Blender). Every helper returns closed, outward-wound mesh objects; units are mm.
Local frame for a face-on ornament: it lies in the XY plane facing +Z (+Y up);
`geometry.ROT_UPRIGHT` turns that into the worn frame (faces -Y, +Z up), so a post
built along local -Z ends up going into the ear along +Y.
"""
from __future__ import annotations

import math

MIN_POST_D = 0.8        # mm, thinnest ear post / hook / nose wire we cast (gate item)
MIN_WALL = 0.6          # mm, thinnest ornament wall (jhumka bell). Not dfm.MIN_WALL (0.8 mm
                        # structural): a hanging ornament shell; assumed, decisions.md Phase 3


def _g():
    from .. import geometry
    return geometry


def post_d(spec) -> float:
    """Ear-post / nose-wire diameter: the spec's gauge, never below MIN_POST_D."""
    return max(float(spec.gauge_mm), MIN_POST_D)


def stone_d(spec) -> float:
    """Diameter of the priced centre stone (0 when the design has none)."""
    return spec.gem_d_mm if spec.gem != "none" and spec.gem_d_mm > 0 else 0.0


def lathe(pts, name: str, steps: int = 48):
    """Solid of revolution about Z from an open profile [(r, z), ...] whose first and last
    points lie on the axis (r == 0, the two poles); every other point has r > 0."""
    import bmesh
    if pts[0][0] != 0 or pts[-1][0] != 0 or any(r <= 0 for r, _ in pts[1:-1]):
        raise ValueError("lathe profile must start and end on the axis")
    bm = bmesh.new()
    top = bm.verts.new((0.0, 0.0, pts[0][1]))
    ang = [2 * math.pi * i / steps for i in range(steps)]
    rings = [[bm.verts.new((r * math.cos(a), r * math.sin(a), z)) for a in ang]
             for r, z in pts[1:-1]]
    bot = bm.verts.new((0.0, 0.0, pts[-1][1]))
    for i in range(steps):
        j = (i + 1) % steps
        bm.faces.new((top, rings[0][i], rings[0][j]))
        for a, b in zip(rings, rings[1:]):
            bm.faces.new((a[i], b[i], b[j], a[j]))
        bm.faces.new((rings[-1][j], rings[-1][i], bot))
    return _g()._obj_from_bm(bm, name)


def sweep(pts, radii, name: str, segs: int = 12, closed: bool = False):
    """Tube of circular section along a polyline, radius per point (parallel-transport
    frames, so planar paths do not twist). Open tubes get flat end caps."""
    import bmesh
    from mathutils import Vector
    P = [Vector(p) for p in pts]
    n = len(P)
    T = []
    for i in range(n):
        d = (P[(i + 1) % n] - P[i - 1]) if closed else (P[min(i + 1, n - 1)] - P[max(i - 1, 0)])
        T.append(d.normalized())
    ref = Vector((0, 0, 1)) if abs(T[0].z) < 0.9 else Vector((1, 0, 0))
    N = (ref - ref.dot(T[0]) * T[0]).normalized()
    bm = bmesh.new()
    rings = []
    for i in range(n):
        N = (N - N.dot(T[i]) * T[i]).normalized()
        B = T[i].cross(N)
        rings.append([bm.verts.new(P[i] + radii[i] * (math.cos(a) * N + math.sin(a) * B))
                      for a in (2 * math.pi * k / segs for k in range(segs))])
    for k in range(n if closed else n - 1):
        a, b = rings[k], rings[(k + 1) % n]
        for i in range(segs):
            j = (i + 1) % segs
            bm.faces.new((a[i], b[i], b[j], a[j]))
    if not closed:
        bm.faces.new(rings[0])
        bm.faces.new(list(reversed(rings[-1])))
    return _g()._obj_from_bm(bm, name)


def wire(pts, r: float, name: str, segs: int = 15, round_start=False, round_end=True):
    """Constant-radius open tube along `pts` with hemispherical (domed) tips built into the
    sweep itself, so no boolean seam sits on a tip."""
    from mathutils import Vector
    P = [Vector(p) for p in pts]
    path, radii = list(P), [r] * len(P)
    if round_end:
        t = (P[-1] - P[-2]).normalized()
        for k in range(1, 7):
            ph = math.radians(15 * k) if k < 6 else math.radians(84)
            path.append(P[-1] + t * r * math.sin(ph))
            radii.append(r * math.cos(ph))
    if round_start:
        t = (P[0] - P[1]).normalized()
        for k in range(1, 7):
            ph = math.radians(15 * k) if k < 6 else math.radians(84)
            path.insert(0, P[0] + t * r * math.sin(ph))
            radii.insert(0, r * math.cos(ph))
    return sweep(path, radii, name, segs)


def post(d: float, length: float, name: str = "post", z_top: float = 0.3, steps: int = 22):
    """Straight ear post along local -Z: flat top buried at z_top (inside the ornament),
    exposed length `length` below z = 0, domed tip."""
    r = d / 2
    pts = [(0.0, z_top), (r, z_top), (r, -length + r)]
    for k in range(1, 6):
        ph = math.radians(15 * k)
        pts.append((r * math.cos(ph), -length + r - r * math.sin(ph)))
    pts.append((0.0, -length))
    return lathe(pts, name, steps)


def threaded_post(d: float, length: float, thread_len: float, pitch: float = 0.35,
                  depth: float = 0.05, name: str = "post", z_top: float = 0.3, steps: int = 22):
    """Post along local -Z whose last `thread_len` mm carry screw-thread grooves for a
    screw-back. Crest diameter = d (the piercing gauge); root = d - 2*depth."""
    r = d / 2
    z_thr = -(length - thread_len)          # thread starts here and runs to the tip
    pts = [(0.0, z_top), (r, z_top), (r, z_thr)]
    n = max(2, int(round((thread_len - r) / pitch * 6)))
    for k in range(1, n + 1):
        z = z_thr - (thread_len - r) * k / n
        u = (z_thr - z) / pitch
        pts.append((r - depth * (0.5 - 0.5 * math.cos(2 * math.pi * u)), z))
    zt, rr = -length + r, pts[-1][0]        # domed tip from the last thread radius
    for k in range(1, 6):
        ph = math.radians(15 * k)
        pts.append((rr * math.cos(ph), zt - r * math.sin(ph)))
    pts.append((0.0, -length))
    return lathe(pts, name, steps)


def ellipsoid(center, radii, name, u=24, v=12):
    return _g().sphere(center, radii, name, u, v)


def flower(d: float, t: float, petals: int, stone: float, name: str = "fl",
           inner: bool = True, pips: bool = False, fill: float = 1.05,
           back: float = 0.6):
    """Layered flower in the local XY plane facing +Z, back at z ~ 0.

    A back disc carries `petals` tilted ellipsoid petals (plus an inner offset layer when
    `inner`), and the centre is a bezel cup holding a stone of diameter `stone` (or a gold
    dome when stone == 0). A stone larger than the flower grows the flower around it.
    `pips` adds a raised gold dome on every outer petal. `fill` caps a petal's width at that
    multiple of the spacing to its neighbour (< 1: separate petals); `back` is the back
    disc radius as a fraction of the flower radius. Returns (parts,
    stone_obj|None, outer radius actually built)."""
    from mathutils import Matrix
    g = _g()
    R = d / 2
    seat_r = max(R * 0.34, stone / 2 + 0.45) if stone > 0 else R * 0.34
    R = max(R, seat_r + 1.0)
    # back disc starts a little below z = 0: a petal's underside reaches z = 0, and a face
    # tangent to the disc's bottom face leaves non-manifold slivers after the boolean
    parts = [g.cylinder((0, 0), max(R * back, seat_r + 0.2), -0.1 * t, t * 0.85, f"{name}_back", 48)]
    r0 = seat_r * 0.5
    L = R - r0
    r_c = r0 + L / 2
    W = min(L * 0.62, 2 * r_c * math.sin(math.pi / petals) * fill)
    for k in range(petals):
        a = 2 * math.pi * k / petals
        p = ellipsoid((0, 0, 0), (L / 2, W / 2, t / 2), f"{name}_petal{k}")
        p.data.transform(Matrix.Translation((0, 0, t * 0.5)) @ Matrix.Rotation(a, 4, "Z")
                         @ Matrix.Translation((r_c, 0, 0)) @ Matrix.Rotation(math.radians(-8), 4, "Y"))
        parts.append(p)
        if pips:
            pr = min(W * 0.28, L * 0.18)
            rp = r_c * 1.08                  # petal top surface sits at ~t there
            parts.append(ellipsoid((rp * math.cos(a), rp * math.sin(a),
                                    t * 0.88 + (rp - r_c) * math.sin(math.radians(8))),
                                   (pr, pr, pr * 0.8), f"{name}_pip{k}", 16, 10))
    if inner:
        L2, W2 = L * 0.6, W * 0.6
        r_c2 = seat_r * 0.7 + L2 / 2
        for k in range(petals):
            a = 2 * math.pi * (k + 0.5) / petals
            p = ellipsoid((0, 0, 0), (L2 / 2, W2 / 2, t * 0.45), f"{name}_inner{k}")
            p.data.transform(Matrix.Translation((0, 0, t * 0.95)) @ Matrix.Rotation(a, 4, "Z")
                             @ Matrix.Translation((r_c2, 0, 0))
                             @ Matrix.Rotation(math.radians(-18), 4, "Y"))
            parts.append(p)
    stone_obj = None
    if stone > 0:
        z_c = t * 1.35
        bw = max(0.3, t * 0.3)
        # cup top sits a little below the bezel mid-plane: a cap exactly on the torus
        # equator leaves sliver faces the boolean cannot resolve cleanly
        parts.append(g.cylinder((0, 0), seat_r, t * 0.4, z_c - 0.37 * bw, f"{name}_cup", 44))
        bez = g.torus(stone / 2 + 0.1, bw, f"{name}_bezel", 64, 12)
        bez.data.transform(Matrix.Translation((0, 0, z_c)))
        parts.append(bez)
        stone_obj, _, _ = g.gem(stone, f"{name}_stone")
        stone_obj.data.transform(Matrix.Translation((0, 0, z_c + 0.05)))
    else:
        parts.append(ellipsoid((0, 0, t * 0.9), (seat_r, seat_r, seat_r * 0.75), f"{name}_dome", 32, 16))
    return parts, stone_obj, R


def place(objs, m) -> None:
    for o in objs:
        if o is not None:
            o.data.transform(m)


JITTER_MM = 0.002       # retry nudge per part (far below casting detail, ~0 g)
JITTER_TRIES = 4


def _union_tri(parts, name: str):
    """Boolean union, then triangulate. Triangulating fixes the split of every non-planar
    polygon the boolean leaves, so `geometry.make_pair`'s mirror image keeps the same
    triangles (a mirrored quad re-split along its other diagonal can cross a near face)."""
    import bmesh
    ob = _g().union(parts, name)
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    bmesh.ops.triangulate(bm, faces=bm.faces[:], quad_method="BEAUTY", ngon_method="BEAUTY")
    bm.to_mesh(ob.data)
    bm.free()
    ob.data.update()
    return ob


def _problems(ob, mirror: bool) -> list[str]:
    import bpy
    from .. import mesh_check
    g = _g()
    out = mesh_check.check(ob).problems()
    if mirror and not out:
        cp = g._mirror_copy(ob, 0.0, ob.name + "_probe")
        out = ["mirror " + p for p in mesh_check.check(cp).problems()]
        bpy.data.objects.remove(cp, do_unlink=True)
    return out


def solid(parts, name: str = "gold", mirror: bool = False):
    """One clean watertight solid from `parts`: union + triangulate, checked with
    `mesh_check` (and its mirror image when `mirror`, for earrings made as a pair).

    Where parts meet at a near-tangent the boolean can, at an isolated scale, leave a
    sliver (one non-manifold edge or crossing triangle). Then the union is redone with
    every part nudged by a deterministic JITTER_MM-sized offset (a few microns: no visible
    or weighable change, so the volume still rises with the solver's scale). Returns the
    first clean result, else the attempt with the fewest problems (mesh checks then
    report it, as for any family)."""
    import bpy
    from mathutils import Matrix
    keep = [(p.name, p.data.copy()) for p in parts]
    best = None
    for attempt in range(JITTER_TRIES + 1):
        if attempt:
            parts = []
            for i, (nm, me) in enumerate(keep):
                ob = bpy.data.objects.new(nm, me.copy())
                bpy.context.scene.collection.objects.link(ob)
                e = JITTER_MM * attempt
                ob.data.transform(Matrix.Translation((e * math.sin(1.7 * i + attempt),
                                                      e * math.cos(2.3 * i + attempt),
                                                      e * math.sin(3.1 * i + 0.5))))
                parts.append(ob)
        ob = _union_tri(parts, name if attempt == 0 else f"{name}_try{attempt}")
        probs = _problems(ob, mirror)
        if best is None or len(probs) < len(best[1]):
            if best is not None:
                bpy.data.objects.remove(best[0], do_unlink=True)
            best = (ob, probs)
        else:
            bpy.data.objects.remove(ob, do_unlink=True)
        if not probs:
            break
    for _, me in keep:
        bpy.data.meshes.remove(me)
    best[0].name = name
    return best[0]
