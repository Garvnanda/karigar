"""Phase 2.5 scaffold without Blender: new piece types in the schema, brief intake
(Hinglish + English piece and family words, chain length, scope), the family registry
contract, designer routing and pricing for chain / coin / earring / nosepin.

Earrings, chains, nose pins and coins were out of scope until the user widened the
scope (decisions.md 2026-11-13 "Design catalogue"); these tests replace the old
out-of-scope cases for them."""
import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from karigar.core import llm
from karigar.core.lang import EN, HINGLISH
from karigar.packs.jewellery import brief as B
from karigar.packs.jewellery import designer, families, pricing
from karigar.packs.jewellery.schema import Brief, DesignSpec

ROOT = Path(__file__).resolve().parents[1]


# ------------------------------------------------------------ piece words
@pytest.mark.parametrize("text,piece", [
    ("22K gold chain, 18 inch, 12 g", "chain"),
    ("22K ki chain chahiye 20 inch 10g", "chain"),
    ("22K sikka banana hai 10g", "coin"),
    ("a 24K gold coin of 10 g in 22K", "coin"),
    ("22K jhumka 8g", "earring"),
    ("22K jhumki chahiye 6g", "earring"),
    ("18K diamond earrings 5 g", "earring"),
    ("22K kaan ki bali 4g", "earring"),
    ("22K bali chahiye 3g", "earring"),
    ("22K chandbali 12 g", "earring"),
    ("22K tops 3 g", "earring"),
    ("22K nath banana hai 2g", "nosepin"),
    ("a 22K nosepin, 1 g", "nosepin"),
    ("a 22K nose pin, 1 g", "nosepin"),
    ("22K laung 1g", "nosepin"),
    ("22K koka 1 g", "nosepin"),
    ("an 18K nose ring 1.5 g", "nosepin"),
])
def test_new_piece_words_map_to_new_piece_types(text, piece):
    r = B.analyse(text)
    assert r.status == "brief", (r.status, r.reply)
    assert r.brief.piece_type == piece


@pytest.mark.parametrize("text,family", [
    ("22K jhumka 8g", "earring_jhumka"),
    ("22K jhumki chahiye 6g", "earring_jhumka"),
    ("22K chandbali 12 g", "earring_chandbali"),
    ("22K kaan ki bali 4g", "earring_bali_hoop"),
    ("18K hoop earrings 4 g", "earring_bali_hoop"),
    ("22K rope chain 20 inch 12g", "chain_rope"),
    ("22K curb chain 22 inch 15g", "chain_curb"),
    ("22K kada size 2-6 25g", "bangle_temple_kada"),
    ("22K temple bangle size 2-6 25g", "bangle_temple_kada"),
    ("22K twisted rope bangle size 2-6 20g", "bangle_twisted_rope"),
    ("18K three stone ring size 12 4g", "ring_three_stone"),
    ("18K halo ring size 12 4g", "ring_halo_solitaire"),
    ("18K butterfly ring size 12 3g", "ring_butterfly"),
    ("18K halo pendant 3g", "pendant_heart_halo"),
    ("22K paisley pendant 4g", "pendant_paisley"),
    ("22K keri pendant 4g", "pendant_paisley"),
    ("22K mango pendant 4g", "pendant_paisley"),
    ("22K temple pendant 6g", "pendant_temple_lotus"),
    ("22K lotus pendant 6g", "pendant_temple_lotus"),
    ("22K lotus coin 10g", "coin_lotus_10g"),
])
def test_style_word_names_a_catalogue_family(text, family):
    r = B.analyse(text)
    assert r.status == "brief", (r.status, r.reply)
    assert r.brief.family == family


@pytest.mark.parametrize("text", [
    "22K beaded kada size 2-6 25g",        # beads asked for: not the temple kada
    "22K plain ring size 12 4g",
    "22K tops 3 g",
    "22K sikka banana hai 10g",
])
def test_no_family_word_leaves_family_unset(text):
    assert B.analyse(text).brief.family is None


def test_chain_without_length_asks_for_length():
    en = B.analyse("A 22K chain of 12 g please")
    assert en.status == "needs_info" and en.topics == ["chain_length"] and en.lang == EN
    assert "16, 18, 20, 22 or 24 inches" in en.reply
    hi = B.analyse("22K ki chain banana hai 12g")
    assert hi.topics == ["chain_length"] and hi.lang == HINGLISH
    assert hi.reply.startswith("Chain kitni lambi chahiye")


@pytest.mark.parametrize("text,inches", [
    ("22K chain 16 inch 8g", 16), ('22K chain 18" 10g', 18), ("22K chain 20 inches 10 g", 20),
    ("22K chain 22in 12g", 22), ("22K chain 24-inch 14g", 24),
])
def test_chain_length_is_read_in_inches(text, inches):
    b = B.analyse(text).brief
    assert b.piece_type == "chain" and b.length_in == inches and b.karat == 22


def test_chain_length_not_in_the_stocked_lengths_is_asked_again():
    r = B.analyse("22K chain 19 inch 10g")
    assert r.status == "needs_info" and "chain_length" in r.topics


@pytest.mark.parametrize("text", ["jhumka 8g", "nosepin 1 g", "gold coin 10 g"])
def test_earring_nosepin_coin_ask_nothing_beyond_karat(text):
    r = B.analyse(text)
    assert r.status == "needs_info" and r.topics == ["karat"]


def test_old_chain_is_still_the_gold_source_for_another_piece():
    r = B.analyse("purani 22K chain 8g se 22K jhumka banana hai")
    assert r.status == "brief" and r.brief.piece_type == "earring"
    assert r.brief.old_gold.weight_g == 8 and r.brief.family == "earring_jhumka"


def test_question_for_piece_lists_the_new_pieces():
    r = B.analyse("22K gold, 10 g")
    assert r.topics[0] == "piece"
    assert "chain, coin, earrings or a nose pin" in r.reply


def test_family_comes_from_code_even_on_the_llm_path(monkeypatch):
    """An LLM-proposed family is dropped (extra keys ignored); the text decides it."""
    monkeypatch.setattr(llm, "complete_json", lambda system, user: {
        "piece_type": "earring", "karat": 22, "target_weight_g": 8, "family": "ring_butterfly"})
    r = B.analyse("22K chandbali 8g")
    assert r.status == "brief" and r.brief.family == "earring_chandbali"


def test_out_of_scope_still_covers_necklaces_mangalsutra_anklets_tikka():
    for text in ("22K necklace 20g", "22K mangalsutra 10g", "22K payal 15g", "22K maang tikka 6g"):
        assert B.analyse(text).status == "out_of_scope", text


# ------------------------------------------------------------ schema
@pytest.mark.parametrize("piece", ["chain", "coin", "earring", "nosepin"])
def test_new_piece_types_validate(piece):
    kw = {"length_in": 18} if piece == "chain" else {}
    s = DesignSpec(name="x", piece_type=piece, **kw)
    assert s.family == "" and s.pair is True and s.gauge_mm == 0.8 and s.stamp is True
    assert Brief(piece_type=piece, karat=22, target_weight_g=5).piece_type == piece


def test_chain_spec_needs_a_stocked_length():
    with pytest.raises(ValidationError, match="length_in"):
        DesignSpec(name="x", piece_type="chain")
    with pytest.raises(ValidationError):
        DesignSpec(name="x", piece_type="chain", length_in=19)


def test_family_must_be_in_the_catalogue_or_registered():
    assert DesignSpec(name="x", piece_type="earring", family="earring_jhumka").family == "earring_jhumka"
    with pytest.raises(ValidationError, match="unknown design family"):
        DesignSpec(name="x", piece_type="ring", family="tanishq_copy")
    with pytest.raises(ValidationError, match="unknown design family"):
        Brief(piece_type="ring", family="anything")


@pytest.mark.parametrize("params", [{"Bad-Key": 1.0}, {"x": float("inf")}, {"x": 1e6},
                                    {f"k{i}": 1.0 for i in range(25)}])
def test_family_params_are_bounded_named_numbers(params):
    with pytest.raises(ValidationError):
        DesignSpec(name="x", piece_type="ring", params=params)


def test_existing_specs_keep_their_defaults():
    s = DesignSpec(name="band", piece_type="ring")
    assert s.family == "" and s.params == {} and s.length_in is None


# ------------------------------------------------------------ registry
def _builder(spec, s):
    raise AssertionError("not built in these tests")


@pytest.fixture
def scratch_registry(monkeypatch):
    monkeypatch.setattr(families, "FAMILIES", {})
    return families.FAMILIES


def test_register_validates_and_exposes_variants(scratch_registry):
    fam = families.register("scratch_ring", "ring", _builder,
                            {"width_mm": 3.0, "petals": 6, "params": {"twist": 2.0}},
                            {"width_mm": (0.8, 1.0, 1.3), "petals": (0.84, 1.0, 1.5),
                             "params.twist": (0.5, 1.0, 2.0)})
    assert families.get("scratch_ring") is fam and families.for_piece("ring") == [fam]
    light, stat = fam.variant_fields("lighter"), fam.variant_fields("statement")
    assert light["width_mm"] == pytest.approx(2.4) and stat["petals"] == 9 and light["petals"] == 5
    assert light["params"]["twist"] == 1.0 and fam.default_spec["params"]["twist"] == 2.0
    assert fam.title == "Ring"


@pytest.mark.parametrize("kwargs,match", [
    (dict(piece_type="chain", default_spec={"length_in": 18}, variant_axes={}), "scale_bounds"),
    (dict(piece_type="ring", default_spec={}, variant_axes={"width_mm": (1, 1)}), "3 positive"),
    (dict(piece_type="ring", default_spec={}, variant_axes={"profile": (1, 1, 1)}), "numeric"),
    (dict(piece_type="ring", default_spec={}, variant_axes={"params.k": (1, 1, 1)}), "params"),
    (dict(piece_type="ring", default_spec={"width_mm": 3.0}, variant_axes={"width_mm": (1, 1, 9)}),
     "does not validate"),
    (dict(piece_type="earring", default_spec={}, variant_axes={}, scale_bounds=(0.8, 1.2),
          builder="nope"), "callable"),
])
def test_register_rejects_bad_families(scratch_registry, kwargs, match):
    kwargs = {"builder": _builder, **kwargs}
    with pytest.raises(ValueError, match=match):
        families.register("scratch_bad", **kwargs)
    assert "scratch_bad" not in families.FAMILIES


def test_register_rejects_a_duplicate_name(scratch_registry):
    families.register("scratch_dup", "earring", _builder, {}, {}, scale_bounds=(0.8, 1.2))
    with pytest.raises(ValueError, match="already registered"):
        families.register("scratch_dup", "earring", _builder, {}, {}, scale_bounds=(0.8, 1.2))


def test_every_module_in_families_is_imported():
    for mod in ("rings", "pendants", "coin", "bangles", "chains", "earrings", "nose"):
        assert f"karigar.packs.jewellery.families.{mod}" in sys.modules, mod


def test_registry_brief_and_designer_import_without_blender():
    code = ("import sys; import karigar.packs.jewellery.families, karigar.packs.jewellery.brief, "
            "karigar.packs.jewellery.designer, karigar.packs.jewellery.pricing; "
            "assert 'bpy' not in sys.modules, 'bpy imported'")
    subprocess.run([sys.executable, "-c", code], cwd=ROOT, check=True)


# ------------------------------------------------------------ designer routing
def test_designer_refuses_a_new_piece_with_no_registered_family(scratch_registry):
    with pytest.raises(designer.NoFamily, match="chain"):
        designer.propose(Brief(piece_type="chain", karat=22, length_in=18), 0.0)


def test_designer_uses_the_named_family_and_the_brief_owns_karat_metal_size_stone(scratch_registry):
    families.register("scratch_ring", "ring", _builder,
                      {"width_mm": 3.0, "gem": "diamond", "gem_d_mm": 3.0},
                      {"width_mm": (0.8, 1.0, 1.3)})
    b = Brief(piece_type="ring", karat=18, metal="rose", ring_inner_d_mm=16.5, family="scratch_ring",
              gem="ruby", gem_ct=0.3)
    specs = designer.propose(b, pricing.requested_ct(b), 3, weigh=_builder)
    assert [s.width_mm for s in specs] == pytest.approx([2.4, 3.0, 3.9])
    for s in specs:
        assert (s.family, s.karat, s.metal, s.inner_d_mm, s.gem) == ("scratch_ring", 18, "rose", 16.5, "ruby")
        assert s.gem_d_mm == pytest.approx(designer._gem_d(b, 0.3))


def test_designer_keeps_original_designs_when_no_family_is_named(scratch_registry):
    families.register("scratch_ring", "ring", _builder, {}, {"width_mm": (0.8, 1.0, 1.3)})
    specs = designer.propose(Brief(piece_type="ring", karat=22), 0.0, 3)
    assert all(s.family == "" for s in specs)


# ------------------------------------------------------------ pricing
@pytest.mark.parametrize("piece", ["chain", "coin", "earring", "nosepin"])
def test_plan_and_quote_accept_new_piece_types(piece):
    kw = {"length_in": 18} if piece == "chain" else {}
    b = Brief(piece_type=piece, karat=22, target_weight_g=0.5, **kw)
    p = pricing.plan(b, 3.0)
    assert p.ok        # no sourced minimum weight for these pieces yet: none enforced
    spec = DesignSpec(name="x", piece_type=piece, **kw)
    q = pricing.quote(spec, p.target_value, b, p)
    assert q["making_charges"] == pytest.approx(q["gold_value"] * 0.035, abs=1)   # 3.5%, decisions.md "Shop numbers"
    assert pricing.requested_ct(b) == 0.0


def test_new_piece_budget_refusal_does_not_print_a_zero_gram_minimum():
    b = Brief(piece_type="earring", karat=22, budget_inr=1000, gem="ruby", gem_ct=1.0)
    p = pricing.plan(b, 3.0)
    assert not p.ok and " 0.0 g " not in p.explanation and " 0 g " not in p.explanation
