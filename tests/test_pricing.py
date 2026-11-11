import pytest

from karigar.core import gold as G
from karigar.packs.jewellery import pricing
from karigar.packs.jewellery.schema import Brief, DesignSpec, OldGold


@pytest.fixture
def rc():
    return pricing.rate_card()


def test_inr_uses_indian_grouping():
    assert pricing.inr(123456) == "₹1,23,456"
    assert pricing.inr(12345678) == "₹1,23,45,678"
    assert pricing.inr(999) == "₹999"
    assert pricing.inr(-1500) == "-₹1,500"


def test_quote_arithmetic_plain_ring(rc):
    spec = DesignSpec(name="Band", piece_type="ring", karat=22)
    brief = Brief(piece_type="ring", karat=22, target_weight_g=9.7)
    plan = pricing.plan(brief, 3.0)
    q = pricing.quote(spec, 10.0, brief, plan)
    finished = 10.0 * 0.97
    gold = finished * rc["gold_rate_per_g"]["22"]
    making = gold * rc["making_charge_pct"]["ring"] / 100
    total = (gold + making) * (1 + rc["gst_pct"] / 100)
    assert q["finished_weight_g"] == pytest.approx(9.7)
    assert q["gold_value"] == round(gold)
    assert q["making_charges"] == round(making)
    assert q["total"] == round(total)
    assert q["rate_card_as_of"] == rc["as_of"]
    assert "exchange_credit" not in q


def test_quote_old_gold_credit_and_to_pay(rc):
    brief = Brief(piece_type="ring", karat=22, old_gold=OldGold(weight_g=8.4, karat=22))
    plan = pricing.plan(brief, 3.0)
    assert plan.ok
    spec = DesignSpec(name="Band", piece_type="ring", karat=22)
    q = pricing.quote(spec, plan.target_value, brief, plan)
    credit = plan.detail["fine_g"] / G.purity(24) * rc["gold_rate_per_g"]["24"]
    assert q["exchange_credit"] == round(credit)
    # total and credit are each rounded before to_pay is shown, so allow ₹1 of rounding.
    assert abs(q["to_pay"] - (q["total"] - q["exchange_credit"])) <= 1


def test_quote_is_deterministic():
    brief = Brief(piece_type="ring", karat=18, target_weight_g=5.0, gem="diamond", gem_ct=0.3)
    plan = pricing.plan(brief, 3.0)
    spec = DesignSpec(name="Sol", piece_type="ring", karat=18, gem="diamond", gem_d_mm=4.3)
    assert pricing.quote(spec, 5.2, brief, plan) == pricing.quote(spec, 5.2, brief, plan)


def test_plan_exchange_targets_modelled_weight():
    brief = Brief(piece_type="ring", karat=22, old_gold=OldGold(weight_g=18.4, karat=22))
    plan = pricing.plan(brief, 3.0)
    assert plan.ok and plan.unit == "g"
    assert plan.target_value == pytest.approx(18.59, abs=0.01)


def test_plan_budget_too_small_for_stone_is_infeasible_with_options():
    brief = Brief(piece_type="ring", karat=22, budget_inr=10000, gem="diamond", gem_ct=1.0)
    plan = pricing.plan(brief, 3.0)
    assert not plan.ok
    assert "Closest options" in plan.explanation


def test_plan_below_minimum_weight_is_infeasible():
    brief = Brief(piece_type="ring", karat=22, target_weight_g=1.0)
    plan = pricing.plan(brief, 3.0)
    assert not plan.ok
    assert "minimum" in plan.explanation


def test_plan_without_target_asks_for_one():
    plan = pricing.plan(Brief(piece_type="ring"), 3.0)
    assert not plan.ok
    assert "budget" in plan.explanation
