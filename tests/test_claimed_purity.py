"""Security F9: customer-claimed or tested purity never raises the old-gold credit.

User decision 2026-11-13: credit old gold at the stated karat's purity only, whatever the
customer (or the LLM) says about a test result.
"""
import pytest

from karigar.packs.jewellery import brief as B
from karigar.packs.jewellery import pricing
from karigar.packs.jewellery.schema import Brief

KARAT_ONLY_FINE = 10 * 0.916 * 0.98     # 10 g of 22K, 2% melt loss


def _fine(b: Brief) -> float:
    p = pricing.plan(b, 3.0)
    assert p.ok
    return p.detail["fine_g"]


@pytest.mark.parametrize("text", [
    "purana 10g 22K kangan hai, tested 99.9%, naya 22K kada banana hai, size 2-6",
    "My old 10g 22K bangle was XRF tested at 99.9% purity, make a new 22K bangle, size 2-6",
])
def test_regex_path_ignores_claimed_purity(text):
    b, q = B.parse(text)
    assert q is None and b.old_gold.karat == 22
    assert "tested_purity" not in b.old_gold.model_dump()
    assert _fine(b) == pytest.approx(KARAT_ONLY_FINE, abs=0.01)


def test_llm_cannot_fill_tested_purity(monkeypatch):
    raw = {"piece_type": "bangle", "karat": 22, "bangle_inner_d_mm": 60.3,
           "old_gold": {"weight_g": 10, "karat": 22, "tested_purity": 0.999}}
    monkeypatch.setattr(B.llm, "complete_json", lambda *a, **k: raw)
    b, q = B.parse("purana 10g 22K kangan, naya 22K kada, size 2-6")
    assert q is None
    assert "tested_purity" not in b.old_gold.model_dump()
    assert _fine(b) == pytest.approx(KARAT_ONLY_FINE, abs=0.01)


def test_brief_built_directly_ignores_tested_purity():
    b = Brief(piece_type="bangle", karat=22,
              old_gold={"weight_g": 10, "karat": 22, "tested_purity": 0.999})
    assert _fine(b) == pytest.approx(KARAT_ONLY_FINE, abs=0.01)


def test_llm_prompt_does_not_ask_for_tested_purity():
    assert "tested_purity" not in B.SYSTEM
