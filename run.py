#!/usr/bin/env python
"""Karigar CLI.

  python run.py order "Mere paas 18.4g purana 22K kangan hai, naya 22K beaded kada banana hai, size 2-6"
  python run.py order "18K lotus pendant with ruby, budget 60k" --quality final
  python run.py calibrate --workshop dariba-01 --designed 18.9 --actual 18.3
  python run.py packs
  python run.py rates refresh            # MCX gold price + ₹5,000 → data/gold_rates.json
  python run.py rates refresh --every-h 6   # worker loop
  python run.py rates show
  python run.py rates set 22=14730 24=16000  # owner, by hand
  python run.py edit ORD-20261113-101500-a3f9 "Middle one, but make the flower slightly bigger"
  python run.py orders show ORD-20261113-101500-a3f9
  python run.py orders list
  python run.py serve                    # Phase 7 HTTP service (env KARIGAR_API_KEY, KARIGAR_WORKER_TOKEN)
  python run.py worker                   # Blender worker polling the service (KARIGAR_SERVICE_URL)
  python run.py ask "22K ring 5g size 12" --conversation K-demo   # KarigarService in-process
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from karigar.core import registry  # noqa: E402
from karigar.core.calibration import CalibrationStore  # noqa: E402
from karigar.core.orchestrator import Orchestrator  # noqa: E402
from karigar.core.orders import OrderStore  # noqa: E402
import karigar.packs.hardware  # noqa: E402,F401  (registers roadmap slot)
import karigar.packs.jewellery  # noqa: E402,F401


def main(argv=None):
    ap = argparse.ArgumentParser(description="Karigar: an AI artisan for anything that gets made")
    sub = ap.add_subparsers(dest="cmd", required=True)
    o = sub.add_parser("order", help="run one customer request through the shop floor")
    o.add_argument("request")
    o.add_argument("--pack", default="jewellery")
    o.add_argument("--quality", choices=["draft", "preview", "final"], default="preview")
    o.add_argument("--variants", type=int, default=3)
    o.add_argument("--workshop", default=None, help="workshop id for learned casting loss")
    o.add_argument("--out", default=str(ROOT / "out"))
    o.add_argument("--sender", default=None,
                   help="sender ID; only IDs in KARIGAR_RATE_SETTERS may set the gold rate")
    o.add_argument("--conversation", default=None, help="external conversation key stored with the order")
    o.add_argument("--db", default=None, help="order store (default $KARIGAR_ORDERS_DB or data/orders.sqlite3)")
    e = sub.add_parser("edit", help="change a stored order: a patch to one version's spec, re-solved")
    e.add_argument("order_id")
    e.add_argument("request")
    e.add_argument("--pack", default="jewellery")
    e.add_argument("--quality", choices=["draft", "preview", "final"], default="preview")
    e.add_argument("--workshop", default=None)
    e.add_argument("--out", default=str(ROOT / "out"))
    e.add_argument("--db", default=None)
    od = sub.add_parser("orders", help="show stored orders")
    osub = od.add_subparsers(dest="orders_cmd", required=True)
    os_ = osub.add_parser("show", help="brief, every version (spec diff, weight, price) and output paths")
    os_.add_argument("order_id")
    os_.add_argument("--db", default=None)
    ol = osub.add_parser("list", help="most recent orders")
    ol.add_argument("--limit", type=int, default=20)
    ol.add_argument("--db", default=None)
    c = sub.add_parser("calibrate", help="record a cast piece's real weight")
    c.add_argument("--workshop", required=True)
    c.add_argument("--designed", type=float, required=True, help="modelled weight (g) from the job card")
    c.add_argument("--actual", type=float, required=True, help="weight after casting + polishing (g)")
    sub.add_parser("packs", help="list domain packs")
    r = sub.add_parser("rates", help="gold rate: refresh from MCX, show, or set by the owner")
    rsub = r.add_subparsers(dest="rates_cmd", required=True)
    rr = rsub.add_parser("refresh", help="fetch the MCX gold price, add the premium, save with a timestamp")
    rr.add_argument("--url", default=None, help="override the configured page (https only)")
    rr.add_argument("--every-h", type=float, default=None,
                    help="keep running, refreshing every N hours (the worker uses 6)")
    rsub.add_parser("show", help="print the stored rates and whether each one is usable")
    rs = rsub.add_parser("set", help="owner sets today's rate by hand, e.g. 22=14730 24=16000")
    rs.add_argument("pairs", nargs="+", metavar="KARAT=RATE")
    sub.add_parser("serve", help="Phase 7 service: OpenAI-compatible /v1, JSON /api, worker API, files")
    sub.add_parser("worker", help="Phase 7 Blender worker: poll the service, run orders, upload results")
    k = sub.add_parser("ask", help="one chat message through KarigarService with an in-process worker")
    k.add_argument("text")
    k.add_argument("--conversation", default=None, help="conversation key (continue an earlier chat)")
    k.add_argument("--agent", choices=["sakhi", "karigar"], default="karigar")
    k.add_argument("--quality", choices=["draft", "preview", "final"], default="draft")
    k.add_argument("--service-dir", default=None, help="jobs DB + files (default data/service)")
    k.add_argument("--out", default=str(ROOT / "out"))
    a = ap.parse_args(argv)

    if a.cmd == "serve":
        from karigar.service.http import main as serve
        return serve()
    if a.cmd == "worker":
        from karigar.service.worker import main as work
        return work()
    if a.cmd == "ask":
        return ask_cmd(a)

    if a.cmd == "rates":
        return rates_cmd(a)
    if a.cmd == "orders":
        return orders_cmd(a)
    if a.cmd == "edit":
        orch = Orchestrator(registry.get(a.pack), out_dir=Path(a.out), workshop=a.workshop,
                            quality=a.quality, store=OrderStore(a.db) if a.db else None)
        res = orch.handle_edit(a.order_id, a.request)
        print("\n" + (res.get("reply") or res.get("explanation") or ""))
        print(json.dumps({k: res[k] for k in ("status", "order_id") if k in res}
                         | ({"version": res["edit"]["to_version"]} if res.get("edit") else {})))
        return 0 if res["status"] == "done" else 1
    if a.cmd == "packs":
        for name, p in registry.all_packs().items():
            print(f"{name:10s} {p.title:16s} {'ready' if p.available else 'roadmap'}")
    elif a.cmd == "calibrate":
        loss = CalibrationStore().record(a.workshop, a.designed, a.actual)
        print(f"Recorded. {a.workshop} learned casting+finishing loss: {loss:.2f}%")
    else:
        orch = Orchestrator(registry.get(a.pack), out_dir=Path(a.out), workshop=a.workshop,
                            quality=a.quality, n_variants=a.variants,
                            store=OrderStore(a.db) if a.db else None)
        res = orch.handle(a.request, sender=a.sender, conversation=a.conversation)
        print("\n" + json.dumps({k: res[k] for k in ("status", "order_id") if k in res}))


def ask_cmd(a) -> int:
    """CLI adapter over KarigarService: queue the message, run it with an in-process worker,
    print the reply (the same text a chat would get; file links are local /files/... paths)."""
    from karigar.service.core import KarigarService
    from karigar.service.worker import LocalClient, Worker

    svc = KarigarService(a.service_dir)
    t = (svc.continue_conversation(a.conversation, a.text, agent=a.agent) if a.conversation
         else svc.start_order(a.text, agent=a.agent))
    w = Worker(LocalClient(svc), out_dir=Path(a.out), quality=a.quality)
    while w.run_once() is not None:
        pass
    print(svc.wait(t, base_url="", budget_s=0))
    print(json.dumps({"conversation": t.conv_key, "job_id": t.job_id}))
    return 0


def orders_cmd(a) -> int:
    """`run.py orders show <id>` / `orders list`. Every number printed is a stored code number."""
    from karigar.core.orders import UnknownOrder

    store = OrderStore(a.db) if a.db else OrderStore()
    if a.orders_cmd == "list":
        for r in store.list(a.limit):
            print(f"{r['order_id']}  {r['created_at']}  {r['status']:10s} {r['n']} version(s)  "
                  f"{r['request'][:60]}")
        return 0
    try:
        o = store.get(a.order_id)
    except UnknownOrder:
        print(f"No order {a.order_id[:40]} in {store.path}")
        return 1
    print(f"{o.order_id}  {o.created_at}  {o.status}  lang={o.lang}"
          + (f"  conversation={o.conversation_key}" if o.conversation_key else ""))
    print(f"request: {o.request}")
    print("brief: " + json.dumps(o.brief, ensure_ascii=False))
    for v in o.versions:
        mark = " *" if v.version == o.chosen else ""
        head = f"v{v.version}{mark}  {v.spec.get('name', '')}"
        if v.parent is not None:
            head += f"  (edit of v{v.parent}: \"{v.edit_text}\")"
        print(head)
        print(f"    finished {v.finished_g:.3f} g (modelled {v.modelled_g:.3f} g, scale {v.scale:.4f})"
              f"  total ₹{v.quote.get('total', 0):,}")
        if v.patch:
            print("    spec diff: " + ", ".join(f"{k} {a_} → {b_}" for k, (a_, b_) in v.patch.items()))
        for k, p in v.outputs.items():
            print(f"    {k}: {p}")
    return 0


def rates_cmd(a) -> int:
    """`run.py rates refresh|show|set`. Returns the exit code (1 when nothing was saved)."""
    from karigar.packs.jewellery import ratejob, rates

    if a.rates_cmd == "refresh":
        if a.every_h is not None:
            ratejob.run_every(a.every_h, url=a.url)
            return 0
        res = ratejob.refresh(url=a.url)
        print(res.message)
        return 0 if res.ok else 1
    if a.rates_cmd == "set":
        new = {}
        for pair in a.pairs:
            k, _, v = pair.partition("=")
            amount = rates._amount(v.strip())
            if k.strip().upper().rstrip("K") not in rates.KARATS or amount is None:
                print(f"Not a KARAT=RATE pair (karat 24/22/18/14, rate in ₹/g): {pair[:30]}")
                return 1
            new[int(k.strip().upper().rstrip("K"))] = amount
        src = rates.RateSource()
        for k, v in new.items():
            lo, hi = src.sane_range(k)
            if not lo <= v <= hi:
                print(f"{k}K ₹{v:g}/g is outside the sane range ₹{lo:g}–₹{hi:g}/g; nothing saved.")
                return 1
        saved = rates.GoldRateStore().set(new, source="manual")
        print(f"Saved {', '.join(f'{k}K ₹{v:g}/g' for k, v in sorted(new.items(), reverse=True))} "
              f"at {saved['set_at']}.")
        return 0
    src = rates.RateSource()
    stored = src.store.load()
    for k in rates.KARATS:
        e = stored.get(k)
        if not e:
            print(f"{k}K  none")
            continue
        p = src.problem([int(k)])
        print(f"{k}K  ₹{e['rate_per_g']:g}/g  set {e['set_at']}  ({e.get('source', 'chat')})  "
              f"{'OK' if p is None else p.kind.upper()}")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
