"""Phase 8.5: one reproduction per cleared docs/security/backlog.md item (no bpy)."""
import time

import pytest

from karigar.core import llm
from probe.server import BadBody, _parse_json


def test_n3_json_prescan_is_linear_on_escaped_quotes():
    body = b'{"a":"' + b'\\"' * 32768          # 64 KB of \" with no closing quote
    t = time.monotonic()
    with pytest.raises(BadBody) as e:
        _parse_json(body)
    assert e.value.code == "invalid_json" and time.monotonic() - t < 1.0
    assert _parse_json(b'{"a":"x\\"y","b":[1,2]}') == {"a": 'x"y', "b": [1, 2]}


def test_f10_deeply_nested_llm_json_falls_back():
    assert llm.extract_json("[" * 100000 + "]" * 100000) is None


from karigar.packs.jewellery import brief as B
from karigar.packs.jewellery.schema import Brief


def test_f12_deadline_is_not_a_budget():
    assert "budget_inr" not in B._regex_parse("22K ring 6g size 12 within 2 weeks")
    assert B._regex_parse("22K ring size 12 within 50000")["budget_inr"] == 50000


def test_f13_budget_has_a_ceiling():
    d, bad = B._regex_draft("22K ring size 12 budget 99999999999")
    assert d.budget_inr is None and "budget_inr" in bad


def test_f14_ambiguous_size_is_asked_and_string_sizes_convert():
    d, bad = B._regex_draft("22K ring 6g size 12.5")
    assert d.ring_inner_d_mm is None and d.ring_size is None and bad
    assert B._regex_parse("22K ring 6g size 17.3")["ring_inner_d_mm"] == 17.3
    from karigar.packs.jewellery import sizes
    b = Brief(piece_type="ring", karat=22, target_weight_g=6, ring_size="12")
    assert b.ring_inner_d_mm == sizes.ring_inner_d_mm(12)


def test_f15_signs_and_exponents_are_not_weights():
    assert "target_weight_g" not in B._regex_parse("22K ring -10 g size 12")
    assert "target_weight_g" not in B._regex_parse("22K ring 1e9 g size 12")
    assert B._regex_parse("22K ring 6.2g size 12")["target_weight_g"] == 6.2


def test_f16_stone_carat_after_gold_carat():
    d = B._regex_parse("22 carat ring with 0.5 ct diamond, size 12, 4g")
    assert d["gem_ct"] == 0.5 and d["karat"] == 22


def test_f11_huge_message_is_refused_before_parsing(monkeypatch):
    from karigar.core import registry
    import karigar.packs.jewellery  # noqa: F401
    called = []
    monkeypatch.setattr(B, "analyse", lambda *a, **k: called.append(1))
    i = registry.get("jewellery").intake("22K ring size 12 6g " + "x" * 5000)
    assert i.status == "needs_info" and i.topics == ["too_long"] and not called


def test_f17_devanagari_is_answered_in_hinglish():
    from karigar.core.lang import detect, HINGLISH
    assert detect("मुझे 22K अंगूठी चाहिए") == HINGLISH


def test_n5_probe_log_tail_is_capped(tmp_path, monkeypatch):
    from probe import server
    monkeypatch.setattr(server, "MAX_TAIL_BYTES", 10_000)
    log = server.RequestLog(tmp_path / "p.jsonl")
    for i in range(100):
        log.write({"i": i, "pad": "x" * 500})
    got = log.tail(500)
    assert 0 < len(got) < 30 and got[-1]["i"] == 99


@pytest.mark.parametrize("text,piece", [
    ("14K pendant, old 13.2g 14K bangle exchange", "pendant"),
    ("old 4.2g 18K bangle exchange 18K pendant banana hai", "pendant"),
    ("purani ring 5g 22K se 22K jhumka", "earring"),
    ("nani ka purana 18.4g 22K kangan hai, naya 22K beaded kada banana hai", "bangle"),
])
def test_sim_old_gold_piece_is_not_the_piece_to_make(text, piece):
    """Phase 8.5 sim cluster: the old piece named after 'old/purani' was read as the new piece."""
    assert B._regex_parse(text)["piece_type"] == piece
