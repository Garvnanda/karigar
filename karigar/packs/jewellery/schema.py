"""Jewellery specs. The LLM designer may only produce these; the builder turns
them into geometry deterministically, so every design is a valid solid."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

PieceType = Literal["ring", "bangle", "pendant"]
Gem = Literal["none", "diamond", "ruby", "emerald", "sapphire"]
Metal = Literal["yellow", "rose", "white"]
Karat = Literal[22, 18, 14]

# Specific gravity relative to diamond, for carat <-> diameter estimates.
GEM_SG = {"diamond": 3.52, "ruby": 4.0, "sapphire": 4.0, "emerald": 2.72}


def gem_ct_from_d(gem: str, d_mm: float) -> float:
    """Round brilliant approximation: 6.5 mm diamond ~ 1.0 ct."""
    if gem == "none" or d_mm <= 0:
        return 0.0
    return 0.0037 * d_mm ** 3 * GEM_SG[gem] / GEM_SG["diamond"]


def gem_d_from_ct(gem: str, ct: float) -> float:
    return (ct / (0.0037 * GEM_SG[gem] / GEM_SG["diamond"])) ** (1 / 3)


class OldGold(BaseModel):
    weight_g: float = Field(gt=0, le=500)
    karat: Literal[24, 22, 18, 14] = 22
    tested_purity: Optional[float] = Field(None, gt=0.3, le=1.0)


class Brief(BaseModel):
    piece_type: PieceType
    karat: Karat = 22
    metal: Metal = "yellow"
    old_gold: Optional[OldGold] = None
    target_weight_g: Optional[float] = Field(None, gt=0, le=500)   # finished weight
    budget_inr: Optional[float] = Field(None, gt=0)
    gem: Gem = "none"
    gem_ct: Optional[float] = Field(None, gt=0, le=5)
    ring_inner_d_mm: float = Field(17.3, ge=12, le=25)      # ~US 7
    bangle_inner_d_mm: float = Field(60.3, ge=45, le=75)    # Indian size 2-6
    style: list[str] = []
    assumptions: list[str] = []


class DesignSpec(BaseModel):
    name: str
    piece_type: PieceType
    karat: Karat = 22
    metal: Metal = "yellow"
    # band (ring / bangle). Width/thickness are at scale 1.0; the solver scales them.
    profile: Literal["comfort", "flat", "knife", "faceted"] = "comfort"
    inner_d_mm: float = Field(17.3, ge=12, le=75)
    width_mm: float = Field(3.0, ge=1.0, le=16)
    thickness_mm: float = Field(1.8, ge=0.6, le=6)
    # stone + setting
    gem: Gem = "none"
    gem_d_mm: float = Field(0.0, ge=0, le=12)
    prongs: Literal[4, 6] = 4
    # bangle motif
    motif: Literal["plain", "beaded"] = "plain"
    bead_count: int = Field(24, ge=8, le=72)
    # pendant
    shape: Literal["disc", "lotus"] = "lotus"
    size_mm: float = Field(18.0, ge=8, le=45)
    petals: int = Field(8, ge=5, le=12)
    rationale: str = ""

    @property
    def gem_ct(self) -> float:
        return gem_ct_from_d(self.gem, self.gem_d_mm)
