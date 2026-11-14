"""Gold-rate worker job: MCX gold price from a public page + ₹5,000 → `data/gold_rates.json`.

User decision 2026-11-13 (decisions.md): Nonilion sends no sender ID, so chat can't set the
rate; a worker job fills the config instead. Defaults (assumed, logged):
  - the page quotes MCX gold futures in ₹ per 10 g of 24K (999);
  - ₹5,000 is added per 10 g (`rate_card.json` gold_rate.mcx_premium_per_10g);
  - 24K ₹/g = (MCX + 5,000) / 10; 22K/18K/14K = 24K × 0.916 / 0.75 / 0.585 (karat_factor);
  - the job runs every 6 h in the worker (`run.py rates refresh --every-h 6`);
  - a failed fetch, parse or sane-range check writes nothing: the last rate and its timestamp
    stay, and RateSource's 24 h staleness rule still applies.

Source page: Economic Times commodity summary for MCX gold
(https://economictimes.indiatimes.com/commoditysummary/symbol-GOLD.cms). The parser reads the
first `<span class="commodityPrice">` inside `<div id="MCX">` and requires the unit span after
it to say "Per 10 GRMS". Stdlib only (urllib + html.parser). The fetcher is injectable so tests
use saved HTML and never touch the network.
"""
from __future__ import annotations

import math
import re
import time
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime
from html.parser import HTMLParser
from typing import Callable

from . import rates as R

USER_AGENT = "Mozilla/5.0 (compatible; karigar-rate-job/1.0)"
MAX_BYTES = 3_000_000
SOURCE = "mcx-job"
_UNIT_10G = re.compile(r"per\s*10\s*gr?a?ms?\b", re.I)
_NUMBER = re.compile(r"\d{1,3}(?:,\d{2,3})+(?:\.\d+)?|\d+(?:\.\d+)?")


class RateJobError(Exception):
    """Fetch, parse or range failure. The message is safe to print (no page content dumped)."""


def fetch(url: str, timeout: float = 20.0) -> str:
    """GET `url` (https only), at most MAX_BYTES, decoded as UTF-8."""
    if not url.startswith("https://"):
        raise RateJobError(f"refusing non-https rate URL: {url[:80]}")
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:   # noqa: S310 (https checked above)
            body = r.read(MAX_BYTES + 1)
    except Exception as e:  # network, TLS, HTTP status: all mean "keep the last rate"
        raise RateJobError(f"fetch failed: {type(e).__name__}: {str(e)[:120]}") from None
    if len(body) > MAX_BYTES:
        raise RateJobError(f"page larger than {MAX_BYTES} bytes")
    return body.decode("utf-8", errors="replace")


@dataclass
class MCXQuote:
    per_10g: float
    unit: str
    quoted_at: str | None = None    # the page's own time label, informational only


class _ETParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.depth = 0            # div depth inside <div id="MCX">; 0 = outside
        self.grab = None          # "price" | "unit" | "time" while inside that element
        self.price = self.unit = self.time = None
        self.buf = ""

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        cls = (a.get("class") or "").split()
        if tag == "div":
            if self.depth:
                self.depth += 1
            elif a.get("id") == "MCX" and self.price is None:
                self.depth = 1
        if not self.depth:
            return
        if tag == "span" and "commodityPrice" in cls and self.price is None:
            self.grab, self.buf = "price", ""
        elif tag == "span" and "text" in cls and self.price is not None and self.unit is None:
            self.grab, self.buf = "unit", ""
        elif tag == "p" and "datetime" in cls and self.time is None:
            self.grab, self.buf = "time", ""

    def handle_endtag(self, tag):
        if self.grab and tag in ("span", "p"):
            setattr(self, self.grab, self.buf.strip())
            self.grab = None
        if tag == "div" and self.depth:
            self.depth -= 1

    def handle_data(self, data):
        if self.grab:
            self.buf += data


def parse_et_mcx(html: str) -> MCXQuote:
    """MCX gold price (₹ per 10 g) from the Economic Times commodity page; RateJobError if absent."""
    p = _ETParser()
    try:
        p.feed(html)
        p.close()
    except Exception as e:   # html.parser is lenient; this is belt and braces
        raise RateJobError(f"page could not be parsed: {type(e).__name__}") from None
    if not p.price:
        raise RateJobError("no MCX gold price on the page (layout changed?)")
    if not p.unit or not _UNIT_10G.search(p.unit):
        raise RateJobError(f"MCX price unit is not 'per 10 grams': {(p.unit or 'missing')[:40]!r}")
    if not _NUMBER.fullmatch(p.price):
        raise RateJobError(f"MCX price is not a number: {p.price[:40]!r}")
    v = float(p.price.replace(",", ""))
    if not math.isfinite(v) or v <= 0:
        raise RateJobError("MCX price is not a positive number")
    return MCXQuote(v, p.unit, p.time)


def rates_from_mcx(per_10g: float, rules: dict) -> dict[int, float]:
    """₹/g for every karat: 24K = (MCX + premium) / 10, others × karat factor; 2 decimals."""
    g24 = (per_10g + rules["mcx_premium_per_10g"]) / 10
    return {int(k): round(g24 * f, 2) for k, f in rules["karat_factor"].items()}


@dataclass
class RefreshResult:
    ok: bool
    message: str
    rates: dict[int, float] = field(default_factory=dict)
    set_at: str | None = None
    mcx_per_10g: float | None = None
    kept: dict = field(default_factory=dict)    # on failure: the last stored entries, unchanged


def refresh(fetcher: Callable[[str], str] = fetch, store: R.GoldRateStore | None = None,
            rules: dict | None = None, now: datetime | None = None,
            url: str | None = None) -> RefreshResult:
    """One run of the job. Writes all four karats on success; writes nothing on failure."""
    store = store or R.GoldRateStore()
    rules = rules or R.rate_card()["gold_rate"]
    url = url or rules["mcx_url"]
    try:
        q = parse_et_mcx(fetcher(url))
        new = rates_from_mcx(q.per_10g, rules)
        lo, hi = rules["sane_range_24k_per_g"]
        if not lo <= new[24] <= hi:
            raise RateJobError(f"MCX {q.per_10g:g}/10 g gives 24K ₹{new[24]:g}/g, outside the "
                               f"sane range ₹{lo:g}–₹{hi:g}/g; not saved")
    except RateJobError as e:
        kept = store.load()
        last = (", ".join(f"{k}K ₹{v['rate_per_g']:g}/g set {v['set_at']}" for k, v in sorted(kept.items()))
                or "none")
        return RefreshResult(False, f"Rate not updated: {e}. Last rate kept: {last}.", kept=kept)
    saved = store.set(new, now=now, source=f"{SOURCE}: MCX {q.per_10g:g}/10g + "
                                           f"{rules['mcx_premium_per_10g']:g}, {_host(url)}")
    shown = ", ".join(f"{k}K ₹{v:g}/g" for k, v in sorted(new.items(), reverse=True))
    return RefreshResult(True, f"Rate updated from MCX {q.per_10g:g}/10 g "
                               f"(+{rules['mcx_premium_per_10g']:g}): {shown}, set {saved['set_at']}.",
                         rates=new, set_at=saved["set_at"], mcx_per_10g=q.per_10g)


def _host(url: str) -> str:
    m = re.match(r"https?://([^/]+)", url)
    return m.group(1) if m else url[:40]


def run_every(hours: float, runs: int | None = None, sleep=time.sleep, log=print, **kw) -> None:
    """Worker loop: refresh now, then every `hours` (6 h default in the CLI). `runs` caps it (tests)."""
    if hours <= 0:
        raise ValueError("--every-h must be positive")
    n = 0
    while runs is None or n < runs:
        log(refresh(**kw).message)
        n += 1
        if runs is None or n < runs:
            sleep(hours * 3600)
