"""Phase 6: edit text → EditRequest → spec patch (no Blender).

Numbers come from the customer's text or code steps (edits.STEP), never from a model.
"""
import pytest

from karigar.core import llm
from karigar.packs.jewellery import edits
from karigar.packs.jewellery.edits import EditRefused, EditRequest
from karigar.packs.jewellery.schema import DesignSpec


def _one(text):
    r = edits.parse(text)
    assert r is not None, text
    return r


@pytest.mark.parametrize("text", ["make it 0.5 mm thinner", "0.5mm patla kar do",
                                  "thinner by 0.5 mm please", "isko 0.5 mm patli karo"])
def test_thinner_by_mm(text):
    r = _one(text)
    assert r.weight is None and r.pick is None
    assert [(c.field, c.op, c.amount) for c in r.changes] == [("thickness_mm", "add", -0.5)]


@pytest.mark.parametrize("text,pick", [
    ("Middle one, but make the flower slightly bigger", "middle"),
    ("beech wala, phool thoda bada karo", "middle"),
    ("pehla wala, phool thoda bada", "first"),
    ("teesra design, flower a bit bigger", "last"),
])
def test_pick_and_flower_slightly_bigger(text, pick):
    r = _one(text)
    assert r.pick == pick
    assert [(c.field, c.op) for c in r.changes] == [("flower", "mul")]
    assert r.changes[0].amount == pytest.approx(1 + edits.STEP["slight"])


@pytest.mark.parametrize("text,op,amount", [
    ("1 g lighter", "add", -1.0), ("make it 1.5 gram halka", "add", -1.5),
    ("heavier by 2 g", "add", 2.0), ("thoda halka karo", "mul", 1 - edits.STEP["slight"]),
    ("make it 10% heavier", "mul", 1.10), ("bahut bhaari karo", "mul", 1 + edits.STEP["large"]),
])
def test_weight_edits(text, op, amount):
    r = _one(text)
    assert r.changes == [] and r.weight.op == op and r.weight.amount == pytest.approx(amount)


@pytest.mark.parametrize("text,field,op,amount", [
    ("wider by 0.3 mm", "width_mm", "add", 0.3),
    ("thoda chauda karo", "width_mm", "mul", 1.10),
    ("narrower", "width_mm", "mul", 0.90),
    ("bigger stone", "gem_d_mm", "mul", 1.10),
    ("nag chhota karo", "gem_d_mm", "mul", 0.90),
    ("more petals", "petals", "add", 1),
    ("kam pankhudi", "petals", "add", -1),
    ("make it 0.2 mm thicker", "thickness_mm", "add", 0.2),
])
def test_dimension_edits(text, field, op, amount):
    r = _one(text)
    assert [(c.field, c.op) for c in r.changes] == [(field, op)]
    assert r.changes[0].amount == pytest.approx(amount)


def test_pick_alone_and_unclear_text():
    r = _one("I like the middle one")
    assert r.pick == "middle" and r.empty
    assert edits.parse("hello, how are you") is None
    assert edits.parse("make it 0.5 g thinner") is None      # the unit doesn't fit the change: ask


def test_pick_index():
    assert [edits.pick_index(p, 3) for p in ("first", "middle", "last")] == [0, 1, 2]


# ------------------------------------------------------------------ patch

FLORAL = DesignSpec(name="Phool Ring (balanced)", piece_type="ring", motif="floral", petals=6,
                    size_mm=10.5, width_mm=3.5, thickness_mm=2.0, inner_d_mm=16.5)
PLAIN = DesignSpec(name="Comfort Band", piece_type="ring", width_mm=3.5, thickness_mm=1.8)


def test_thinner_patch_changes_only_thickness_by_finished_mm():
    p = edits.apply(PLAIN, 1.2, _one("make it 0.5 mm thinner"))
    d = edits.diff(PLAIN.model_dump(), p.spec.model_dump())
    assert list(d) == ["thickness_mm"]
    assert p.spec.thickness_mm * 1.2 == pytest.approx(1.8 * 1.2 - 0.5)   # finished, at the old scale
    assert p.locked == {"thickness_mm": pytest.approx(1.8 * 1.2 - 0.5)}
    assert p.shown["thickness_mm"] == (pytest.approx(2.16), pytest.approx(1.66))


def test_flower_patch_resolves_to_size_mm_and_locks_it():
    p = edits.apply(FLORAL, 0.9, _one("middle one, flower slightly bigger"))
    assert list(edits.diff(FLORAL.model_dump(), p.spec.model_dump())) == ["size_mm"]
    assert p.locked["size_mm"] == pytest.approx(10.5 * 0.9 * 1.10)


def test_at_scale_keeps_locked_finished_value():
    p = edits.apply(PLAIN, 1.2, _one("make it 0.5 mm thinner"))
    for s in (0.9, 1.0, 1.4):
        assert edits.at_scale(p.spec, s, p.locked).thickness_mm * s == pytest.approx(1.66)


def test_petals_patch_is_an_integer_and_not_locked():
    p = edits.apply(FLORAL, 0.9, _one("more petals"))
    assert p.spec.petals == 7 and p.locked == {}


@pytest.mark.parametrize("spec,text,kind", [
    (PLAIN, "flower bigger", "no_flower"),
    (PLAIN, "bigger stone", "no_stone"),
    (PLAIN, "make it bigger", "ring_size"),
    (PLAIN, "make it 1.5 mm thinner", "out_of_range"),   # 0.6 mm minimum spec thickness
    (FLORAL, "make it 20 mm wider", "out_of_range"),
])
def test_refused_edits(spec, text, kind):
    with pytest.raises(EditRefused) as e:
        edits.apply(spec, 1.0, _one(text))
    assert e.value.kind == kind
    assert edits.refused_text(e.value, "en") and edits.refused_text(e.value, "hinglish")


def test_only_whitelisted_fields_can_be_patched():
    with pytest.raises(ValueError):
        edits.Change(field="karat", op="add", amount=4)
    with pytest.raises(ValueError):
        edits.Change(field="inner_d_mm", op="add", amount=1)
    for f in edits.EDITABLE:
        edits.Change(field=f, op="mul", amount=1.1)


# ------------------------------------------------------------------ optional LLM path

def _llm(monkeypatch, reply):
    calls = []

    def fake(system, user, max_tokens=2000, runner=None):
        calls.append(user)
        return reply
    monkeypatch.setattr(llm, "complete_json", fake)
    return calls


def test_rules_first_llm_not_called_when_rules_understand(monkeypatch):
    calls = _llm(monkeypatch, {"changes": []})
    assert edits.understand("make it 0.5 mm thinner").changes[0].field == "thickness_mm"
    assert calls == []


def test_llm_maps_words_to_allowed_fields(monkeypatch):
    _llm(monkeypatch, {"pick": "last", "changes": [{"target": "flower", "direction": "up", "step": "slight"}]})
    r = edits.understand("woh aakhri wala, uska gulab thoda khila hua chahiye")
    assert r.source == "llm" and r.pick == "last"
    assert r.changes[0].field == "flower" and r.changes[0].amount == pytest.approx(1.10)


def test_llm_number_not_in_text_is_rejected(monkeypatch):
    _llm(monkeypatch, {"changes": [{"target": "thickness", "direction": "down", "amount": 0.7, "unit": "mm"}]})
    assert edits.understand("uski motai kam kar do na") is None


def test_llm_number_written_by_customer_is_kept(monkeypatch):
    _llm(monkeypatch, {"changes": [{"target": "thickness", "direction": "down", "amount": 0.3, "unit": "mm"}]})
    r = edits.understand("motai 0.3 mm kam kar do")
    assert (r.changes[0].field, r.changes[0].op, r.changes[0].amount) == ("thickness_mm", "add", -0.3)


@pytest.mark.parametrize("reply", [
    {"changes": [{"target": "karat", "direction": "up"}]},              # not an allowed target
    {"changes": [{"target": "width", "direction": "up", "price": 5}]},  # extra field
    {"pick": "fourth"}, ["not", "an", "object"], None,
])
def test_llm_invalid_output_falls_back_to_none(monkeypatch, reply):
    _llm(monkeypatch, reply)
    assert edits.understand("kuch alag sa kar do") is None


def test_edit_request_is_pydantic():
    assert EditRequest().empty
