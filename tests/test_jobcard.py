"""Phase 5 production package: Markdown job card (no bpy) and the shrinkage factor."""
from pathlib import Path

import pytest

from karigar.core.registry import Plan, Solved
from karigar.packs.jewellery import job_card, jobcard, pricing
from karigar.packs.jewellery.schema import Brief, DesignSpec


def _job(**brief_kw):
    rc = pricing.rate_card()
    brief = Brief(piece_type="ring", karat=22, target_weight_g=6.0, ring_size=12,
                  ring_inner_d_mm=16.5, **brief_kw)
    spec = DesignSpec(name="Lotus Sol", piece_type="ring", karat=22, gem=brief.gem,
                      gem_d_mm=5.0 if brief.gem != "none" else 0.0, inner_d_mm=16.5)
    solved = Solved(spec, True, 1.02, 6.2, 6.19, 5, issues=["thickness 1.80 mm ≥ 1.5 mm"])
    plan = Plan(True, target_value=6.19, detail={"casting_loss_pct": 3.0})
    return job_card(spec, solved, brief, plan, {"width_mm": 3.1, "thickness_mm": 1.84}, 1, rc), rc


def test_job_card_markdown_has_every_section(tmp_path):
    job, rc = _job(gem="diamond")
    renders = {"render_hero": tmp_path / "render_hero.png", "render_top": tmp_path / "render_top.png"}
    md = jobcard.job_card_md(job, renders, tmp_path)
    for section in ("## Renders", "## Dimensions", "## Size", "## Purity", "## Weights", "## Stones",
                    "## Finishing notes", "## Hallmarking", "## Rule warnings"):
        assert section in md
    assert "![render_hero](render_hero.png)" in md and "![render_top](render_top.png)" in md
    assert "width mm: 3.1" in md and "thickness mm: 1.84" in md
    assert "Indian size 12, inner diameter 16.5 mm" in md
    assert "22K yellow gold, fineness 916" in md
    assert "Modelled (wax/CAD): 6.2 g" in md and "Expected finished: 6.014 g" in md
    assert f"STL scaled up {rc['casting_shrinkage_pct']:g}% for casting shrinkage" in md
    assert "diamond: 5.0 mm" in md and "4-claw setting" in md
    assert "stone size assumed" in md                  # diamond named without a size
    assert "⚠ stone size assumed" in md                # also listed as a rule warning
    assert "HUID reminder" in md and "6-digit HUID (1 × ₹75)" in md and "HUID: ______" in md
    assert "High polish" in md and "comfort edge" in md
    assert "thickness 1.80 mm ≥ 1.5 mm" in md


def test_job_card_without_stone_or_warnings(tmp_path):
    job, _ = _job()
    md = jobcard.job_card_md(job, {}, tmp_path)
    assert "## Stones\n\n- none" in md and "## Rule warnings\n\n- none" in md
    assert job["stone"] is None and job["warnings"] == []


def test_earring_pair_is_two_hallmarked_articles(tmp_path):
    rc = pricing.rate_card()
    brief = Brief(piece_type="earring", karat=22, target_weight_g=3.0)
    spec = DesignSpec(name="Jhumka", piece_type="earring", karat=22)
    job = job_card(spec, Solved(spec, True, 1.0, 3.1, 3.1, 3), brief,
                   Plan(True, detail={"casting_loss_pct": 3.0}), {}, 2, rc)
    md = jobcard.job_card_md(job, {}, tmp_path)
    assert job["pieces_to_cast"] == 2 and "(2 × ₹75)" in md and "Size\n\n- not applicable" in md


def test_chain_size_is_its_length():
    assert jobcard.size_text("chain", Brief(piece_type="chain", length_in=18)) == "length 18 in"


def test_shrinkage_factor_default_and_guard():
    from karigar.packs.jewellery.render import shrinkage_scale
    assert pricing.rate_card()["casting_shrinkage_pct"] == 1.0
    assert shrinkage_scale(1.0) == pytest.approx(1.01)
    with pytest.raises(ValueError):
        shrinkage_scale(-1)
