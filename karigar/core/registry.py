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
    # Phase 4: manufacturability measured on the built mesh. `warnings` are warn/fail lines for
    # the job card; `mesh_checks` the per-rule results ({rule, status, measured_mm, min_mm,
    # location, text}).
    warnings: list[str] = field(default_factory=list)
    mesh_checks: list[dict] = field(default_factory=list)


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


@dataclass
class EditOutcome:
    """What a pack made of an edit (Phase 6).

    status "solved" -> `solved` is the re-solved version under `plan`;
    "refused" / "needs_info" -> `reply` says why or asks; "infeasible" -> `solved` carries the
    infeasible contract. `data` is pack-private (e.g. the patch) for `edit_report`."""
    status: str
    solved: Any = None
    plan: Any = None
    reply: str = ""
    data: Any = None


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

    def intake(self, text: str, attachments: list[Path] | None = None,
               sender: str | None = None) -> Intake:
        """Classify a message (order, question, or a non-order like a rate update).
        `sender` is the chat identity of whoever sent it (None when unknown); packs use it
        to decide who may change shop settings such as the gold rate.
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

    def weights(self, solved: Solved, plan: Plan) -> dict[str, float]:
        """What a result reports about the solved quantity (Phase 3): the jewellery pack gives
        casting_g, finished_g, expected_loss_g/pct and tolerance_g/pct. Default: the value."""
        loss = plan.detail.get("casting_loss_pct", 0.0)
        return {"modelled_g": round(solved.value, 3),
                "finished_g": round(solved.value * (1 - loss / 100), 3)}

    def deliver(self, solved: Solved, brief, plan: Plan, out_dir: Path, quality: str) -> dict[str, Path]:
        """Build final geometry, render, export production files. Returns name -> path."""
        raise NotImplementedError

    def quote(self, solved: Solved, brief, plan: Plan) -> dict:
        raise NotImplementedError

    # Phase 6: edits as spec patches (see core/orders.py for the store).
    def load_brief(self, data: dict):
        """Rebuild a brief from the order store's JSON."""
        raise NotImplementedError

    def load_spec(self, data: dict):
        raise NotImplementedError

    def parse_edit(self, text: str):
        """An edit request (pack type; has `.pick` and `.empty`), or None when not understood."""
        raise NotImplementedError

    def pick_index(self, pick, n: int) -> int:
        raise NotImplementedError

    def edit_text(self, key: str, lang: str) -> str:
        """Counter replies for edits: 'help' (not understood), 'which' (which variant?)."""
        raise NotImplementedError

    def apply_edit(self, spec, scale: float, modelled_g: float, request, plan: Plan,
                   lang: str = "en", on_iter=None) -> EditOutcome:
        raise NotImplementedError

    def edit_report(self, base: dict, new_version: int, outcome: EditOutcome, brief,
                    lang: str = "en") -> dict:
        """v_base -> v_new: changed fields, weight and price difference, summary text."""
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
