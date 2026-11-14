"""Jauhari's desk: targets from exchange / weight / budget, and the quote.

Quote (Phase 5, decisions.md "Shop numbers" + "Phase 5 quote"):
  gold value  = finished weight (mg precision) × gold rate for the karat (RateSource)
  making      = gold value × making % (3.5%, per piece type in rate_card.json)
  stones      = carats (2 dp) × rate card ₹/ct
  hallmarking = ₹75 per article (an earring pair is 2 articles)
  GST         = 3% on gold + stones, 5% on making (custom piece); none on the hallmark fee
  old gold    = weight × purity × 24K rate − 2% deduction (the only deduction)
Every amount is whole rupees, rounded half-up per line; the total is the sum of the lines,
so the same inputs give the same quote to the rupee. Every line names its source and says
whether its number is assumed. The gold rate and its timestamp come from the plan (read once
through `rates.RateSource`), never from the LLM and never estimated.
"""
from __future__ import annotations

import math
from decimal import ROUND_HALF_UP, Decimal

from karigar.core import gold as G
from karigar.core.registry import Plan

from . import rates as R
from .rates import RATE_CARD, rate_card  # noqa: F401  (re-exported: callers use pricing.rate_card)
from .schema import Brief, DesignSpec


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


DEFAULT_CT = {"ring": 0.5, "pendant": 0.25, "bangle": 0.0}  # stated to the customer by brief.py


def requested_ct(brief: Brief) -> float:
    if brief.gem == "none":
        return 0.0
    if brief.gem_ct:
        return brief.gem_ct
    return DEFAULT_CT.get(brief.piece_type, 0.0)   # no sourced default for the Phase 2.5 pieces


def articles(piece_type: str, pair: bool = True) -> int:
    """Articles hallmarked (HUID) separately: an earring pair is two."""
    return 2 if piece_type == "earring" and pair else 1


def weights(modelled_g: float, p: Plan) -> dict:
    """What every result reports about weight (Phase 3): the casting (modelled, stone seats cut)
    weight, the expected finished weight after the workshop's loss, that loss, and the +- band
    on the finished weight (plan.detail['tolerance'] from the workshop's calibration records, else
    the configured default; core/gold.tolerance). Code and data only."""
    loss = p.detail["casting_loss_pct"]
    fin = modelled_g * (1 - loss / 100)
    tol = p.detail.get("tolerance") or G.tolerance()
    tol_g = fin * tol["pct"] / 100
    return {
        "casting_g": round(modelled_g, 3), "modelled_g": round(modelled_g, 3),
        "finished_g": round(fin, 3), "expected_loss_g": round(modelled_g - fin, 3),
        "expected_loss_pct": round(loss, 2), "tolerance_g": round(tol_g, 2),
        "tolerance_pct": round(tol["pct"], 2),
    }


def weight_text(w: dict) -> str:
    """'7.60 g ± 0.30 g finished (cast 7.84 g, expected loss 0.24 g = 3%)'."""
    fin = w["casting_g"] * (1 - w["expected_loss_pct"] / 100)     # one rounding, not two
    return (f"{fin:.2f} g ± {w['tolerance_g']:.2f} g finished "
            f"(cast {w['casting_g']:.2f} g, expected loss {w['expected_loss_g']:.2f} g = "
            f"{w['expected_loss_pct']:g}%)")


def _gst(rc: dict) -> tuple[float, float]:
    g = rc["gst_pct"]
    return g["gold_and_stones"] / 100, g["making"] / 100


def _rate_problem_plan(e: R.RateProblem) -> Plan:
    return Plan(False, explanation=e.reply("en"), detail={"rate_problem": e.kind, "karat": e.karat},
                binding_constraint=f"gold rate: {e.karat}K rate {e.kind.replace('_', ' ')}",
                best_achievable={"value": 0.0, "unit": "g"},
                alternatives=["update today's gold rate (rate job or owner), then send the order again",
                              "ask the shop owner for today's rate"])


def plan(brief: Brief, loss_pct: float, source: R.RateSource | None = None, now=None) -> Plan:
    rc = rate_card()
    k = brief.karat
    try:
        gr = (source or R.rate_source()).get_many(R.karats_needed(k, bool(brief.old_gold)), now)
    except R.RateProblem as e:
        return _rate_problem_plan(e)
    rate = gr[k].per_g
    mk = rc["making_charge_pct"][brief.piece_type] / 100
    gg, gm = _gst(rc)
    hall = rc["hallmark_fee_inr_per_article"] * articles(brief.piece_type)
    unit = rate * ((1 + gg) + mk * (1 + gm))        # all-in rupees per finished gram of gold
    ct = requested_ct(brief)
    stone_rate = rc["stone_rate_per_ct"].get(brief.gem, 1)
    stones = stone_cost(brief.gem, ct, rc)
    stones_in = stones * (1 + gg)
    # Phase 2.5 pieces have no sourced minimum yet (QUESTIONS): no minimum is enforced for them.
    min_known = brief.piece_type in rc["min_finished_weight_g"]
    min_w = rc["min_finished_weight_g"].get(brief.piece_type, 0.0)
    rate_detail = {str(kk): v.as_dict() for kk, v in gr.items()}

    if brief.old_gold:
        og = brief.old_gold
        t = G.target_from_exchange(og.weight_g, og.karat, k, loss_pct, rc["old_gold_deduction_pct"])
        mode = "exchange"
        head = (f"Your {og.weight_g:g} g of {og.karat}K carries {t.fine_g:.2f} g of pure gold after "
                f"the {rc['old_gold_deduction_pct']:g}% deduction. That makes a {k}K piece of "
                f"{t.finished_gross_g:.2f} g finished.")
    elif brief.target_weight_g:
        t = G.target_from_gross(brief.target_weight_g, k, loss_pct)
        mode = "weight"
        head = f"Target finished weight {t.finished_gross_g:.2f} g in {k}K."
    elif brief.budget_inr:
        mode = "budget"
        money = brief.budget_inr - hall
        gold_budget = money - stones_in
        if gold_budget <= 0:
            alt_ct = (money * 0.45) / (stone_rate * (1 + gg))
            plain_g = money / unit
            min_price = min_w * unit + hall
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
            needed = min_w * unit + stones_in + hall
            if len(opts) < 2:
                opts.append(f"a budget of about {inr(needed)} for this {ct:g} ct {brief.gem} "
                            f"in a {f'{min_w} g ' if min_known else ''}{k}K {brief.piece_type}")
            # Largest stone the budget covers once the lightest wearable piece is paid for.
            room = money - min_w * unit
            best_ct = max(0.0, room / (stone_rate * (1 + gg)))
            expl = (f"I can't do that one honestly: a {ct:g} ct {brief.gem} alone costs about {inr(stones)} "
                    f"before tax, more than the {inr(brief.budget_inr)} budget. Closest options: "
                    + "; ".join(f"({i}) {o}" for i, o in enumerate(opts, 1)) + ". Which would you like?")
            return Plan(False, explanation=expl, detail={"mode": mode, "stones_inr": stones},
                        binding_constraint="budget: the stone alone costs more than the budget",
                        best_achievable={"value": round(best_ct, 2), "unit": "ct"},
                        alternatives=opts)
        w = math.floor(gold_budget / unit * 1000) / 1000   # whole mg, so the bill never tops the budget
        t = G.target_from_gross(w, k, loss_pct)
        head = (f"Budget {inr(brief.budget_inr)} buys {w:.2f} g of {k}K after making charges, stones, "
                f"hallmarking and GST.")
    else:
        return Plan(False, explanation="Tell me the old gold weight, a target weight, or a budget.",
                    binding_constraint="no target: no old gold, weight or budget given",
                    best_achievable={"value": 0.0, "unit": "g"},
                    alternatives=["your old gold's weight and karat", "a target finished weight",
                                  "a budget"])

    if min_known and t.finished_gross_g < min_w:
        if mode == "budget":
            alts = [f"a smaller stone (about {max(0.05, ct * 0.4):.2f} ct)", "14K gold",
                    f"a budget of about {inr(min_w * unit + stones_in + hall)}"]
        else:
            alts = [f"a pendant (needs only {rc['min_finished_weight_g']['pendant']} g)",
                    "14K gold for more volume per gram", "adding a little gold"]
        if brief.piece_type == "pendant":
            alts = [a for a in alts if not a.startswith("a pendant")]
        expl = (f"That leaves {t.finished_gross_g:.2f} g of gold, below the {min_w} g minimum for a "
                f"{brief.piece_type} that survives daily wear. Options: {', '.join(alts[:-1])}, or {alts[-1]}.")
        # The closest thing that can be made is the minimum itself (a budget buys less gold, so
        # there the closest is what the money buys).
        best = t.finished_gross_g if mode == "budget" else min_w
        return Plan(False, explanation=expl,
                    detail={"mode": mode, "min_weight_g": min_w, "requested_ct": ct, **t.as_dict()},
                    binding_constraint=f"minimum finished weight for a {brief.piece_type} ({min_w} g)",
                    best_achievable={"value": round(best, 2), "unit": "g"},
                    alternatives=alts)

    summary = (f"{head} Workshop loss {loss_pct:.1f}%, so Karigar models {t.design_gross_g:.2f} g. "
               f"Gold rate {k}K {inr(rate)}/g as of {R._shown_time(gr[k].set_at)} ({gr[k].source}).")
    detail = {"mode": mode, "requested_ct": ct, "gold_rate": rate_detail, "tolerance": G.tolerance(),
              **t.as_dict()}
    if mode == "budget" and brief.gem != "none" and not brief.gem_ct:
        # No stone size named: the stone and the gold are solved together per design
        # (JewelleryPack.solve), so the bill lands on the budget; this target is only a start.
        detail["joint_stone"] = True
        detail["budget_inr"] = brief.budget_inr
    return Plan(True, target_value=t.design_gross_g, unit="g", summary=summary, detail=detail)


# ---------------------------------------------------------------- quote

def _d(x) -> Decimal:
    return Decimal(str(x))


def rupees(x: Decimal) -> int:
    """Whole rupees, half-up (₹0.50 → ₹1), the way a bill is rounded."""
    return int(x.quantize(Decimal(1), rounding=ROUND_HALF_UP))


ASSUMED = "assumed — confirm with your caster/CA"


def _rate_for(p: Plan, karat: int) -> R.GoldRate:
    """The rate the plan read (same rate and timestamp for plan and quote); else RateSource now."""
    d = (p.detail.get("gold_rate") or {}).get(str(karat))
    if d:
        return R.GoldRate(karat, float(d["per_g"]), d["set_at"], d["source"])
    return R.rate_source().get(karat)


def _source_label(g: R.GoldRate) -> str:
    return {"chat": "set in chat by shop staff", "manual": "set by the shop owner"}.get(
        g.source, f"rate job ({g.source})")


def quote(spec: DesignSpec, modelled_g: float, brief: Brief, p: Plan) -> dict:
    rc = rate_card()
    assumed = set(rc.get("assumed", []))
    k = spec.karat
    loss = p.detail["casting_loss_pct"]
    finished = modelled_g * (1 - loss / 100)
    w = _d(f"{finished:.3f}")                  # billed to the milligram, as shown
    g = _rate_for(p, k)
    when = R._shown_time(g.set_at)
    from_job = g.source.startswith("mcx")
    mk_pct = rc["making_charge_pct"][spec.piece_type]
    gg, gm = (_d(v) for v in (rc["gst_pct"]["gold_and_stones"], rc["gst_pct"]["making"]))
    n_art = articles(spec.piece_type, spec.pair)
    hall_fee = rc["hallmark_fee_inr_per_article"]

    lines: list[dict] = []

    def line(key, label, amount, source, is_assumed):
        lines.append({"key": key, "label": label, "amount_inr": amount, "source": source,
                      "assumed": bool(is_assumed)})
        return amount

    gold_v = line("gold", f"Gold {w} g {k}K × {inr(g.per_g)}/g", rupees(w * _d(g.per_g)),
                  f"gold rate {k}K {inr(g.per_g)}/g as of {when}, {_source_label(g)}"
                  + (f" (MCX + ₹{rc['gold_rate']['mcx_premium_per_10g']:,}/10 g, karat factor; {ASSUMED})"
                     if from_job else ""),
                  from_job and "gold_rate_formula" in assumed)
    making = line("making", f"Making charge {mk_pct:g}% of gold value",
                  rupees(_d(gold_v) * _d(mk_pct) / 100),
                  f"rate card: making {mk_pct:g}% for a {spec.piece_type}"
                  + (f" ({ASSUMED})" if "making_charge_pct" in assumed else ""),
                  "making_charge_pct" in assumed)
    stone_assumed = spec.gem != "none" and brief.gem != "none" and not brief.gem_ct
    assumptions = []
    stones = 0
    if spec.gem != "none":
        ct = _d(f"{spec.gem_ct:.2f}")
        per_ct = rc["stone_rate_per_ct"][spec.gem]
        label = f"Stone {ct} ct {spec.gem} × {inr(per_ct)}/ct"
        if stone_assumed and p.detail.get("joint_stone"):
            note = (f"stone size solved with the budget: {ct} ct ({spec.gem_d_mm:.2f} mm), "
                    "stone and gold sized together")
            assumptions.append(note)
            label += f" — {note}"
        elif stone_assumed:
            note = f"stone size assumed: {ct} ct ({spec.gem_d_mm:g} mm, the design's own stone)"
            assumptions.append(note)
            label += f" — {note}"
        stones = line("stones", label, rupees(ct * _d(per_ct)),
                      f"rate card: {spec.gem} {inr(per_ct)}/ct ({rc['stone_note']})"
                      + (f" ({ASSUMED})" if "stone_rate_per_ct" in assumed else ""),
                      stone_assumed or "stone_rate_per_ct" in assumed)
    hall = line("hallmark", f"Hallmarking (BIS HUID) {n_art} × ₹{hall_fee}", hall_fee * n_art,
                "BIS hallmarking fee ₹75/article (BIS Amendment Regulations 2026)"
                + (f"; earring pair = 2 articles ({ASSUMED})" if n_art > 1 else ""),
                n_art > 1 and "hallmark_per_article" in assumed)
    gst_gs = line("gst_gold_stones", f"GST {gg}% on gold + stones", rupees((_d(gold_v) + _d(stones)) * gg / 100),
                  f"GST {gg}% on gold and stones" + (f" ({ASSUMED})" if "gst_pct" in assumed else ""),
                  "gst_pct" in assumed)
    gst_mk = line("gst_making", f"GST {gm}% on making", rupees(_d(making) * gm / 100),
                  f"GST {gm}% on making charges, custom piece" + (f" ({ASSUMED})" if "gst_pct" in assumed else ""),
                  "gst_pct" in assumed)
    total = gold_v + making + stones + hall + gst_gs + gst_mk

    wt = weights(modelled_g, p)
    q = {
        "design": spec.name, "piece": spec.piece_type, "karat": k, "metal": spec.metal,
        "finished_weight_g": float(w), "modelled_weight_g": round(modelled_g, 3),
        "weights": wt, "weight_text": weight_text(wt),
        "gold_rate_per_g": g.per_g, "gold_rate_as_of": g.set_at, "gold_rate_source": g.source,
        "gold_value": gold_v, "making_charges": making,
        "stone": f"{spec.gem_ct:.2f} ct {spec.gem}" if spec.gem != "none" else "none",
        "stone_value": stones, "hallmarking": hall, "gst_gold_stones": gst_gs, "gst_making": gst_mk,
        "gst": gst_gs + gst_mk, "total": total, "lines": lines, "assumptions": assumptions,
        "rate_card_as_of": rc["as_of"],
    }
    rate_note = f"gold rate {k}K {inr(g.per_g)}/g as of {when}"
    if brief.old_gold:
        og = brief.old_gold
        g24 = _rate_for(p, 24)
        ded = rc["old_gold_deduction_pct"]
        pur = G.purity(og.karat)
        credit = rupees(_d(og.weight_g) * _d(pur) * _d(g24.per_g) * (1 - _d(ded) / 100))
        line("old_gold_credit",
             f"Old gold credit {og.weight_g:g} g {og.karat}K × {pur} × {inr(g24.per_g)}/g − {ded:g}%",
             -credit,
             f"24K rate {inr(g24.per_g)}/g as of {R._shown_time(g24.set_at)}, {_source_label(g24)}; "
             f"purity of the stated {og.karat}K; {ded:g}% deduction, no separate melt loss"
             + (f" ({ASSUMED})" if "old_gold_deduction_pct" in assumed else ""),
             "old_gold_deduction_pct" in assumed)
        q["exchange_credit"] = credit
        q["to_pay"] = total - credit
        pay = (f"you pay {inr(total - credit)}" if total >= credit
               else f"the shop owes you {inr(credit - total)}")
        q["summary"] = (f"{spec.name}: {w} g {k}K"
                        f"{', ' + q['stone'] if spec.gem != 'none' else ''}. Total {inr(total)}, "
                        f"old gold credit {inr(credit)}, {pay} "
                        f"(making charges{', stone' if stones else ''}, hallmarking and GST). {rate_note}.")
    else:
        q["summary"] = (f"{spec.name}: {w} g {k}K. Total {inr(total)} incl. GST and hallmarking. "
                        f"{rate_note}.")
    q["summary"] += f" Weight: {weight_text(wt)}."
    if assumptions:
        q["summary"] += " " + "; ".join(a[0].upper() + a[1:] for a in assumptions) + "."
    return q
