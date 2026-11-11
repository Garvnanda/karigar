"""Jauhari's desk: targets from exchange / weight / budget, and the quote."""
from __future__ import annotations

import json
from pathlib import Path

from karigar.core import gold as G
from karigar.core.registry import Plan

from .schema import Brief, DesignSpec, gem_ct_from_d, gem_d_from_ct

RATE_CARD = Path(__file__).resolve().parents[3] / "data" / "rate_card.json"


def rate_card() -> dict:
    return json.loads(RATE_CARD.read_text())


def inr(x: float) -> str:
    """Indian digit grouping: 1,23,456."""
    s = f"{abs(round(x)):d}"
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        s = ",".join(parts + [tail])
    return ("-₹" if x < 0 else "₹") + s


def stone_cost(gem: str, ct: float, rc: dict) -> float:
    return 0.0 if gem == "none" else ct * rc["stone_rate_per_ct"][gem]


def requested_ct(brief: Brief) -> float:
    if brief.gem == "none":
        return 0.0
    if brief.gem_ct:
        return brief.gem_ct
    return {"ring": 0.5, "pendant": 0.25, "bangle": 0.0}[brief.piece_type]


def plan(brief: Brief, loss_pct: float) -> Plan:
    rc = rate_card()
    k = brief.karat
    rate = rc["gold_rate_per_g"][str(k)]
    mk = rc["making_charge_pct"][brief.piece_type] / 100
    gst = rc["gst_pct"] / 100
    ct = requested_ct(brief)
    stones = stone_cost(brief.gem, ct, rc)
    min_w = rc["min_finished_weight_g"][brief.piece_type]

    if brief.old_gold:
        og = brief.old_gold
        t = G.target_from_exchange(og.weight_g, og.karat, k, loss_pct,
                                   rc["exchange"]["melt_loss_pct"], og.tested_purity)
        mode = "exchange"
        head = (f"Your {og.weight_g:g} g of {og.karat}K carries {t.fine_g:.2f} g of pure gold after "
                f"testing and melting. That makes a {k}K piece of {t.finished_gross_g:.2f} g finished.")
    elif brief.target_weight_g:
        t = G.target_from_gross(brief.target_weight_g, k, loss_pct)
        mode = "weight"
        head = f"Target finished weight {t.finished_gross_g:.2f} g in {k}K."
    elif brief.budget_inr:
        mode = "budget"
        gold_budget = brief.budget_inr / (1 + gst) - stones
        if gold_budget <= 0:
            alt_ct = (brief.budget_inr / (1 + gst) * 0.45) / rc["stone_rate_per_ct"].get(brief.gem, 1)
            plain_g = brief.budget_inr / (1 + gst) / (rate * (1 + mk))
            min_price = min_w * rate * (1 + mk) * (1 + gst)
            opts = []
            if plain_g >= min_w:
                opts.append(f"a plain {k}K {brief.piece_type} of about {plain_g:.1f} g")
            else:
                opts.append(f"even a plain {k}K {brief.piece_type} needs at least {min_w} g "
                            f"(about {inr(min_price)}), so a higher budget or 14K gold")
            if alt_ct >= 0.05 and plain_g * 0.55 >= min_w:
                opts.append(f"a {alt_ct:.2f} ct {brief.gem} with the rest in gold")
            if plain_g >= min_w and brief.gem == "diamond":
                opts.append("a ruby or emerald instead of a diamond")
            expl = (f"I can't do that one honestly: a {ct:g} ct {brief.gem} alone costs about {inr(stones)} "
                    f"before tax, more than the {inr(brief.budget_inr)} budget. Closest options: "
                    + "; ".join(f"({i}) {o}" for i, o in enumerate(opts, 1)) + ". Which would you like?")
            return Plan(False, explanation=expl, detail={"mode": mode, "stones_inr": stones})
        w = gold_budget / (rate * (1 + mk))
        t = G.target_from_gross(w, k, loss_pct)
        head = f"Budget {inr(brief.budget_inr)} buys {w:.2f} g of {k}K after making charges, stones and GST."
    else:
        return Plan(False, explanation="Tell me the old gold weight, a target weight, or a budget.")

    if t.finished_gross_g < min_w:
        if mode == "budget":
            fix = (f"a smaller stone (about {max(0.05, ct * 0.4):.2f} ct), 14K gold, or a budget of about "
                   f"{inr((min_w * rate * (1 + mk) + stones) * (1 + gst))}")
        else:
            fix = (f"a pendant (needs only {rc['min_finished_weight_g']['pendant']} g), 14K gold for more "
                   f"volume per gram, or adding a little gold")
        expl = (f"That leaves {t.finished_gross_g:.2f} g of gold, below the {min_w} g minimum for a "
                f"{brief.piece_type} that survives daily wear. Options: {fix}.")
        return Plan(False, explanation=expl, detail={"mode": mode, **t.as_dict()})

    summary = (f"{head} Workshop loss {loss_pct:.1f}%, so Karigar models {t.design_gross_g:.2f} g.")
    return Plan(True, target_value=t.design_gross_g, unit="g", summary=summary,
                detail={"mode": mode, "requested_ct": ct, **t.as_dict()})


def quote(spec: DesignSpec, modelled_g: float, brief: Brief, p: Plan) -> dict:
    rc = rate_card()
    k = spec.karat
    loss = p.detail["casting_loss_pct"]
    finished = modelled_g * (1 - loss / 100)
    rate = rc["gold_rate_per_g"][str(k)]
    gold_val = finished * rate
    making = gold_val * rc["making_charge_pct"][spec.piece_type] / 100
    ct = spec.gem_ct
    stones = stone_cost(spec.gem, ct, rc)
    sub = gold_val + making + stones
    gst = sub * rc["gst_pct"] / 100
    total = sub + gst
    q = {
        "design": spec.name, "karat": k, "metal": spec.metal,
        "finished_weight_g": round(finished, 2), "modelled_weight_g": round(modelled_g, 2),
        "gold_rate_per_g": rate, "gold_value": round(gold_val),
        "making_charges": round(making), "stone": f"{ct:.2f} ct {spec.gem}" if spec.gem != "none" else "none",
        "stone_value": round(stones), "gst": round(gst), "total": round(total),
        "rate_card_as_of": rc["as_of"],
    }
    if brief.old_gold:
        credit = p.detail["fine_g"] / G.purity(24) * rc["gold_rate_per_g"]["24"]
        q["exchange_credit"] = round(credit)
        q["to_pay"] = round(total - credit)
        q["summary"] = (f"{spec.name}: {finished:.2f} g {k}K"
                        f"{', ' + q['stone'] if spec.gem != 'none' else ''}. Total {inr(total)}, "
                        f"old gold credit {inr(credit)}, you pay {inr(total - credit)} "
                        f"(mostly making charges{', stone' if stones else ''} and GST).")
    else:
        q["summary"] = f"{spec.name}: {finished:.2f} g {k}K. Total {inr(total)} incl. GST."
    return q
