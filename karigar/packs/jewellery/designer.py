"""Naqqash in the studio: propose design variants as validated specs.

Every proposal is three variants, lighter / balanced / statement, whose
natural gold weights (at scale 1.0, before the solver rescales them to the
target) rise by at least 15% from one to the next, so the customer sees a
real choice of look. The LLM is free to be creative inside the schema.
Anything that fails validation is dropped; if the LLM's designs are too alike
in weight, deterministic designs fill the gaps, so the studio always delivers.
The customer's size always comes from the brief, never from the model.
"""
from __future__ import annotations

from itertools import combinations
from typing import Callable, Optional

from pydantic import ValidationError

from karigar.core import llm

from .schema import Brief, DesignSpec, gem_d_from_ct

SPREAD = 1.15                      # each variant >= 15% heavier than the previous one
LABELS = ("lighter", "balanced", "statement")
FLORAL_WORDS = {"floral", "flower", "flowers", "phool", "petal", "petals", "lotus", "kamal", "leaf"}

SYSTEM = """You are Naqqash, a jewellery designer for an Indian shop. Propose {n} distinct designs
as a JSON list, from lightest to boldest: a lighter, a balanced and a statement design, each
using clearly more gold than the one before (at least 15% more).
Each item must use ONLY these fields:
name (evocative, 2-4 words), rationale (one line), piece_type, karat, metal,
profile: comfort|flat|knife|faceted (ring/bangle cross-section),
width_mm (ring 1.8-6, bangle 3-12), thickness_mm (ring 1.4-2.6, bangle 1.8-4),
gem: none|diamond|ruby|emerald|sapphire, gem_d_mm (ring 3-8, pendant 2.5-6), prongs: 4|6,
motif: plain (any piece) | floral (ring only: flower top, size_mm = flower diameter 8-13, petals 5-12)
| beaded (bangle only, with bead_count 12-48),
shape: disc|lotus (pendant), size_mm (pendant 12-28), petals (5-12).
The customer's ring/bangle size is fixed by the shop; do not set it.
Width/thickness are starting proportions; the workshop rescales them to hit the exact gold weight.
Make the {n} designs clearly different from each other."""


def _gem_d(brief: Brief, ct: float) -> float:
    if brief.gem == "none" or ct <= 0:
        return 0.0
    return round(gem_d_from_ct(brief.gem, ct), 2)


def _fixed(brief: Brief) -> dict:
    """Fields the brief owns on every variant, LLM or fallback."""
    out = dict(piece_type=brief.piece_type, karat=brief.karat, metal=brief.metal)
    if brief.piece_type == "ring":
        out["inner_d_mm"] = brief.ring_inner_d_mm
    elif brief.piece_type == "bangle":
        out["inner_d_mm"] = brief.bangle_inner_d_mm
    return out


def wants_floral(brief: Brief) -> bool:
    return any(w.lower() in FLORAL_WORDS for w in brief.style)


def fallback(brief: Brief, ct: float) -> list[DesignSpec]:
    """Deterministic lighter, balanced, statement designs (in that order). The
    proportions are chosen so the weights at scale 1.0 rise by >= 15% each step
    (tests/test_designer_variants_bpy.py) and Hero A's floral ring solves near
    scale 1.0 for an 8.4 g exchange."""
    fx = _fixed(brief)
    gd = _gem_d(brief, ct)
    gem = dict(gem=brief.gem, gem_d_mm=gd) if brief.gem != "none" else {}
    if brief.piece_type == "ring" and wants_floral(brief):
        return [
            DesignSpec(name="Chhota Phool", motif="floral", petals=5, size_mm=9.5, profile="comfort",
                       width_mm=3.2, thickness_mm=1.9,
                       rationale="A small five-petal flower on a slim band: delicate and light.", **gem, **fx),
            DesignSpec(name="Phool Ring", motif="floral", petals=6, size_mm=10.5, profile="comfort",
                       width_mm=3.5, thickness_mm=2.0,
                       rationale="A six-petal flower with a gold bud at its heart.", **gem, **fx),
            DesignSpec(name="Gulab Statement", motif="floral", petals=8, size_mm=12, profile="comfort",
                       width_mm=4.0, thickness_mm=2.2,
                       rationale="A full eight-petal bloom on a broad band: made to be seen.", **gem, **fx),
        ]
    if brief.piece_type == "ring" and brief.gem != "none":
        return [
            DesignSpec(name="Classic Solitaire", profile="comfort", width_mm=2.0, thickness_mm=1.5, prongs=4,
                       rationale="Four claws, slim rounded band: timeless and lets the stone lead.",
                       **gem, **fx),
            DesignSpec(name="Knife-Edge Six Claw", profile="knife", width_mm=2.4, thickness_mm=1.9, prongs=6,
                       rationale="A sharp ridge catches light; six claws hold the stone securely.",
                       **gem, **fx),
            DesignSpec(name="Court Band Solitaire", profile="flat", width_mm=3.2, thickness_mm=2.0, prongs=4,
                       rationale="Wider flat band for a modern, sturdy daily-wear look.", **gem, **fx),
        ]
    if brief.piece_type == "ring":
        return [
            DesignSpec(name="Knife-Edge Band", profile="knife", width_mm=2.5, thickness_mm=1.8,
                       rationale="A central ridge gives a bold line with less gold.", **fx),
            DesignSpec(name="Comfort Band", profile="comfort", width_mm=3.5, thickness_mm=1.8,
                       rationale="Rounded inside and out; the most comfortable everyday band.", **fx),
            DesignSpec(name="Flat Court Band", profile="flat", width_mm=4.5, thickness_mm=2.0,
                       rationale="Clean, wide and modern.", **fx),
        ]
    if brief.piece_type == "bangle":
        return [
            DesignSpec(name="Classic Round Bangle", profile="comfort", width_mm=4.0, thickness_mm=2.4,
                       rationale="Smooth, rounded and easy to wear every day.", **fx),
            DesignSpec(name="Faceted Kada", profile="faceted", width_mm=6.0, thickness_mm=3.0,
                       rationale="Hand-cut-style facets that sparkle without stones.", **fx),
            DesignSpec(name="Beaded Kada", profile="comfort", motif="beaded", bead_count=44,
                       width_mm=6.0, thickness_mm=3.0,
                       rationale="A rolling line of gold beads on a broad kada: festive and rich.", **fx),
        ]
    return [
        DesignSpec(name="Gold Coin Pendant", shape="disc", size_mm=15, thickness_mm=1.1,
                   rationale="A domed coin with a raised rim: minimal and auspicious.", **gem, **fx),
        DesignSpec(name="Six-Petal Lotus", shape="lotus", petals=6, size_mm=18, thickness_mm=1.2,
                   rationale="Two layers of fuller petals: simple and bold.", **gem, **fx),
        DesignSpec(name="Kamal Pendant", shape="lotus", petals=8, size_mm=21, thickness_mm=1.3,
                   rationale="A large two-layer lotus around a centre piece.", **gem, **fx),
    ]


def _label(specs: list[DesignSpec]) -> list[DesignSpec]:
    if len(specs) != len(LABELS):
        return specs
    return [s.model_copy(update={"name": f"{s.name} ({lab})"}) for s, lab in zip(specs, LABELS)]


def _weigh_default(spec: DesignSpec) -> float:
    from . import geometry  # bpy only when the LLM actually proposed something
    return geometry.gold_volume(spec, 1.0)


def _pick(pool: list[DesignSpec], is_llm: list[bool], weights: list[float], n: int):
    """n designs from the pool, light to heavy, each >= SPREAD x the previous;
    as many LLM designs as possible, then earliest in the pool. None if impossible."""
    best, best_key = None, None
    for combo in combinations(range(len(pool)), n):
        order = sorted(combo, key=lambda i: weights[i])
        if any(weights[b] < SPREAD * weights[a] for a, b in zip(order, order[1:])):
            continue
        key = (-sum(is_llm[i] for i in combo), sum(combo))
        if best_key is None or key < best_key:
            best, best_key = order, key
    return None if best is None else [pool[i] for i in best]


def propose(brief: Brief, ct: float, n: int = 3,
            weigh: Optional[Callable[[DesignSpec], float]] = None) -> list[DesignSpec]:
    fb = fallback(brief, ct)
    raw = llm.complete_json(SYSTEM.format(n=n), brief.model_dump_json() +
                            f"\nStone diameter if any: {_gem_d(brief, ct)} mm")
    fixed = _fixed(brief)
    specs: list[DesignSpec] = []
    if isinstance(raw, list):
        for item in raw[:n]:
            try:
                specs.append(DesignSpec(**{**item, **fixed}))   # the brief overrides the model
            except (ValidationError, TypeError, AttributeError, ValueError):
                continue
    if not specs:
        return _label(fb[:n])
    weigh = weigh or _weigh_default
    names = {s.name for s in specs}
    pool = specs + [s for s in fb if s.name not in names]
    is_llm = [True] * len(specs) + [False] * (len(pool) - len(specs))
    picked = _pick(pool, is_llm, [weigh(s) for s in pool], n)
    return _label(picked if picked else fb[:n])
