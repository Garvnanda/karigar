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


# Phase 3 gate: a result is accepted when it is within ACCEPT_ABS (in the solved unit, grams for
# gold) or ACCEPT_REL of the target, whichever is tighter; the solver itself aims at rel_tol
# (0.3%) and stops after MAX_ITER interior probes (+2 for the bounds) whatever happens.
ACCEPT_ABS = 0.1
ACCEPT_REL = 0.02
MAX_ITER = 12


def accept_window(target: float, accept_abs: float | None = ACCEPT_ABS,
                  accept_rel: float = ACCEPT_REL) -> float:
    w = abs(target) * accept_rel
    return w if accept_abs is None else min(accept_abs, w)


def solve_monotone(
    f: Callable[[float], float],
    target: float,
    lo: float,
    hi: float,
    rel_tol: float = 0.003,
    max_iter: int = MAX_ITER,
    on_iter: Callable[[int, float, float], None] | None = None,
    accept_abs: float | None = ACCEPT_ABS,
    accept_rel: float = ACCEPT_REL,
) -> SolveResult:
    """Scale in [lo, hi] at which f hits target. At most max_iter + 2 evaluations of f.
    ok results are within accept_window(target) (tighter of accept_abs and accept_rel)."""
    its: list[tuple[float, float]] = []
    window = min(accept_window(target, accept_abs, accept_rel), abs(target) * rel_tol)
    final = accept_window(target, accept_abs, accept_rel)

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
        if abs(v - target) <= window:
            return SolveResult(True, s, v, target, its)
        if v < target:
            a, fa = s, v
        else:
            b, fb = s, v
    s, v = min(its, key=lambda t: abs(t[1] - target))
    ok = abs(v - target) <= final
    return SolveResult(ok, s, v, target, its, "" if ok else "no_convergence")
