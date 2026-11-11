import pytest

from karigar.core import gold as G


def test_exchange_target_matches_readme_example():
    t = G.target_from_exchange(18.4, 22, 22, casting_loss_pct=3.0, melt_loss_pct=2.0)
    assert t.fine_g == pytest.approx(16.52, abs=0.005)
    assert t.finished_gross_g == pytest.approx(18.03, abs=0.005)
    assert t.design_gross_g == pytest.approx(18.59, abs=0.005)


def test_exchange_notes_flag_assumed_purity_and_melt_loss():
    t = G.target_from_exchange(10, 22, 22, 3.0)
    assert any("Assumed old purity" in n for n in t.notes)
    assert any("Melting loss" in n for n in t.notes)


def test_tested_purity_overrides_karat_claim():
    t = G.target_from_exchange(10, 22, 22, 0.0, melt_loss_pct=0.0, tested_purity=0.80)
    assert t.fine_g == pytest.approx(8.0)
    assert not any("Assumed old purity" in n for n in t.notes)


def test_target_from_gross_adds_casting_loss():
    t = G.target_from_gross(9.7, 22, 3.0)
    assert t.design_gross_g == pytest.approx(10.0)
    assert t.fine_g == pytest.approx(9.7 * 0.916)


def test_grams_mm3_round_trip():
    for k in (22, 18, 14):
        assert G.mm3_to_grams(G.grams_to_mm3(7.5, k), k) == pytest.approx(7.5)


def test_unsupported_karat_rejected():
    with pytest.raises(ValueError):
        G.purity(10)
