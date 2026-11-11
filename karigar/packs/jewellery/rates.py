"""Gold rate set in chat ("aaj ka rate 22K 14730"): parse, store with a timestamp, acknowledge.

Runtime file `data/gold_rates.json` (git-ignored). Sane-range checks and staleness are Phase 5;
here only non-positive numbers are rejected.
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

RATES_FILE = Path(__file__).resolve().parents[3] / "data" / "gold_rates.json"

_RATE_WORD = re.compile(r"\b(rates?|bhav|bhaav|bhaw|daam)\b")
_PAIR = re.compile(
    r"\b(24|22|18|14)\s*(?:k|kt|karat|carat)\b"            # karat
    r"(?:\s*(?:gold|rate|bhav|bhaav|ka|ki|=|:|@|is|hai|rs\.?|inr|₹|/g|per\s*g(?:ram)?))*\s*"
    r"(-?\d[\d,]*(?:\.\d+)?)"                                # rate
)


def parse_rate_message(text: str) -> dict[int, float] | None:
    """{karat: rate} when the message sets gold rates, else None. Non-positive values come
    back as-is so the caller can reject them."""
    t = text.lower()
    if not _RATE_WORD.search(t):
        return None
    pairs = {int(m.group(1)): float(m.group(2).replace(",", "")) for m in _PAIR.finditer(t)}
    return pairs or None


class GoldRateStore:
    def __init__(self, path: Path | None = None):
        # Looked up per instance so tests can point RATES_FILE at a temp file.
        self.path = Path(path) if path else RATES_FILE

    def load(self) -> dict:
        if not self.path.exists():
            return {}
        return json.loads(self.path.read_text(encoding="utf-8"))

    def set(self, rates: dict[int, float], now: datetime | None = None) -> dict:
        if not rates or any(v <= 0 for v in rates.values()):
            raise ValueError("gold rates must be positive numbers")
        when = (now or datetime.now().astimezone()).isoformat(timespec="seconds")
        data = self.load()
        for k, v in rates.items():
            data[str(k)] = {"rate_per_g": v, "set_at": when}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return {"rates": {str(k): v for k, v in rates.items()}, "set_at": when}
