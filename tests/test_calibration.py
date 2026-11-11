import pytest

from karigar.core.calibration import WINDOW, CalibrationStore


def test_default_loss_without_records(tmp_path):
    s = CalibrationStore(tmp_path / "c.json", default_loss_pct=3.0)
    assert s.loss_pct("w1") == 3.0
    assert "no records" in s.summary("w1")


def test_loss_is_mean_of_records_and_persists(tmp_path):
    p = tmp_path / "c.json"
    s = CalibrationStore(p)
    s.record("w1", 20.0, 19.0)   # 5%
    loss = s.record("w1", 10.0, 9.9)  # 1%
    assert loss == pytest.approx(3.0)
    assert CalibrationStore(p).loss_pct("w1") == pytest.approx(3.0)


def test_workshops_are_separate(tmp_path):
    s = CalibrationStore(tmp_path / "c.json", default_loss_pct=3.0)
    s.record("w1", 20.0, 19.0)
    assert s.loss_pct("w2") == 3.0


def test_only_recent_window_used(tmp_path):
    s = CalibrationStore(tmp_path / "c.json")
    s.record("w1", 10.0, 5.0)  # 50% outlier, pushed out of the window
    for _ in range(WINDOW):
        s.record("w1", 10.0, 9.8)
    assert s.loss_pct("w1") == pytest.approx(2.0)


@pytest.mark.parametrize("designed,actual", [(0, 5), (5, 0), (-1, 5)])
def test_rejects_non_positive_weights(tmp_path, designed, actual):
    s = CalibrationStore(tmp_path / "c.json")
    with pytest.raises(ValueError):
        s.record("w1", designed, actual)
