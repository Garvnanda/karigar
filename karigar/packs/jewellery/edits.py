"""Edits as spec patches (Phase 6, spec §11).

"make it 0.5 mm thinner", "Middle one, but make the flower slightly bigger", "1 g halka karo":
the customer's words become an `EditRequest` (which variant, which whitelisted spec fields move,
or a new weight), the request becomes a patch on the chosen version's spec, and the workshop
re-solves the patched spec and reruns the checks.

Rules (decisions.md "Phase 6: edits are spec patches"):
- Only `EDITABLE` fields can be patched; ring size, karat, metal, stone type, piece type and
  family come from the brief and are never patched here.
- A size edit says what the *finished* piece should measure. The solver's scale multiplies
  width/thickness/size, so an edited dimension is held at its new finished value while the
  scale moves ("locked"): the gold target is kept by re-solving the rest of the piece (the band).
- A weight edit (lighter/heavier, halka/bhaari) changes the gold target instead and locks nothing.
- Relative words map to code-defined steps (`STEP`); numbers come only from the customer's text.
  The optional LLM path may only name fields, directions and step words; a number it returns is
  accepted only when that number is written in the customer's message.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from karigar.core import llm

from .schema import DesignSpec

# Relative words → code-defined steps (never from the model).
STEP = {"slight": 0.10, "normal": 0.10, "large": 0.25}
COUNT_STEP = {"petals": 1, "bead_count": 4}

# Fields an edit may touch. `params.<key>` entries are family knobs.
EDITABLE = ("thickness_mm", "width_mm", "size_mm", "gem_d_mm", "petals", "bead_count", "link_w_mm",
            "params.flower_d")
INT_FIELDS = {"petals", "bead_count"}

# How a field's finished size follows the solver's scale s: finished = value × s**power.
# Default 1 for dimensions; 0 = not scaled (stone, counts). Family exceptions below.
POWER = {"thickness_mm": 1.0, "width_mm": 1.0, "size_mm": 1.0, "link_w_mm": 1.0,
         "params.flower_d": 1.0, "gem_d_mm": 0.0, "petals": 0.0, "bead_count": 0.0}
FAMILY_POWER = {("coin_lotus_10g", "size_mm"): 0.5,       # coin diameter ∝ √s
                ("earring_bali_hoop", "size_mm"): 0.0}    # hoop size is the fit; never scaled

LOCK_TOL = 1e-6


class Change(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
    field: str
    op: Literal["add", "mul"]
    amount: float

    @field_validator("field")
    @classmethod
    def _editable(cls, v):
        if v not in EDITABLE:
            raise ValueError(f"{v!r} cannot be edited")
        return v


class WeightChange(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
    op: Literal["add", "mul"]          # add: grams of finished weight; mul: factor
    amount: float


Pick = Literal["first", "middle", "last"]


class EditRequest(BaseModel):
    pick: Optional[Pick] = None
    changes: list[Change] = []
    weight: Optional[WeightChange] = None
    source: Literal["rules", "llm"] = "rules"

    @property
    def empty(self) -> bool:
        return not self.changes and self.weight is None


# ------------------------------------------------------------------ parsing

_PICK = [
    ("first", r"\b(first|1st|pehla|pehli|pehle|pahla|pahli|pahle|option\s*1|design\s*1|v1)\b"),
    ("middle", r"\b(middle|beech|bich|beech\s*wala|bichla|bichwala|second|2nd|doosra|doosri|dusra|"
               r"dusri|option\s*2|design\s*2|v2)\b"),
    ("last", r"\b(last|third|3rd|teesra|teesri|tisra|tisri|aakhri|akhri|option\s*3|design\s*3|v3)\b"),
]
_SLIGHT = r"\b(slightly|slight|a\s+bit|a\s+little|little|bit|thoda|thodi|thode|zara|halka\s+sa)\b"
_LARGE = r"\b(much|a\s+lot|lot|way|bahut|kaafi|kafi|zyada\s+hi|significantly)\b"
_NUM = r"(\d+(?:\.\d+)?)\s*(mm|millimet(?:er|re)s?|g|gm|gms|gram|grams|grm|%|percent|pc)\b"

_UP, _DOWN = "up", "down"
# (field-or-target, direction, pattern). Order matters: counts before sizes, thickness/width
# before the generic bigger/smaller.
_RULES = [
    ("petals", _UP, r"\b(more|zyada|jyada|extra)\s+(petals?|pankhudi(?:yan|yaan)?)\b"),
    ("petals", _DOWN, r"\b(fewer|less|kam)\s+(petals?|pankhudi(?:yan|yaan)?)\b"),
    ("bead_count", _UP, r"\b(more|zyada|jyada|extra)\s+(beads?|moti|dane)\b"),
    ("bead_count", _DOWN, r"\b(fewer|less|kam)\s+(beads?|moti|dane)\b"),
    ("thickness_mm", _DOWN, r"\b(thinner|thin|patla|patli|patle|patlaa)\b"),
    ("thickness_mm", _UP, r"\b(thicker|thick|mota|moti|mote|motaa)\b"),
    ("width_mm", _UP, r"\b(wider|broader|chauda|chaudi|chaude|chaura|chauri)\b"),
    ("width_mm", _DOWN, r"\b(narrower|kam\s+chauda|kam\s+chaudi)\b"),
    ("size", _UP, r"\b(bigger|larger|big|large|bada|badi|bade|badaa|bara|bari)\b"),
    ("size", _DOWN, r"\b(smaller|small|chhota|chhoti|chhote|chota|choti|chote)\b"),
    ("weight", _DOWN, r"\b(lighter|light|halka|halki|halke|less\s+gold|kam\s+sona|kam\s+weight|kam\s+wazan)\b"),
    ("weight", _UP, r"\b(heavier|heavy|bhaari|bhari|bhaara|more\s+gold|zyada\s+sona|zyada\s+weight)\b"),
]
# What "bigger/smaller" is about.
_TARGETS = [
    ("flower", r"\b(flower|phool|phul|bloom|petals?|pankhudi\w*|lotus|kamal)\b"),
    ("stone", r"\b(stone|nag|naag|diamond|heera|hira|ruby|manik|emerald|panna|sapphire|neelam|gem)\b"),
    ("link", r"\b(links?|kadi|kadiyan)\b"),
]


def _clauses(text: str) -> list[str]:
    return [c for c in re.split(r"\b(?:and|but|aur|lekin|par|magar|then|phir)\b|[,;.]+(?!\d)", text) if c.strip()]


def _amount(clause: str):
    m = re.search(_NUM, clause)
    if not m:
        return None, None
    unit = m.group(2)
    unit = "mm" if unit.startswith("mm") or unit.startswith("milli") else \
           "%" if unit in ("%", "percent", "pc") else "g"
    return float(m.group(1)), unit


def _step(clause: str) -> str:
    if re.search(_LARGE, clause):
        return "large"
    if re.search(_SLIGHT, clause):
        return "slight"
    return "normal"


def _pick(text: str) -> Optional[Pick]:
    for name, pat in _PICK:
        if re.search(pat, text):
            return name
    return None


def _clause_change(clause: str):
    """One clause → ("field"|"weight"|"size:<target>", direction, amount, unit, step) or None."""
    for what, direction, pat in _RULES:
        if re.search(pat, clause):
            if what == "size":
                target = next((t for t, tp in _TARGETS if re.search(tp, clause)), "piece")
                what = f"size:{target}"
            amount, unit = _amount(clause)
            return what, direction, amount, unit, _step(clause)
    return None


def parse(text: str) -> Optional[EditRequest]:
    """Deterministic parse (English + Hinglish). None when nothing is understood."""
    low = text.lower()
    pick = _pick(low)
    changes, weight = [], None
    for clause in _clauses(low):
        c = _clause_change(clause)
        if c is None:
            continue
        what, direction, amount, unit, step = c
        built = _to_change(what, direction, amount, unit, step)
        if built is None:
            return None                  # understood the word but not the number/unit: ask
        if isinstance(built, WeightChange):
            weight = built
        else:
            changes.append(built)
    if pick is None and not changes and weight is None:
        return None
    return EditRequest(pick=pick, changes=changes, weight=weight)


def _to_change(what, direction, amount, unit, step):
    sign = 1 if direction == _UP else -1
    if what == "weight":
        if amount is None:
            return WeightChange(op="mul", amount=1 + sign * STEP[step])
        if unit == "g":
            return WeightChange(op="add", amount=sign * amount)
        if unit == "%":
            return WeightChange(op="mul", amount=1 + sign * amount / 100)
        return None
    if what in COUNT_STEP:
        n = int(amount) if amount is not None and unit is None else COUNT_STEP[what]
        return Change(field=what, op="add", amount=sign * n)
    field_name = what
    if what.startswith("size:"):
        field_name = {"flower": "size_mm", "stone": "gem_d_mm", "link": "link_w_mm",
                      "piece": "size_mm"}[what.split(":", 1)[1]]
        if what == "size:flower":
            field_name = "flower"          # resolved against the spec (size_mm or params.flower_d)
    if amount is None:
        return Change.model_construct(field=field_name, op="mul", amount=1 + sign * STEP[step])
    if unit == "mm":
        return Change.model_construct(field=field_name, op="add", amount=sign * amount)
    if unit == "%":
        return Change.model_construct(field=field_name, op="mul", amount=1 + sign * amount / 100)
    return None


# ------------------------------------------------------------------ optional LLM path

LLM_SYSTEM = """You map a jeweller's edit request (English or Hinglish) to a JSON object:
{"pick": "first"|"middle"|"last"|null,
 "changes": [{"target": "thickness"|"width"|"flower"|"stone"|"link"|"petals"|"beads"|"weight"|"size",
              "direction": "up"|"down", "step": "slight"|"normal"|"large",
              "amount": number|null, "unit": "mm"|"g"|"%"|null}]}
Use amount only when the customer wrote that exact number. Never invent numbers."""

_LLM_TARGET = {"thickness": "thickness_mm", "width": "width_mm", "flower": "size:flower",
               "stone": "size:stone", "link": "size:link", "size": "size:piece",
               "petals": "petals", "beads": "bead_count", "weight": "weight"}


class _LLMChange(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    target: Literal["thickness", "width", "flower", "stone", "link", "petals", "beads", "weight", "size"]
    direction: Literal["up", "down"]
    step: Literal["slight", "normal", "large"] = "normal"
    amount: Optional[float] = Field(None, gt=0, le=100)
    unit: Optional[Literal["mm", "g", "%"]] = None


class _LLMEdit(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pick: Optional[Pick] = None
    changes: list[_LLMChange] = Field(default_factory=list, max_length=4)


def _written(amount: float, text: str) -> bool:
    """The number appears in the customer's own words (so it is theirs, not the model's)."""
    return any(math.isclose(float(n), amount) for n in re.findall(r"\d+(?:\.\d+)?", text))


def parse_llm(text: str, runner=None) -> Optional[EditRequest]:
    raw = llm.complete_json(LLM_SYSTEM, text[:500], max_tokens=300, runner=runner)
    if not isinstance(raw, dict):
        return None
    try:
        e = _LLMEdit(**raw)
    except (ValidationError, TypeError):
        return None
    changes, weight = [], None
    for c in e.changes:
        if c.amount is not None and not _written(c.amount, text):
            return None                     # a number the customer never said: reject it all
        built = _to_change(_LLM_TARGET[c.target], c.direction, c.amount, c.unit, c.step)
        if built is None:
            return None
        if isinstance(built, WeightChange):
            weight = built
        else:
            changes.append(built)
    if e.pick is None and not changes and weight is None:
        return None
    return EditRequest(pick=e.pick, changes=changes, weight=weight, source="llm")


def understand(text: str, runner=None) -> Optional[EditRequest]:
    """Rules first; the LLM only when the rules find no change (and only if configured).
    A variant the rules picked wins over the model's."""
    r = parse(text)
    if r is not None and not r.empty:
        return r
    m = parse_llm(text, runner)
    if m is None:
        return r
    if r is not None and r.pick:
        m = m.model_copy(update={"pick": r.pick})
    return m


def pick_index(pick: Pick, n: int) -> int:
    return {"first": 0, "middle": n // 2, "last": n - 1}[pick]


# ------------------------------------------------------------------ patching

class EditRefused(ValueError):
    """The edit can't apply to this design (no such feature, or outside the castable range)."""

    def __init__(self, kind: str, detail: str = ""):
        super().__init__(kind)
        self.kind, self.detail = kind, detail


def power(spec: DesignSpec, name: str) -> float:
    return FAMILY_POWER.get((spec.family, name), POWER.get(name, 0.0))


def get(spec: DesignSpec, name: str) -> float:
    if name.startswith("params."):
        return float(spec.params[name.split(".", 1)[1]])
    return float(getattr(spec, name))


def _resolve_field(spec: DesignSpec, name: str) -> str:
    """Which field a customer word names on this design; EditRefused if the design has none."""
    if name == "flower":
        if "flower_d" in spec.params:
            return "params.flower_d"
        if (spec.piece_type == "ring" and spec.motif == "floral") or \
                (spec.piece_type == "pendant" and spec.shape == "lotus" and not spec.family) or \
                spec.family in ("earring_floral_stud", "nosepin_flower", "ring_floral_cluster"):
            return "size_mm"
        raise EditRefused("no_flower")
    if name == "gem_d_mm" and spec.gem == "none":
        raise EditRefused("no_stone")
    if name == "link_w_mm" and spec.piece_type != "chain":
        raise EditRefused("not_applicable", "link")
    if name == "bead_count" and spec.motif != "beaded":
        raise EditRefused("not_applicable", "beads")
    if name == "size_mm" and spec.piece_type in ("ring", "bangle") and spec.motif != "floral" \
            and not spec.family:
        raise EditRefused("ring_size")      # the finger/wrist size is the brief's, not an edit
    if name == "width_mm" and spec.piece_type not in ("ring", "bangle"):
        raise EditRefused("not_applicable", "width")
    if name.startswith("params.") and name.split(".", 1)[1] not in spec.params:
        raise EditRefused("not_applicable", name)
    return name


def _with(spec: DesignSpec, values: dict) -> dict:
    d = spec.model_dump()
    d["params"] = dict(d["params"])
    for k, v in values.items():
        if k.startswith("params."):
            d["params"][k.split(".", 1)[1]] = v
        else:
            d[k] = v
    return d


@dataclass
class Patched:
    spec: DesignSpec                         # the patched spec, at the base version's scale
    locked: dict[str, float]                 # field → finished value the re-solve must keep
    shown: dict[str, tuple[float, float]]    # field → (finished before, finished after)
    base_scale: float
    weight: Optional[WeightChange] = None


def apply(spec: DesignSpec, scale: float, req: EditRequest) -> Patched:
    """Patch `spec` (solved at `scale`). Each change is applied to the *finished* value."""
    values, locked, shown = {}, {}, {}
    for c in req.changes:
        name = _resolve_field(spec, c.field)
        p = power(spec, name)
        k = scale ** p
        cur = values.get(name, get(spec, name))
        before = cur * k
        after = before + c.amount if c.op == "add" else before * c.amount
        if name in INT_FIELDS:
            after = float(round(after))
            if after == before:
                after = before + (1 if c.amount > (0 if c.op == "add" else 1) else -1)
        if after <= 0:
            raise EditRefused("out_of_range", name)
        values[name] = int(after) if name in INT_FIELDS else after / k
        if p > 0:
            locked[name] = after
        shown[name] = (shown.get(name, (before, None))[0], after)
    try:
        new = DesignSpec.model_validate(_with(spec, values))
    except ValidationError as e:
        raise EditRefused("out_of_range", "; ".join(err["msg"] for err in e.errors())[:200]) from None
    return Patched(new, locked, shown, scale, req.weight)


def at_scale(spec: DesignSpec, s: float, locked: dict[str, float]) -> DesignSpec:
    """The spec whose locked fields give their finished value at scale `s` (unvalidated probe)."""
    if not locked:
        return spec
    vals = {k: v / s ** power(spec, k) for k, v in locked.items()}
    d = _with(spec, vals)
    return spec.model_copy(update={k: d[k] for k in d if k in DesignSpec.model_fields})


def diff(a: dict, b: dict) -> dict[str, list]:
    """Spec fields that differ between two spec dicts: {field: [a, b]} (params as params.<k>)."""
    out = {}
    for k in sorted(set(a) | set(b)):
        if k == "params":
            pa, pb = a.get("params", {}) or {}, b.get("params", {}) or {}
            for pk in sorted(set(pa) | set(pb)):
                if pa.get(pk) != pb.get(pk):
                    out[f"params.{pk}"] = [pa.get(pk), pb.get(pk)]
        elif a.get(k) != b.get(k):
            out[k] = [a.get(k), b.get(k)]
    return out


def finished_dims(spec: DesignSpec, scale: float) -> dict[str, float]:
    """Finished value of every editable field the design uses (code numbers, for the report)."""
    out = {}
    for name in EDITABLE:
        try:
            v = get(spec, name)
        except (KeyError, AttributeError):
            continue
        out[name] = v * scale ** power(spec, name)
    return out


# ------------------------------------------------------------------ re-solve

def resolve(spec: DesignSpec, plan, locked: dict[str, float], base_scale: float, on_iter=None):
    """Solve the patched spec to `plan.target_value`, holding `locked` finished values.

    The scale then moves only the unlocked dimensions (the band). Casting rules are checked on
    the spec as it will be built at the solved scale; the checks list is rerun for the job card.
    """
    from karigar.core import gold as G
    from karigar.core.registry import Solved
    from karigar.core.solver import solve_monotone

    from . import dfm, geometry
    from . import solve_failure

    lo, hi = dfm.scale_bounds(at_scale(spec, base_scale, locked))
    if lo > hi:
        return Solved(spec, False, base_scale, 0.0, plan.target_value, 0,
                      explanation="This change can't be cast safely with this design.",
                      binding_constraint="edited dimension vs. minimum castable proportions",
                      best_achievable={"value": 0.0, "unit": "g"},
                      alternatives=["a smaller change", "another design from the set"])
    f = lambda s: G.mm3_to_grams(geometry.gold_volume(at_scale(spec, s, locked), s), spec.karat)
    r = solve_monotone(f, plan.target_value, lo, hi, on_iter=on_iter)
    final = at_scale(spec, r.scale, locked)
    if not r.ok:
        fail = solve_failure(r, plan.detail["casting_loss_pct"])
        return Solved(final, False, r.scale, r.value, r.target, len(r.iterations), **fail)
    lo2, hi2 = dfm.scale_bounds(final)
    if not lo2 - LOCK_TOL <= r.scale <= hi2 + LOCK_TOL:
        loss = plan.detail["casting_loss_pct"]
        return Solved(final, False, r.scale, r.value, r.target, len(r.iterations),
                      explanation="Keeping the gold weight with this change pushes the rest of the "
                                  "piece outside the casting rules.",
                      binding_constraint="casting rules after re-solving the edited design",
                      best_achievable={"value": round(r.value * (1 - loss / 100), 2), "unit": "g"},
                      alternatives=["a smaller change", "change the weight as well (lighter/heavier)"])
    final = DesignSpec.model_validate(final.model_dump())
    return Solved(final, True, r.scale, r.value, r.target, len(r.iterations),
                  issues=dfm.check(final, r.scale))


def retarget(plan, base_modelled_g: float, w: WeightChange):
    """A copy of `plan` aimed at the edited finished weight (from the base version's weight)."""
    import copy
    loss = plan.detail["casting_loss_pct"]
    fin = base_modelled_g * (1 - loss / 100)
    new_fin = fin + w.amount if w.op == "add" else fin * w.amount
    if new_fin <= 0:
        raise EditRefused("out_of_range", "weight")
    p = copy.deepcopy(plan)
    p.target_value = new_fin / (1 - loss / 100)
    p.detail = {**p.detail, "mode": "edit", "finished_gross_g": new_fin,
                "design_gross_g": p.target_value}
    return p


# ------------------------------------------------------------------ report

LABEL = {"thickness_mm": "thickness", "width_mm": "width", "size_mm": "size", "gem_d_mm": "stone",
         "petals": "petals", "bead_count": "beads", "link_w_mm": "link width",
         "params.flower_d": "flower"}

REFUSED = {
    "no_flower": {"en": "This design has no flower to change. Try thinner/thicker, wider, or lighter/heavier.",
                  "hinglish": "Is design mein phool nahi hai. Patla/mota, chauda, ya halka/bhaari bol sakte hain."},
    "no_stone": {"en": "This design has no stone to resize.",
                 "hinglish": "Is design mein nag nahi hai."},
    "ring_size": {"en": "The ring/bangle size comes from the customer's size; send the new size as a new order.",
                  "hinglish": "Ring/kangan ka size customer ke naap se aata hai; naya size naye order mein bhejiye."},
    "not_applicable": {"en": "That change doesn't apply to this design ({detail}).",
                       "hinglish": "Yeh badlav is design par nahi hota ({detail})."},
    "out_of_range": {"en": "That change goes outside what this design can be made at ({detail}).",
                     "hinglish": "Itna badlav is design mein nahi ho sakta ({detail})."},
}
HELP = {
    "en": ("I didn't catch the change. Say e.g. \"make it 0.5 mm thinner\", \"wider\", "
           "\"flower slightly bigger\", \"1 g lighter\", and which design (first, middle, last)."),
    "hinglish": ("Badlav samajh nahi aaya. Jaise: \"0.5 mm patla karo\", \"chauda\", "
                 "\"phool thoda bada\", \"1 g halka\", aur kaunsa design (pehla, beech wala, teesra)."),
}
WHICH = {
    "en": "Which design should I change: the first, the middle or the last one?",
    "hinglish": "Kaunsa design badlun: pehla, beech wala ya teesra?",
}


def refused_text(e: EditRefused, lang: str) -> str:
    t = REFUSED[e.kind]
    return t.get(lang, t["en"]).format(detail=LABEL.get(e.detail, e.detail))


def report(base_v: int, new_v: int, base_spec: DesignSpec, base_scale: float, base_modelled: float,
           solved, patched: Patched, q_before: dict, q_after: dict, loss_pct: float, lang: str) -> dict:
    """v_base → v_new: changed fields (finished values), what the re-solve moved, weight Δ, price Δ.
    Every number is from code: the solver, the geometry fields and pricing.quote."""
    from .pricing import inr

    rnd = lambda x: round(x, 2)
    changed = {k: {"from": rnd(a), "to": rnd(b)} for k, (a, b) in patched.shown.items()}
    before = finished_dims(base_spec, base_scale)
    after = finished_dims(solved.spec, solved.scale)
    moved = {k: {"from": rnd(before[k]), "to": rnd(after[k])} for k in before
             if k in after and k not in changed and abs(after[k] - before[k]) >= 0.005}
    w0 = base_modelled * (1 - loss_pct / 100)
    w1 = solved.value * (1 - loss_pct / 100)
    weight = {"from": round(w0, 3), "to": round(w1, 3), "delta": round(w1 - w0, 3)}
    price = {"from": q_before["total"], "to": q_after["total"], "delta": q_after["total"] - q_before["total"]}
    out = {"from_version": base_v, "to_version": new_v, "changed": changed, "resolved": moved,
           "kept_gold_target": patched.weight is None, "weight_g": weight, "price_inr": price,
           "spec_diff": diff(base_spec.model_dump(), solved.spec.model_dump())}
    if "to_pay" in q_after and "to_pay" in q_before:
        out["to_pay_inr"] = {"from": q_before["to_pay"], "to": q_after["to_pay"],
                             "delta": q_after["to_pay"] - q_before["to_pay"]}
    unit = lambda k: "" if k in INT_FIELDS else " mm"
    parts = [f"{LABEL.get(k, k)} {v['from']:g}{unit(k)} → {v['to']:g}{unit(k)}" for k, v in changed.items()]
    rs = [f"{LABEL.get(k, k)} {v['from']:g} → {v['to']:g} mm" for k, v in moved.items()]
    sgn = lambda x: f"+{x:.2f}" if x >= 0 else f"{x:.2f}"
    dp = price["delta"]
    money = ("+" if dp >= 0 else "−") + inr(abs(dp))
    head = ", ".join(parts) or ("wazan badla" if lang == "hinglish" else "weight changed")
    if lang == "hinglish":
        txt = (f"v{new_v} (v{base_v} se): " + head
               + (f". Sona wahi rakhne ke liye band dobara solve kiya: {', '.join(rs)}" if rs and patched.weight is None else "")
               + f". Wazan {w0:.2f} g → {w1:.2f} g ({sgn(w1 - w0)} g), daam {inr(price['from'])} → "
               f"{inr(price['to'])} ({money}).")
    else:
        txt = (f"v{new_v} (from v{base_v}): " + head
               + (f". Band re-solved to keep the gold: {', '.join(rs)}" if rs and patched.weight is None else "")
               + f". Weight {w0:.2f} g → {w1:.2f} g ({sgn(w1 - w0)} g), price {inr(price['from'])} → "
               f"{inr(price['to'])} ({money}).")
    out["summary"] = txt
    return out
