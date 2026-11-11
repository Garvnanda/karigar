"""Golden-file tests for the bpy geometry builders.

The same DesignSpec at the same scale must give the same gold weight to 0.01 g,
both within one process and against the value stored in tests/golden/.

Regenerating the golden file (only after an intentional geometry change):
    KARIGAR_REGEN_GOLDEN=1 ./venv/bin/python -m pytest -q tests/test_geometry_bpy.py
A missing file or key fails the test. Review the diff of the JSON before
staging it: a changed weight means a changed casting.
"""
import json
import os
from pathlib import Path

import pytest

from karigar.core import gold as G
from karigar.packs.jewellery.schema import DesignSpec

GOLDEN = Path(__file__).parent / "golden" / "gold_volume.json"
TOL_G = 0.01

CASES = {
    "ring_plain": (DesignSpec(name="Comfort Band", piece_type="ring", karat=22, profile="comfort",
                              inner_d_mm=17.3, width_mm=3.5, thickness_mm=1.8), 1.0),
    "ring_solitaire": (DesignSpec(name="Classic Solitaire", piece_type="ring", karat=18, metal="white",
                                  profile="comfort", inner_d_mm=16.5, width_mm=2.4, thickness_mm=1.7,
                                  gem="diamond", gem_d_mm=5.2, prongs=4), 1.2),
    "bangle_beaded": (DesignSpec(name="Beaded Kada", piece_type="bangle", karat=22, profile="comfort",
                                 motif="beaded", bead_count=44, inner_d_mm=60.3, width_mm=4.0,
                                 thickness_mm=2.0), 1.0),
    "pendant_lotus": (DesignSpec(name="Kamal Pendant", piece_type="pendant", karat=22, shape="lotus",
                                 petals=8, size_mm=18, thickness_mm=1.2, gem="ruby", gem_d_mm=4.0), 1.0),
}


@pytest.fixture(scope="module")
def geometry():
    from karigar.packs.jewellery import geometry
    return geometry


def _grams(geometry, key):
    spec, scale = CASES[key]
    return G.mm3_to_grams(geometry.gold_volume(spec, scale), spec.karat)


@pytest.fixture(scope="module")
def golden():
    data = json.loads(GOLDEN.read_text()) if GOLDEN.exists() else {}
    yield data
    if os.environ.get("KARIGAR_REGEN_GOLDEN") and data.get("_dirty"):
        data.pop("_dirty", None)
        GOLDEN.parent.mkdir(parents=True, exist_ok=True)
        GOLDEN.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


@pytest.mark.parametrize("key", list(CASES))
def test_gold_weight_matches_golden(geometry, golden, key):
    first = _grams(geometry, key)
    second = _grams(geometry, key)
    assert first > 0
    assert abs(first - second) < TOL_G, f"{key}: {first:.4f} g vs {second:.4f} g in one process"
    if os.environ.get("KARIGAR_REGEN_GOLDEN"):
        golden[key] = round(first, 4)
        golden["_dirty"] = True
        return
    # A lost baseline must fail loudly, never pass silently.
    assert key in golden, (f"{key}: no golden value in {GOLDEN.name}; "
                           "run with KARIGAR_REGEN_GOLDEN=1 to create it, then review the diff.")
    assert abs(first - golden[key]) < TOL_G, (
        f"{key}: {first:.4f} g, golden {golden[key]:.4f} g. If the geometry change is intended, "
        f"regenerate with KARIGAR_REGEN_GOLDEN=1 (see module docstring).")


def test_bigger_scale_is_heavier(geometry):
    spec, _ = CASES["ring_plain"]
    assert geometry.gold_volume(spec, 1.3) > geometry.gold_volume(spec, 1.0)
