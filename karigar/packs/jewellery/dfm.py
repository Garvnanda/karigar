"""Manufacturability rules for lost-wax gold casting.

These are conservative starting defaults. Confirm each with your casting
unit and karigar; they belong in the shop's knowledge base, not in code.
"""
from __future__ import annotations

from .schema import DesignSpec

RULES = {
    "ring":    {"min_thickness": 1.2, "min_width": 1.6, "max_thickness": 3.5, "max_width": 9.0},
    "bangle":  {"min_thickness": 1.2, "min_width": 2.0, "max_thickness": 5.0, "max_width": 14.0},
    "pendant": {"min_thickness": 0.8, "min_size": 9.0, "max_thickness": 3.0, "max_size": 40.0},
}
PRONG_D = 0.8          # mm, claw diameter
MIN_BAIL_HOLE = 2.6    # mm, chain must pass


def scale_bounds(spec: DesignSpec) -> tuple[float, float]:
    """Range of the solver's scale knob that keeps every dimension castable."""
    r = RULES[spec.piece_type]
    if spec.piece_type in ("ring", "bangle"):
        lo = max(r["min_thickness"] / spec.thickness_mm, r["min_width"] / spec.width_mm)
        hi = min(r["max_thickness"] / spec.thickness_mm, r["max_width"] / spec.width_mm)
        if spec.gem != "none" and spec.piece_type == "ring":
            # The band must be wide enough to carry the head visually and structurally.
            lo = max(lo, (spec.gem_d_mm * 0.28) / spec.width_mm)
    else:
        lo = max(r["min_thickness"] / spec.thickness_mm, r["min_size"] / spec.size_mm)
        hi = min(r["max_thickness"] / spec.thickness_mm, r["max_size"] / spec.size_mm)
        if spec.gem != "none":
            lo = max(lo, (spec.gem_d_mm * 1.6) / spec.size_mm)
    return lo, hi


def check(spec: DesignSpec, scale: float) -> list[str]:
    """Human-readable list of checks passed, for the job card."""
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
        out.append(f"claw diameter {PRONG_D} mm, {spec.prongs if spec.piece_type == 'ring' else 'bezel'} setting")
    return out
