"""Phase 5 rate job: MCX page → +₹5,000 → GoldRateStore. Never touches the network."""
import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from karigar.packs.jewellery import rates, ratejob

FIXTURE = (Path(__file__).parent / "data" / "mcx_et_gold.html").read_text(encoding="utf-8")
NOW = datetime(2026, 11, 13, 18, 0).astimezone()


def _rules():
    return rates.rate_card()["gold_rate"]


def _fake(html):
    calls = []

    def fetcher(url):
        calls.append(url)
        return html
    fetcher.calls = calls
    return fetcher


def test_parser_reads_the_mcx_price_per_10g_from_the_saved_page():
    q = ratejob.parse_et_mcx(FIXTURE)
    assert q.per_10g == 136607.0                 # not the breadcrumb 999 or the NCDEX block
    assert "10 GRMS" in q.unit and q.quoted_at == "05.36PM IST | 13 Nov, 2026"


def test_rates_from_mcx_adds_5000_per_10g_and_scales_by_karat():
    r = ratejob.rates_from_mcx(136607.0, _rules())
    assert r[24] == pytest.approx(14160.7)       # (1,36,607 + 5,000) / 10
    assert r[22] == pytest.approx(round(14160.7 * 0.916, 2))
    assert r[18] == pytest.approx(round(14160.7 * 0.75, 2))
    assert r[14] == pytest.approx(round(14160.7 * 0.585, 2))


def test_refresh_saves_all_karats_with_timestamp_and_source(tmp_path):
    store = rates.GoldRateStore(tmp_path / "r.json")
    f = _fake(FIXTURE)
    res = ratejob.refresh(fetcher=f, store=store, now=NOW)
    assert res.ok and f.calls == [_rules()["mcx_url"]]
    data = json.loads((tmp_path / "r.json").read_text())
    assert set(data) == {"24", "22", "18", "14"}
    assert data["24"]["rate_per_g"] == pytest.approx(14160.7)
    assert data["24"]["set_at"] == NOW.isoformat(timespec="seconds")
    assert data["24"]["source"].startswith("mcx-job: MCX 136607/10g + 5000")
    # RateSource accepts what the job wrote, and quotes it with that timestamp.
    g = rates.RateSource(store, clock=lambda: NOW + timedelta(hours=1)).get(22)
    assert g.per_g == data["22"]["rate_per_g"] and g.set_at == data["22"]["set_at"]


@pytest.mark.parametrize("html,why", [
    ("<html><body>maintenance</body></html>", "no MCX gold price"),
    (FIXTURE.replace("Per&nbsp;10 GRMS", "Per&nbsp;1 KG"), "not 'per 10 grams'"),
    (FIXTURE.replace(">136607.0<", ">--<"), "not a number"),
    (FIXTURE.replace(">136607.0<", ">1e308<"), "not a number"),
    (FIXTURE.replace(">136607.0<", ">13660<"), "outside the sane range"),      # misread / per-g figure
    (FIXTURE.replace(">136607.0<", ">13660700.0<"), "outside the sane range"),  # per-kg figure
])
def test_bad_page_saves_nothing_and_keeps_the_last_rate(tmp_path, html, why):
    store = rates.GoldRateStore(tmp_path / "r.json")
    old = datetime(2026, 11, 13, 6, 0).astimezone()
    store.set({22: 12900.0}, now=old, source="mcx-job: earlier")
    before = (tmp_path / "r.json").read_text()
    res = ratejob.refresh(fetcher=_fake(html), store=store, now=NOW)
    assert not res.ok and why in res.message
    assert "Last rate kept: 22K ₹12900/g set 2026-11-13T06:00:00" in res.message
    assert (tmp_path / "r.json").read_text() == before


def test_failed_fetch_keeps_the_last_rate_and_staleness_still_applies(tmp_path):
    store = rates.GoldRateStore(tmp_path / "r.json")
    set_at = datetime(2026, 11, 12, 6, 0).astimezone()
    store.set({22: 12900.0}, now=set_at, source="mcx-job: earlier")

    def down(url):
        raise ratejob.RateJobError("fetch failed: URLError: offline")
    res = ratejob.refresh(fetcher=down, store=store, now=NOW)
    assert not res.ok and "offline" in res.message and res.kept["22"]["rate_per_g"] == 12900.0
    src = rates.RateSource(store, clock=lambda: set_at + timedelta(hours=25))
    assert src.problem([22]).kind == "stale"


def test_fetch_refuses_plain_http_without_a_network_call():
    with pytest.raises(ratejob.RateJobError, match="non-https"):
        ratejob.fetch("http://example.invalid/gold")


def test_run_every_loops_on_the_interval(tmp_path):
    store = rates.GoldRateStore(tmp_path / "r.json")
    slept, logs = [], []
    ratejob.run_every(6, runs=2, sleep=slept.append, log=logs.append,
                      fetcher=_fake(FIXTURE), store=store, now=NOW)
    assert slept == [6 * 3600] and len(logs) == 2 and logs[0].startswith("Rate updated")


def test_cli_rates_refresh_and_show(tmp_path, monkeypatch, capsys):
    import run
    monkeypatch.setattr(rates, "RATES_FILE", tmp_path / "r.json")
    monkeypatch.setattr(ratejob, "fetch", _fake(FIXTURE))
    # refresh's default fetcher was bound at definition time; route through the patched one.
    real = ratejob.refresh
    monkeypatch.setattr(ratejob, "refresh", lambda **kw: real(fetcher=ratejob.fetch, **kw))
    assert run.main(["rates", "refresh"]) == 0
    assert "Rate updated from MCX 136607/10 g" in capsys.readouterr().out
    run.main(["rates", "show"])
    out = capsys.readouterr().out
    assert "24K  ₹14160.7/g" in out and "OK" in out


def test_cli_rates_set_is_range_checked(tmp_path, monkeypatch, capsys):
    import run
    monkeypatch.setattr(rates, "RATES_FILE", tmp_path / "r.json")
    assert run.main(["rates", "set", "22=1300"]) == 1           # a per-g misread: refused
    assert not (tmp_path / "r.json").exists()
    assert run.main(["rates", "set", "22=13000", "24K=14200"]) == 0
    data = json.loads((tmp_path / "r.json").read_text())
    assert data["22"]["rate_per_g"] == 13000.0 and data["22"]["source"] == "manual"
    assert run.main(["rates", "set", "21=13000"]) == 1
