"""Gold arithmetic: assay-aware targets, purity, density.

Everything the solver aims at starts here. The key idea for old-gold exchange:
the customer's old piece is worth its *fine gold after testing and melting*,
not its gross weight. We design the new piece to carry that fine gold.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# Fineness by karat (BIS hallmark grades).
PURITY = {24: 0.995, 22: 0.916, 18: 0.750, 14: 0.585}

# Approximate densities (g/cm^3) for yellow alloys. White/rose alloys vary by
# recipe (roughly +/-5%); a workshop's calibration factor absorbs that error.
DENSITY = {24: 19.32, 22: 17.8, 18: 15.5, 14: 13.1}


def purity(karat: int) -> float:
    if karat not in PURITY:
        raise ValueError(f"Unsupported karat {karat}; use one of {sorted(PURITY)}")
    return PURITY[karat]


def grams_to_mm3(grams: float, karat: int) -> float:
    return grams / DENSITY[karat] * 1000.0


def mm3_to_grams(mm3: float, karat: int) -> float:
    return mm3 / 1000.0 * DENSITY[karat]


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
    tested_purity: float | None = None,
) -> GoldTarget:
    """Old piece -> fine gold -> finished weight of the new piece -> modelled weight."""
    notes = []
    p_old = tested_purity if tested_purity is not None else purity(old_karat)
    if tested_purity is None:
        notes.append(
            f"Assumed old purity {p_old:.3f} from {old_karat}K claim; "
            "final value depends on the shop's purity test."
        )
    fine = old_weight_g * p_old * (1 - melt_loss_pct / 100.0)
    notes.append(f"Melting loss deducted: {melt_loss_pct:.1f}%")
    finished = fine / purity(new_karat)
    design = finished / (1 - casting_loss_pct / 100.0)
    return GoldTarget(new_karat, fine, finished, design, casting_loss_pct, notes)


def target_from_gross(finished_gross_g: float, karat: int, casting_loss_pct: float) -> GoldTarget:
    fine = finished_gross_g * purity(karat)
    design = finished_gross_g / (1 - casting_loss_pct / 100.0)
    return GoldTarget(karat, fine, finished_gross_g, design, casting_loss_pct, [])
