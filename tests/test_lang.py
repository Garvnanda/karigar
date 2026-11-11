import pytest

from karigar.core.lang import EN, HINGLISH, detect


@pytest.mark.parametrize("text", [
    "Nani ka purana 18.4g 22K kangan hai, naya beaded kada banana hai",
    "aaj ka rate 22K 14730",
    "kuch sundar sa bana do",
    "mujhe ek ring chahiye",
    "purani 22K chain 6.2g se ruby lotus pendant banao",
])
def test_hinglish(text):
    assert detect(text) == HINGLISH


@pytest.mark.parametrize("text", [
    "18K white gold solitaire with 0.5 ct diamond, budget 1.2 lakh, size 6",
    "today's rate 22k 14,730 and 18k 12060",
    "Can you do a 22K ring of 4 g?",
    "1 ct diamond ring under 10k",
    "Make this catalogue ring about 20% lighter",
])
def test_english(text):
    assert detect(text) == EN
