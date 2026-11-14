"""Nose families: N1 flower nosepin (L-pin, tiny stone), N2 convertible screw-back stud
(fits a nose piercing and an ear lobe).

Original parametric designs in traditional Indian retail styles; each is ONE piece (no
pair). Worn frame: +Z up, the face looks along -Y, the wire goes in along +Y. The wire is
spec.gauge_mm, never below 0.8 mm, and does not scale with the solver. N2's screw-back
disc is a standard separate finding: not cast, not in the gold weight.
"""
from __future__ import annotations

import math

from . import register
from ._ornament import MIN_POST_D, post_d, stone_d

# N2 fit: the screw-back can sit anywhere on the thread, so the tissue it grips ranges from
# (post_len - thread_len) to (post_len - SCREW_BACK_T). Typical depths it must hold:
NOSE_WALL_MM = 3.0      # nostril wall at a nose piercing
EAR_LOBE_MM = 5.0       # ear lobe
SCREW_BACK_T = 1.0      # mm, thickness of a standard screw-back disc
SCREW_NOTE = "screw-back: standard separate finding, not cast, not in the gold weight"


# ------------------------------------------------------------------ N1 flower nosepin
def build_nose_flower(spec, s):
    """Five-petal flower with a bezel-set centre stone on an L-shaped pin: a straight stem
    through the nostril, a rounded 90 degree bend and a short leg that holds it inside."""
    from mathutils import Matrix
    from .. import geometry as g
    from . import _ornament as o

    t = spec.thickness_mm * s
    parts, stone, R = o.flower(spec.params["flower_d"] * s, t, spec.petals, stone_d(spec), "fl",
                               inner=False)
    pd = post_d(spec)
    stem, leg, rb = spec.params["stem"], spec.params["leg"], 0.8
    a = stem - rb
    path = [(0, 0, 0.3), (0, 0, -a * 0.5), (0, 0, -a)]
    for k in range(1, 10):                          # bend: centre (0, -rb, -a), radius rb
        ps = math.radians(10 * k)
        path.append((0, -rb + rb * math.cos(ps), -a - rb * math.sin(ps)))
    path.append((0, -rb - (leg - rb), -a - rb))
    parts.append(o.wire(path, pd / 2, "pin"))
    o.place(parts + [stone], g.ROT_UPRIGHT)
    gold = o.solid(parts)
    dims = {"flower_d_mm": round(2 * R, 2), "thickness_mm": round(t, 2), "petals": spec.petals,
            "post_d_mm": pd, "stem_mm": stem, "leg_mm": leg}
    return g.Built(gold, [stone] if stone else [], g.mesh_volume(gold), dims)


register("nosepin_flower", "nosepin", build_nose_flower,
         {"thickness_mm": 0.7, "petals": 5, "gem": "diamond", "gem_d_mm": 1.5, "gauge_mm": 0.8,
          "params": {"flower_d": 5.0, "stem": 5.5, "leg": 2.5}},
         {"params.flower_d": (0.85, 1.0, 1.2), "thickness_mm": (0.9, 1.0, 1.1)},
         scale_bounds=lambda sp: (0.5 / sp.thickness_mm, min(1.8 / sp.thickness_mm,
                                                             10.0 / sp.params["flower_d"])),
         checks=lambda sp, s: [f"nose wire {post_d(sp):.2f} mm gauge ≥ {MIN_POST_D} mm",
                               f"petal thickness {sp.thickness_mm * s:.2f} mm ≥ 0.5 mm",
                               "L-pin: no back needed"],
         title="Phool Nosepin")


# ------------------------------------------------------------------ N2 convertible stud
def fit(spec) -> dict:
    """Wearing range of the convertible stud: tissue depths its screw-back can grip."""
    L, thr = spec.params["post_len"], spec.params["thread_len"]
    return {"post_len_mm": L, "thread_len_mm": thr, "grip_min_mm": round(L - thr, 2),
            "grip_max_mm": round(L - SCREW_BACK_T, 2)}


def build_convertible(spec, s):
    """Round bezel stud: a tapered cup holding the stone, a milgrain ring of granules round
    the rim, on a 0.8 mm post whose outer part is threaded for a screw-back."""
    from mathutils import Matrix
    from .. import geometry as g
    from . import _ornament as o

    pd = post_d(spec)
    sd = stone_d(spec)
    h = spec.thickness_mm * s                       # cup height
    Rh = max(spec.params["head_d"] * s / 2, sd / 2 + 0.45, pd / 2 + 0.6)
    rp = pd / 2 + 0.3
    cup = o.lathe([(0.0, 0.0), (rp, 0.0), (Rh * 0.78, h * 0.5), (Rh, h * 0.82), (Rh, h), (0.0, h)],
                  "cup", 48)
    parts = [cup]
    stone = None
    if sd > 0:
        bw = max(0.25, 0.22 * h)        # bezel wire; its mid-plane sits off the cup top (no coplanar seam)
        bez = g.torus(sd / 2 + 0.08, bw, "bezel", 64, 10)
        bez.data.transform(Matrix.Translation((0, 0, h + 0.3 * bw)))
        parts.append(bez)
        stone, _, _ = g.gem(sd, "stone")
        stone.data.transform(Matrix.Translation((0, 0, h + 0.3 * bw + 0.05)))
    else:
        parts.append(g.sphere((0, 0, h * 0.9), (Rh * 0.7, Rh * 0.7, Rh * 0.45), "dome", 32, 12))
    gr = max(0.2, 0.12 * Rh)
    ng = int(2 * math.pi * Rh / (2.2 * gr))
    for k in range(ng):
        a = 2 * math.pi * k / ng
        rm = Rh + 0.3 * gr               # milgrain on the bezel band, between its vertex rings
        parts.append(g.sphere((rm * math.cos(a), rm * math.sin(a), h * 0.91), (gr,) * 3, f"mil{k}", 12, 8))
    f = fit(spec)
    parts.append(o.threaded_post(pd, f["post_len_mm"], f["thread_len_mm"], name="post"))
    o.place(parts + [stone], g.ROT_UPRIGHT)
    gold = o.solid(parts)
    dims = {"head_d_mm": round(2 * Rh, 2), "post_d_mm": pd, **f}
    return g.Built(gold, [stone] if stone else [], g.mesh_volume(gold), dims)


def _convertible_checks(spec, s):
    f = fit(spec)
    return [f"post {post_d(spec):.2f} mm gauge ≥ {MIN_POST_D} mm (nose and ear)",
            f"post {f['post_len_mm']:g} mm, thread grips {f['grip_min_mm']:g}-{f['grip_max_mm']:g} mm: "
            f"nose ({NOSE_WALL_MM:g} mm) and ear lobe ({EAR_LOBE_MM:g} mm)", SCREW_NOTE]


register("nosepin_convertible_stud", "nosepin", build_convertible,
         {"thickness_mm": 1.2, "gem": "diamond", "gem_d_mm": 2.5, "gauge_mm": 0.8,
          "params": {"head_d": 4.0, "post_len": 6.5, "thread_len": 4.0}},
         {"params.head_d": (0.85, 1.0, 1.2), "thickness_mm": (0.9, 1.0, 1.15)},
         scale_bounds=lambda sp: (0.8 / sp.thickness_mm, min(2.5 / sp.thickness_mm,
                                                             8.0 / sp.params["head_d"])),
         checks=_convertible_checks, title="Convertible Stud")
