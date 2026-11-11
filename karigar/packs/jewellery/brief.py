"""Sakhi at the counter: turn a customer's words (English/Hinglish) into a Brief,
or ask one follow-up question when something essential is missing."""
from __future__ import annotations

import re

from pydantic import ValidationError

from karigar.core import llm

from .schema import Brief


def inr(x):
    from .pricing import inr as _inr
    return _inr(x)

PIECE_WORDS = {
    "ring": r"\b(ring|anguthi|angoothi|solitaire)\b",
    "bangle": r"\b(bangle|kada|kara|kangan|chudi|churi|bracelet)\b",
    "pendant": r"\b(pendant|locket|lotus pendant)\b",
}
GEM_WORDS = {
    "diamond": r"\b(diamond|heera|solitaire)\b", "ruby": r"\b(ruby|manik|manikya)\b",
    "emerald": r"\b(emerald|panna)\b", "sapphire": r"\b(sapphire|neelam)\b",
}
OLD_WORDS = r"\b(old|purana|purani|exchange|grandm\w*|nani|dadi|mummy|mom'?s|melt|trade)\b"

SYSTEM = """You are Sakhi, the counter assistant of an Indian jewellery shop.
Extract the customer's request into JSON with these keys (omit unknown ones):
piece_type: "ring"|"bangle"|"pendant"; karat (new piece): 22|18|14; metal: "yellow"|"rose"|"white";
old_gold: {weight_g, karat (24|22|18|14), tested_purity (0-1, only if a test result is given)};
target_weight_g (finished weight, only if they ask for a weight and have no old gold);
budget_inr; gem: "none"|"diamond"|"ruby"|"emerald"|"sapphire"; gem_ct;
ring_inner_d_mm; bangle_inner_d_mm; style: list of words like lotus, beaded, plain, knife, faceted, minimal.
Indian bangle sizes like 2-6 mean 2 6/16 inch inner diameter. "22 carat" means karat 22, not gem carats.
If the piece type is unclear, or there is no old gold, weight or budget, add "question": one short
follow-up question in the customer's language."""


def _num(s: str) -> float:
    return float(s.replace(",", ""))


def _regex_parse(text: str) -> dict:
    t = text.lower()
    d: dict = {"style": []}
    for piece, pat in PIECE_WORDS.items():
        if re.search(pat, t):
            d["piece_type"] = piece
            break
    for g, pat in GEM_WORDS.items():
        if re.search(pat, t):
            d["gem"] = g
            break
    kms = list(re.finditer(r"\b(24|22|18|14)\s*-?\s*(k|kt|karat|carat|ct)\b", t))
    gem_ct = re.search(r"\b(\d+(?:\.\d+)?)\s*(?:ct|carat|cts)\b", t)
    if gem_ct and _num(gem_ct.group(1)) < 6:
        d["gem_ct"] = _num(gem_ct.group(1))
        d.setdefault("gem", "diamond")
    grams = re.search(r"(\d+(?:\.\d+)?)\s*(?:g|gm|gms|gram|grams)\b", t)
    is_old = bool(re.search(OLD_WORDS, t))
    if grams and is_old:
        # The karat mentioned nearest the old-gold weight describes the old gold.
        near = min(kms, key=lambda m: abs(m.start() - grams.start()), default=None)
        d["old_gold"] = {"weight_g": _num(grams.group(1)), "karat": int(near.group(1)) if near else 22}
        others = [int(m.group(1)) for m in kms if m is not near and m.group(1) != "24"]
        if others:
            d["karat"] = others[0]
        elif near and near.group(1) != "24":
            d["karat"] = int(near.group(1))
    else:
        if grams:
            d["target_weight_g"] = _num(grams.group(1))
        news = [int(m.group(1)) for m in kms if m.group(1) != "24"]
        if news:
            d["karat"] = news[0]
    tested = re.search(r"test\w*\D{0,12}(\d{2}(?:\.\d+)?)\s*%", t)
    if tested and "old_gold" in d:
        d["old_gold"]["tested_purity"] = _num(tested.group(1)) / 100
    lakh = re.search(r"(\d+(?:\.\d+)?)\s*(?:lakh|lac)", t)
    kbud = re.search(r"(?:₹|rs\.?|inr|budget|under|within)\s*(\d[\d,]*(?:\.\d+)?)\s*(k)?\b", t)
    if lakh:
        d["budget_inr"] = _num(lakh.group(1)) * 100000
    elif kbud:
        d["budget_inr"] = _num(kbud.group(1)) * (1000 if kbud.group(2) else 1)
    for m in ("rose", "white", "yellow"):
        if m in t:
            d["metal"] = m
    bsize = re.search(r"\b2[-.](\d{1,2})\b", t)
    if bsize and d.get("piece_type") == "bangle":
        d["bangle_inner_d_mm"] = round((2 + int(bsize.group(1)) / 16) * 25.4, 1)
    rsize = re.search(r"size\s*(\d+(?:\.\d+)?)\s*(mm)?", t)
    if rsize and d.get("piece_type") == "ring":
        v = _num(rsize.group(1))
        d["ring_inner_d_mm"] = v if rsize.group(2) or v > 12 else round(11.63 + 0.8128 * v, 1)  # US size
    for w in ("lotus", "kamal", "beaded", "plain", "minimal", "knife", "faceted", "coin", "flat"):
        if w in t:
            d["style"].append("lotus" if w == "kamal" else w)
    return d


def parse(text: str) -> tuple[Brief | None, str | None]:
    d = llm.complete_json(SYSTEM, text) or _regex_parse(text)
    q = d.pop("question", None)
    if "piece_type" not in d:
        return None, q or "What would you like made: a ring, a bangle or a pendant?"
    if not any(d.get(k) for k in ("old_gold", "target_weight_g", "budget_inr")):
        return None, q or ("How should I size it? Tell me your old gold's weight and karat, "
                           "a target weight, or a budget.")
    assumptions = []
    if d["piece_type"] == "ring" and "ring_inner_d_mm" not in d:
        assumptions.append("Ring size assumed 17.3 mm inner diameter (US 7). Tell me yours to change it.")
    if d["piece_type"] == "bangle" and "bangle_inner_d_mm" not in d:
        assumptions.append("Bangle size assumed 2-6 (60.3 mm). Tell me yours to change it.")
    d["assumptions"] = assumptions
    try:
        return Brief(**{k: v for k, v in d.items() if v is not None}), None
    except ValidationError as e:
        field = e.errors()[0]["loc"][0]
        return None, f"I couldn't read the {field} correctly. Could you say it again?"


def describe(b: Brief) -> str:
    src = (f"{b.old_gold.weight_g:g} g old {b.old_gold.karat}K gold" if b.old_gold
           else f"{b.target_weight_g:g} g" if b.target_weight_g else f"a budget of {inr(b.budget_inr)}")
    gem = f", {b.gem}{f' {b.gem_ct:g} ct' if b.gem_ct else ''}" if b.gem != "none" else ""
    style = f", style: {', '.join(b.style)}" if b.style else ""
    s = f"{'An' if b.karat == 18 else 'A'} {b.karat}K {b.metal} gold {b.piece_type} from {src}{gem}{style}."
    if b.assumptions:
        s += " " + " ".join(b.assumptions)
    return s
