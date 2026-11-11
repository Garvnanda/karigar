"""Naqqash in the studio: propose design variants as validated specs.

The LLM is free to be creative inside the schema. Anything that fails
validation is dropped and replaced with a deterministic variant, so the
studio always delivers.
"""
from __future__ import annotations

from pydantic import ValidationError

from karigar.core import llm

from .schema import Brief, DesignSpec, gem_d_from_ct

SYSTEM = """You are Naqqash, a jewellery designer for an Indian shop. Propose {n} distinct designs
as a JSON list. Each item must use ONLY these fields:
name (evocative, 2-4 words), rationale (one line), piece_type, karat, metal,
profile: comfort|flat|knife|faceted (ring/bangle cross-section),
inner_d_mm (keep the customer's size), width_mm (ring 1.8-6, bangle 3-12), thickness_mm (ring 1.4-2.6, bangle 1.8-4),
gem: none|diamond|ruby|emerald|sapphire, gem_d_mm (ring 3-8, pendant 2.5-6), prongs: 4|6,
motif: plain|beaded (bangle), bead_count (12-48),
shape: disc|lotus (pendant), size_mm (pendant 12-28), petals (5-12).
Width/thickness are starting proportions; the workshop rescales them to hit the exact gold weight.
Make the {n} designs clearly different from each other."""


def _gem_d(brief: Brief, ct: float) -> float:
    if brief.gem == "none" or ct <= 0:
        return 0.0
    return round(gem_d_from_ct(brief.gem, ct), 2)


def fallback(brief: Brief, ct: float) -> list[DesignSpec]:
    base = dict(karat=brief.karat, metal=brief.metal)
    gd = _gem_d(brief, ct)
    if brief.piece_type == "ring":
        ring = dict(piece_type="ring", inner_d_mm=brief.ring_inner_d_mm, **base)
        if brief.gem != "none":
            return [
                DesignSpec(name="Classic Solitaire", profile="comfort", width_mm=2.4, thickness_mm=1.7,
                           gem=brief.gem, gem_d_mm=gd, prongs=4,
                           rationale="Four claws, rounded band: timeless and lets the stone lead.", **ring),
                DesignSpec(name="Knife-Edge Six Claw", profile="knife", width_mm=2.2, thickness_mm=2.0,
                           gem=brief.gem, gem_d_mm=gd, prongs=6,
                           rationale="A sharp ridge catches light; six claws hold the stone securely.", **ring),
                DesignSpec(name="Court Band Solitaire", profile="flat", width_mm=3.0, thickness_mm=1.5,
                           gem=brief.gem, gem_d_mm=gd, prongs=4,
                           rationale="Wider flat band for a modern, sturdy daily-wear look.", **ring),
            ]
        return [
            DesignSpec(name="Comfort Band", profile="comfort", width_mm=3.5, thickness_mm=1.8,
                       rationale="Rounded inside and out; the most comfortable everyday band.", **ring),
            DesignSpec(name="Knife-Edge Band", profile="knife", width_mm=3.0, thickness_mm=2.2,
                       rationale="A central ridge gives a bold line with less gold.", **ring),
            DesignSpec(name="Flat Court Band", profile="flat", width_mm=4.5, thickness_mm=1.6,
                       rationale="Clean, wide and modern.", **ring),
        ]
    if brief.piece_type == "bangle":
        bang = dict(piece_type="bangle", inner_d_mm=brief.bangle_inner_d_mm, **base)
        return [
            DesignSpec(name="Beaded Kada", profile="comfort", motif="beaded", bead_count=44,
                       width_mm=5.0, thickness_mm=2.4,
                       rationale="A rolling line of gold beads: festive but light.", **bang),
            DesignSpec(name="Faceted Kada", profile="faceted", width_mm=6.0, thickness_mm=3.0,
                       rationale="Hand-cut-style facets that sparkle without stones.", **bang),
            DesignSpec(name="Classic Round Bangle", profile="comfort", width_mm=4.0, thickness_mm=3.0,
                       rationale="Smooth, rounded and easy to wear every day.", **bang),
        ]
    pend = dict(piece_type="pendant", **base)
    gem = dict(gem=brief.gem, gem_d_mm=gd) if brief.gem != "none" else {}
    return [
        DesignSpec(name="Kamal Pendant", shape="lotus", petals=8, size_mm=18, thickness_mm=1.2,
                   rationale="Two layers of lotus petals around a centre stone.", **gem, **pend),
        DesignSpec(name="Six-Petal Lotus", shape="lotus", petals=6, size_mm=20, thickness_mm=1.1,
                   rationale="Fewer, fuller petals: bolder and simpler.", **gem, **pend),
        DesignSpec(name="Gold Coin Pendant", shape="disc", size_mm=17, thickness_mm=1.3,
                   rationale="A domed coin with a raised rim: minimal and auspicious.", **gem, **pend),
    ]


def _order_by_style(specs: list[DesignSpec], style: list[str]) -> list[DesignSpec]:
    def score(s: DesignSpec) -> int:
        tags = {s.profile, s.motif, s.shape, *s.name.lower().split()}
        return -sum(1 for w in style if w in tags or (w == "lotus" and s.shape == "lotus"))
    return sorted(specs, key=score)


def propose(brief: Brief, ct: float, n: int = 3) -> list[DesignSpec]:
    fb = _order_by_style(fallback(brief, ct), brief.style)
    raw = llm.complete_json(SYSTEM.format(n=n), brief.model_dump_json() +
                            f"\nStone diameter if any: {_gem_d(brief, ct)} mm")
    specs: list[DesignSpec] = []
    if isinstance(raw, list):
        for item in raw[:n]:
            try:
                item.update(piece_type=brief.piece_type, karat=brief.karat, metal=brief.metal)
                specs.append(DesignSpec(**item))
            except (ValidationError, TypeError, AttributeError):
                continue
    for s in fb:  # top up with deterministic designs
        if len(specs) >= n:
            break
        specs.append(s)
    return specs[:n]
