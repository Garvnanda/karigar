"""Generic constraint solver: find the scale at which a monotone quantity hits a target.

Every domain pack exposes one scalar "scale" knob whose effect on the
constrained quantity (gold grams, PLA grams, fabric metres...) is monotone
increasing. The solver brackets and closes in on the target, and when the
target is outside what manufacturing rules allow it says so explicitly
instead of returning a bad design.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable


@dataclass
class SolveResult:
    ok: bool
    scale: float
    value: float
    target: float
    iterations: list[tuple[float, float]] = field(default_factory=list)
    reason: str = ""            # "", "below_min", "above_max", "no_convergence"

    @property
    def error_pct(self) -> float:
        return (self.value - self.target) / self.target * 100.0


def solve_monotone(
    f: Callable[[float], float],
    target: float,
    lo: float,
    hi: float,
    rel_tol: float = 0.003,
    max_iter: int = 25,
    on_iter: Callable[[int, float, float], None] | None = None,
) -> SolveResult:
    its: list[tuple[float, float]] = []

    def ev(s: float) -> float:
        v = f(s)
        its.append((s, v))
        if on_iter:
            on_iter(len(its), s, v)
        return v

    v_lo = ev(lo)
    if v_lo > target * (1 + rel_tol):
        # Even the thinnest manufacturable version is heavier than the target.
        return SolveResult(False, lo, v_lo, target, its, "below_min")
    v_hi = ev(hi)
    if v_hi < target * (1 - rel_tol):
        # Even the heaviest sensible version is lighter than the target.
        return SolveResult(False, hi, v_hi, target, its, "above_max")

    a, fa, b, fb = lo, v_lo, hi, v_hi
    for _ in range(max_iter):
        # Interpolate in log-log space: volume ~ scale^k, so this converges in a few steps.
        if fa > 0 and fb > 0 and fa != fb:
            k = math.log(fb / fa) / math.log(b / a)
            s = a * (target / fa) ** (1 / k) if k > 0 else 0.5 * (a + b)
        else:
            s = 0.5 * (a + b)
        if not (a < s < b):
            s = 0.5 * (a + b)
        v = ev(s)
        if abs(v - target) <= target * rel_tol:
            return SolveResult(True, s, v, target, its)
        if v < target:
            a, fa = s, v
        else:
            b, fb = s, v
    s, v = min(its, key=lambda t: abs(t[1] - target))
    return SolveResult(abs(v - target) <= target * rel_tol * 3, s, v, target, its, "no_convergence")
