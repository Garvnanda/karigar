import json
import math
from pathlib import Path

import pytest

from karigar.packs.jewellery import brief as B
from karigar.packs.jewellery import sizes
from karigar.packs.jewellery.schema import Brief

CHART = json.loads((Path(__file__).resolve().parents[1] / "data" / "ring_sizes.json").read_text())


def test_chart_is_cited_and_complete():
    assert CHART["source_url"].startswith("https://") and CHART["source_name"] and CHART["retrieved"]
    assert sorted(map(int, CHART["sizes"])) == list(range(1, 31))


@pytest.mark.parametrize("size", range(1, 31))
def test_brief_ring_size_converts_through_the_chart(size):
    row = CHART["sizes"][str(size)]
    assert Brief(piece_type="ring", ring_size=size).ring_inner_d_mm == row["inner_d_mm"]
    assert sizes.ring_inner_d_mm(size) == row["inner_d_mm"]
    # Indian sizes grow with the finger; diameter and circumference agree within the
    # chart's rounding (size 29's published circumference is the known exception).
    if size > 1:
        assert row["inner_d_mm"] > CHART["sizes"][str(size - 1)]["inner_d_mm"]
    if size != 29:
        assert abs(math.pi * row["inner_d_mm"] - row["circumference_mm"]) < 0.6


@pytest.mark.parametrize("size", [1, 12, 30])
def test_parsed_ring_size_uses_the_chart(size):
    b, q = B.parse(f"22K ring of 6 g, size {size}")
    assert q is None and b.ring_inner_d_mm == CHART["sizes"][str(size)]["inner_d_mm"]


def test_explicit_mm_wins_over_ring_size():
    assert Brief(piece_type="ring", ring_size=12, ring_inner_d_mm=18.0).ring_inner_d_mm == 18.0


def test_unknown_ring_size_is_rejected():
    with pytest.raises(Exception):
        Brief(piece_type="ring", ring_size=31)
    with pytest.raises(ValueError):
        sizes.ring_inner_d_mm(0)


def test_bangle_sizes():
    assert sizes.bangle_inner_d_mm(6) == 60.3
    assert sizes.bangle_inner_d_mm(4) == pytest.approx(57.15, abs=0.06)
    assert sizes.bangle_inner_d_mm(8) == 63.5
