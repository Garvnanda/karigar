"""Design-family registry (Phase 2.5 catalogue).

A family is one parametric design: a builder that turns a `DesignSpec` (with
`spec.family == name`) and a scale into a `geometry.Built`, plus the metadata
the rest of the pack needs without Blender:

- `default_spec`: DesignSpec fields of the balanced design (validated at register time),
- `variant_axes`: which numeric fields the designer scales for lighter / balanced /
  statement, as {field: (lighter, balanced, statement)} multipliers; a field is a
  DesignSpec number (`width_mm`, `petals`, ...) or `params.<key>` for a family-own knob,
- `scale_bounds`: (lo, hi) or `fn(spec) -> (lo, hi)`, the castable range of the
  solver's scale knob. Required for chain / coin / earring / nosepin (dfm.RULES has
  no rules for them); ring / bangle / pendant families fall back to dfm.RULES.
- `checks`: optional `fn(spec, scale) -> list[str]` for the job card's "checks passed".
- `relax`: optional `fn(spec, failed_rules) -> (spec, what changed) | None`, the Phase 4 retry
  after a failed mesh check: the same design with optional features relaxed (fewer stones,
  ...). Without it meshdfm.relax makes the design less spread out (width / size smaller).

Every module in this package is imported on first import of the package, so a new
file that calls `register(...)` at import time is picked up without touching shared
files. Family modules must NOT import bpy / bmesh / mathutils / geometry at module
level (the brief and designer run without Blender): import them inside the builder.

Earrings: the builder returns ONE earring. `geometry.build` mirrors it into a pair
when `spec.pair` is True; the pair's volume (both pieces) is what the solver weighs.
"""
from __future__ import annotations

import importlib
import pkgutil
from dataclasses import dataclass, field
from typing import Callable, Optional, Union

# The Phase 2.5 catalogue (implementation.md): 4 rings, 3 pendants, 2 chains, 1 coin,
# 3 bangles, 4 earrings, 2 nose pieces. Brief intake may name any of these even
# before its builder is registered; the designer only uses registered ones.
CATALOGUE: tuple[str, ...] = (
    "ring_floral_cluster", "ring_three_stone", "ring_halo_solitaire", "ring_butterfly",
    "pendant_heart_halo", "pendant_paisley", "pendant_temple_lotus",
    "chain_rope", "chain_curb",
    "coin_lotus_10g",
    "bangle_temple_kada", "bangle_twisted_rope", "bangle_leaf_vine",
    "earring_jhumka", "earring_chandbali", "earring_floral_stud", "earring_bali_hoop",
    "nosepin_flower", "nosepin_convertible_stud",
)

LABELS = ("lighter", "balanced", "statement")
Bounds = Union[tuple[float, float], Callable[..., tuple[float, float]]]


@dataclass(frozen=True)
class Family:
    name: str
    piece_type: str
    builder: Callable           # builder(spec: DesignSpec, scale: float) -> geometry.Built
    default_spec: dict
    variant_axes: dict          # {field: (lighter, balanced, statement)}
    scale_bounds: Optional[Bounds] = None
    checks: Optional[Callable] = None
    title: str = ""
    relax: Optional[Callable] = None

    def bounds(self, spec) -> tuple[float, float]:
        b = self.scale_bounds
        return tuple(b(spec)) if callable(b) else tuple(b)

    def variant_fields(self, label: str) -> dict:
        """DesignSpec fields of one variant: default_spec with each axis multiplied."""
        i = LABELS.index(label)
        out = {**self.default_spec, "params": dict(self.default_spec.get("params", {}))}
        for axis, factors in self.variant_axes.items():
            f = factors[i]
            if axis.startswith("params."):
                k = axis.split(".", 1)[1]
                out["params"][k] = out["params"][k] * f
            else:
                v = out[axis] * f
                out[axis] = round(v) if _spec_fields()[axis].annotation is int else v
        return out


FAMILIES: dict[str, Family] = {}


def _spec_fields() -> dict:
    from ..schema import DesignSpec
    return DesignSpec.model_fields


def register(name: str, piece_type: str, builder: Callable, default_spec: dict,
             variant_axes: dict, *, scale_bounds: Optional[Bounds] = None,
             checks: Optional[Callable] = None, title: str = "",
             relax: Optional[Callable] = None) -> Family:
    """Register a design family. Returns the Family. Raises ValueError on a bad registration
    (duplicate name, unknown piece type, default spec or any variant failing DesignSpec)."""
    from ..dfm import RULES
    from ..schema import DesignSpec

    if name in FAMILIES:
        raise ValueError(f"family {name!r} is already registered")
    if not callable(builder):
        raise ValueError(f"family {name!r}: builder must be callable")
    if scale_bounds is None and piece_type not in RULES:
        raise ValueError(f"family {name!r}: a {piece_type} family must give scale_bounds "
                         "(dfm.RULES has no rules for it)")
    fields = _spec_fields()
    num_axes = {}
    for axis, factors in variant_axes.items():
        if not (isinstance(factors, (tuple, list)) and len(factors) == 3
                and all(isinstance(f, (int, float)) and f > 0 for f in factors)):
            raise ValueError(f"family {name!r}: axis {axis!r} needs 3 positive multipliers")
        if axis.startswith("params."):
            if axis.split(".", 1)[1] not in default_spec.get("params", {}):
                raise ValueError(f"family {name!r}: {axis!r} is not in default_spec['params']")
        elif axis not in fields or fields[axis].annotation not in (int, float):
            raise ValueError(f"family {name!r}: {axis!r} is not a numeric DesignSpec field")
        num_axes[axis] = tuple(factors)
    spec = {**{a: fields[a].default for a in num_axes if not a.startswith("params.")
               and a not in default_spec}, **default_spec}
    fam = Family(name, piece_type, builder, spec, num_axes, scale_bounds, checks,
                 title or name.split("_", 1)[-1].replace("_", " ").title(), relax)
    base = {"name": fam.title, "piece_type": piece_type}   # family name checked once registered
    try:
        DesignSpec(**{**base, **spec})
        for lab in LABELS:
            DesignSpec(**{**base, **fam.variant_fields(lab)})
    except Exception as e:                      # surface as a registration error
        raise ValueError(f"family {name!r}: spec does not validate: {e}") from e
    FAMILIES[name] = fam
    return fam


def unregister(name: str) -> None:
    """Remove a family (tests register throwaway families)."""
    FAMILIES.pop(name, None)


def get(name: str) -> Family:
    if name not in FAMILIES:
        raise KeyError(f"design family {name!r} is not registered")
    return FAMILIES[name]


def for_piece(piece_type: str) -> list[Family]:
    """Registered families of one piece type, catalogue order first, then by name."""
    order = {n: i for i, n in enumerate(CATALOGUE)}
    fams = [f for f in FAMILIES.values() if f.piece_type == piece_type]
    return sorted(fams, key=lambda f: (order.get(f.name, len(order)), f.name))


def _load_all() -> None:
    for m in sorted(pkgutil.iter_modules(__path__), key=lambda m: m.name):
        if not m.name.startswith("_"):
            importlib.import_module(f"{__name__}.{m.name}")


_load_all()
