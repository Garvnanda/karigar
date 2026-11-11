"""Phase 2: the designer proposes lighter / balanced / statement variants whose
natural gold weights (at scale 1.0, before the solver) differ by >= 15% from
one to the next, for every piece type, from the fallback and from the LLM path.
The customer's size always comes from the brief, never from the model."""
import pytest

from karigar.packs.jewellery import brief as B, designer, pricing
from karigar.packs.jewellery.schema import Brief, DesignSpec

SPREAD = 1.15
LABELS = ("lighter", "balanced", "statement")
HERO_A = ("Purani 8.4g 22K chain exchange karni hai, uske badle 22K ladies ring chahiye, "
          "size 12, chhota floral design")

BRIEFS = {
    "ring_plain": Brief(piece_type="ring", karat=22, ring_inner_d_mm=17.3),
    "ring_gem": Brief(piece_type="ring", karat=18, metal="white", gem="diamond", gem_ct=0.5,
                      ring_inner_d_mm=16.5),
    "ring_floral": Brief(piece_type="ring", karat=22, ring_inner_d_mm=16.5, style=["floral"]),
    "ring_floral_gem": Brief(piece_type="ring", karat=22, ring_inner_d_mm=18.1, style=["flower"],
                             gem="ruby", gem_ct=0.2),
    "bangle": Brief(piece_type="bangle", karat=22, bangle_inner_d_mm=57.2),
    "pendant": Brief(piece_type="pendant", karat=22, gem="ruby", gem_ct=0.3),
    "pendant_plain": Brief(piece_type="pendant", karat=18, metal="rose"),
}


@pytest.fixture(scope="module")
def weigh():
    from karigar.packs.jewellery import geometry
    return lambda spec: geometry.gold_volume(spec, 1.0)


def _inner(brief):
    return brief.ring_inner_d_mm if brief.piece_type == "ring" else brief.bangle_inner_d_mm


def _assert_spread(specs, weigh):
    w = [weigh(s) for s in specs]
    for a, b in zip(w, w[1:]):
        assert b >= SPREAD * a, f"{[s.name for s in specs]}: weights {w}"
    return w


def _assert_labels(specs):
    assert len(specs) == 3
    for s, label in zip(specs, LABELS):
        assert s.name.lower().endswith(f"({label})"), s.name


@pytest.mark.parametrize("key", list(BRIEFS))
def test_fallback_variants_are_lighter_balanced_statement(key, weigh):
    b = BRIEFS[key]
    specs = designer.propose(b, pricing.requested_ct(b), 3)
    _assert_labels(specs)
    _assert_spread(specs, weigh)
    assert len({s.name for s in specs}) == 3
    for s in specs:
        assert s.piece_type == b.piece_type and s.karat == b.karat and s.metal == b.metal
        if b.piece_type != "pendant":
            assert s.inner_d_mm == _inner(b)
        if b.gem != "none":
            assert s.gem == b.gem and s.gem_d_mm > 0


def test_floral_style_gives_floral_rings():
    for key in ("ring_floral", "ring_floral_gem"):
        b = BRIEFS[key]
        specs = designer.propose(b, pricing.requested_ct(b), 3)
        assert all(s.motif == "floral" for s in specs)
    plain = designer.propose(BRIEFS["ring_plain"], 0.0, 3)
    assert all(s.motif == "plain" for s in plain)


def test_hero_a_floral_ring_solves_near_scale_one(tmp_path):
    from karigar.core.calibration import CalibrationStore
    from karigar.packs.jewellery import JewelleryPack
    b, q = B.parse(HERO_A)
    assert q is None and b.ring_inner_d_mm == 16.5 and "floral" in b.style
    plan = pricing.plan(b, CalibrationStore(tmp_path / "c.json").loss_pct(None))
    assert plan.ok
    specs = designer.propose(b, pricing.requested_ct(b), 3)
    assert any(s.motif == "floral" for s in specs)
    pack = JewelleryPack()
    for s in specs:
        r = pack.solve(s, plan)
        assert r.ok, s.name
        assert 0.85 <= r.scale <= 1.2, f"{s.name}: scale {r.scale:.3f}"
        assert s.size_mm * r.scale < 12.0 or s.name.endswith("(statement)")


# ---- LLM path ----------------------------------------------------------------------

class FakeLLM:
    def __init__(self, answer):
        self.answer = answer

    def __call__(self, system, user, *a, **kw):
        return [dict(x) for x in self.answer] if isinstance(self.answer, list) else self.answer


def _band(name, w, t, **kw):
    return {"name": name, "profile": "comfort", "width_mm": w, "thickness_mm": t, **kw}


def test_llm_variants_with_enough_spread_are_kept(monkeypatch, weigh):
    b = BRIEFS["ring_plain"]
    monkeypatch.setattr(designer.llm, "complete_json", FakeLLM(
        [_band("Heavy", 5.0, 2.4), _band("Slim", 2.2, 1.5), _band("Middle", 3.2, 1.9)]))
    specs = designer.propose(b, 0.0, 3, weigh=weigh)
    _assert_labels(specs)
    _assert_spread(specs, weigh)
    assert [s.name.split(" (")[0] for s in specs] == ["Slim", "Middle", "Heavy"]


def test_llm_variants_too_alike_are_topped_up_from_fallback(monkeypatch, weigh):
    b = BRIEFS["ring_plain"]
    monkeypatch.setattr(designer.llm, "complete_json", FakeLLM(
        [_band("A", 3.0, 1.8), _band("B", 3.05, 1.8), _band("C", 3.1, 1.8)]))
    specs = designer.propose(b, 0.0, 3, weigh=weigh)
    _assert_labels(specs)
    _assert_spread(specs, weigh)
    assert any(s.name.split(" (")[0] in "ABC" for s in specs)   # the LLM's idea survives


def test_llm_never_sets_the_customer_size(monkeypatch, weigh):
    b = BRIEFS["ring_plain"].model_copy(update={"ring_inner_d_mm": 19.4})
    monkeypatch.setattr(designer.llm, "complete_json", FakeLLM(
        [_band("NoSize", 2.2, 1.5), _band("WrongSize", 3.2, 1.9, inner_d_mm=15.0),
         _band("BigSize", 5.0, 2.4, inner_d_mm=24.0)]))
    specs = designer.propose(b, 0.0, 3, weigh=weigh)
    assert {s.name.split(" (")[0] for s in specs} == {"NoSize", "WrongSize", "BigSize"}
    assert all(s.inner_d_mm == 19.4 for s in specs)


def test_llm_bangle_size_comes_from_brief(monkeypatch, weigh):
    b = BRIEFS["bangle"]
    monkeypatch.setattr(designer.llm, "complete_json", FakeLLM(
        [{"name": "X", "width_mm": 4.0, "thickness_mm": 2.0, "inner_d_mm": 70.0}]))
    specs = designer.propose(b, 0.0, 3, weigh=weigh)
    assert all(s.inner_d_mm == 57.2 for s in specs)


def test_llm_motif_mismatch_is_dropped_and_topped_up(monkeypatch, weigh):
    b = BRIEFS["bangle"]
    monkeypatch.setattr(designer.llm, "complete_json", FakeLLM(
        [{"name": "Phool Kada", "motif": "floral", "width_mm": 5.0, "thickness_mm": 2.5}]))
    specs = designer.propose(b, 0.0, 3, weigh=weigh)
    _assert_labels(specs)
    _assert_spread(specs, weigh)
    assert all(s.motif != "floral" for s in specs)


def test_llm_garbage_falls_back(monkeypatch):
    b = BRIEFS["pendant"]
    monkeypatch.setattr(designer.llm, "complete_json", FakeLLM({"not": "a list"}))
    specs = designer.propose(b, pricing.requested_ct(b), 3, weigh=lambda s: pytest.fail("no weighing"))
    _assert_labels(specs)


# ---- piece / motif validation ------------------------------------------------------

@pytest.mark.parametrize("piece,motif,ok", [
    ("ring", "plain", True), ("ring", "floral", True), ("ring", "beaded", False),
    ("bangle", "plain", True), ("bangle", "beaded", True), ("bangle", "floral", False),
    ("pendant", "plain", True), ("pendant", "floral", False), ("pendant", "beaded", False),
])
def test_motif_must_fit_the_piece(piece, motif, ok):
    if ok:
        assert DesignSpec(name="x", piece_type=piece, motif=motif).motif == motif
    else:
        with pytest.raises(ValueError, match="motif"):
            DesignSpec(name="x", piece_type=piece, motif=motif)
