import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


@pytest.fixture(autouse=True)
def no_llm(monkeypatch, tmp_path):
    """Tests run the deterministic paths; never call the real API or read the real .env."""
    from karigar.core import llm
    monkeypatch.setattr(llm, "ENV_FILE", tmp_path / "no.env")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("AGENTROUTER_API_KEY", raising=False)
    monkeypatch.setenv("KARIGAR_LLM_BACKEND", "none")


@pytest.fixture(autouse=True)
def tmp_gold_rates(monkeypatch, tmp_path):
    """Chat rate updates go to a temp file, never data/gold_rates.json."""
    from karigar.packs.jewellery import rates
    path = tmp_path / "gold_rates.json"
    monkeypatch.setattr(rates, "RATES_FILE", path)
    return path


SEED_RATES = {24: 14160.7, 22: 12971.2, 18: 10620.5, 14: 8284.0}   # MCX 1,36,607 + 5,000


@pytest.fixture(autouse=True)
def seeded_rate_source(monkeypatch, tmp_path):
    """Pricing reads a fresh, in-range rate from a temp store (never data/gold_rates.json).

    `rates.rate_source` is replaced; tests of the real factory restore it with
    `monkeypatch.setattr(rates, "rate_source", rates.RateSource...)` or build a RateSource."""
    from karigar.packs.jewellery import rates
    store = rates.GoldRateStore(tmp_path / "seeded_gold_rates.json")
    store.set(SEED_RATES, source="mcx-job: test seed")
    monkeypatch.setattr(rates, "rate_source", lambda: rates.RateSource(store))
    return store


@pytest.fixture(autouse=True)
def tmp_orders_db(monkeypatch, tmp_path):
    """The order store's default file is a temp file, never data/orders.sqlite3."""
    path = tmp_path / "orders.sqlite3"
    monkeypatch.setenv("KARIGAR_ORDERS_DB", str(path))
    return path


@pytest.fixture(autouse=True)
def no_rate_setters(monkeypatch):
    """No owner/staff IDs leak in from the real environment; tests configure their own."""
    monkeypatch.delenv("KARIGAR_RATE_SETTERS", raising=False)
