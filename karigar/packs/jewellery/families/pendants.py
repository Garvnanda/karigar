"""Pendant families: P1 heart halo, P2 paisley (keri), P3 temple lotus.

Original parametric designs in popular Indian retail styles (no brand's piece is copied).
Built flat in the XY plane (face +Z, top +Y), then stood up with geometry.ROT_UPRIGHT so
the face looks at the camera (-Y), like geometry.build_pendant. Each has a bail whose hole
is at least dfm.MIN_BAIL_HOLE. size_mm is the pendant's overall width (heart, lotus) or
height (paisley) without the bail; the solver's scale grows everything except the stones.

Family knobs live in spec.params. No bpy at module level. Scale bounds fall back to
dfm.RULES["pendant"] (thickness, size, stone vs. size).
"""
from __future__ import annotations

import math

from . import register

WIRE_MIN_D = 0.6        # mm, = _gemwork.WIRE_MIN_D (that module needs Blender; this one must not)


def _done(parts, gems, spec, s, **dims):
    from .. import geometry as g
    from ._gemwork import union_clean
    g._place(parts + gems, g.ROT_UPRIGHT)
    gold = union_clean(parts)
    d = {"size_mm": round(spec.size_mm * s, 2), "thickness_mm": round(spec.thickness_mm * s, 2),
         "stones": len(gems), **dims}
    return g.Built(gold, gems, g.mesh_volume(gold), d)


def _pendant_checks(extra):
    def checks(spec, s):
        from ..dfm import MIN_BAIL_HOLE, RULES
        r = RULES["pendant"]
        out = [f"thickness {spec.thickness_mm * s:.2f} mm ≥ {r['min_thickness']} mm",
               f"size {spec.size_mm * s:.1f} mm ≥ {r['min_size']} mm",
               f"bail hole ≥ {MIN_BAIL_HOLE} mm"]
        return out + extra(spec, s)
    return checks


def _pendant_bounds(min_scale):
    """dfm.RULES["pendant"] bounds (thickness, size, stone vs. size), raised to the family's
    own floor `min_scale(spec)` (e.g. its thinnest filigree wire reaching WIRE_MIN_D)."""
    def bounds(spec):
        from ..dfm import RULES
        r = RULES["pendant"]
        lo = max(r["min_thickness"] / spec.thickness_mm, r["min_size"] / spec.size_mm, min_scale(spec))
        hi = min(r["max_thickness"] / spec.thickness_mm, r["max_size"] / spec.size_mm)
        if spec.gem != "none":
            lo = max(lo, spec.gem_d_mm * 1.6 / spec.size_mm)
        return lo, hi
    return bounds


def _paisley_wire_r(spec, s):
    return 0.3 * s + 0.1 * spec.thickness_mm * s


def _rim_path(contour, r: float, z: float):
    """Closed path for a rim wire of radius r: the outline resampled finely with every bend
    tighter than 1.5 r rounded off (a heart's tip and notch would fold the wire)."""
    from ._gemwork import relax, resample
    perim = sum(math.dist(contour[i], contour[i - 1]) for i in range(len(contour)))
    pts = relax(resample(contour, max(24, round(perim / (0.5 * r)))), 1.5 * r)
    return [(p.x, p.y, z) for p in pts]


def _arc_samples(pts, step: float):
    """Points every `step` mm along a closed polyline (plus each one's unit tangent)."""
    from mathutils import Vector
    P = [Vector((p[0], p[1], 0.0)) for p in pts]
    seg = [(P[i], P[(i + 1) % len(P)]) for i in range(len(P))]
    L = sum((b - a).length for a, b in seg)
    n = max(3, int(L // step))
    d = L / n
    out, acc, k = [], 0.0, 0
    target = 0.0
    for a, b in seg:
        ln = (b - a).length
        while k < n and target <= acc + ln:
            t = (target - acc) / ln if ln else 0.0
            out.append((a.lerp(b, t), (b - a).normalized()))
            k += 1
            target = k * d
        acc += ln
    return out, L


# ------------------------------------------------------------------ P1 heart halo
HEART_C, HEART_H = 0.55, 2.3        # lobe centre offset and tip depth, in lobe radii


def heart_contour(rho: float, delta: float = 0.0, n_arc: int = 40, n_line: int = 14):
    """CCW outline of a heart made of two lobes (radius rho, centres (+-c, 0)) and two
    straight sides meeting at the tip (0, -h), offset outward by `delta` exactly (the
    offset of each lobe and side), so halo rows run parallel. Star-shaped about (0, 0)."""
    c, h = HEART_C * rho, HEART_H * rho
    R = rho + delta
    D = math.hypot(c, h)
    beta = math.atan2(c, h) + math.asin(rho / D)          # half-angle at the tip
    tip_y = -(h + delta / math.sin(beta))
    a0 = -beta                                             # right tangent point angle on the right lobe
    yN = math.sqrt(R * R - c * c)
    aN = math.atan2(yN, -c)                                # notch angle on the right lobe
    tp = (c + R * math.cos(a0), R * math.sin(a0))
    pts = []
    for i in range(n_line):                                # tip -> right tangent point
        t = i / n_line
        pts.append((tp[0] * t, tip_y + (tp[1] - tip_y) * t))
    for i in range(n_arc):                                 # right lobe up to the notch
        a = a0 + (aN - a0) * i / n_arc
        pts.append((c + R * math.cos(a), R * math.sin(a)))
    right = pts[1:]
    left = [(-x, y) for x, y in reversed(right)]
    return [(0.0, tip_y)] + right + [(0.0, yN)] + left


def build_heart_halo(spec, s):
    """Puffed gold heart (or a stone at its centre when the spec has one) inside a heart
    halo of melee on a backed frame with a raised outer rim, bail in the notch."""
    from mathutils import Matrix
    from .. import geometry as g
    from ._gemwork import bail, bezel_seat, cushion, place, prism, stone, tube
    th = spec.thickness_mm * s
    dh = spec.params.get("halo_d", 1.3)
    gap = 0.3 * s
    rim_r = 0.36 * s + 0.12 * th
    d_row = gap + dh / 2                                   # halo row: offset of the stone centres
    d_out = d_row + dh / 2 + rim_r * 1.1                   # outer frame
    rho = (spec.size_mm * s / 2 - d_out) / (1 + HEART_C)
    plate_t = 0.42 * th
    parts = [prism(heart_contour(rho, d_out), 0, plate_t, "back")]
    parts.append(tube(_rim_path(heart_contour(rho, d_out - rim_r * 0.7), rim_r, plate_t), rim_r,
                      "rim", True, 12))
    parts.append(tube(_rim_path(heart_contour(rho, 0.15 * s), rim_r * 0.75, plate_t), rim_r * 0.75,
                      "inner_rim", True, 10))
    heart = cushion(heart_contour(rho, 0.0), (0, 0), plate_t * 0.5, plate_t + 0.75 * th, "heart", 10, 2.6)
    parts.append(heart)
    gems = []
    row, _ = _arc_samples(heart_contour(rho, d_row, 60, 20), dh + 0.3)
    for k, (p, tng) in enumerate(row):
        st, _, _ = stone(dh, f"halo{k}")
        place([st], Matrix.Translation((p.x, p.y, plate_t + 0.12)))
        gems.append(st)
        q = row[(k + 1) % len(row)][0]
        m = (p + q) / 2
        parts.append(g.sphere((m.x, m.y, plate_t + 0.1), (0.3 * s,) * 3, f"grain{k}", 12, 8))
    if spec.gem != "none" and spec.gem_d_mm > 0:
        cp, st, _ = bezel_seat(spec.gem_d_mm, 0.4 * s, "centre")
        place(cp + [st], Matrix.Translation((0, -0.15 * rho, plate_t + 0.75 * th + 0.1)))
        parts += cp
        gems.append(st)
    yN = math.sqrt((rho + d_out) ** 2 - (HEART_C * rho) ** 2)
    b, _, _ = bail(yN - 0.2 * s, th, below=parts)
    parts += b
    return _done(parts, gems, spec, s, halo_stones=len(row))


register(
    "pendant_heart_halo", "pendant", build_heart_halo,
    {"size_mm": 14.4, "thickness_mm": 1.6, "gem": "diamond", "gem_d_mm": 0.0,
     "params": {"halo_d": 1.3}},
    {"size_mm": (0.88, 1.0, 1.12), "thickness_mm": (0.85, 1.0, 1.15)},
    checks=_pendant_checks(lambda sp, s: ["halo melee held by grain beads on a backed frame"]),
    title="Heart Halo Pendant")


# ------------------------------------------------------------------ P2 paisley
# CCW outline, height 1 (y in -0.52..0.52): round body low, tail sweeping up and
# curling left at the top: the keri / mango motif.
PAISLEY = ((0.00, -0.52), (0.22, -0.46), (0.31, -0.30), (0.30, -0.10), (0.22, 0.08),
           (0.12, 0.24), (0.04, 0.38), (-0.04, 0.48), (-0.12, 0.52), (-0.18, 0.47),
           (-0.15, 0.38), (-0.12, 0.28), (-0.17, 0.12), (-0.27, -0.02), (-0.31, -0.20),
           (-0.25, -0.40))
PAISLEY_BODY = (0.0, -0.21)          # centre of the round body
PAISLEY_STAR = (0.07, 0.23)          # the outline is star-shaped about this point (plate fill)
PAISLEY_SPINE = ((0.07, 0.02), (0.06, 0.13), (0.02, 0.24), (-0.03, 0.34), (-0.08, 0.42))


def build_paisley(spec, s):
    """Keri outline with a raised rim on a backing plate, a filigree spiral scroll in the
    body (round a centre stone when the spec has one) and a graduated stone line up the tail."""
    from mathutils import Matrix
    from .. import geometry as g
    from ._gemwork import bail, bezel_seat, catmull, place, prism, tube, wire
    from ..dfm import MIN_WALL
    H, th = spec.size_mm * s, spec.thickness_mm * s
    plate_t = max(MIN_WALL, 0.4 * th)                  # the backing plate is never under the wall minimum
    wr = _paisley_wire_r(spec, s)
    out = [(p.x * H, p.y * H) for p in catmull(PAISLEY, 6)]
    parts = [prism(out, 0, plate_t, "back", (PAISLEY_STAR[0] * H, PAISLEY_STAR[1] * H)),
             tube(_rim_path(out, wr * 1.15, plate_t), wr * 1.15, "rim", True, 12)]
    gems = []
    cx, cy = PAISLEY_BODY[0] * H, PAISLEY_BODY[1] * H
    r_end = 0.21 * H
    r0 = 0.9 * s
    if spec.gem != "none" and spec.gem_d_mm > 0:
        cp, st, dep = bezel_seat(spec.gem_d_mm, 0.4 * s, "centre")
        # the cup sinks 0.25 mm (x scale) into the plate at every scale and stone size
        place(cp + [st], Matrix.Translation((cx, cy, plate_t + dep - 0.25 * s)))
        parts += cp
        gems.append(st)
        r0 = spec.gem_d_mm / 2 + 0.4 * s + wr * 1.6
    else:
        parts.append(g.sphere((cx, cy, plate_t), (0.9 * s, 0.9 * s, 0.6 * th), "boss", 24, 12))
    turns = max(0.6, min(1.75, (r_end - r0) / (2.6 * wr + 0.25)))
    pts = []
    m = int(48 * turns)
    for i in range(m + 1):                                  # Archimedean scroll, opening anticlockwise
        f = i / m
        a = -math.pi / 2 + 2 * math.pi * turns * f
        r = r0 + (r_end - r0) * f
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a), plate_t))
    parts += wire(pts, wr, "scroll")
    n = max(3, min(7, round(spec.params.get("line_stones", 5))))
    d0 = spec.params.get("line_d", 1.6)
    spine = catmull(PAISLEY_SPINE, 12, closed=False)
    for k in range(n):
        p = spine[round(k * (len(spine) - 1) / (n - 1))]
        d = d0 * (1 - 0.3 * k / (n - 1))
        cp, st, dep = bezel_seat(d, 0.34 * s, f"line{k}")
        place(cp + [st], Matrix.Translation((p.x * H, p.y * H, plate_t + dep - 0.25 * s)))
        parts += cp
        gems.append(st)
    tip = max(out, key=lambda p: p[1])
    b, _, _ = bail(tip[1] - 0.2 * s, th, x=tip[0], below=parts)
    parts += b
    return _done(parts, gems, spec, s, line_stones=n, scroll_turns=round(turns, 2))


register(
    "pendant_paisley", "pendant", build_paisley,
    {"size_mm": 19.8, "thickness_mm": 1.5, "gem": "ruby", "gem_d_mm": 0.0,
     "params": {"line_stones": 5, "line_d": 1.6}},
    {"size_mm": (0.88, 1.0, 1.12), "thickness_mm": (0.85, 1.0, 1.15)},
    scale_bounds=_pendant_bounds(lambda sp: WIRE_MIN_D / (2 * _paisley_wire_r(sp, 1.0))),
    checks=_pendant_checks(lambda sp, s: [f"filigree wire {2 * _paisley_wire_r(sp, s):.2f} mm "
                                          f"(min {WIRE_MIN_D} mm)"]),
    title="Paisley Pendant")


# ------------------------------------------------------------------ P3 temple lotus
def lotus_petal(L: float, W: float, n: int = 16):
    """Pointed lotus petal outline along +X from x=0 (base) to x=L (tip), max width W."""
    right, left = [], []
    for i in range(1, n):
        u = i / n
        hw = W / 2 * math.sin(math.pi * u) ** 0.85 * (1 - 0.35 * u)
        right.append((L * u, -hw))
        left.append((L * u, hw))
    return [(0.0, 0.0)] + right + [(L, 0.0)] + list(reversed(left))


def build_temple_lotus(spec, s):
    """Temple-work lotus: beaded rim round a backing disc, two layered rings of pointed
    petals with a raised midrib, a beaded collar round the centre stone, beaded bail."""
    from mathutils import Matrix
    from .. import geometry as g
    from ._gemwork import bail, bezel_seat, cushion, disc, place, wire
    R, th = spec.size_mm * s / 2, spec.thickness_mm * s
    from ..dfm import MIN_WALL
    rb = 0.32 * s + 0.12 * th                       # rim bead radius
    plate_t = max(MIN_WALL, 0.38 * th)              # the backing disc is never under the wall minimum
    parts = [disc(R - 1.35 * rb, -plate_t / 2, plate_t / 2, "back", 96)]   # edge inside the rim beads, off their centres
    nb = int(2 * math.pi * (R - rb) // (2 * rb * 1.08))
    for k in range(nb):
        a = 2 * math.pi * k / nb
        parts.append(g.sphere(((R - rb) * math.cos(a), (R - rb) * math.sin(a), 0), (rb,) * 3, f"rim{k}", 12, 8))
    n = spec.petals
    gems = []
    dc = spec.gem_d_mm if spec.gem != "none" and spec.gem_d_mm > 0 else 0.0
    core = max(dc / 2 + 0.45 * s, 0.16 * R)
    for layer, (r_in, r_tip, z0, h, off) in enumerate(((core * 0.8, R - 2.2 * rb, plate_t / 2 - 0.1, 0.55 * th, 0.0),
                                                       (core * 0.8, 0.66 * R, plate_t / 2 + 0.25 * th, 0.6 * th, 0.5))):
        L = r_tip - r_in
        W = min(2 * (r_in + L * 0.55) * math.sin(math.pi / n) * 1.25, L * 0.62)
        for k in range(n):
            a = 2 * math.pi * (k + off) / n
            M = Matrix.Rotation(a, 4, "Z") @ Matrix.Translation((r_in, 0, 0))
            # every petal's back sinks into the disc: a raised back on the inner ring left
            # sealed voids over the disc between neighbouring outer petals (seen at 10 petals)
            petal = cushion(lotus_petal(L, W), (L * 0.42, 0), plate_t / 2 - 0.1, z0 + h, f"petal{layer}_{k}",
                            8, 2.2)
            place([petal], M)
            rib = wire([(L * 0.12, 0, z0 + h * 0.85), (L * 0.55, 0, z0 + h * 0.75), (L * 0.86, 0, z0 + h * 0.3)],
                       0.18 * s + 0.06 * th, f"rib{layer}_{k}")
            place(rib, M)
            parts += [petal] + rib
    z_top = plate_t / 2 + 0.85 * th
    parts.append(g.cylinder((0, 0), core, plate_t / 2 - 0.1, z_top, "hub", 48))
    nc = max(8, int(2 * math.pi * core // (0.62 * s + 0.15)))
    for k in range(nc):                              # beaded collar
        a = 2 * math.pi * k / nc
        parts.append(g.sphere((core * math.cos(a), core * math.sin(a), z_top), (0.3 * s,) * 3, f"collar{k}", 12, 8))
    if dc:
        cp, st, _ = bezel_seat(dc, 0.4 * s, "centre")
        place(cp + [st], Matrix.Translation((0, 0, z_top + 0.25 * s)))
        parts += cp
        gems.append(st)
    else:
        parts.append(g.sphere((0, 0, z_top), (core * 0.75, core * 0.75, 0.5 * th), "dome", 32, 16))
    b, _, _ = bail(R - rb * 0.5, th, bead=True, below=parts)
    parts += b
    return _done(parts, gems, spec, s, petals=n, rim_beads=nb)


register(
    "pendant_temple_lotus", "pendant", build_temple_lotus,
    {"size_mm": 19.8, "thickness_mm": 1.6, "gem": "ruby", "gem_d_mm": 3.5, "petals": 8},
    {"size_mm": (0.88, 1.0, 1.12), "thickness_mm": (0.85, 1.0, 1.15)},
    checks=_pendant_checks(lambda sp, s: [f"{sp.petals}+{sp.petals} petals, beaded rim and collar",
                                          "centre stone in a rub-over bezel" if sp.gem_d_mm > 0 else
                                          "gold centre dome"]),
    title="Temple Lotus Pendant")
