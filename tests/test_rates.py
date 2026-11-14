import json
from datetime import datetime

import pytest

from karigar.core import registry
from karigar.core.calibration import CalibrationStore
from karigar.core.orchestrator import Orchestrator
from karigar.packs.jewellery import rates
import karigar.packs.jewellery  # noqa: F401


@pytest.mark.parametrize("text,expected", [
    ("aaj ka rate 22K 14730", {22: 14730.0}),
    ("today's rate 22k 14,730 and 18k 12060", {22: 14730.0, 18: 12060.0}),
    ("rate 24K 16000", {24: 16000.0}),
    ("22K ka bhav 14,800 hai", {22: 14800.0}),
])
def test_parse_rate_message(text, expected):
    r = rates.parse_rate_message(text)
    assert r.rates == expected and r.bad == []


@pytest.mark.parametrize("text", ["22K ring of 6 g, size 12", "rate kya hai aaj?", "what is your making rate"])
def test_non_rate_messages(text):
    assert rates.parse_rate_message(text) is None


def test_store_writes_timestamped_rates(tmp_path):
    store = rates.GoldRateStore(tmp_path / "r.json")
    now = datetime(2026, 11, 11, 10, 15).astimezone()
    saved = store.set({22: 14730.0}, now=now)
    data = json.loads((tmp_path / "r.json").read_text())
    assert data["22"] == {"rate_per_g": 14730.0, "set_at": now.isoformat(timespec="seconds"), "source": "chat"}
    assert saved["set_at"] == now.isoformat(timespec="seconds")
    store.set({18: 12060.0})
    assert set(store.load()) == {"22", "18"}   # later updates merge


def test_store_rejects_non_positive(tmp_path):
    with pytest.raises(ValueError):
        rates.GoldRateStore(tmp_path / "r.json").set({22: 0})
    assert not (tmp_path / "r.json").exists()


OWNER = "owner-1"


@pytest.fixture
def staff(monkeypatch):
    """Owner/staff IDs allowed to set the rate (security F2)."""
    monkeypatch.setenv(rates.SETTERS_ENV, f" {OWNER} , staff-7 ")


def _orch(tmp_path):
    return Orchestrator(registry.get("jewellery"), out_dir=tmp_path / "out",
                        calibration=CalibrationStore(tmp_path / "c.json"))


def test_rate_message_sets_rate_instead_of_starting_an_order(tmp_path, tmp_gold_rates, staff):
    res = _orch(tmp_path).handle("aaj ka rate 22K 14730", sender=OWNER)
    assert res["status"] == "rate_set"
    assert res["lang"] == "hinglish" and res["reply"].startswith("Rate save kar liya: 22K ₹14,730/g")
    assert res["rates"]["rates"] == {"22": 14730.0}
    datetime.fromisoformat(res["rates"]["set_at"])
    assert json.loads(tmp_gold_rates.read_text())["22"]["rate_per_g"] == 14730.0
    assert not (tmp_path / "out").exists()       # no order was started


def test_english_rate_message_replies_in_english(tmp_path, tmp_gold_rates, staff):
    res = _orch(tmp_path).handle("today's rate 22k 14,730 and 18k 12060", sender="staff-7")
    assert res["status"] == "rate_set" and res["lang"] == "en"
    assert res["reply"].startswith("Gold rate saved: 22K ₹14,730/g, 18K ₹12,060/g")


def test_malformed_rate_is_rejected(tmp_path, tmp_gold_rates, staff):
    res = _orch(tmp_path).handle("rate 22K -14730", sender=OWNER)
    assert res["status"] == "needs_info" and "-14730" in res["question"]
    assert not tmp_gold_rates.exists()


# ---- security F2: only configured owner/staff may set the rate ---------------------

def test_setters_come_from_config(monkeypatch, staff):
    assert rates.rate_setters() == {OWNER, "staff-7"}
    assert rates.may_set_rate(OWNER) and rates.may_set_rate(" staff-7 ")
    assert not rates.may_set_rate("cust-9") and not rates.may_set_rate(None)
    assert not rates.may_set_rate("")


def test_no_setters_configured_means_nobody_can_set(monkeypatch):
    monkeypatch.delenv(rates.SETTERS_ENV, raising=False)
    assert rates.rate_setters() == set()
    assert not rates.may_set_rate(OWNER)


@pytest.mark.parametrize("sender", [None, "", "cust-9", "OWNER-1"])
def test_rate_from_unknown_or_missing_sender_is_rejected(tmp_path, tmp_gold_rates, staff, sender):
    res = _orch(tmp_path).handle("aaj ka rate 22K 14730", sender=sender)
    assert res["status"] == "needs_info" and res["topics"] == ["rate_permission"]
    assert res["lang"] == "hinglish" and "owner ya staff" in res["reply"]
    assert res["rates"] is None
    assert not tmp_gold_rates.exists()           # the config rate keeps applying
    assert not (tmp_path / "out").exists()


def test_rejection_reply_mirrors_english(tmp_path, tmp_gold_rates, staff):
    res = _orch(tmp_path).handle("today's rate 22k 14,730", sender="cust-9")
    assert res["status"] == "needs_info" and res["lang"] == "en"
    assert "Only the shop owner or staff can set the gold rate" in res["reply"]
    assert not tmp_gold_rates.exists()


def test_rate_rejected_when_nobody_is_configured(tmp_path, tmp_gold_rates, monkeypatch):
    monkeypatch.delenv(rates.SETTERS_ENV, raising=False)
    res = _orch(tmp_path).handle("aaj ka rate 22K 14730", sender=OWNER)
    assert res["topics"] == ["rate_permission"] and not tmp_gold_rates.exists()


def test_setters_read_from_env_file(monkeypatch, tmp_path):
    from karigar.core import llm
    env = tmp_path / "staff.env"
    env.write_text(f"# staff\n{rates.SETTERS_ENV}=owner-9\n", encoding="utf-8")
    monkeypatch.setattr(llm, "ENV_FILE", env)
    monkeypatch.delenv(rates.SETTERS_ENV, raising=False)
    assert rates.rate_setters() == {"owner-9"}
