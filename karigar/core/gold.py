"""Gold arithmetic: assay-aware targets, purity, density.

Everything the solver aims at starts here. The key idea for old-gold exchange:
the customer's old piece is worth its *fine gold after melting*, not its gross
weight. We design the new piece to carry that fine gold. The old gold is credited at
its stated karat's purity only; a claimed or tested purity never changes the number
(security F9, user decision 2026-11-13).
"""
from __future__ import annotations

import json
import statistics
from dataclasses import dataclass, field
from pathlib import Path

# Fineness by karat (BIS hallmark grades).
PURITY = {24: 0.995, 22: 0.916, 18: 0.750, 14: 0.585}

# Densities, casting minimums and the weight tolerance live in a config file a shop can edit
# (decisions.md "Shop numbers", "Phase 3"), never in code. Yellow alloys; white/rose vary by
# recipe (roughly +/-5%) and a workshop's calibration absorbs that error.
CASTING_FILE = Path(__file__).resolve().parents[2] / "data" / "casting.json"
_CACHE: dict[Path, tuple[float, dict]] = {}


def casting_config(path: Path | None = None) -> dict:
    """data/casting.json (re-read when the file changes)."""
    p = Path(path or CASTING_FILE)
    mtime = p.stat().st_mtime
    hit = _CACHE.get(p)
    if hit is None or hit[0] != mtime:
        _CACHE[p] = (mtime, json.loads(p.read_text(encoding="utf-8")))
    return _CACHE[p][1]


def density(karat: int) -> float:
    """g/cm^3 for the karat, from the config file."""
    d = casting_config()["density_g_cm3"]
    if str(karat) not in d:
        raise ValueError(f"No density configured for {karat}K; add it to {CASTING_FILE.name}")
    return float(d[str(karat)])


def purity(karat: int) -> float:
    if karat not in PURITY:
        raise ValueError(f"Unsupported karat {karat}; use one of {sorted(PURITY)}")
    return PURITY[karat]


def grams_to_mm3(grams: float, karat: int) -> float:
    return grams / density(karat) * 1000.0


def mm3_to_grams(mm3: float, karat: int) -> float:
    return mm3 / 1000.0 * density(karat)


def tolerance(losses_pct: list[float] | None = None) -> dict:
    """The +- band on a predicted finished weight, as a % of it, from code and data only.

    Fewer than `min_records` recorded casting losses: the configured default (labelled assumed).
    Otherwise `sigma` x the sample standard deviation of the recorded loss %, floored at
    `floor_pct`. Returns {"pct", "source", "assumed"}."""
    t = casting_config()["tolerance"]
    losses = list(losses_pct or [])
    if len(losses) < t["min_records"]:
        return {"pct": float(t["default_pct"]), "assumed": True,
                "source": f"default ±{t['default_pct']:g}% (alloy density + loss spread; "
                          f"fewer than {t['min_records']} cast pieces recorded)"}
    sd = statistics.stdev(losses)
    pct = max(float(t["floor_pct"]), t["sigma"] * sd)
    return {"pct": round(pct, 3), "assumed": False,
            "source": f"{t['sigma']:g}σ of the loss over {len(losses)} cast pieces "
                      f"(σ {sd:.2f}%, floor {t['floor_pct']:g}%)"}


@dataclass
class GoldTarget:
    karat: int
    fine_g: float               # pure gold the new piece must carry
    finished_gross_g: float     # weight of the finished, polished piece
    design_gross_g: float       # weight we model (before casting/finishing loss)
    casting_loss_pct: float
    notes: list[str] = field(default_factory=list)

    @property
    def design_volume_mm3(self) -> float:
        return grams_to_mm3(self.design_gross_g, self.karat)

    def as_dict(self) -> dict:
        return {
            "karat": self.karat,
            "fine_g": round(self.fine_g, 3),
            "finished_gross_g": round(self.finished_gross_g, 3),
            "design_gross_g": round(self.design_gross_g, 3),
            "casting_loss_pct": round(self.casting_loss_pct, 2),
            "notes": self.notes,
        }


def target_from_exchange(
    old_weight_g: float,
    old_karat: int,
    new_karat: int,
    casting_loss_pct: float,
    melt_loss_pct: float = 2.0,
) -> GoldTarget:
    """Old piece -> fine gold -> finished weight of the new piece -> modelled weight."""
    p_old = purity(old_karat)
    notes = [
        f"Assumed old purity {p_old:.3f} from {old_karat}K claim; "
        "final value depends on the shop's purity test."
    ]
    fine = old_weight_g * p_old * (1 - melt_loss_pct / 100.0)
    notes.append(f"Melting loss deducted: {melt_loss_pct:.1f}%")
    finished = fine / purity(new_karat)
    design = finished / (1 - casting_loss_pct / 100.0)
    return GoldTarget(new_karat, fine, finished, design, casting_loss_pct, notes)


def target_from_gross(finished_gross_g: float, karat: int, casting_loss_pct: float) -> GoldTarget:
    fine = finished_gross_g * purity(karat)
    design = finished_gross_g / (1 - casting_loss_pct / 100.0)
    return GoldTarget(karat, fine, finished_gross_g, design, casting_loss_pct, [])
