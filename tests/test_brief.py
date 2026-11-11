from karigar.packs.jewellery import brief as B


def test_unclear_request_asks_follow_up():
    b, q = B.parse("kuch sundar sa bana do")
    assert b is None and q


def test_piece_without_target_asks_for_gold_or_budget():
    b, q = B.parse("ek ring banana hai")
    assert b is None and "budget" in q


def test_hinglish_old_gold_exchange():
    b, q = B.parse("Nani ka purana 18.4g 22K kangan hai, naya beaded kada banana hai")
    assert q is None
    assert b.piece_type == "bangle"
    assert b.old_gold.weight_g == 18.4 and b.old_gold.karat == 22
    assert "beaded" in b.style


def test_budget_in_lakh_and_ring_size():
    b, q = B.parse("18K white gold solitaire with 0.5 ct diamond, budget 1.2 lakh, size 6")
    assert q is None
    assert b.karat == 18 and b.metal == "white"
    assert b.gem == "diamond" and b.gem_ct == 0.5
    assert b.budget_inr == 120000
    assert b.ring_inner_d_mm == 16.5


def test_missing_ring_size_is_recorded_as_assumption():
    b, _ = B.parse("22K ring of 6g")
    assert any("Ring size assumed" in a for a in b.assumptions)
