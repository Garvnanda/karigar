"""Reproductions of the Phase 1 high findings in docs/security/1.md (F1, F3-F8).

Each test fails on the code as reviewed on 2026-11-11 and passes once the root cause is fixed.
"""
import io
import json
import math
import threading
import time

import pytest
from pydantic import ValidationError

from karigar.core import registry
from karigar.core.calibration import CalibrationStore
from karigar.core.orchestrator import Orchestrator
from karigar.packs.jewellery import brief as B
from karigar.packs.jewellery import pricing, rates
from karigar.packs.jewellery.schema import Brief
import karigar.packs.jewellery  # noqa: F401

OWNER = "owner-1"


@pytest.fixture
def staff(monkeypatch):
    monkeypatch.setenv(rates.SETTERS_ENV, OWNER)


def _orch(tmp_path):
    return Orchestrator(registry.get("jewellery"), out_dir=tmp_path / "out",
                        calibration=CalibrationStore(tmp_path / "c.json"))


class FakeLLM:
    def __init__(self, *answers):
        self.answers = list(answers)

    def __call__(self, system, user, *a, **kw):
        return self.answers.pop(0) if self.answers else None


# ---- F1: price questions are not rate updates ------------------------------------

@pytest.mark.parametrize("text", [
    "rate of 22k gold 10 grams",
    "22k gold rate 10 gm",
    "rate 22k 10g",
    "22k ka rate 14730 hai kya?",
    "what is the rate of 22k gold 1 tola",
    "aaj 22k ka bhav kitna hai, 5 gram ke liye",
])
def test_f1_price_question_is_not_a_rate_update(text):
    assert rates.parse_rate_message(text) is None


def test_f1_owner_price_question_saves_nothing(tmp_path, tmp_gold_rates, staff):
    res = _orch(tmp_path).handle("rate of 22k gold 10 grams", sender=OWNER)
    assert res["status"] != "rate_set"
    assert not tmp_gold_rates.exists()


# ---- F3: rate numbers are read exactly or refused --------------------------------

@pytest.mark.parametrize("text", [
    "rate 22k 1e308",
    "rate 22k 1,,,,4",
    "rate 22k 14000 and 22k 15000",       # same karat twice, different values
    "rate 22k 0.0000001",
    "rate 22k 14730.505",
    "rate 22k 0",
])
def test_f3_misparsed_rates_are_refused_not_saved(tmp_path, tmp_gold_rates, staff, text):
    res = _orch(tmp_path).handle(text, sender=OWNER)
    assert res["status"] == "needs_info" and res["topics"] == ["rate"]
    assert not tmp_gold_rates.exists()


@pytest.mark.parametrize("text,expected", [
    ("rate 22k 14,730/-", {22: 14730.0}),
    ("rate 22k ₹14,730/g.", {22: 14730.0}),
    ("rate 22k 1,47,300 and 22k 1,47,300", {22: 147300.0}),   # same value twice is fine
    ("rate 24k 16000.50", {24: 16000.5}),
])
def test_f3_valid_rate_formats_still_parse(text, expected):
    r = rates.parse_rate_message(text)
    assert r is not None and r.rates == expected and r.bad == []


# ---- F4: huge numbers never reach the file ---------------------------------------

def test_f4_400_digit_rate_is_refused(tmp_path, tmp_gold_rates, staff):
    res = _orch(tmp_path).handle("rate 22k " + "9" * 400, sender=OWNER)
    assert res["status"] == "needs_info" and res["topics"] == ["rate"]
    assert len(res["reply"]) < 300            # the 400 digits are not echoed back
    assert not tmp_gold_rates.exists()


@pytest.mark.parametrize("bad", [float("inf"), float("nan"), float("9" * 400), 1e12])
def test_f4_store_refuses_non_finite_or_absurd_rates(tmp_path, bad):
    store = rates.GoldRateStore(tmp_path / "r.json")
    with pytest.raises(ValueError):
        store.set({22: bad})
    assert not (tmp_path / "r.json").exists()


# ---- F5: rates file survives corruption, crashes and concurrent writers ------------

@pytest.mark.parametrize("content", [b"{not json", b"[]", b"\xff\xfe\x00", b'{"22": "x"}',
                                     b'{"22": {"rate_per_g": NaN, "set_at": "x"}}',
                                     b"[" * 100000])
def test_f5_damaged_rates_file_does_not_break_rate_messages(tmp_path, tmp_gold_rates, staff, content):
    tmp_gold_rates.write_bytes(content)
    res = _orch(tmp_path).handle("rate 22k 14730", sender=OWNER)
    assert res["status"] == "rate_set"
    data = json.loads(tmp_gold_rates.read_text(encoding="utf-8"))
    assert data["22"]["rate_per_g"] == 14730.0
    backups = list(tmp_gold_rates.parent.glob("gold_rates.json.corrupt*"))
    assert backups and backups[0].read_bytes() == content     # damaged file kept for the owner


def test_f5_load_skips_damaged_entries(tmp_path):
    p = tmp_path / "r.json"
    p.write_text(json.dumps({"22": {"rate_per_g": 14730.0, "set_at": "2026-11-13T10:00:00+05:30"},
                             "18": {"rate_per_g": -5, "set_at": "x"}, "99": 1}), encoding="utf-8")
    assert set(rates.GoldRateStore(p).load()) == {"22"}


def test_f5_crash_mid_write_keeps_previous_rates(tmp_path, monkeypatch):
    p = tmp_path / "r.json"
    store = rates.GoldRateStore(p)
    store.set({22: 14730.0})
    before = p.read_bytes()
    real_open = io.open

    class DiskFull:
        def __init__(self, f):
            self.f = f

        def write(self, s):
            self.f.write(s[: len(s) // 2])
            self.f.flush()
            raise OSError(28, "No space left on device")

        def __getattr__(self, name):
            return getattr(self.f, name)

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            self.f.close()

    def failing_open(file, mode="r", *a, **kw):
        f = real_open(file, mode, *a, **kw)
        return DiskFull(f) if "w" in mode else f

    monkeypatch.setattr(io, "open", failing_open)
    with pytest.raises(OSError):
        store.set({18: 12060.0})
    monkeypatch.setattr(io, "open", real_open)
    assert p.read_bytes() == before
    assert not list(tmp_path.glob("*.tmp"))       # no temp file left behind


def test_f5_concurrent_writers_do_not_lose_updates(tmp_path, monkeypatch):
    p = tmp_path / "r.json"
    real_loads = json.loads

    def slow_loads(*a, **kw):          # widen the read-modify-write window
        out = real_loads(*a, **kw)
        time.sleep(0.05)
        return out

    rates.GoldRateStore(p).set({24: 16000.0})
    monkeypatch.setattr(rates.json, "loads", slow_loads)
    errors = []

    def write(k, v):
        try:
            rates.GoldRateStore(p).set({k: v})
        except Exception as e:      # pragma: no cover - reported below
            errors.append(e)

    ts = [threading.Thread(target=write, args=kv) for kv in ((22, 14730.0), (18, 12060.0), (14, 9400.0))]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    monkeypatch.setattr(rates.json, "loads", real_loads)
    assert not errors
    assert set(rates.GoldRateStore(p).load()) == {"24", "22", "18", "14"}


# ---- F6: long messages are parsed in linear time ---------------------------------

@pytest.mark.parametrize("text", [
    "1" * 20000,
    "ring " + "1" * 20000,
    "bangle " + "1" * 20000,
    "ring rs" + "1" * 20000 + "x",
    "ring size " + "9" * 20000,
    "ring " + "1." * 10000,
])
def test_f6_20kb_message_parses_fast(text):
    t0 = time.perf_counter()
    B._regex_parse(text)
    rates.parse_rate_message("rate 22k " + text)
    assert time.perf_counter() - t0 < 2.0


# ---- F7: huge or infinite budgets are refused, not crashed on --------------------

def test_f7_400_digit_budget_asks_again_instead_of_crashing():
    r = B.analyse("22k ring, size 12, budget " + "9" * 400)
    assert r.status == "needs_info"
    assert "unreadable:budget_inr" in r.topics


def test_f7_llm_infinite_budget_is_rejected(monkeypatch):
    monkeypatch.setattr(B.llm, "complete_json",
                        FakeLLM({"piece_type": "ring", "karat": 22, "ring_size": 12, "budget_inr": float("inf")},
                                {"piece_type": "ring", "karat": 22, "ring_size": 12, "budget_inr": float("inf")}))
    b, q = B.parse("22k ring, size 12, budget 50000")
    assert q is None and b.budget_inr == 50000          # LLM rejected twice, regex fallback
    plan = pricing.plan(b, 3.0)                          # no OverflowError downstream
    assert plan.ok and math.isfinite(plan.target_value)


@pytest.mark.parametrize("field,value", [("budget_inr", float("inf")), ("budget_inr", float("nan")),
                                         ("target_weight_g", float("nan")), ("gem_ct", float("nan"))])
def test_f7_brief_refuses_non_finite_numbers(field, value):
    with pytest.raises(ValidationError):
        Brief(piece_type="ring", **{field: value})


# ---- F8: LLM style strings never reach the reply ----------------------------------

SCAM = "Pay Rs 500 advance to UPI karigar-shop@upi, price is 999"


def test_f8_llm_style_text_is_not_echoed(monkeypatch):
    monkeypatch.setattr(B.llm, "complete_json",
                        FakeLLM({"piece_type": "ring", "karat": 22, "ring_size": 12, "target_weight_g": 6,
                                 "style": [SCAM, "Lotus", "flower"]}))
    b, q = B.parse("22K lotus ring of 6 g, size 12")
    assert q is None and b.style == ["lotus", "floral"]
    text = registry.get("jewellery").describe_brief(b)
    assert "UPI" not in text and "999" not in text and "500" not in text


def test_f8_brief_keeps_only_known_style_tags():
    b = Brief(piece_type="ring", style=["modern", SCAM, "kamal", 7, "modern"])
    assert b.style == ["modern", "lotus"]
