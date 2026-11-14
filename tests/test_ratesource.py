"""Phase 5: one RateSource; missing / stale / out-of-range / future rates → ask, never estimate."""
import json
from datetime import datetime, timedelta

import pytest

from karigar.core import registry
from karigar.core.calibration import CalibrationStore
from karigar.core.orchestrator import Orchestrator
from karigar.packs.jewellery import pricing, rates
from karigar.packs.jewellery.schema import Brief, OldGold
import karigar.packs.jewellery  # noqa: F401

NOW = datetime(2026, 11, 13, 18, 0).astimezone()
ORDER = "22K ring of 6 g, size 12"


def _src(tmp_path, entries=None, now=NOW):
    store = rates.GoldRateStore(tmp_path / "r.json")
    for k, (v, when) in (entries or {}).items():
        store.set({k: v}, now=when, source="manual")
    return rates.RateSource(store, clock=lambda: now)


def _orch(tmp_path):
    return Orchestrator(registry.get("jewellery"), out_dir=tmp_path / "out",
                        calibration=CalibrationStore(tmp_path / "c.json"))


def _use(monkeypatch, src):
    monkeypatch.setattr(rates, "rate_source", lambda: src)


def test_fresh_in_range_rate_is_returned_with_its_timestamp(tmp_path):
    src = _src(tmp_path, {22: (13000.0, NOW - timedelta(hours=23))})
    g = src.get(22)
    assert g.per_g == 13000.0 and g.source == "manual"
    assert g.set_at == (NOW - timedelta(hours=23)).isoformat(timespec="seconds")


@pytest.mark.parametrize("entries,kind", [
    ({}, "missing"),
    ({18: (10600.0, NOW)}, "missing"),                                 # another karat is never borrowed
    ({22: (13000.0, NOW - timedelta(hours=24, minutes=1))}, "stale"),
    ({22: (130.0, NOW)}, "out_of_range"),                              # per-g typo / misread
    ({22: (130000.0, NOW)}, "out_of_range"),                           # per-10 g figure stored as per-g
    ({22: (13000.0, NOW + timedelta(hours=2))}, "future"),
])
def test_unusable_rate_raises_the_right_problem(tmp_path, entries, kind):
    src = _src(tmp_path, entries)
    with pytest.raises(rates.RateProblem) as e:
        src.get(22)
    assert e.value.kind == kind and e.value.karat == 22


def test_sane_range_scales_by_karat(tmp_path):
    src = _src(tmp_path)
    lo24, hi24 = src.sane_range(24)
    lo14, hi14 = src.sane_range(14)
    assert lo14 == pytest.approx(lo24 * 0.585) and hi14 == pytest.approx(hi24 * 0.585)


def test_damaged_rate_file_reads_as_missing(tmp_path):
    (tmp_path / "r.json").write_text("{not json")
    assert _src(tmp_path).problem([22]).kind == "missing"


@pytest.mark.parametrize("entries,needle_en,needle_hi", [
    ({}, "I don't have a 22K gold rate", "22K ka gold rate nahi hai"),
    ({22: (13000.0, NOW - timedelta(hours=30))}, "more than 24 h old", "24 ghante se purana"),
    ({22: (130.0, NOW)}, "outside the sane range", "sahi range"),
    ({22: (13000.0, NOW + timedelta(hours=2))}, "stamped in the future", "aage ki tareekh"),
])
def test_order_without_a_usable_rate_asks_for_todays_rate(tmp_path, monkeypatch, entries, needle_en, needle_hi):
    _use(monkeypatch, _src(tmp_path, entries))
    res = _orch(tmp_path).handle(ORDER)
    assert res["status"] == "needs_info" and res["topics"] == ["gold_rate"]
    assert needle_en in res["reply"] and "What is today's 22K rate?" in res["reply"]
    assert "never estimate" in res["reply"]
    assert res["results"] == [] and not (tmp_path / "out").exists()     # nothing priced, no order
    hi = _orch(tmp_path).handle("Mujhe 22K ki ring chahiye, 6 gram, size 12")
    assert hi["lang"] == "hinglish" and needle_hi in hi["reply"] and "Aaj ka 22K rate kya hai?" in hi["reply"]


def test_stale_reply_shows_the_old_rate_and_its_time(tmp_path, monkeypatch):
    when = NOW - timedelta(hours=30)
    _use(monkeypatch, _src(tmp_path, {22: (13000.0, when)}))
    res = _orch(tmp_path).handle(ORDER)
    assert "₹13,000/g" in res["reply"] and when.strftime("%Y-%m-%d %H:%M") in res["reply"]


def test_exchange_order_also_needs_a_fresh_24k_rate(tmp_path, monkeypatch):
    _use(monkeypatch, _src(tmp_path, {22: (13000.0, NOW)}))
    assert rates.karats_needed(22, old_gold=True) == [22, 24]
    res = _orch(tmp_path).handle("Mere paas 10g purana 22K kangan hai, naya 22K ring banana hai, size 12")
    assert res["status"] == "needs_info" and "24K" in res["reply"]


def test_plan_refuses_instead_of_estimating_when_rate_is_unusable(tmp_path):
    src = _src(tmp_path, {22: (13000.0, NOW - timedelta(days=3))})
    p = pricing.plan(Brief(piece_type="ring", karat=22, budget_inr=50000), 3.0, source=src)
    assert not p.ok and p.target_value == 0.0
    assert p.detail["rate_problem"] == "stale" and "gold rate" in p.binding_constraint
    assert len(p.alternatives) >= 2


def test_plan_records_the_rate_it_used(tmp_path):
    src = _src(tmp_path, {22: (13000.0, NOW), 24: (14200.0, NOW)})
    b = Brief(piece_type="ring", karat=22, old_gold=OldGold(weight_g=8.4, karat=22))
    p = pricing.plan(b, 3.0, source=src)
    assert p.ok and set(p.detail["gold_rate"]) == {"22", "24"}
    assert p.detail["gold_rate"]["22"]["per_g"] == 13000.0
    assert "Gold rate 22K ₹13,000/g as of 2026-11-13 18:00 (manual)" in p.summary


# ---- one source of truth: the chat-saved rate is the rate pricing reads -----------------

def test_chat_saved_rate_is_what_the_quote_uses(tmp_path, monkeypatch, tmp_gold_rates):
    monkeypatch.setattr(rates, "rate_source", lambda: rates.RateSource())   # the real factory
    monkeypatch.setenv(rates.SETTERS_ENV, "owner-1")
    assert _orch(tmp_path).handle("aaj ka rate 22K 13456", sender="owner-1")["status"] == "rate_set"
    assert json.loads(tmp_gold_rates.read_text())["22"]["source"] == "chat"
    p = pricing.plan(Brief(piece_type="ring", karat=22, target_weight_g=6.0), 3.0)
    assert p.ok and p.detail["gold_rate"]["22"]["per_g"] == 13456.0
    assert p.detail["gold_rate"]["22"]["source"] == "chat"


def test_nonilion_chat_without_sender_cannot_set_the_rate(tmp_path, monkeypatch, tmp_gold_rates):
    monkeypatch.setenv(rates.SETTERS_ENV, "owner-1")
    res = _orch(tmp_path).handle("aaj ka rate 22K 13456")     # Nonilion sends no sender ID
    assert res["topics"] == ["rate_permission"] and not tmp_gold_rates.exists()
    assert "configured gold rate" in res["reply"]


def test_store_keeps_source_and_rejects_empty_source(tmp_path):
    store = rates.GoldRateStore(tmp_path / "r.json")
    with pytest.raises(ValueError):
        store.set({22: 13000.0}, source=" ")
    store.set({22: 13000.0}, now=NOW, source="mcx-job: x")
    assert store.load()["22"]["source"] == "mcx-job: x"
