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
