"""The five README example orders, end to end at draft quality.

Phase 1 made ring/bangle size and the new piece's karat blocking questions, so the README
examples state them (decisions.md "Phase 1: size and new-piece karat are always asked").

LLM is off (conftest), output goes to tmp_path, calibration reads/writes a temp
file only. Real bpy geometry, Cycles renders, STL/GLB export.
"""
import json

import pytest

from karigar.core import registry
from karigar.core.calibration import CalibrationStore
from karigar.core.orchestrator import Orchestrator
import karigar.packs.jewellery  # noqa: F401  (registers the pack)

ORDERS = [
    ("kangan", "Nani ka purana 18.4g 22K kangan hai, naya 22K beaded kada banana hai, size 2-6", "done"),
    ("solitaire", "18K white gold solitaire with 0.5 ct diamond, budget 1.2 lakh, size 12", "done"),
    ("pendant", "purani 22K chain 6.2g se 22K ruby lotus pendant banao", "done"),
    ("impossible", "18K 1 ct diamond ring under 10k, size 12", "infeasible"),
    ("unclear", "kuch sundar sa bana do", "needs_info"),
]
VARIANT_FILES = ("casting.stl", "model.glb", "job_card.json", "quote.json", "render_hero.png")


@pytest.mark.parametrize("name,text,expected", ORDERS, ids=[o[0] for o in ORDERS])
def test_readme_order(tmp_path, name, text, expected):
    calib_path = tmp_path / "calibration.json"
    out = tmp_path / "out"
    orch = Orchestrator(registry.get("jewellery"), out_dir=out, quality="draft",
                        calibration=CalibrationStore(calib_path))
    res = orch.handle(text)

    assert res["status"] == expected, res
    assert not calib_path.exists()
    if expected == "needs_info":
        assert res["question"].strip()
        return
    if expected == "infeasible":
        assert res["explanation"].strip()
        assert res["infeasible"]["binding_constraint"] and len(res["infeasible"]["alternatives"]) >= 2
        return

    order_dir = out / res["order_id"]
    assert len(res["results"]) == 3
    summary = json.loads((order_dir / "order.json").read_text())
    assert summary["status"] == "done"
    for i, r in enumerate(res["results"], 1):
        vdir = order_dir / f"v{i}"
        for f in VARIANT_FILES:
            assert (vdir / f).is_file() and (vdir / f).stat().st_size > 0, f"{name} v{i}: {f} missing"
        job = json.loads((vdir / "job_card.json").read_text())
        assert job["modelled_weight_g"] > 0
        assert r["quote"]
        if name == "solitaire":  # regression: diamond material crashed on bpy 5.0.1
            assert job["stone"]["type"] == "diamond"


def test_orchestrator_uses_injected_calibration(tmp_path):
    store = CalibrationStore(tmp_path / "c.json")
    assert Orchestrator(registry.get("jewellery"), out_dir=tmp_path, calibration=store).calib is store
