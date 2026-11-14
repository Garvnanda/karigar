"""Ring families: R1 floral cluster, R2 three-stone, R3 halo solitaire, R4 butterfly.

Original parametric designs in popular Indian retail styles (no brand's piece is copied).
Every ring stands upright (axis Y, top at +Z, as geometry.ROT_UPRIGHT), its finger hole is
exactly spec.inner_d_mm (inscribed circle of the shank polygon) and nothing in the head
comes nearer the ring axis than the shank's inner surface. The solver's scale grows the
metal (shank, walls, wires); stones keep the size the brief / spec gives them.

Family knobs live in spec.params (see each default_spec). No bpy at module level.
"""
from __future__ import annotations

import math

from ..dfm import MIN_WALL
from . import register

TAPER_W, TAPER_T = 0.72, 0.85      # shank bottom width / thickness as a share of the top
SCALE_CAP = 1.5                     # heads are sized for scale ~1; beyond this they look swollen


def _ring_bounds(cap: float = SCALE_CAP, tw: float = TAPER_W):
    """dfm ring rules on the shank (top width/thickness) and the bottom of the taper,
    capped so the head stays in proportion."""
    def bounds(spec):
        from ..dfm import RULES
        r = RULES["ring"]
        t, w = spec.thickness_mm, spec.width_mm
        lo = max(r["min_thickness"] / (t * TAPER_T), r["min_width"] / (w * tw))
        if spec.gem != "none":
            lo = max(lo, spec.gem_d_mm * 0.28 / w)
        hi = min(r["max_thickness"] / t, r["max_width"] / w, cap)
        return lo, hi
    return bounds


def _rules():
    from ..dfm import RULES
    return RULES["ring"]


def _ring_checks(extra, tw: float = TAPER_W):
    def checks(spec, s):
        t, w = spec.thickness_mm * s, spec.width_mm * s
        out = [f"shank top {w:.2f} x {t:.2f} mm, tapering to {w * tw:.2f} x {t * TAPER_T:.2f} mm "
               f"(min {_rules()['min_width']:g} x {_rules()['min_thickness']:g} mm)",
               f"finger hole {spec.inner_d_mm:.2f} mm kept clear of the head"]
        return out + extra(spec, s)
    return checks


def _shank(spec, s, tw: float = TAPER_W):
    from ._gemwork import tapered_shank
    w, t = spec.width_mm * s, spec.thickness_mm * s
    sh = tapered_shank(spec.inner_d_mm, w, w * tw, t, t * TAPER_T)
    return sh, w, t, spec.inner_d_mm / 2 + t


def _done(parts, gems, spec, s, **dims):
    from .. import geometry as g
    from ._gemwork import union_clean
    gold = union_clean(parts)
    d = {"width_mm": round(spec.width_mm * s, 2), "thickness_mm": round(spec.thickness_mm * s, 2),
         "inner_d_mm": spec.inner_d_mm, "stones": len(gems), **dims}
    return g.Built(gold, gems, g.mesh_volume(gold), d)


def _shoulder_leaves(spec, s, t, phi):
    """V of two leaves and a bead sunk into the shank's outer surface at angle phi."""
    from mathutils import Matrix
    from .. import geometry as g
    from ._gemwork import on_shank, place, shank_thickness
    tt = shank_thickness(t, t * TAPER_T, phi)
    M = on_shank(spec.inner_d_mm, tt * 0.78, phi)
    w = spec.width_mm * s
    parts = []
    for k, sgn in enumerate((1, -1)):
        leaf = g.sphere((0, 0, 0), (1.25 * s, 0.42 * s, 0.42 * s), f"leaf{phi:.2f}_{k}", 20, 10)
        place([leaf], M @ Matrix.Translation((0.35 * s * math.copysign(1, phi), sgn * w * 0.17, 0))
              @ Matrix.Rotation(sgn * math.radians(28) * math.copysign(1, phi), 4, "Z"))
        parts.append(leaf)
    bead = g.sphere((0, 0, 0), (0.42 * s,) * 3, f"sbead{phi:.2f}", 14, 8)
    place([bead], M @ Matrix.Translation((-0.85 * s * math.copysign(1, phi), 0, 0.12 * s)))
    return parts + [bead]


# ------------------------------------------------------------------ R1 floral cluster
def build_floral_cluster(spec, s):
    """5-8 petal stones in cups around a centre stone, raised on an open gallery
    (centre post, spokes, rail) over a tapered shank with leaf-and-bead shoulders."""
    from mathutils import Matrix
    from .. import geometry as g
    from ._gemwork import bezel_seat, place, wire
    shank, w, t, top = _shank(spec, s)
    parts, gems = [shank], []
    n = max(5, min(8, round(spec.params.get("petal_stones", 6))))
    dp = spec.params.get("petal_d", 2.0)
    dc = spec.gem_d_mm if spec.gem != "none" and spec.gem_d_mm > 0 else 0.0
    wall = 0.42 * s
    core = dc if dc else dp * 0.9                       # gold bead in the middle when no stone
    # Neighbouring petal cups never just touch: a near-tangent pair of rims seals tiny voids
    # (extra mesh components) between them. They stand a clear `gap` apart, bridged by a
    # grain bead, and clear of the centre seat.
    rim_p = dp / 2 + 1.1 * wall * 0.85                  # petal cup's outer rim radius
    gap = 0.3 * s
    rp = max(core / 2 + dp / 2 + wall * 0.55, (2 * rim_p + gap) / (2 * math.sin(math.pi / n)))
    zc = top + 0.8 * s + 0.43 * core                    # centre girdle
    zp = zc - 0.35 * s                                  # petal girdles, tilted outward
    if dc:
        cp, st, depth_c = bezel_seat(dc, wall, "centre")
        place(cp + [st], Matrix.Translation((0, 0, zc)))
        parts += cp
        gems.append(st)
    else:
        parts.append(g.sphere((0, 0, zc), (core / 2 + wall * 0.4,) * 2 + (core * 0.45 + wall,), "centre", 32, 16))
    depth_p = 0
    for k in range(n):
        a = 2 * math.pi * k / n
        cp, st, depth_p = bezel_seat(dp, wall * 0.85, f"petal{k}")
        place(cp + [st], Matrix.Rotation(a, 4, "Z") @ Matrix.Translation((rp, 0, zp))
              @ Matrix.Rotation(math.radians(16), 4, "Y"))
        parts += cp
        gems.append(st)
        b = a + math.pi / n                             # grain bead bridging the gap to the next cup
        rb = rp * math.cos(math.pi / n)
        rg = gap / 2 + 0.27 * s
        parts.append(g.sphere((rb * math.cos(b), rb * math.sin(b), zp + 0.05), (rg,) * 3, f"grain{k}", 14, 9))
        # gallery spoke: centre post foot -> under the petal cup
        parts += wire([(0.55 * rp * math.cos(a), 0.55 * rp * math.sin(a), top - 0.25 * t),
                       (0.85 * rp * math.cos(a), 0.85 * rp * math.sin(a), zp - depth_p * 0.75)],
                      0.32 * s, f"spoke{k}")
    # the post reaches 0.3 mm into the centre seat's bowl at every scale (a fixed offset
    # left the seat floating at large scales with 8 petals)
    z_post = zc - (depth_c if dc else 0.43 * core * 0.85 + wall) + 0.3
    parts.append(g.cylinder((0, 0), 0.6 * rp, top - 0.45 * t, z_post, "post", 40))
    rail = g.torus(rp * 0.9, 0.3 * s, "gallery_rail", 72, 10)
    rail.data.transform(Matrix.Translation((0, 0, zp - depth_p * 0.6)))
    parts.append(rail)
    for phi in (0.62, -0.62):
        parts += _shoulder_leaves(spec, s, t, phi)
    return _done(parts, gems, spec, s, cluster_d_mm=round(2 * rp + dp + 2 * wall, 2), petal_stones=n)


def _relax_param(key: str, step: int, floor: int, default: float, what: str):
    """Phase 4 retry hook: one fewer optional stone group (params[key] - step, not below floor)."""
    def relax(spec, failed):
        n = round(spec.params.get(key, default))
        m = max(floor, n - step)
        if m >= n:
            return None
        return (spec.model_copy(update={"params": {**spec.params, key: float(m)}}), f"{what} {n} -> {m}")
    return relax


register(
    "ring_floral_cluster", "ring", build_floral_cluster,
    {"width_mm": 2.6, "thickness_mm": 1.7, "gem": "diamond", "gem_d_mm": 3.0,
     "params": {"petal_stones": 6, "petal_d": 2.0}},
    {"width_mm": (0.85, 1.0, 1.2), "thickness_mm": (0.85, 1.0, 1.15)},
    scale_bounds=_ring_bounds(),
    checks=_ring_checks(lambda sp, s: [f"{max(5, min(8, round(sp.params.get('petal_stones', 6))))} petal stones "
                                       f"in {0.42 * s:.2f} mm cup walls"]),
    title="Floral Cluster Ring", relax=_relax_param("petal_stones", 1, 5, 6, "petal stones"))


# ------------------------------------------------------------------ R2 three-stone
def build_three_stone(spec, s):
    """Centre stone and two lower side stones in claw baskets, carried on cathedral
    arches that spring from the shoulders of a tapered shank."""
    from mathutils import Matrix
    from .. import dfm, geometry as g
    from ._gemwork import catmull, claw_head, place, tube
    shank, w, t, top = _shank(spec, s)
    parts, gems = [shank], []
    dc = spec.gem_d_mm if spec.gem != "none" and spec.gem_d_mm > 0 else 4.5
    ds = spec.params.get("side_d", 3.0)
    wr = dfm.PRONG_D / 2 * max(1.0, s)
    pc = 0.43 * dc
    zc = top + 0.45 * s + pc
    head, st = claw_head(dc, spec.prongs, wr, (top - 0.4 * t) - zc, "centre")
    place(head + [st], Matrix.Translation((0, 0, zc)))
    parts += head
    gems.append(st)
    parts.append(g.sphere((0, 0, top + 0.1 * s), (dc * 0.3 + wr, dc * 0.3 + wr, 0.5 * s), "centre_foot", 24, 10))
    xs = dc / 2 + ds / 2 + 0.5
    zs = zc - 0.25 * dc
    ps = 0.43 * ds
    zb = -(ps + 0.55 * s)                                # side basket foot (local)
    for sgn in (1, -1):
        M = (Matrix.Translation((sgn * xs, 0, zs)) @ Matrix.Rotation(math.radians(12 * sgn), 4, "Y"))
        # side claws as thick as the centre ones: never under the prong minimum (dfm.PRONG_D)
        head, st = claw_head(ds, 4, wr, zb, f"side{sgn}", rails=1)
        foot = g.sphere((0, 0, zb), (ds * 0.24 + wr, ds * 0.24 + wr, 0.45 * s), f"side{sgn}_foot", 20, 10)
        place(head + [st, foot], M)
        parts += head + [foot]
        gems.append(st)
        fx, fz = sgn * xs + math.sin(math.radians(12 * sgn)) * zb, zs + math.cos(math.radians(12)) * zb
        for yy in (w * 0.3, -w * 0.3):                  # cathedral arch: shoulder -> side foot -> centre
            phi = sgn * 0.62
            r0 = spec.inner_d_mm / 2 + t * 0.55
            pts = catmull([(r0 * math.sin(phi), yy, r0 * math.cos(phi)),
                           (fx + sgn * 0.3, yy * 0.75, fz - 0.15),
                           (sgn * dc * 0.3, yy * 0.45, top + 0.35 * s)], 10, closed=False)
            parts.append(tube(pts, 0.42 * s, f"arch{sgn}{yy:+.1f}", segs=12, up=(0, 1, 0)))
            parts.append(g.sphere(pts[0], (0.46 * s,) * 3, f"arch_end{sgn}{yy:+.1f}", 12, 8))
    return _done(parts, gems, spec, s, centre_d_mm=dc, side_d_mm=ds)


register(
    "ring_three_stone", "ring", build_three_stone,
    {"width_mm": 2.5, "thickness_mm": 1.8, "gem": "diamond", "gem_d_mm": 4.5, "prongs": 4,
     "params": {"side_d": 3.0}},
    {"width_mm": (0.85, 1.0, 1.2), "thickness_mm": (0.85, 1.0, 1.15)},
    scale_bounds=_ring_bounds(),
    checks=_ring_checks(lambda sp, s: ["claw diameter 0.8 mm (min), centre {}-claw basket, "
                                       "side stones 4-claw".format(sp.prongs)]),
    title="Three-Stone Ring")


# ------------------------------------------------------------------ R3 halo solitaire
def halo_count(r_h: float, d_h: float) -> int:
    return max(8, int(2 * math.pi * r_h // (d_h + 0.32)))


def build_halo_solitaire(spec, s):
    """Centre stone in 4/6 claws ringed by a halo of pave melee on a raised frame,
    pave stones running down both shoulders."""
    from mathutils import Matrix
    from .. import dfm, geometry as g
    from ._gemwork import claw_head, on_shank, pave_stone, place, shank_thickness
    shank, w, t, top = _shank(spec, s)
    parts, gems = [shank], []
    dc = spec.gem_d_mm if spec.gem != "none" and spec.gem_d_mm > 0 else 5.0
    dh = spec.params.get("halo_d", 1.2)
    wr = dfm.PRONG_D / 2 * max(1.0, s)
    pc = 0.43 * dc
    zc = top + 0.9 * s + pc
    head, st = claw_head(dc, spec.prongs, wr, (top - 0.4 * t) - zc, "centre")
    place(head + [st], Matrix.Translation((0, 0, zc)))
    parts += head
    gems.append(st)
    # halo frame: a flat ring under the melee
    rh = dc / 2 + 0.35 + dh / 2
    a, b = dh / 2 + 0.28 * s, 0.42 * s
    zh = zc - pc * 0.5                                  # halo girdles
    frame = g._obj_from_bm(g._revolve(g._profile(rh, a, b, 3.0, 3.0, 20), 96), "halo_frame")
    frame.data.transform(Matrix.Translation((0, 0, zh - b + 0.12)))
    parts.append(frame)
    n = halo_count(rh, dh)
    for k in range(n):
        ang = 2 * math.pi * k / n
        stp, stn = pave_stone(dh, 0.26 * s, f"halo{k}", beads=0)
        place([stn], Matrix.Translation((rh * math.cos(ang), rh * math.sin(ang), zh)))
        gems.append(stn)
        bang = ang + math.pi / n
        parts.append(g.sphere((rh * math.cos(bang), rh * math.sin(bang), zh + 0.08), (0.27 * s,) * 3,
                              f"hgrain{k}", 12, 8))
    for k in range(4):                                  # under-gallery posts, between the claws
        ang = math.pi / 2 * k
        # rod() returns the post and its round tip; both go into the gold (a dropped tip
        # would stay in the scene as a stray object)
        parts += g.rod((0.9 * math.cos(ang), 0.9 * math.sin(ang), top - 0.35 * t),
                       (rh * math.cos(ang), rh * math.sin(ang), zh - b), 0.36 * s, f"post{k}", 12)
    # pave shoulders
    m = max(0, min(6, round(spec.params.get("shoulder_stones", 4))))
    r_out = top
    phi0 = math.atan2(rh + a + dh * 0.4, zh) + (dh / 2 + 0.2) / r_out
    dphi = (dh + 0.3) / r_out
    for sgn in (1, -1):
        for k in range(m):
            phi = sgn * (phi0 + k * dphi)
            tt = shank_thickness(t, t * TAPER_T, phi)
            M = on_shank(spec.inner_d_mm, tt - 0.04, phi) @ Matrix.Rotation(math.pi / 2, 4, "Z")
            bp, stn = pave_stone(dh * 0.95, 0.24 * s, f"sh{sgn}_{k}", beads=2)
            place(bp + [stn], M)
            parts += bp
            gems.append(stn)
    return _done(parts, gems, spec, s, centre_d_mm=dc, halo_stones=n, shoulder_stones=2 * m)


register(
    "ring_halo_solitaire", "ring", build_halo_solitaire,
    {"width_mm": 2.4, "thickness_mm": 1.7, "gem": "diamond", "gem_d_mm": 5.0, "prongs": 4,
     "params": {"halo_d": 1.2, "shoulder_stones": 4}},
    {"width_mm": (0.85, 1.0, 1.2), "thickness_mm": (0.85, 1.0, 1.15)},
    scale_bounds=_ring_bounds(),
    checks=_ring_checks(lambda sp, s: [f"centre {sp.prongs}-claw, claw diameter 0.8 mm (min)",
                                       "halo and shoulder melee held by grain beads"]),
    title="Halo Solitaire Ring", relax=_relax_param("shoulder_stones", 4, 0, 4, "shoulder stones"))


# ------------------------------------------------------------------ R4 butterfly
BUTTERFLY_TAPER_W = 0.85           # slim shank: a gentler taper keeps its bottom >= 1.6 mm
UPPER_WING = ((0.10, 0.06), (0.30, 0.40), (0.62, 0.62), (0.92, 0.55), (1.00, 0.30),
              (0.82, 0.08), (0.48, 0.02))
LOWER_WING = ((0.10, -0.06), (0.42, -0.06), (0.70, -0.22), (0.66, -0.50), (0.42, -0.58),
              (0.18, -0.34))


def butterfly_wire_r(s: float) -> float:
    """Wing wire radius: grows with the scale, never under the wall minimum (dfm.MIN_WALL):
    the Phase 4 mesh check measures the wings as wall."""
    return max(MIN_WALL / 2, 0.36 * s)


def build_butterfly(spec, s):
    """Butterfly lying along the top of a slim tapered shank: openwork wings (outline,
    inner loop and veins, so the gaps are cut-outs), one stone per wing, a beaded body
    and curled antennae. The design is laid out flat and wrapped onto the ring."""
    from mathutils import Matrix, Vector
    from .. import geometry as g
    from ._gemwork import bezel_seat, catmull, place, relax, tube, wire
    shank, w, t, top = _shank(spec, s, BUTTERFLY_TAPER_W)
    parts, gems = [shank], []
    span = spec.size_mm * s / 2                         # half wingspan (along the ring)
    sv = span * 0.85                                    # wing height (along the finger)
    wr = butterfly_wire_r(s)
    wr_min = MIN_WALL / 2                               # veins / antennae: never under the wall minimum
    R0 = top - 0.25 * t

    def wrap(u, v, h):
        R = R0 + h
        return Vector((R * math.sin(u / R0), v, R * math.cos(u / R0)))

    def frame(u, v, h):
        phi = u / R0
        M = Matrix.Rotation(phi, 4, "Y")
        M.translation = wrap(u, v, h)
        return M

    ds = spec.gem_d_mm if spec.gem != "none" and spec.gem_d_mm > 0 else 1.6
    hw = 0.3 * s                                        # wing wires' height over the shank
    for side in (1, -1):
        for shape, ends in ((UPPER_WING, (2, 4)), (LOWER_WING, (2, 3))):
            ctrl = [(side * x * span, y * sv) for x, y in shape]
            out = relax(catmull(ctrl, 8), 1.6 * wr)     # the wing root is a sharp corner
            parts.append(tube([wrap(p.x, p.y, hw) for p in out], wr, "wing", True, 12))
            cx = sum(p[0] for p in ctrl) / len(ctrl)
            cy = sum(p[1] for p in ctrl) / len(ctrl)
            # veins from the body to the outline (the gaps between them are the cut-outs);
            # the first runs through the wing stone
            root = (side * 0.06 * span, ctrl[0][1] * 0.5)
            for i, e in enumerate(ends):
                tip = ctrl[e]
                mids = [(cx, cy)] if i == 0 else [((root[0] + tip[0]) / 2, (root[1] + tip[1]) / 2 * 1.1)]
                vein = relax(catmull([root, *mids, (tip[0] * 0.98, tip[1] * 0.98)], 8, closed=False),
                             1.6 * wr, closed=False)
                parts += wire([wrap(p.x, p.y, hw) for p in vein], max(wr_min, wr * 0.85), f"vein{i}")
            cp, st, _ = bezel_seat(ds, 0.34 * s, "wing_stone")
            place(cp + [st], frame(cx, cy, hw + 0.35 * s))
            parts += cp
            gems.append(st)
    # body: beaded thorax/abdomen along the finger, head and antennae
    for k, (v, r) in enumerate(((1.4, 0.62), (0.4, 0.68), (-0.7, 0.6), (-1.7, 0.5), (-2.6, 0.42))):
        rr = r * s
        parts.append(g.sphere(wrap(0, v * s, 0.35 * s), (rr, rr * 1.3, rr), f"body{k}", 20, 12))
    hv = 2.4 * s
    parts.append(g.sphere(wrap(0, hv, 0.45 * s), (0.6 * s,) * 3, "head", 20, 12))
    for side in (1, -1):
        ant = catmull([(side * 0.2 * s, hv + 0.3 * s), (side * 0.1 * span, hv + 1.4 * s),
                       (side * 0.24 * span, hv + 2.0 * s)], 8, closed=False)
        parts += wire([wrap(p.x, p.y, 0.5 * s) for p in ant], max(wr_min, wr * 0.8), f"antenna{side}")
    return _done(parts, gems, spec, s, wingspan_mm=round(2 * span, 2), wire_d_mm=round(2 * wr, 2))


register(
    "ring_butterfly", "ring", build_butterfly,
    {"width_mm": 2.2, "thickness_mm": 1.5, "gem": "diamond", "gem_d_mm": 1.6, "size_mm": 14.0},
    {"width_mm": (0.85, 1.0, 1.15), "thickness_mm": (0.85, 1.0, 1.15), "size_mm": (0.9, 1.0, 1.12)},
    scale_bounds=_ring_bounds(1.4, BUTTERFLY_TAPER_W),
    checks=_ring_checks(lambda sp, s: [f"filigree wire {2 * butterfly_wire_r(s):.2f} mm (min {MIN_WALL:g} mm)",
                                       "4 wing stones in rub-over bezels"], BUTTERFLY_TAPER_W),
    title="Butterfly Ring")
