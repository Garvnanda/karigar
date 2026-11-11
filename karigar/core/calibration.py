"""Workshop calibration: the data moat.

After a piece is cast and polished, the karigar weighs it and records the
actual weight. Each workshop's real loss (casting + finishing) is learned from
those records, so predictions get sharper with every order.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

DEFAULT_PATH = Path(__file__).resolve().parents[2] / "data" / "calibration.json"
WINDOW = 20  # most recent records used


class CalibrationStore:
    def __init__(self, path: Path = DEFAULT_PATH, default_loss_pct: float = 3.0):
        self.path = Path(path)
        self.default_loss_pct = default_loss_pct
        self.data = json.loads(self.path.read_text()) if self.path.exists() else {}

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, indent=2))

    def record(self, workshop: str, designed_g: float, actual_g: float) -> float:
        if designed_g <= 0 or actual_g <= 0:
            raise ValueError("weights must be positive")
        recs = self.data.setdefault(workshop, {"records": []})["records"]
        recs.append({"designed_g": designed_g, "actual_g": actual_g, "ts": int(time.time())})
        self._save()
        return self.loss_pct(workshop)

    def loss_pct(self, workshop: str | None) -> float:
        recs = (self.data.get(workshop or "", {}) or {}).get("records", [])[-WINDOW:]
        if not recs:
            return self.default_loss_pct
        losses = [(1 - r["actual_g"] / r["designed_g"]) * 100 for r in recs]
        return sum(losses) / len(losses)

    def summary(self, workshop: str | None) -> str:
        n = len((self.data.get(workshop or "", {}) or {}).get("records", []))
        if n == 0:
            return f"default loss {self.default_loss_pct:.1f}% (no records yet)"
        return f"learned loss {self.loss_pct(workshop):.2f}% from {min(n, WINDOW)} cast pieces"
