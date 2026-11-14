"""The scripted briefs (tests/data/briefs.json): each gives a valid Brief or the right question."""
import json
from pathlib import Path

import pytest

from karigar.core import registry
from karigar.packs.jewellery import pricing, rates
import karigar.packs.jewellery  # noqa: F401

CASES = json.loads((Path(__file__).parent / "data" / "briefs.json").read_text(encoding="utf-8"))


def test_at_least_ten_with_the_hero_scenarios():
    ids = [c["id"] for c in CASES]
    assert len(ids) >= 10
    for hero in ("hero_a", "hero_b", "hero_c", "hero_d"):
        assert any(i.startswith(hero) for i in ids)
    statuses = {c["status"] for c in CASES}
    assert {"brief", "needs_info", "rate_set", "out_of_scope"} <= statuses
    assert {c["lang"] for c in CASES} == {"en", "hinglish"}


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_scripted_brief(case, tmp_gold_rates, monkeypatch):
    monkeypatch.setenv(rates.SETTERS_ENV, "owner-1")
    r = registry.get("jewellery").intake(case["text"], sender=case.get("sender"))
    assert r.status == case["status"], (r.status, r.reply)
    assert r.lang == case["lang"]
    if case["status"] == "brief":
        b = r.brief
        assert b.lang == case["lang"]
        for k, v in case["fields"].items():
            if k == "style_includes":
                assert set(v) <= set(b.style)
            elif k == "old_gold":
                assert b.old_gold.model_dump(exclude_none=True) == v
            else:
                assert getattr(b, k) == v, k
    elif case["status"] == "needs_info":
        assert r.topics == case["topics"] and r.reply
    elif case["status"] == "rate_set":
        assert r.data["rates"]["rates"] == case["rates"]
    else:
        assert r.data["suggestion"] == case["suggestion"]


def test_hero_d_brief_is_valid_and_the_plan_declares_it_infeasible():
    case = next(c for c in CASES if c["id"].startswith("hero_d"))
    b = registry.get("jewellery").intake(case["text"]).brief
    p = pricing.plan(b, 3.0)
    assert not p.ok and "minimum" in p.binding_constraint and len(p.alternatives) >= 2
