from datetime import datetime

import pytest

from karigar.packs.jewellery import pricing, rates
from karigar.packs.jewellery.schema import Brief, DesignSpec, OldGold

NOW = datetime(2026, 11, 13, 18, 0).astimezone()


@pytest.fixture
def src(tmp_path):
    """Fixed rates: 22K ₹13,000/g, 24K ₹14,200/g, set by the owner at NOW."""
    store = rates.GoldRateStore(tmp_path / "r.json")
    store.set({22: 13000.0, 24: 14200.0}, now=NOW, source="manual")
    return rates.RateSource(store, clock=lambda: NOW)


def _lines(q):
    return {ln["key"]: ln for ln in q["lines"]}


def test_inr_uses_indian_grouping():
    assert pricing.inr(123456) == "₹1,23,456"
    assert pricing.inr(12345678) == "₹1,23,45,678"
    assert pricing.inr(999) == "₹999"
    assert pricing.inr(-1500) == "-₹1,500"


def test_quote_lines_to_the_rupee_plain_ring(src):
    """Hand-computed: 9.700 g × ₹13,000 = 1,26,100; making 3.5% = 4,413.5 → 4,414 (half-up);
    hallmark 75; GST 3% of 1,26,100 = 3,783; GST 5% of 4,414 = 220.7 → 221; total 1,34,593."""
    brief = Brief(piece_type="ring", karat=22, target_weight_g=9.7)
    plan = pricing.plan(brief, 3.0, source=src)
    q = pricing.quote(DesignSpec(name="Band", piece_type="ring", karat=22), 10.0, brief, plan)
    assert q["finished_weight_g"] == pytest.approx(9.7)
    assert (q["gold_value"], q["making_charges"], q["stone_value"], q["hallmarking"]) == (126100, 4414, 0, 75)
    assert (q["gst_gold_stones"], q["gst_making"], q["gst"]) == (3783, 221, 4004)
    assert q["total"] == 134593 == sum(ln["amount_inr"] for ln in q["lines"])
    assert "exchange_credit" not in q


def test_quote_shows_rate_and_timestamp(src):
    brief = Brief(piece_type="ring", karat=22, target_weight_g=9.7)
    plan = pricing.plan(brief, 3.0, source=src)
    q = pricing.quote(DesignSpec(name="Band", piece_type="ring", karat=22), 10.0, brief, plan)
    assert q["gold_rate_per_g"] == 13000.0 and q["gold_rate_as_of"] == NOW.isoformat(timespec="seconds")
    assert q["gold_rate_source"] == "manual"
    assert "gold rate 22K ₹13,000/g as of 2026-11-13 18:00" in q["summary"]
    assert "as of 2026-11-13 18:00" in _lines(q)["gold"]["source"]


def test_every_line_has_a_source_and_assumed_values_are_marked(src):
    brief = Brief(piece_type="ring", karat=22, target_weight_g=9.7, gem="diamond", gem_ct=0.3)
    plan = pricing.plan(brief, 3.0, source=src)
    spec = DesignSpec(name="Sol", piece_type="ring", karat=22, gem="diamond", gem_d_mm=4.3)
    q = pricing.quote(spec, 10.0, brief, plan)
    L = _lines(q)
    assert set(L) == {"gold", "making", "stones", "hallmark", "gst_gold_stones", "gst_making"}
    assert all(ln["label"] and ln["source"] and isinstance(ln["assumed"], bool) for ln in q["lines"])
    assert L["making"]["assumed"] and "assumed" in L["making"]["source"]          # 3.5% is a user choice
    assert L["gst_making"]["assumed"] and L["stones"]["assumed"]                  # CA / lab-grown rate
    assert not L["gold"]["assumed"]           # owner-set rate: a fact, with its timestamp
    assert not L["hallmark"]["assumed"] and "BIS" in L["hallmark"]["source"]
    assert "making 3.5%" in L["making"]["source"]


def test_quote_prices_the_stone_and_puts_it_in_the_3pct_gst_base(src):
    """Stone line = ct (2 dp) × rate-card ₹/ct, half-up; GST 3% is on gold + stones together."""
    from decimal import Decimal, ROUND_HALF_UP

    def r(x):
        return int(Decimal(x).quantize(Decimal(1), rounding=ROUND_HALF_UP))

    brief = Brief(piece_type="ring", karat=22, target_weight_g=9.7, gem="diamond", gem_ct=0.3)
    plan = pricing.plan(brief, 3.0, source=src)
    spec = DesignSpec(name="Sol", piece_type="ring", karat=22, gem="diamond", gem_d_mm=4.3)
    q = pricing.quote(spec, 10.0, brief, plan)
    ct = Decimal(f"{spec.gem_ct:.2f}")
    per_ct = pricing.rate_card()["stone_rate_per_ct"]["diamond"]
    assert per_ct == 25000 and ct > 0
    stones = r(ct * per_ct)
    assert q["stone_value"] == stones == _lines(q)["stones"]["amount_inr"]
    assert q["gold_value"] == 126100
    assert q["gst_gold_stones"] == r((Decimal(126100) + stones) * 3 / 100)
    assert q["gst_gold_stones"] > r(Decimal(126100) * 3 / 100)          # stones really are in the base
    assert q["total"] == sum(ln["amount_inr"] for ln in q["lines"])


def test_job_rate_is_marked_assumed_formula(tmp_path):
    store = rates.GoldRateStore(tmp_path / "r.json")
    store.set({22: 13000.0}, now=NOW, source="mcx-job: MCX 136607/10g + 5000, example")
    s = rates.RateSource(store, clock=lambda: NOW)
    brief = Brief(piece_type="ring", karat=22, target_weight_g=9.7)
    q = pricing.quote(DesignSpec(name="B", piece_type="ring", karat=22), 10.0, brief,
                      pricing.plan(brief, 3.0, source=s))
    g = _lines(q)["gold"]
    assert g["assumed"] and "MCX + ₹5,000/10 g" in g["source"] and "rate job" in g["source"]


def test_old_gold_credit_is_weight_purity_rate_minus_2pct(src):
    """8.4 g × 0.916 × ₹14,200 × 0.98 = 1,07,075.27 → 1,07,075. One deduction only."""
    brief = Brief(piece_type="ring", karat=22, old_gold=OldGold(weight_g=8.4, karat=22))
    plan = pricing.plan(brief, 3.0, source=src)
    assert plan.ok
    q = pricing.quote(DesignSpec(name="Band", piece_type="ring", karat=22), 10.0, brief, plan)
    assert q["exchange_credit"] == 107075
    assert q["total"] == 134593 and q["to_pay"] == 134593 - 107075
    credit = _lines(q)["old_gold_credit"]
    assert credit["amount_inr"] == -107075 and credit["assumed"]
    assert "2% deduction, no separate melt loss" in credit["source"]
    assert "24K rate ₹14,200/g as of 2026-11-13 18:00" in credit["source"]


def test_exchange_target_uses_the_same_single_2pct_deduction(src):
    brief = Brief(piece_type="ring", karat=22, old_gold=OldGold(weight_g=18.4, karat=22))
    plan = pricing.plan(brief, 3.0, source=src)
    assert plan.ok and plan.unit == "g"
    assert plan.detail["fine_g"] == pytest.approx(18.4 * 0.916 * 0.98, abs=1e-3)
    assert plan.target_value == pytest.approx(18.59, abs=0.01)


def test_same_inputs_give_the_same_quote_to_the_rupee(src):
    brief = Brief(piece_type="ring", karat=22, target_weight_g=5.0, gem="diamond", gem_ct=0.3)
    spec = DesignSpec(name="Sol", piece_type="ring", karat=22, gem="diamond", gem_d_mm=4.3)
    q1 = pricing.quote(spec, 5.2, brief, pricing.plan(brief, 3.0, source=src))
    q2 = pricing.quote(spec, 5.2, brief, pricing.plan(brief, 3.0, source=src))
    assert q1 == q2
    assert all(isinstance(ln["amount_inr"], int) for ln in q1["lines"])
    assert isinstance(q1["total"], int) and q1["total"] == sum(ln["amount_inr"] for ln in q1["lines"])


@pytest.mark.parametrize("piece,articles", [("chain", 1), ("coin", 1), ("earring", 2), ("nosepin", 1)])
def test_new_piece_types_quote_with_3_5pct_making(src, piece, articles):
    kw = {"length_in": 18} if piece == "chain" else {}
    brief = Brief(piece_type=piece, karat=22, target_weight_g=2.0, **kw)
    plan = pricing.plan(brief, 3.0, source=src)
    assert plan.ok
    q = pricing.quote(DesignSpec(name="x", piece_type=piece, **kw), 2.0, brief, plan)
    gold = round(2.0 * 0.97 * 13000)
    assert q["gold_value"] == gold and q["making_charges"] == round(gold * 0.035)
    assert q["hallmarking"] == 75 * articles


def test_stone_named_without_size_gets_an_assumed_size_line(src):
    brief = Brief(piece_type="ring", karat=22, target_weight_g=4.0, gem="ruby")     # no carat given
    spec = DesignSpec(name="Ruby", piece_type="ring", karat=22, gem="ruby", gem_d_mm=5.0)
    q = pricing.quote(spec, 4.2, brief, pricing.plan(brief, 3.0, source=src))
    note = f"stone size assumed: {spec.gem_ct:.2f} ct (5 mm, the design's own stone)"
    assert q["assumptions"] == [note]
    assert note in _lines(q)["stones"]["label"] and _lines(q)["stones"]["assumed"]
    assert "Stone size assumed" in q["summary"]
    # A stated size is not flagged.
    b2 = Brief(piece_type="ring", karat=22, target_weight_g=4.0, gem="ruby", gem_ct=0.5)
    q2 = pricing.quote(spec, 4.2, b2, pricing.plan(b2, 3.0, source=src))
    assert q2["assumptions"] == [] and "assumed:" not in _lines(q2)["stones"]["label"]


def test_budget_plan_solves_to_the_quote_total(src):
    """A budget order is planned to whole mg: the quote never tops the budget, and misses it by
    less than 1 mg of gold all-in (~₹14 at ₹13,000/g)."""
    brief = Brief(piece_type="ring", karat=22, budget_inr=100000)
    p = pricing.plan(brief, 3.0, source=src)
    assert p.ok
    q = pricing.quote(DesignSpec(name="B", piece_type="ring", karat=22), p.target_value, brief, p)
    assert 100000 - 15 <= q["total"] <= 100000


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


def test_rate_card_holds_no_gold_rate():
    """One source of truth: the gold rate lives only in the RateSource store."""
    rc = pricing.rate_card()
    assert "gold_rate_per_g" not in rc and "exchange" not in rc
    assert set(rc["making_charge_pct"].values()) == {3.5}
    assert rc["gst_pct"] == {"gold_and_stones": 3, "making": 5}
    assert rc["hallmark_fee_inr_per_article"] == 75 and rc["old_gold_deduction_pct"] == 2.0
