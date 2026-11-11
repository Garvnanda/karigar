import pytest

from karigar.core.solver import solve_monotone


def cubic(s):
    return 5.0 * s ** 2.3  # volume-like: grows as a power of scale


def test_converges_within_tolerance():
    r = solve_monotone(cubic, target=12.0, lo=0.5, hi=3.0)
    assert r.ok
    assert abs(r.error_pct) <= 0.3
    assert len(r.iterations) <= 10


def test_below_min_when_lightest_version_too_heavy():
    r = solve_monotone(cubic, target=0.1, lo=0.5, hi=3.0)
    assert not r.ok and r.reason == "below_min"
    assert r.scale == 0.5


def test_above_max_when_heaviest_version_too_light():
    r = solve_monotone(cubic, target=1000.0, lo=0.5, hi=3.0)
    assert not r.ok and r.reason == "above_max"
    assert r.scale == 3.0


def test_on_iter_called_for_every_evaluation():
    seen = []
    r = solve_monotone(cubic, 12.0, 0.5, 3.0, on_iter=lambda i, s, v: seen.append(i))
    assert seen == list(range(1, len(r.iterations) + 1))


def test_deterministic():
    a = solve_monotone(cubic, 12.0, 0.5, 3.0)
    b = solve_monotone(cubic, 12.0, 0.5, 3.0)
    assert a.iterations == b.iterations
