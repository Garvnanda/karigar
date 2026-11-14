"""Manufacturability rules for lost-wax gold casting.

The sourced minimums (ring shank 1.5 mm, wall 0.8 mm, prong 0.8 mm; decisions.md "Shop
numbers") come from data/casting.json `dfm_min_mm`, so a shop edits them there. The other
proportions are conservative starting defaults; confirm each with your casting unit.
"""
from __future__ import annotations

from karigar.core.gold import casting_config

from .schema import DesignSpec

_MIN = casting_config()["dfm_min_mm"]
MIN_SHANK = float(_MIN["ring_shank"])  # mm, ring shank thickness (women's, high-karat gold)
MIN_WALL = float(_MIN["wall"])         # mm, structural wall
PRONG_D = float(_MIN["prong_d"])       # mm, claw diameter

RULES = {
    "ring":    {"min_thickness": MIN_SHANK, "min_width": 1.6, "max_thickness": 3.5, "max_width": 9.0},
    "bangle":  {"min_thickness": 1.2, "min_width": 2.0, "max_thickness": 5.0, "max_width": 14.0},
    "pendant": {"min_thickness": MIN_WALL, "min_size": 9.0, "max_thickness": 3.0, "max_size": 40.0},
}
MIN_BAIL_HOLE = 2.6    # mm, chain must pass
RING_GEM_PER_WIDTH = 0.28    # a ring band at least 0.28 x the stone diameter wide carries the head
PENDANT_GEM_PER_SIZE = 1.6   # a pendant at least 1.6 x the stone diameter across


def _family(spec: DesignSpec):
    if not spec.family:
        return None
    from . import families      # lazy: families/__init__ imports RULES from here
    return families.get(spec.family)


def scale_bounds(spec: DesignSpec) -> tuple[float, float]:
    """Range of the solver's scale knob that keeps every dimension castable.
    A catalogue family gives its own bounds; otherwise the piece type's RULES apply."""
    fam = _family(spec)
    if fam is not None and fam.scale_bounds is not None:
        return fam.bounds(spec)
    r = RULES[spec.piece_type]
    if spec.piece_type in ("ring", "bangle"):
        lo = max(r["min_thickness"] / spec.thickness_mm, r["min_width"] / spec.width_mm)
        hi = min(r["max_thickness"] / spec.thickness_mm, r["max_width"] / spec.width_mm)
        if spec.gem != "none" and spec.piece_type == "ring":
            # The band must be wide enough to carry the head visually and structurally.
            lo = max(lo, (spec.gem_d_mm * RING_GEM_PER_WIDTH) / spec.width_mm)
    else:
        lo = max(r["min_thickness"] / spec.thickness_mm, r["min_size"] / spec.size_mm)
        hi = min(r["max_thickness"] / spec.thickness_mm, r["max_size"] / spec.size_mm)
        if spec.gem != "none":
            lo = max(lo, (spec.gem_d_mm * PENDANT_GEM_PER_SIZE) / spec.size_mm)
    return lo, hi


def _rule_terms(spec: DesignSpec) -> tuple[list[tuple[float, str]], list[tuple[float, str]]]:
    """(lower, upper) scale limits of the original builders, each with the rule it comes from."""
    r = RULES[spec.piece_type]
    if spec.piece_type in ("ring", "bangle"):
        what = "ring shank" if spec.piece_type == "ring" else "bangle"
        lo = [(r["min_thickness"] / spec.thickness_mm, f"minimum {what} thickness {r['min_thickness']:g} mm"),
              (r["min_width"] / spec.width_mm, f"minimum {what} width {r['min_width']:g} mm")]
        hi = [(r["max_thickness"] / spec.thickness_mm, f"maximum {what} thickness {r['max_thickness']:g} mm"),
              (r["max_width"] / spec.width_mm, f"maximum {what} width {r['max_width']:g} mm")]
        if spec.gem != "none" and spec.piece_type == "ring":
            lo.append((spec.gem_d_mm * RING_GEM_PER_WIDTH / spec.width_mm,
                       f"band wide enough to carry a {spec.gem_d_mm:g} mm stone"))
    else:
        lo = [(r["min_thickness"] / spec.thickness_mm, f"minimum wall {r['min_thickness']:g} mm"),
              (r["min_size"] / spec.size_mm, f"minimum pendant size {r['min_size']:g} mm")]
        hi = [(r["max_thickness"] / spec.thickness_mm, f"maximum thickness {r['max_thickness']:g} mm"),
              (r["max_size"] / spec.size_mm, f"maximum pendant size {r['max_size']:g} mm")]
        if spec.gem != "none":
            lo.append((spec.gem_d_mm * PENDANT_GEM_PER_SIZE / spec.size_mm,
                       f"pendant large enough to frame a {spec.gem_d_mm:g} mm stone"))
    return lo, hi


def binding_rule(spec: DesignSpec, side: str) -> str:
    """The casting rule that sets the lower ("lo") or upper ("hi") end of the scale range:
    what stops the design getting lighter (below_min) or heavier (above_max)."""
    fam = _family(spec)
    if fam is not None and fam.scale_bounds is not None:
        if side == "lo":
            return f"minimum castable proportions of the {fam.title} design (casting rules)"
        return f"maximum sensible proportions of the {fam.title} design"
    lo, hi = _rule_terms(spec)
    return max(lo)[1] if side == "lo" else min(hi)[1]


def max_stone_d(spec: DesignSpec) -> float:
    """Largest stone diameter (mm, 0.05 mm steps) this design can carry inside its castable
    range (scale_bounds lo <= hi). 0.0 when none fits. Bounds only: no Blender."""
    if spec.gem == "none":
        return 0.0

    def fits(d: float) -> bool:
        lo, hi = scale_bounds(spec.model_copy(update={"gem_d_mm": d}))
        return lo <= hi
    if not fits(0.5):
        return 0.0
    lo_d, hi_d = 0.5, max(spec.gem_d_mm, 0.5)
    if fits(hi_d):
        return round(hi_d, 2)
    for _ in range(30):                 # bisection on the stone diameter
        mid = (lo_d + hi_d) / 2
        lo_d, hi_d = (mid, hi_d) if fits(mid) else (lo_d, mid)
    return round(int(lo_d / 0.05 + 1e-9) * 0.05, 2)


def check(spec: DesignSpec, scale: float) -> list[str]:
    """Human-readable list of checks passed, for the job card."""
    fam = _family(spec)
    if fam is not None and fam.checks is not None:
        return list(fam.checks(spec, scale))
    if spec.piece_type not in RULES:
        return []
    r = RULES[spec.piece_type]
    out = []
    if spec.piece_type in ("ring", "bangle"):
        t, w = spec.thickness_mm * scale, spec.width_mm * scale
        out.append(f"thickness {t:.2f} mm ≥ {r['min_thickness']} mm")
        out.append(f"width {w:.2f} mm ≥ {r['min_width']} mm")
    else:
        t, s = spec.thickness_mm * scale, spec.size_mm * scale
        out.append(f"thickness {t:.2f} mm ≥ {r['min_thickness']} mm")
        out.append(f"size {s:.1f} mm ≥ {r['min_size']} mm")
        out.append(f"bail hole ≥ {MIN_BAIL_HOLE} mm")
    if spec.gem != "none":
        out.append(f"claw diameter {PRONG_D:g} mm, {spec.prongs if spec.piece_type == 'ring' else 'bezel'} setting")
    return out
