"""Gold rate: the one store (`GoldRateStore`), the one reader (`RateSource`), chat rate parsing.

Runtime file `data/gold_rates.json` (git-ignored) holds one entry per karat
`{rate_per_g, set_at, source}`. It is written by the rate job (`ratejob.py`, `run.py rates
refresh`: MCX price + ₹5,000), by the owner on the command line (`run.py rates set`), or by a
chat message from a configured owner/staff sender (Nonilion sends no sender ID, so its chat
rates are always refused). Pricing reads rates only through `RateSource`, which refuses a rate
that is missing, older than `max_age_h` (24 h), stamped in the future, or outside the sane range
(`data/rate_card.json` → `gold_rate`); Karigar then asks for today's rate and never estimates.

A chat rate must be a well-formed rupee amount (security F3/F4): digits with optional
Indian/Western comma grouping, at most 2 decimals, at least ₹1 and at most 7 integer digits.
Anything else is refused and echoed back (shortened) so the owner can resend it.

A message is a rate update only when it states rates: a question ("?", "kya", "kitna", "what",
"how", ...) or a number that is a weight ("10 grams", "1 tola") is a price question, not an
update (security F1), and goes on to the brief.

Only the shop's owner/staff may set the rate (security F2, user decision 2026-11-13): their
sender IDs are listed, comma-separated, in the `KARIGAR_RATE_SETTERS` environment variable
(or `.env`). No list, or a sender not on it, means the chat rate is refused and the stored
rate keeps applying.

The file is written atomically (temp file + fsync + os.replace) under an exclusive lock, and a
damaged file is moved aside to `gold_rates.json.corrupt-<time>` instead of crashing every later
rate message (security F5).
"""
from __future__ import annotations

import json
import math
import os
import re
import tempfile
from contextlib import contextmanager, suppress
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

try:
    import fcntl
except ImportError:          # Windows: msvcrt fallback (the app runs in WSL / on Linux)
    fcntl = None
    import msvcrt

DATA = Path(__file__).resolve().parents[3] / "data"
RATES_FILE = DATA / "gold_rates.json"
RATE_CARD = DATA / "rate_card.json"
FUTURE_SKEW = timedelta(minutes=5)   # clock skew tolerated before a timestamp counts as "future"


def rate_card() -> dict:
    """Shop numbers (making %, GST, stone rates, rate rules). Holds no gold rate itself."""
    return json.loads(RATE_CARD.read_text(encoding="utf-8"))
SETTERS_ENV = "KARIGAR_RATE_SETTERS"
KARATS = ("24", "22", "18", "14")
MAX_INT_DIGITS = 7           # ₹99,99,999/g: far above any real rate, far below float overflow
_SHOWN = 15                  # characters of a refused token echoed back

_RATE_WORD = re.compile(r"\b(rates?|bhav|bhaav|bhaw|daam)\b")
_QUESTION = re.compile(r"\?|\b(kya|kitna|kitni|kitne|kaisa|kaise|what|whats|how|batao|bataiye|"
                       r"bataye|bata|tell|quote)\b")
_PAIR = re.compile(
    r"\b(24|22|18|14)\s*(?:k|kt|karat|carat)\b"            # karat
    r"(?:\s*(?:gold|rate|bhav|bhaav|ka|ki|=|:|@|is|hai|rs\.?|inr|₹|/g|per\s*g(?:ram)?))*\s*"
    r"([-+]?\d\S*)"                                          # rate token, validated below
)
_WEIGHT_UNIT = r"(?:g|gm|gms|gram|grams|gramme|grammes|tola|tolas|kg|mg|ct|cts|carat|mm|%)"
_WEIGHT_SUFFIX = re.compile(rf"\d\s*{_WEIGHT_UNIT}$")
_WEIGHT_NEXT = re.compile(rf"\s*{_WEIGHT_UNIT}\b")
_PRICE_SUFFIX = re.compile(r"(?:/-|/(?:g|gm|gram)|rs\.?|inr)$")
_AMOUNT = re.compile(r"(?:\d{1,3}(?:,\d{2,3})+|\d+)(?:\.\d{1,2})?")


@dataclass
class RateMessage:
    """A message that states gold rates: the well-formed ones, and the refused tokens."""
    rates: dict[int, float] = field(default_factory=dict)
    bad: list[str] = field(default_factory=list)


def valid_rate(v) -> bool:
    """A storable rate: finite, at least ₹1, at most MAX_INT_DIGITS integer digits."""
    return (isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)
            and 1 <= v < 10 ** MAX_INT_DIGITS)


def _amount(token: str) -> float | None:
    if not _AMOUNT.fullmatch(token):
        return None
    v = float(token.replace(",", ""))
    return v if valid_rate(v) else None


def _short(token: str) -> str:
    return token if len(token) <= _SHOWN else token[:_SHOWN] + "…"


def parse_rate_message(text: str) -> RateMessage | None:
    """The rates a message sets, or None when it doesn't set any (no rate word, a question,
    or only weights after the karats). Malformed numbers land in `bad`, never in `rates`."""
    t = text.lower()
    if not _RATE_WORD.search(t) or _QUESTION.search(t):
        return None
    out = RateMessage()
    seen = False
    for m in _PAIR.finditer(t):
        k, token = int(m.group(1)), m.group(2).rstrip(".,;:!)]")
        if _WEIGHT_SUFFIX.search(token) or _WEIGHT_NEXT.match(t, m.end()):
            continue                     # "22k gold 10 grams": a weight, not a rate
        seen = True
        v = _amount(_PRICE_SUFFIX.sub("", token))
        if v is None:
            out.bad.append(f"{k}K {_short(token)}")
        elif k in out.rates and out.rates[k] != v:
            out.bad.append(f"{k}K twice")
        else:
            out.rates[k] = v
    return out if seen else None


def rate_setters() -> set[str]:
    """Sender IDs allowed to set the gold rate in chat (owner/staff), from config."""
    from karigar.core.llm import load_env_file
    load_env_file()
    raw = os.environ.get(SETTERS_ENV, "")
    return {s.strip() for s in raw.split(",") if s.strip()}


def may_set_rate(sender: str | None) -> bool:
    """Exact ID match after trimming spaces; a missing sender never may."""
    return bool(sender and sender.strip()) and sender.strip() in rate_setters()


def _valid_entry(k, v) -> bool:
    return (k in KARATS and isinstance(v, dict) and valid_rate(v.get("rate_per_g"))
            and isinstance(v.get("set_at"), str) and isinstance(v.get("source", ""), str))


class GoldRateStore:
    def __init__(self, path: Path | None = None):
        # Looked up per instance so tests can point RATES_FILE at a temp file.
        self.path = Path(path) if path else RATES_FILE

    def _read(self) -> tuple[dict, bool]:
        """(valid entries, whether the file held anything else)."""
        try:
            raw = self.path.read_bytes()
        except FileNotFoundError:
            return {}, False
        try:
            obj = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError, RecursionError):
            return {}, True
        if not isinstance(obj, dict):
            return {}, True
        good = {k: v for k, v in obj.items() if _valid_entry(k, v)}
        return good, len(good) != len(obj)

    def load(self) -> dict:
        """Valid entries only; a damaged file or entry reads as missing."""
        return self._read()[0]

    @contextmanager
    def _lock(self):
        lock = self.path.with_name(self.path.name + ".lock")
        with open(lock, "a+b") as f:
            if fcntl:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            else:
                f.seek(0)
                msvcrt.locking(f.fileno(), msvcrt.LK_LOCK, 1)
            try:
                yield
            finally:
                if fcntl:
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
                else:
                    f.seek(0)
                    msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)

    def _write(self, data: dict) -> None:
        body = json.dumps(data, indent=2, allow_nan=False)
        fd, tmp = tempfile.mkstemp(prefix=self.path.name + ".", suffix=".tmp", dir=self.path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(body)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, self.path)
        except BaseException:
            with suppress(OSError):
                os.unlink(tmp)
            raise

    def set(self, rates: dict[int, float], now: datetime | None = None, source: str = "chat") -> dict:
        """Merge `rates` in, all stamped `now` and labelled `source` (chat / manual / mcx-job)."""
        if not rates or not all(str(k) in KARATS and valid_rate(v) for k, v in rates.items()):
            raise ValueError("gold rates must be finite amounts from ₹1 to "
                             f"{MAX_INT_DIGITS} digits, for 24/22/18/14K")
        if not isinstance(source, str) or not source.strip():
            raise ValueError("a gold rate needs a source label")
        when = (now or datetime.now().astimezone()).isoformat(timespec="seconds")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock():
            data, damaged = self._read()
            if damaged:   # keep the damaged file for the owner, start from its valid entries
                stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
                os.replace(self.path, self.path.with_name(f"{self.path.name}.corrupt-{stamp}"))
            for k, v in rates.items():
                data[str(k)] = {"rate_per_g": float(v), "set_at": when, "source": source}
            self._write(data)
        return {"rates": {str(k): float(v) for k, v in rates.items()}, "set_at": when, "source": source}


# ---------------------------------------------------------------- RateSource (Phase 5)

@dataclass(frozen=True)
class GoldRate:
    """One karat's usable rate: ₹ per gram, when it was set (ISO), who set it."""
    karat: int
    per_g: float
    set_at: str
    source: str

    def as_dict(self) -> dict:
        return {"karat": self.karat, "per_g": self.per_g, "set_at": self.set_at, "source": self.source}


class RateProblem(Exception):
    """Why a karat's rate can't be used: missing | stale | out_of_range | future."""

    def __init__(self, kind: str, karat: int, entry: dict | None = None, **info):
        self.kind, self.karat, self.entry, self.info = kind, karat, entry or {}, info
        super().__init__(f"{karat}K gold rate {kind}")

    def reply(self, lang: str) -> str:
        """The counter's answer (messages.py): says what is wrong and asks for today's rate."""
        from . import messages as M
        from .pricing import inr
        kw = {"karat": self.karat}
        if self.entry:
            kw.update(rate=inr(self.entry["rate_per_g"]), when=_shown_time(self.entry["set_at"]))
        if self.kind == "stale":
            kw["hours"] = f"{self.info['max_age_h']:g}"
        if self.kind == "out_of_range":
            kw.update(lo=inr(self.info["lo"]), hi=inr(self.info["hi"]))
        return M.t(f"rate_{self.kind}", lang, **kw)


def _shown_time(iso: str) -> str:
    return iso.replace("T", " ")[:16]


def _parse_time(iso: str) -> datetime | None:
    try:
        t = datetime.fromisoformat(iso)
    except (TypeError, ValueError):
        return None
    return t if t.tzinfo else t.astimezone()   # a naive stamp is read as local time


class RateSource:
    """The only way pricing gets a gold rate. Reads `GoldRateStore`; checks age and range.

    Rules come from `rate_card.json` → `gold_rate`: `max_age_h`, `sane_range_24k_per_g`
    (scaled by `karat_factor` for 22/18/14K). A rate that fails any rule raises `RateProblem`;
    nothing is ever estimated or borrowed from another karat."""

    def __init__(self, store: GoldRateStore | None = None, rules: dict | None = None,
                 clock=None):
        self.store = store or GoldRateStore()
        self.rules = rules or rate_card()["gold_rate"]
        self.clock = clock or (lambda: datetime.now().astimezone())

    def sane_range(self, karat: int) -> tuple[float, float]:
        lo, hi = self.rules["sane_range_24k_per_g"]
        f = self.rules["karat_factor"][str(karat)]
        return lo * f, hi * f

    def get(self, karat: int, now: datetime | None = None) -> GoldRate:
        now = now or self.clock()
        entry = self.store.load().get(str(karat))
        if entry is None:
            raise RateProblem("missing", karat)
        when = _parse_time(entry["set_at"])
        if when is None:
            raise RateProblem("missing", karat)
        if when - now > FUTURE_SKEW:
            raise RateProblem("future", karat, entry)
        max_age = float(self.rules["max_age_h"])
        if now - when > timedelta(hours=max_age):
            raise RateProblem("stale", karat, entry, max_age_h=max_age)
        lo, hi = self.sane_range(karat)
        if not lo <= entry["rate_per_g"] <= hi:
            raise RateProblem("out_of_range", karat, entry, lo=lo, hi=hi)
        return GoldRate(karat, float(entry["rate_per_g"]), entry["set_at"], entry.get("source") or "chat")

    def get_many(self, karats, now: datetime | None = None) -> dict[int, GoldRate]:
        """All of `karats` (one clock reading), or the first RateProblem in the given order."""
        now = now or self.clock()
        return {k: self.get(k, now) for k in dict.fromkeys(karats)}

    def problem(self, karats, now: datetime | None = None) -> RateProblem | None:
        try:
            self.get_many(karats, now)
        except RateProblem as e:
            return e
        return None


def rate_source() -> RateSource:
    """The shop's RateSource. Tests replace this (conftest) so they never read data/."""
    return RateSource()


def karats_needed(piece_karat: int, old_gold: bool) -> list[int]:
    """The new piece's karat, plus 24K when old gold is credited (credit = fine gold × 24K rate)."""
    return [piece_karat, 24] if old_gold and piece_karat != 24 else [piece_karat]
