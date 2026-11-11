"""Jewellery specs. The LLM designer may only produce these; the builder turns
them into geometry deterministically, so every design is a valid solid."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator

from . import sizes

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
    # Canonical ring size is the inner diameter. `ring_size` (Indian, 1-30) converts through
    # data/ring_sizes.json. The schema defaults below are for code paths that build a Brief
    # directly; brief.parse never relies on them (it asks for the size instead).
    ring_size: Optional[int] = Field(None, ge=1, le=30)
    ring_inner_d_mm: float = Field(17.3, ge=12, le=25)
    bangle_inner_d_mm: float = Field(60.3, ge=45, le=75)    # Indian size 2-6
    style: list[str] = []
    assumptions: list[str] = []
    lang: Literal["en", "hinglish"] = "en"                  # reply language of the request

    @model_validator(mode="before")
    @classmethod
    def _ring_size_to_mm(cls, data):
        if (isinstance(data, dict) and data.get("ring_size") is not None
                and data.get("ring_inner_d_mm") is None):
            size = data["ring_size"]
            if isinstance(size, (int, float)) and 1 <= size <= 30 and float(size).is_integer():
                data = {**data, "ring_inner_d_mm": sizes.ring_inner_d_mm(int(size))}
        return data


# Which motifs each piece is built with (the pendant's look comes from `shape`).
MOTIFS = {"ring": ("plain", "floral"), "bangle": ("plain", "beaded"), "pendant": ("plain",)}


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
    # motif: "beaded" = bangle beads; "floral" = ring with a flower top (petals, size_mm)
    motif: Literal["plain", "beaded", "floral"] = "plain"
    bead_count: int = Field(24, ge=8, le=72)
    # pendant (size_mm/petals also give a floral ring's flower diameter and petal count)
    shape: Literal["disc", "lotus"] = "lotus"
    size_mm: float = Field(18.0, ge=8, le=45)
    petals: int = Field(8, ge=5, le=12)
    rationale: str = ""

    @model_validator(mode="after")
    def _motif_fits_piece(self):
        allowed = MOTIFS[self.piece_type]
        if self.motif not in allowed:
            raise ValueError(f"motif '{self.motif}' is not made for a {self.piece_type}; "
                             f"use one of {', '.join(allowed)}")
        return self

    @property
    def gem_ct(self) -> float:
        return gem_ct_from_d(self.gem, self.gem_d_mm)
