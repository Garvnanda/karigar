"""Run the user simulation: `./venv/bin/python -m sim.run [--users 1000] [--solve-every 10]`.

Every user goes through the counter (pack.intake) and, for a brief, the pricing desk (pack.plan).
Every `solve-every`-th brief also designs and solves its balanced variant on the mesh (bpy,
mesh checks included). Renders are skipped (measured separately: decisions.md). Writes only to a
temp dir (gold rates, orders); never data/ or out/. Exit 1 when the pass bar is missed.
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
import traceback
from collections import Counter
from pathlib import Path

from sim.users import users

P95_INTAKE_S = 0.5       # counter reply (intake + plan), no bpy
P95_SOLVE_S = 30.0       # one variant solved + mesh-checked on the laptop CPU


def p95(xs):
    xs = sorted(xs)
    return xs[int(0.95 * (len(xs) - 1))] if xs else 0.0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--users", type=int, default=1000)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--solve-every", type=int, default=10)
    ap.add_argument("--report", default="")
    a = ap.parse_args(argv)

    tmp = Path(tempfile.mkdtemp(prefix="karigar-sim-"))
    import os
    os.environ["KARIGAR_LLM_BACKEND"] = "none"
    os.environ["KARIGAR_ORDERS_DB"] = str(tmp / "orders.sqlite3")
    os.environ.pop("KARIGAR_RATE_SETTERS", None)
    from karigar.core import registry
    from karigar.packs.jewellery import rates
    import karigar.packs.jewellery  # noqa: F401
    rates.RATES_FILE = tmp / "gold_rates.json"
    store = rates.GoldRateStore(tmp / "seed_rates.json")
    store.set({24: 14160.7, 22: 12971.2, 18: 10620.5, 14: 8284.0}, source="sim seed")
    rates.rate_source = lambda: rates.RateSource(store)
    pack = registry.get("jewellery")

    rows, crashes, briefs = [], [], 0
    for u in users(a.users, a.seed):
        row = {"uid": u.uid, "kind": u.kind, "text": u.text[:120]}
        t = time.monotonic()
        try:
            i = pack.intake(u.text, sender=None)
            row["status"] = i.status
            if i.status == "brief":
                plan = pack.plan(i.brief, 3.0)
                row["plan_ok"] = bool(plan.ok)
                row["intake_s"] = time.monotonic() - t
                briefs += 1
                if plan.ok and briefs % a.solve_every == 1:
                    t2 = time.monotonic()
                    specs = pack.propose(i.brief, 3)
                    s = pack.solve(specs[len(specs) // 2], plan)
                    row["solved"] = bool(s.ok)
                    row["solve_s"] = time.monotonic() - t2
                    if not s.ok:
                        row["binding"] = getattr(s, "binding_constraint", None) or getattr(s, "reason", "")
            else:
                row["intake_s"] = time.monotonic() - t
            if rates.RATES_FILE.exists():
                row["rate_saved"] = True
        except Exception as e:   # a crash is a finding, never a stop
            row["crash"] = f"{type(e).__name__}: {e}"[:300]
            crashes.append((u, traceback.format_exc()))
        row["ok"] = "crash" not in row and row.get("status") in u.expect and not row.get("rate_saved")
        rows.append(row)

    kinds = Counter(r["kind"] for r in rows)
    wrong = Counter(r["kind"] for r in rows if not r["ok"])
    valid = [r for r in rows if r["kind"] in ("order", "partial", "scope", "rate")]
    invalid = [r for r in rows if r["kind"] == "invalid"]
    solves = [r for r in rows if "solve_s" in r]
    summary = {
        "users": len(rows), "kinds": dict(kinds), "crashes": len(crashes),
        "valid_error_rate_pct": round(100 * sum(not r["ok"] for r in valid) / max(1, len(valid)), 2),
        "invalid_rejected_pct": round(100 * sum(r["ok"] for r in invalid) / max(1, len(invalid)), 2),
        "wrong_by_kind": dict(wrong),
        "p95_intake_s": round(p95([r["intake_s"] for r in rows if "intake_s" in r]), 3),
        "solves": len(solves), "solved_ok": sum(r["solved"] for r in solves),
        "p95_solve_s": round(p95([r["solve_s"] for r in solves]), 2),
        "unsolved": [(r["text"], r.get("binding")) for r in solves if not r["solved"]],
        "wrong_examples": [(r["kind"], r.get("status"), r["text"]) for r in rows if not r["ok"]][:25],
    }
    summary["pass"] = (summary["crashes"] == 0 and summary["valid_error_rate_pct"] < 1
                       and summary["invalid_rejected_pct"] == 100
                       and summary["p95_intake_s"] <= P95_INTAKE_S and summary["p95_solve_s"] <= P95_SOLVE_S)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    for u, tb in crashes[:5]:
        print(f"--- crash uid {u.uid} ({u.kind}): {u.text[:80]!r}\n{tb}", file=sys.stderr)
    if a.report:
        Path(a.report).write_text(json.dumps({"summary": summary, "rows": rows}, indent=1, ensure_ascii=False))
    return 0 if summary["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
