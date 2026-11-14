"""Earring families: E1 flower jhumka, E2 chandbali, E3 floral cluster stud, E4 bali hoop.

Original parametric designs in traditional Indian retail styles. Each builder returns
ONE earring (gold = one watertight solid); `geometry.build` mirrors it into a pair when
spec.pair, and the pair's volume is what the solver weighs.

Worn frame: +Z up, the face looks at the viewer along -Y, posts go into the ear along +Y.
Posts / hook wire are spec.gauge_mm, never below 0.8 mm (`_ornament.MIN_POST_D`), and do
not scale with the solver (a piercing does not change with the gold weight).
Butterfly backs are standard separate findings: not cast, not in the gold weight, named
in the job card checks.
"""
from __future__ import annotations

import math

from . import register
from ._ornament import MIN_POST_D, MIN_WALL, post_d, stone_d

EAR_POST_LEN = 10.0     # mm, exposed stud post length (standard butterfly post)
BACK_NOTE = "butterfly back: standard separate finding, not cast, not in the gold weight"


def _post_checks(spec) -> list[str]:
    return [f"ear post {post_d(spec):.2f} mm ≥ {MIN_POST_D} mm", BACK_NOTE,
            "made and weighed as a pair (2 pieces)" if spec.pair else "single earring"]


# ------------------------------------------------------------------ E1 jhumka
def build_jhumka(spec, s):
    """Floral stud top (petals + centre stone) -> short link with a bead -> hollow bell
    open at the bottom (wall = thickness_mm * s), two relief bands, beaded rim and small
    hanging drops; ear post behind the stud."""
    from mathutils import Matrix
    from .. import geometry as g
    from . import _ornament as o

    t_f = spec.thickness_mm * s * 1.25
    fl_parts, stone, R_f = o.flower(spec.params["flower_d"] * s, t_f, spec.petals, stone_d(spec), "top")
    pd = post_d(spec)
    head = fl_parts + [o.post(pd, EAR_POST_LEN, "post")]
    o.place(head + [stone], g.ROT_UPRIGHT)          # face -Y, post +Y
    yc = -t_f / 2                                   # bell axis runs through the stud's mid-depth

    R, w = spec.size_mm * s / 2, spec.thickness_mm * s
    H = R * spec.params["bell_h"]
    n = 16
    outer = [(R * math.sin(math.pi / 2 * k / n), -H * (1 - math.cos(math.pi / 2 * k / n)))
             for k in range(1, n + 1)]
    z_rim, r_fl = -1.12 * H, 1.08 * R
    inner = [((R - w) * math.sin(math.pi / 2 * k / n), -H + (H - w) * math.cos(math.pi / 2 * k / n))
             for k in range(n, 0, -1)]
    prof = [(0.0, 0.0)] + outer + [(r_fl, z_rim), (r_fl - 1.25 * w, z_rim)] + inner + [(0.0, -w)]
    bell = [o.lathe(prof, "bell", 64)]
    band_r = max(0.28, 0.4 * w)
    for i, ph in enumerate((40, 66)):
        p = math.radians(ph)
        tb = g.torus(R * math.sin(p), band_r, f"band{i}", 96, 10)
        tb.data.transform(Matrix.Translation((0, 0, -H * (1 - math.cos(p)))))
        bell.append(tb)
    r_mid, b = r_fl - 0.6 * w, 0.95 * w
    nb = max(12, int(2 * math.pi * r_mid / (1.7 * b)))
    nb -= nb % 2
    drop_r, drop_len = 0.55 * s, 1.4 * s
    for k in range(nb):
        a = 2 * math.pi * k / nb
        # bead centres sit below the flat rim plane: coplanar faces upset the boolean
        c = (r_mid * math.cos(a), r_mid * math.sin(a), z_rim - 0.2 * b)
        bell.append(g.sphere(c, (b, b, b), f"rimbead{k}", 16, 10))
        if k % 2 == 0:
            p1 = (c[0], c[1], c[2] - drop_len)
            bell.append(o.wire([c, p1], max(0.3, 0.32 * s), f"droprod{k}", 11))
            bell.append(g.sphere((p1[0], p1[1], p1[2] - drop_r * 0.9), (drop_r, drop_r, drop_r * 1.4),
                                 f"drop{k}", 16, 12))
    link_len = 2.0 * s
    z_bt = -R_f - link_len
    o.place(bell, Matrix.Translation((0, yc, z_bt)))
    lr = max(0.45, 0.5 * s)
    link = [g.cylinder((0, yc), lr, z_bt - 0.3, -R_f * 0.5, "link", 24),
            g.sphere((0, yc, z_bt + link_len * 0.45), (lr * 1.7,) * 3, "linkbead", 20, 12)]
    gold = o.solid(head + link + bell, mirror=spec.pair)
    dims = {"bell_d_mm": round(2 * r_fl, 2), "bell_h_mm": round(-z_rim, 2), "wall_mm": round(w, 2),
            "flower_d_mm": round(2 * R_f, 2), "post_d_mm": pd, "post_len_mm": EAR_POST_LEN,
            "drops": nb // 2, "length_mm": round(R_f - z_bt - z_rim + drop_len + 2.2 * drop_r, 1)}
    return g.Built(gold, [stone] if stone else [], g.mesh_volume(gold), dims)


def _jhumka_checks(spec, s):
    return [f"bell wall {spec.thickness_mm * s:.2f} mm ≥ {MIN_WALL} mm",
            "bell open at the bottom (hollow)"] + _post_checks(spec)


register("earring_jhumka", "earring", build_jhumka,
         {"size_mm": 11.0, "thickness_mm": 0.8, "petals": 6, "gem": "ruby", "gem_d_mm": 2.5,
          "gauge_mm": 0.8, "params": {"flower_d": 9.0, "bell_h": 0.95}},
         {"size_mm": (0.85, 1.0, 1.2), "thickness_mm": (0.9, 1.0, 1.1), "params.flower_d": (0.9, 1.0, 1.1)},
         scale_bounds=lambda sp: (MIN_WALL / sp.thickness_mm, min(1.6, 1.6 / sp.thickness_mm)),
         checks=_jhumka_checks, title="Phool Jhumka")


# ------------------------------------------------------------------ E2 chandbali
def build_chandbali(spec, s):
    """Crescent moon (horns up) built as an openwork frame: outer and inner edge wires
    joined by a row of round jaali rings (the openings), a granule line along the outer
    edge, horn finials, drops along the lower curve; a stone medallion in the hollow and a
    small flower top carrying the ear post."""
    from mathutils import Matrix
    from .. import geometry as g
    from . import _ornament as o

    re = spec.thickness_mm * s / 2                  # edge wire radius (plate depth = thickness)
    Ro = spec.size_mm * s / 2
    w_max = spec.params["band_w"] * s
    w_min = max(4.2 * re, w_max * 0.4)
    Rc = Ro - w_max / 2
    beta = math.radians(50)                         # half of the open gap at the top
    th0, th1 = math.pi / 2 + beta, 5 * math.pi / 2 - beta

    def width(th):                                  # widest at the bottom (th = 3pi/2)
        u = (th - 3 * math.pi / 2) / (th1 - 3 * math.pi / 2)
        return w_min + (w_max - w_min) * (1 - u * u)

    N = 72
    ths = [th0 + (th1 - th0) * k / N for k in range(N + 1)]
    edge = lambda sgn: [((Rc + sgn * (width(t) / 2 - re)) * math.cos(t),
                         (Rc + sgn * (width(t) / 2 - re)) * math.sin(t), 0.0) for t in ths]
    parts = [o.sweep(edge(+1), [re] * len(ths), "outer_edge", 12),
             o.sweep(edge(-1), [re] * len(ths), "inner_edge", 12)]
    for i, t in enumerate((th0, th1)):              # horn finials cap both wire ends
        fr = width(t) / 2 + 0.25 * re
        parts.append(g.sphere((Rc * math.cos(t), Rc * math.sin(t), 0), (fr, fr, max(fr * 0.7, re * 1.3)),
                              f"finial{i}", 20, 12))
    # jaali rings along the centreline, from the bottom outwards, while the band is wide
    rr = re * 0.65
    rings, half = [], []
    t = 3 * math.pi / 2
    while True:
        wl = width(t)
        if wl < 0.55 * w_max:
            break
        half.append(t)
        out_r = wl / 2 - 0.4 * re
        t += 2 * out_r * 0.92 / Rc
    for t in sorted(set([*half, *[3 * math.pi - x for x in half[1:]]])):
        wl = width(t)
        maj = wl / 2 - 0.4 * re - rr
        tr = g.torus(maj, rr, "jaali", 48, 10)
        tr.data.transform(Matrix.Translation((Rc * math.cos(t), Rc * math.sin(t), 0)))
        rings.append(tr)
    parts += rings
    # granule line on the front of the outer edge
    gr = re * 0.7
    arc = sum((math.dist(a, b) for a, b in zip(edge(+1), edge(+1)[1:])))
    ng = int(arc / (2.3 * gr))
    pe = edge(+1)
    for k in range(1, ng):
        idx = k * (len(pe) - 1) / ng
        i0 = int(idx)
        f = idx - i0
        p = [pe[i0][j] + (pe[min(i0 + 1, len(pe) - 1)][j] - pe[i0][j]) * f for j in range(2)]
        parts.append(g.sphere((p[0], p[1], re * 0.55), (gr, gr, gr), f"gran{k}", 12, 8))
    # drops along the lower curve, hanging straight down
    nd = int(spec.params["drops"])
    drop_r, drop_len = 0.75 * s, 1.8 * s
    for k in range(nd):
        t = math.radians(215 + (325 - 215) * k / max(1, nd - 1))
        rr_e = Rc + width(t) / 2 - re
        p0 = (rr_e * math.cos(t), rr_e * math.sin(t), 0.0)
        p1 = (p0[0], p0[1] - re - drop_len, 0.0)
        parts.append(o.wire([p0, p1], max(0.3, 0.35 * s), f"droprod{k}", 11))
        parts.append(g.sphere((p1[0], p1[1] - drop_r * 1.1, 0), (drop_r, drop_r * 1.45, drop_r),
                              f"drop{k}", 16, 12))
    # stone medallion sitting on the inner edge at the bottom of the hollow
    Ri = Rc - w_max / 2
    med, stone, Rm = o.flower(min(spec.params["medallion_d"] * s, Ri * 1.1), re * 1.6,
                              spec.petals, stone_d(spec), "med", fill=0.8)
    y_m = -Ri + Rm - 0.45 * re
    o.place(med + [stone], Matrix.Translation((0, y_m, -0.37 * re)))   # off the plate mid-plane
    parts += med
    zs = 0.21 * re       # stems sit off every mid-plane (coplanar seams upset the boolean)
    # stems tie the medallion to the inner edge and the top to the medallion whatever
    # the petal count (a petal may not point straight down)
    parts.append(o.wire([(0, y_m - 0.3 * Rm, zs), (0, -Ri - re, zs)], re * 0.8, "stem_low", 11))
    # flower top above the medallion, carrying the post
    top, _, Rt = o.flower(spec.params["top_d"] * s, re * 1.5, 5, 0.0, "top", inner=False, back=0.5)
    pd = post_d(spec)
    top.append(o.post(pd, EAR_POST_LEN, "post"))
    y_t = y_m + Rm + max(1.0, spec.params["top_d"] * s / 2) - 0.6
    o.place(top, Matrix.Translation((0, y_t, -0.33 * re)))
    parts += top + [o.wire([(0, y_t - pd, zs), (0, y_m, zs)], re * 0.8, "stem_top", 11)]
    o.place(parts + [stone], g.ROT_UPRIGHT)
    gold = o.solid(parts, mirror=spec.pair)
    dims = {"width_mm": round(2 * Ro, 2), "band_w_mm": round(w_max, 2), "depth_mm": round(2 * re, 2),
            "jaali_openings": len(rings), "drops": nd, "medallion_d_mm": round(2 * Rm, 2),
            "post_d_mm": pd, "post_len_mm": EAR_POST_LEN,
            "length_mm": round(y_t + Rt + Rc + w_max / 2 + drop_len + 2.6 * drop_r, 1)}
    return g.Built(gold, [stone] if stone else [], g.mesh_volume(gold), dims)


def _chandbali_checks(spec, s):
    return [f"frame wire {spec.thickness_mm * s:.2f} mm ≥ 1.0 mm"] + _post_checks(spec)


register("earring_chandbali", "earring", build_chandbali,
         {"size_mm": 26.0, "thickness_mm": 1.2, "petals": 8, "gem": "ruby", "gem_d_mm": 3.0,
          "gauge_mm": 0.8, "params": {"band_w": 6.0, "medallion_d": 7.0, "top_d": 6.0, "drops": 7}},
         {"size_mm": (0.85, 1.0, 1.15), "thickness_mm": (0.9, 1.0, 1.1), "params.band_w": (0.9, 1.0, 1.12)},
         scale_bounds=lambda sp: (1.0 / sp.thickness_mm, min(1.5, 2.4 / sp.thickness_mm, 40 / sp.size_mm)),
         checks=_chandbali_checks, title="Chandbali")


# ------------------------------------------------------------------ E3 floral cluster stud
def build_floral_stud(spec, s):
    """Flower cluster: two petal layers, a raised gold pip on every outer petal and a
    bezel-set centre stone, on a butterfly post."""
    from .. import geometry as g
    from . import _ornament as o

    t = spec.thickness_mm * s
    parts, stone, R = o.flower(spec.size_mm * s, t, spec.petals, stone_d(spec), "fl", pips=True)
    pd = post_d(spec)
    parts.append(o.post(pd, EAR_POST_LEN, "post"))
    o.place(parts + [stone], g.ROT_UPRIGHT)
    gold = o.solid(parts, mirror=spec.pair)
    dims = {"flower_d_mm": round(2 * R, 2), "thickness_mm": round(t, 2), "petals": spec.petals,
            "post_d_mm": pd, "post_len_mm": EAR_POST_LEN}
    return g.Built(gold, [stone] if stone else [], g.mesh_volume(gold), dims)


register("earring_floral_stud", "earring", build_floral_stud,
         {"size_mm": 9.0, "thickness_mm": 1.0, "petals": 7, "gem": "diamond", "gem_d_mm": 2.5,
          "gauge_mm": 0.8},
         {"size_mm": (0.9, 1.0, 1.2), "thickness_mm": (0.9, 1.0, 1.1)},
         scale_bounds=lambda sp: (max(0.6 / sp.thickness_mm, 6.0 / sp.size_mm),
                                  min(2.0 / sp.thickness_mm, 16.0 / sp.size_mm)),
         checks=lambda sp, s: [f"petal thickness {sp.thickness_mm * s:.2f} mm ≥ 0.6 mm"] + _post_checks(sp),
         title="Phool Stud")


# ------------------------------------------------------------------ E4 bali hoop
def build_bali(spec, s):
    """Traditional bali: a hoop whose tube tapers from a fine ear wire at the top to its
    full thickness at the bottom, ribbed on the thick part, with hinge and latch collars
    where the wire meets the body (solid simulation of the hinged latch) and a few granules
    at the bottom."""
    from mathutils import Matrix, Vector
    from .. import geometry as g
    from . import _ornament as o

    Rh = spec.size_mm / 2                           # hoop size is the fit; it does not scale
    r_max = spec.thickness_mm * s / 2
    pd = post_d(spec)
    r_w = pd / 2
    ribs = 18
    N = 216
    pts, radii = [], []
    for k in range(N):
        psi = 2 * math.pi * k / N                   # 0 = top of the hoop
        u = (1 - math.cos(psi)) / 2                 # 0 top -> 1 bottom
        body = max(0.0, (u - 0.12) / 0.88) ** 0.8
        rib = 1 + 0.07 * body * math.cos(ribs * psi)
        pts.append((Rh * math.sin(psi), Rh * math.cos(psi), 0.0))
        radii.append((r_w + (r_max - r_w) * body) * rib)
    parts = [o.sweep(pts, radii, "hoop", 16, closed=True)]
    for i, psi in enumerate((math.radians(45), math.radians(-45))):   # hinge / latch collars
        u = (1 - math.cos(psi)) / 2
        r_here = r_w + (r_max - r_w) * max(0.0, (u - 0.12) / 0.88) ** 0.8
        c = g.torus(r_here + 0.12, max(0.22, 0.28 * r_max), f"collar{i}", 32, 10)
        tan = Vector((math.cos(psi), -math.sin(psi), 0))
        rot = Vector((0, 0, 1)).rotation_difference(tan).to_matrix().to_4x4()
        c.data.transform(Matrix.Translation((Rh * math.sin(psi), Rh * math.cos(psi), 0)) @ rot)
        parts.append(c)
    nb = int(spec.params["beads"])
    gr = r_max * 0.55
    for k in range(nb):
        psi = math.pi + (k - (nb - 1) / 2) * math.radians(14)
        rr = Rh + r_max * 0.95
        parts.append(g.sphere((rr * math.sin(psi), rr * math.cos(psi), 0), (gr,) * 3, f"gran{k}", 16, 10))
    o.place(parts, g.ROT_UPRIGHT)
    gold = o.solid(parts, mirror=spec.pair)
    zs = [v.co.z for v in gold.data.vertices]
    dims = {"hoop_d_mm": round(2 * (Rh + r_max), 2), "inner_d_mm": round(2 * (Rh - r_max), 2),
            "tube_d_mm": round(2 * r_max, 2), "wire_d_mm": pd, "beads": nb,
            "length_mm": round(max(zs) - min(zs), 2)}   # wire top to granules, measured
    return g.Built(gold, [], g.mesh_volume(gold), dims)


register("earring_bali_hoop", "earring", build_bali,
         {"size_mm": 18.0, "thickness_mm": 2.4, "gauge_mm": 0.8, "params": {"beads": 3}},
         {"size_mm": (0.9, 1.0, 1.1), "thickness_mm": (0.85, 1.0, 1.15)},
         scale_bounds=lambda sp: (max(1.4 / sp.thickness_mm, 1.2 * post_d(sp) / sp.thickness_mm),
                                  min(4.0 / sp.thickness_mm, sp.size_mm / 3 / sp.thickness_mm)),
         checks=lambda sp, s: [f"ear wire {post_d(sp):.2f} mm ≥ {MIN_POST_D} mm",
                               f"tube {sp.thickness_mm * s:.2f} mm at its thickest",
                               "hinged latch modelled solid: the karigar cuts and fits the hinge",
                               "made and weighed as a pair (2 pieces)" if sp.pair else "single earring"],
         title="Bali")
