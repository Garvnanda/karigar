"""Phase 6 gate, with real Blender geometry: edits are spec patches, re-solved and re-checked.

- "make it 0.5 mm thinner" changes only that parameter (v1/v2 spec diff),
- "Middle one, but make the flower slightly bigger" keeps the gold target by re-solving the band,
- weight edits move the target; weight Δ and price Δ are reported (pricing via RateSource).
"""
import pytest

from karigar.core import gold as G
from karigar.packs.jewellery import PACK, edits
from karigar.packs.jewellery import brief as B
from karigar.packs.jewellery import geometry
from karigar.packs.jewellery.schema import Brief

HERO_A = ("Purani 8.4g 22K chain exchange karni hai, uske badle 22K ladies ring chahiye, "
          "size 12, chhota floral design")
LOSS = 3.0
REL_TOL = 0.003 * 3          # solver tolerance (incl. its no-convergence allowance)


def _built_dims(spec, s):
    geometry.clear_scene()
    d = geometry.build(spec, s).dims
    geometry.clear_scene()
    return d


@pytest.fixture  # function scope: the autouse no-LLM / seeded-rate fixtures must apply
def hero():
    brief, q = B.parse(HERO_A)
    assert q is None
    plan = PACK.plan(brief, LOSS)
    assert plan.ok
    specs = PACK.propose(brief, 3)
    middle = PACK.solve(specs[1], plan)
    assert middle.ok and middle.spec.motif == "floral"
    return brief, plan, specs, middle


@pytest.fixture  # function scope: the autouse no-LLM / seeded-rate fixtures must apply
def band():
    # 8 g: the band is ~2.1 mm thick, so "0.5 mm thinner" stays above the 1.5 mm shank minimum
    # (Phase 3 sourced value; at the old 5 g the edit hit the new minimum, decisions.md Phase 3)
    brief = Brief(piece_type="ring", karat=22, target_weight_g=8.0, ring_inner_d_mm=17.3)
    plan = PACK.plan(brief, LOSS)
    spec = PACK.propose(brief, 3)[1]           # plain comfort band
    v1 = PACK.solve(spec, plan)
    assert v1.ok
    return brief, plan, v1


def _edit(base, plan, text):
    req = PACK.parse_edit(text)
    out = PACK.apply_edit(base.spec, base.scale, base.value, req, plan)
    assert out.status == "solved", (out.status, out.reply, getattr(out.solved, "explanation", ""))
    return out


def test_thinner_changes_only_thickness(band):
    brief, plan, v1 = band
    out = _edit(v1, plan, "make it 0.5 mm thinner")
    v2 = out.solved
    diff = edits.diff(v1.spec.model_dump(), v2.spec.model_dump())
    assert list(diff) == ["thickness_mm"]
    t1 = _built_dims(v1.spec, v1.scale)["thickness_mm"]
    t2 = _built_dims(v2.spec, v2.scale)["thickness_mm"]
    assert t2 == pytest.approx(t1 - 0.5, abs=0.011)       # built geometry is 0.5 mm thinner
    assert v2.value == pytest.approx(plan.target_value, rel=REL_TOL)   # gold target kept
    assert v2.issues and any("thickness" in i for i in v2.issues)      # checks rerun on v2


def test_middle_one_flower_slightly_bigger_keeps_gold_by_resolving_band(hero):
    brief, plan, specs, middle = hero
    req = PACK.parse_edit("Middle one, but make the flower slightly bigger")
    assert req.pick == "middle" and PACK.pick_index(req.pick, 3) == 1
    out = PACK.apply_edit(middle.spec, middle.scale, middle.value, req, plan)
    assert out.status == "solved"
    v2 = out.solved
    assert list(edits.diff(middle.spec.model_dump(), v2.spec.model_dump())) == ["size_mm"]
    d1, d2 = _built_dims(middle.spec, middle.scale), _built_dims(v2.spec, v2.scale)
    assert d2["flower_d_mm"] == pytest.approx(d1["flower_d_mm"] * (1 + edits.STEP["slight"]), abs=0.011)
    # same gold: the band was re-solved (thinner/narrower) to pay for the bigger flower
    assert v2.value == pytest.approx(plan.target_value, rel=REL_TOL)
    assert G.mm3_to_grams(geometry.gold_volume(v2.spec, v2.scale), 22) == pytest.approx(v2.value, rel=1e-6)
    assert v2.scale < middle.scale
    assert d2["width_mm"] < d1["width_mm"] and d2["thickness_mm"] < d1["thickness_mm"]

    rep = PACK.edit_report({"version": 2}, 4, out, brief, "en")
    assert rep["kept_gold_target"] is True
    assert set(rep["changed"]) == {"size_mm"} and {"width_mm", "thickness_mm"} <= set(rep["resolved"])
    assert abs(rep["weight_g"]["delta"]) <= plan.target_value * REL_TOL
    assert "v4 (from v2)" in rep["summary"]


def test_weight_edit_moves_target_and_reports_weight_and_price_delta(band):
    brief, plan, v1 = band
    out = _edit(v1, plan, "1 g lighter")
    v2 = out.solved
    assert edits.diff(v1.spec.model_dump(), v2.spec.model_dump()) == {}   # same design, new scale
    fin = lambda m: m * (1 - LOSS / 100)
    assert fin(v2.value) == pytest.approx(fin(v1.value) - 1.0, abs=fin(v2.target) * REL_TOL)

    rep = PACK.edit_report({"version": 2}, 4, out, brief, "en")
    q_before = PACK.quote(v1, brief, out.plan)
    assert rep["kept_gold_target"] is False
    assert rep["weight_g"]["delta"] == pytest.approx(rep["weight_g"]["to"] - rep["weight_g"]["from"], abs=1e-3)
    assert rep["weight_g"]["delta"] == pytest.approx(-1.0, abs=0.05)
    assert rep["price_inr"]["from"] == q_before["total"]
    assert rep["price_inr"]["to"] == rep["quote"]["total"]
    assert rep["price_inr"]["delta"] == rep["price_inr"]["to"] - rep["price_inr"]["from"] < 0
    assert "Weight" in rep["summary"] and "price" in rep["summary"]


def test_exchange_edit_reports_to_pay_delta(hero):
    brief, plan, specs, middle = hero
    out = _edit(middle, plan, "thoda halka karo")
    rep = PACK.edit_report({"version": 2}, 4, out, brief, "hinglish")
    assert rep["to_pay_inr"]["delta"] == rep["price_inr"]["delta"]      # same old-gold credit
    assert rep["weight_g"]["delta"] < 0 and "Wazan" in rep["summary"]


def test_too_thin_is_infeasible_not_a_bad_design(band):
    brief, plan, v1 = band
    t1 = v1.spec.thickness_mm * v1.scale
    cut = round(t1 - 1.0, 2)           # leaves 1.0 mm, under the 1.5 mm ring shank minimum
    req = PACK.parse_edit(f"make it {cut} mm thinner")
    out = PACK.apply_edit(v1.spec, v1.scale, v1.value, req, plan)
    assert out.status == "infeasible"
    assert out.solved.binding_constraint and len(out.solved.alternatives) >= 2
