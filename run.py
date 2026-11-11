#!/usr/bin/env python
"""Karigar CLI.

  python run.py order "Mere paas 18.4g purana 22K kangan hai, naya 22K beaded kada banana hai, size 2-6"
  python run.py order "18K lotus pendant with ruby, budget 60k" --quality final
  python run.py calibrate --workshop dariba-01 --designed 18.9 --actual 18.3
  python run.py packs
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
    c = sub.add_parser("calibrate", help="record a cast piece's real weight")
    c.add_argument("--workshop", required=True)
    c.add_argument("--designed", type=float, required=True, help="modelled weight (g) from the job card")
    c.add_argument("--actual", type=float, required=True, help="weight after casting + polishing (g)")
    sub.add_parser("packs", help="list domain packs")
    a = ap.parse_args(argv)

    if a.cmd == "packs":
        for name, p in registry.all_packs().items():
            print(f"{name:10s} {p.title:16s} {'ready' if p.available else 'roadmap'}")
    elif a.cmd == "calibrate":
        loss = CalibrationStore().record(a.workshop, a.designed, a.actual)
        print(f"Recorded. {a.workshop} learned casting+finishing loss: {loss:.2f}%")
    else:
        orch = Orchestrator(registry.get(a.pack), out_dir=Path(a.out), workshop=a.workshop,
                            quality=a.quality, n_variants=a.variants)
        res = orch.handle(a.request)
        print("\n" + json.dumps({k: res[k] for k in ("status", "order_id") if k in res}))


if __name__ == "__main__":
    main()
