import json

import pytest

from karigar.core.lang import EN, HINGLISH
from karigar.packs.jewellery import brief as B
from karigar.packs.jewellery import designer, pricing
from karigar.packs.jewellery.schema import Brief


def test_unclear_request_asks_follow_up():
    b, q = B.parse("kuch sundar sa bana do")
    assert b is None and q


def test_piece_without_target_asks_for_gold_or_budget():
    b, q = B.parse("ek ring banana hai")
    assert b is None and "budget" in q


def test_hinglish_old_gold_exchange():
    b, q = B.parse("Nani ka purana 18.4g 22K kangan hai, naya 22K beaded kada banana hai, size 2-6")
    assert q is None
    assert b.piece_type == "bangle"
    assert b.old_gold.weight_g == 18.4 and b.old_gold.karat == 22
    assert b.karat == 22
    assert b.bangle_inner_d_mm == 60.3
    assert "beaded" in b.style
    assert b.lang == HINGLISH


def test_budget_in_lakh_and_indian_ring_size():
    b, q = B.parse("18K white gold solitaire with 0.5 ct diamond, budget 1.2 lakh, size 6")
    assert q is None
    assert b.karat == 18 and b.metal == "white"
    assert b.gem == "diamond" and b.gem_ct == 0.5
    assert b.budget_inr == 120000
    assert b.ring_size == 6 and b.ring_inner_d_mm == 14.6   # Indian size 6, not US 6


def test_explicit_us_size_and_mm_still_accepted():
    us, _ = B.parse("18K ring of 4 g, US size 7")
    assert us.ring_inner_d_mm == 17.3
    mm, _ = B.parse("18K ring of 4 g, 17.8 mm")
    assert mm.ring_inner_d_mm == 17.8


# ---- out of scope -------------------------------------------------------------

# Earrings and nose pins moved into scope in Phase 2.5 (user decision, decisions.md 2026-11-13
# "Design catalogue"); their old cases here are now in-scope tests in test_brief_catalogue.py.
@pytest.mark.parametrize("text,lang,nearest", [
    ("I want a gold necklace of 20 g in 22K", EN, "chain + pendant"),
    ("mujhe 22K ka mangalsutra banana hai 10g", HINGLISH, "chain + pendant"),
    ("chandi jaisi payal sone mein chahiye 22K 15g", HINGLISH, "bangle"),
    ("a 22K maang tikka, 6 g", EN, "pendant"),
])
def test_out_of_scope_explains_scope_and_offers_nearest(text, lang, nearest):
    r = B.analyse(text)
    assert r.status == "out_of_scope" and r.brief is None
    assert r.lang == lang and r.suggestion == nearest
    assert nearest in r.reply
    if lang == EN:
        assert "rings, bangles, pendants, chains, coins, earrings and nose pins" in r.reply
    else:
        assert "sirf ring, bangle, pendant, chain, sikka, earrings aur nose pin" in r.reply


def test_old_chain_as_gold_source_is_not_out_of_scope():
    r = B.analyse("purani 22K chain 6.2g se 22K ruby lotus pendant banao")
    assert r.status == "brief" and r.brief.piece_type == "pendant"


# ---- language mirroring ---------------------------------------------------------

def test_hinglish_in_hinglish_out():
    r = B.analyse("ek 22K ring banana hai 4g ki")
    assert r.lang == HINGLISH
    assert r.reply.startswith("Ring ka size kya hai?")


def test_english_in_english_out():
    r = B.analyse("A 22K ring of 4 g please")
    assert r.lang == EN
    assert r.reply.startswith("What is the ring size?")


def test_brief_summary_line_mirrors_language():
    hi, _ = B.parse("purani 22K chain 6.2g se 22K ruby lotus pendant banao")
    en, _ = B.parse("Make an 18K rose gold lotus pendant with a ruby, 5 g")
    assert "purane 22K sone se" in B.describe(hi)
    assert "from 5 g" in B.describe(en) and "An 18K rose gold pendant" in B.describe(en)


# ---- questions policy -----------------------------------------------------------

def test_missing_ring_size_is_asked_not_assumed():
    r = B.analyse("22K ring of 6g")
    assert r.status == "needs_info" and r.topics == ["ring_size"]
    assert "17.3" not in r.reply


def test_missing_bangle_size_is_asked():
    r = B.analyse("22K plain bangle of 20 g")
    assert r.status == "needs_info" and r.topics == ["bangle_size"]
    assert "2-6" in r.reply


def test_missing_new_karat_is_asked_not_copied_from_old_gold():
    r = B.analyse("purana 8.4g 22K kangan hai, naya kada banana hai, size 2-6")
    assert r.status == "needs_info" and r.topics == ["karat"]


def test_missing_old_gold_karat_is_asked():
    r = B.analyse("18K ring from my old 10g gold, size 12")
    assert r.status == "needs_info" and r.topics == ["old_karat"]


def test_at_most_three_questions_in_one_reply():
    r = B.analyse("kuch sundar sa bana do")
    assert r.topics == ["piece", "target", "karat"]
    assert len(r.questions) == 3
    assert "(1)" in r.reply and "(3)" in r.reply


def test_only_blocking_fields_are_asked_metal_gets_a_stated_default():
    b, q = B.parse("22K ring of 6 g, size 12")
    assert q is None
    assert b.metal == "yellow"
    assert any("default" in a for a in b.assumptions)


def test_reference_piece_without_photo_asks_for_photo_or_weight():
    r = B.analyse("Make this catalogue ring about 20% lighter")
    assert r.status == "needs_info"
    assert r.topics[0] == "reference" and "photo" in r.reply and "weight" in r.reply


def test_reference_with_current_weight_becomes_target():
    b, q = B.parse("This 22K ring weighs 10 g, make it 20% lighter, size 12")
    assert q is None and b.target_weight_g == 8.0


# ---- ambiguous style ------------------------------------------------------------

@pytest.mark.parametrize("word", ["traditional", "modern", "simple"])
def test_ambiguous_style_gives_three_variants_without_a_question(word):
    b, q = B.parse(f"A {word} 22K bangle, size 2-8, 20 g")
    assert q is None and word in b.style
    specs = designer.propose(b, pricing.requested_ct(b), 3)
    assert len(specs) == 3 and len({s.name for s in specs}) == 3


# ---- LLM repair -----------------------------------------------------------------

class FakeLLM:
    def __init__(self, *answers):
        self.answers = list(answers)
        self.calls = []

    def __call__(self, system, user, *a, **kw):
        self.calls.append(user)
        return self.answers.pop(0) if self.answers else None


TEXT = "22K ring of 6 g, size 12"


def test_llm_bad_json_twice_falls_back_to_regex(monkeypatch):
    fake = FakeLLM({"piece_type": "necklace"}, ["not", "an", "object"])
    monkeypatch.setattr(B.llm, "complete_json", fake)
    b, q = B.parse(TEXT)
    assert len(fake.calls) == 2
    assert "failed validation" in fake.calls[1] and "piece_type" in fake.calls[1]
    assert q is None and b.piece_type == "ring" and b.ring_size == 12   # regex result


def test_llm_bad_then_good_json_is_repaired(monkeypatch):
    good = {"piece_type": "ring", "karat": 18, "target_weight_g": 6, "ring_size": 12, "style": ["knife"]}
    fake = FakeLLM({"piece_type": "ring", "karat": 99}, good)
    monkeypatch.setattr(B.llm, "complete_json", fake)
    b, q = B.parse(TEXT)
    assert len(fake.calls) == 2
    assert q is None and b.karat == 18 and b.style == ["knife"]   # repaired LLM, not regex (22)


def test_llm_good_json_first_time_is_used_without_repair(monkeypatch):
    fake = FakeLLM({"piece_type": "ring", "karat": 22, "target_weight_g": 6, "ring_size": 12})
    monkeypatch.setattr(B.llm, "complete_json", fake)
    b, q = B.parse(TEXT)
    assert len(fake.calls) == 1 and q is None and b.ring_inner_d_mm == 16.5


# ---- Brief contract ---------------------------------------------------------------

def test_brief_dumps_to_json():
    b, _ = B.parse(TEXT)
    assert json.loads(b.model_dump_json())["ring_size"] == 12
    assert isinstance(b, Brief)
