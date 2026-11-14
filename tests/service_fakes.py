"""Shared fakes for the Phase 7 service tests: a scripted shop floor (no bpy, no LLM)."""
from __future__ import annotations

import threading
from pathlib import Path

from karigar.core import llm

QUOTES = [{"total": 61234, "summary": "q"}, {"total": 72345, "summary": "q"}, {"total": 83456, "summary": "q"}]
WEIGHTS = [{"casting_g": 5.124, "finished_g": 4.97, "tolerance_g": 0.2, "tolerance_pct": 4.0},
           {"casting_g": 6.281, "finished_g": 6.093, "tolerance_g": 0.24, "tolerance_pct": 4.0},
           {"casting_g": 7.402, "finished_g": 7.18, "tolerance_g": 0.29, "tolerance_pct": 4.0}]


class Script:
    """What the fake shop floor does; tests tweak it. `gate` blocks rendering until set."""

    def __init__(self):
        self.calls: list[tuple] = []
        self.gate: threading.Event | None = None
        self.fail_render = False
        self.llm_threads: list[str] = []
        self.counter = 0


def make_factory(script: Script):
    def factory(transport, on_stage, out_dir: Path, quality: str):
        return FakeOrch(script, transport, on_stage, Path(out_dir))
    return factory


class FakeOrch:
    def __init__(self, script, transport, on_stage, out_dir):
        self.s, self.t, self.on_stage, self.out = script, transport, on_stage, out_dir

    def _llm(self):
        # Stands in for the brief/designer LLM call: records which thread made it.
        self.s.llm_threads.append(threading.current_thread().name)
        llm.complete_json("sys", "user")

    def handle(self, text, conversation=None, **kw):
        self.s.calls.append(("handle", text, conversation))
        self._llm()
        self.on_stage("intake", {})
        if "size" not in text:
            q = "Which ring size?"
            return {"status": "needs_info", "order_id": "ORD-q", "lang": "en", "reply": q,
                    "question": q, "questions": [q], "topics": ["ring_size"]}
        self.s.counter += 1
        oid = f"ORD-2026-{self.s.counter:04d}"
        results = [{"variant": n, "version": i + 1, "weights": dict(WEIGHTS[i]), "files": {},
                    "quote": dict(QUOTES[i])} for i, n in enumerate(("Plain", "Floral", "Twist"))]
        partial = {"status": "done", "order_id": oid, "lang": "en", "results": results}
        self.on_stage("solved", {**partial, "results": [dict(r) for r in results]})
        if self.s.gate is not None:
            assert self.s.gate.wait(10)
        if self.s.fail_render:
            raise RuntimeError("render crashed")
        for r in results:
            d = self.out / oid / f"v{r['version']}"
            d.mkdir(parents=True, exist_ok=True)
            (d / "render_hero.png").write_bytes(b"\x89PNG fake " + r["variant"].encode())
            (d / "casting.stl").write_bytes(b"solid x")
            (d / "secret.txt").write_text("not uploaded")
            r["files"] = {"render_hero": str(d / "render_hero.png"), "stl": str(d / "casting.stl"),
                          "order_json": str(d / "secret.txt")}
        self.on_stage("done", partial)
        return {**partial, "results": results}

    def handle_edit(self, order_id, text):
        self.s.calls.append(("edit", order_id, text))
        if "middle" in text and "lighter" not in text:
            msg = "Picked v2: Floral."
            return {"status": "done", "order_id": order_id, "lang": "en", "reply": msg}
        if "lighter" in text:
            r = {"variant": "Floral", "version": 4, "weights": {"casting_g": 5.3, "finished_g": 5.141,
                                                                "tolerance_g": 0.21},
                 "files": {}, "quote": {"total": 65000}}
            ed = {"summary": "v4 (from v2): weight 6.09 g → 5.14 g, price ₹72,345 → ₹65,000",
                  "to_version": 4, "weight_g": {"from": 6.093, "to": 5.141},
                  "price_inr": {"from": 72345, "to": 65000}}
            return {"status": "done", "order_id": order_id, "lang": "en", "reply": ed["summary"],
                    "edit": ed, "results": [r]}
        q = "Tell me what to change, e.g. thinner."
        return {"status": "needs_info", "order_id": order_id, "lang": "en", "reply": q, "question": q,
                "questions": [q], "topics": ["edit"]}
