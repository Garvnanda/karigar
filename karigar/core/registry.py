"""Domain packs plug into the shared engine.

A pack supplies only what differs between domains: the spec schema, the
geometry builder, the manufacturability rules, the constraint target, and
the production deliverables. Brief -> design -> solve -> check -> render ->
deliver is the same everywhere.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class Plan:
    """What the constraint solver must hit, or why it can't be done."""
    ok: bool
    target_value: float = 0.0          # in the pack's solved unit (e.g. modelled grams)
    unit: str = "g"
    summary: str = ""
    detail: dict = field(default_factory=dict)
    explanation: str = ""              # filled when ok=False: what's impossible + options
    # ok=False contract (core/result.py Infeasible): which rule binds, the closest result, >= 2 options.
    binding_constraint: str = ""
    best_achievable: dict | None = None  # {"value": float, "unit": str}
    alternatives: list[str] = field(default_factory=list)


@dataclass
class Solved:
    spec: Any
    ok: bool
    scale: float
    value: float
    target: float
    iterations: int
    issues: list[str] = field(default_factory=list)
    explanation: str = ""
    binding_constraint: str = ""
    best_achievable: dict | None = None
    alternatives: list[str] = field(default_factory=list)


@dataclass
class Intake:
    """What the counter made of a message, before any pipeline work.

    status "brief" -> run the pipeline on `brief`; anything else ("needs_info",
    "out_of_scope", "rate_set") is answered at the counter with `reply`.
    """
    status: str
    brief: Any = None
    reply: str = ""
    lang: str = "en"
    questions: list[str] = field(default_factory=list)
    topics: list[str] = field(default_factory=list)
    data: dict = field(default_factory=dict)


class DomainPack:
    name = "base"
    title = "Base"
    available = True
    agents = {  # role -> character name shown in the office
        "brief": "Sakhi", "design": "Naqqash", "build": "Karigar",
        "price": "Jauhari", "render": "Chitrakar",
    }

    def parse_brief(self, text: str, attachments: list[Path] | None = None) -> tuple[Any, str | None]:
        """Return (brief, follow_up_question). Question is set when the request is unclear."""
        raise NotImplementedError

    def intake(self, text: str, attachments: list[Path] | None = None) -> Intake:
        """Classify a message (order, question, or a non-order like a rate update).
        Default: every message is an order brief."""
        brief, question = self.parse_brief(text, attachments)
        if question:
            return Intake("needs_info", reply=question, questions=[question])
        return Intake("brief", brief=brief)

    def describe_brief(self, brief, lang: str = "en") -> str:
        raise NotImplementedError

    def plan(self, brief, loss_pct: float) -> Plan:
        raise NotImplementedError

    def propose(self, brief, n: int = 3) -> list:
        raise NotImplementedError

    def solve(self, spec, plan: Plan, on_iter=None) -> Solved:
        raise NotImplementedError

    def deliver(self, solved: Solved, brief, plan: Plan, out_dir: Path, quality: str) -> dict[str, Path]:
        """Build final geometry, render, export production files. Returns name -> path."""
        raise NotImplementedError

    def quote(self, solved: Solved, brief, plan: Plan) -> dict:
        raise NotImplementedError


_PACKS: dict[str, DomainPack] = {}


def register(pack: DomainPack) -> DomainPack:
    _PACKS[pack.name] = pack
    return pack


def get(name: str) -> DomainPack:
    if name not in _PACKS:
        raise KeyError(f"No pack '{name}'. Available: {', '.join(_PACKS)}")
    p = _PACKS[name]
    if not p.available:
        raise RuntimeError(f"Pack '{name}' is on the roadmap but not built yet.")
    return p


def all_packs() -> dict[str, DomainPack]:
    return dict(_PACKS)
