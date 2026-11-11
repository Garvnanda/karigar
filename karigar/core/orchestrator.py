"""The office: five agents hand one order through the shop floor.

Sakhi (counter) -> Jauhari (pricing) -> Naqqash (studio) -> Karigar (workshop)
-> Chitrakar (photo studio) -> Jauhari (quote) -> Sakhi (hands it over).
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from .calibration import CalibrationStore
from .registry import DomainPack
from .result import JobResult
from .transport import ConsoleTransport, Transport


class Orchestrator:
    def __init__(
        self,
        pack: DomainPack,
        transport: Transport | None = None,
        out_dir: Path = Path("out"),
        workshop: str | None = None,
        quality: str = "preview",
        n_variants: int = 3,
        calibration: CalibrationStore | None = None,
    ):
        self.pack = pack
        self.t = transport or ConsoleTransport()
        self.out_dir = Path(out_dir)
        self.workshop = workshop
        self.quality = quality
        self.n = n_variants
        self.calib = calibration or CalibrationStore()

    def _a(self, role: str) -> str:
        return self.pack.agents[role]

    def handle(self, text: str, attachments: list[Path] | None = None) -> dict:
        """Run one message. Returns `JobResult(...).model_dump()` (core/result.py)."""
        t0 = time.time()
        order_id = time.strftime("ORD-%Y%m%d-%H%M%S")
        S, N, K, J, C = (self._a(r) for r in ("brief", "design", "build", "price", "render"))

        # 1. Counter: a non-order (rate update), a scope reply, questions, or a brief.
        self.t.move_to(S, "counter")
        intake = self.pack.intake(text, attachments)
        lang = intake.lang
        if intake.status != "brief":
            (self.t.ask if intake.status == "needs_info" else self.t.say)(S, intake.reply)
            res = JobResult(
                status=intake.status, order_id=order_id, lang=lang, reply=intake.reply,
                question=intake.reply if intake.status == "needs_info" else None,
                questions=intake.questions, topics=intake.topics,
                rates=intake.data.get("rates"), suggestion=intake.data.get("suggestion"))
            return res.model_dump()
        brief = intake.brief
        out = self.out_dir / order_id
        out.mkdir(parents=True, exist_ok=True)
        self.t.say(S, self.pack.describe_brief(brief, lang))

        # 2. Pricing desk: what must the piece weigh (or cost)?
        loss = self.calib.loss_pct(self.workshop)
        self.t.move_to(J, "pricing desk")
        self.t.progress(J, f"Workshop calibration: {self.calib.summary(self.workshop)}")
        plan = self.pack.plan(brief, loss)
        if not plan.ok:
            self.t.say(J, plan.explanation)
            return _infeasible(order_id, lang, brief, plan.explanation, plan)
        self.t.say(J, plan.summary)

        # 3. Studio: design variants.
        self.t.move_to(N, "design studio")
        specs = self.pack.propose(brief, self.n)
        self.t.say(N, "Proposing: " + "; ".join(getattr(s, "name", str(i)) for i, s in enumerate(specs, 1)))

        # 4. Workshop: solve each variant to the target and check it can be made.
        self.t.move_to(K, "workshop")
        solved, failed = [], []
        for spec in specs:
            name = getattr(spec, "name", "variant")
            r = self.pack.solve(
                spec, plan,
                on_iter=lambda i, s, v, name=name: self.t.progress(
                    K, f"{name}: pass {i}, scale {s:.3f} → {v:.2f} {plan.unit}"),
            )
            if r.ok:
                self.t.progress(K, f"✓ {name}: {r.value:.2f} {plan.unit} "
                                   f"(target {r.target:.2f}, {r.iterations} passes)")
                solved.append(r)
            else:
                self.t.say(K, f"✗ {name}: {r.explanation}")
                failed.append(r)
        if not solved:
            msg = "None of the designs can carry exactly this gold within casting rules. " \
                  "Options are listed above for each design."
            self.t.say(K, msg)
            return _infeasible(order_id, lang, brief, msg, *failed)

        # 5. Photo studio + production files, 6. quote.
        self.t.move_to(C, "photo studio")
        results = []
        for i, r in enumerate(solved, 1):
            vdir = out / f"v{i}"
            self.t.progress(C, f"Rendering {r.spec.name} ({self.quality})…")
            files = self.pack.deliver(r, brief, plan, vdir, self.quality)
            q = self.pack.quote(r, brief, plan)
            (vdir / "quote.json").write_text(json.dumps(q, indent=2, ensure_ascii=False))
            files["quote"] = vdir / "quote.json"
            for k, p in files.items():
                if k.startswith("render"):
                    self.t.send_image(C, p, f"{r.spec.name} · {k}")
            for k in ("stl", "glb", "job_card", "quote"):
                if k in files:
                    self.t.send_file(J if k == "quote" else K, files[k], r.spec.name)
            self.t.say(J, q.get("summary", ""))
            loss = plan.detail.get("casting_loss_pct", 0.0)
            results.append({"variant": r.spec.name,
                            "weights": {"modelled_g": round(r.value, 3),
                                        "finished_g": round(r.value * (1 - loss / 100), 3)},
                            "files": {k: str(v) for k, v in files.items()}, "quote": q})

        self.t.move_to(S, "counter")
        self.t.say(S, f"{len(results)} design{'s' if len(results) != 1 else ''} ready in {time.time() - t0:.0f}s. "
                      "Tell me which one you like, or ask Karigar to make any of them lighter.")
        summary = JobResult(status="done", order_id=order_id, lang=lang, brief=_jsonable(brief),
                            plan=plan.detail, results=results).model_dump()
        (out / "order.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False))
        return summary


def _infeasible(order_id: str, lang: str, brief, explanation: str, *sources) -> dict:
    """Infeasible JobResult from a failed Plan or failed Solved results.

    The binding constraint and best result come from the closest miss; alternatives are
    pooled (deduplicated) across all misses."""
    src = [s for s in sources if getattr(s, "binding_constraint", "")]
    if not src:
        raise ValueError("infeasible result without a binding constraint")
    best = min(src, key=lambda s: abs(getattr(s, "value", 0) - getattr(s, "target", 0)))
    alts: list[str] = []
    for s in [best, *src]:
        alts += [a for a in s.alternatives if a not in alts]
    return JobResult(
        status="infeasible", order_id=order_id, lang=lang, brief=_jsonable(brief),
        explanation=explanation,
        infeasible={"binding_constraint": best.binding_constraint,
                    "best_achievable": best.best_achievable, "alternatives": alts},
    ).model_dump()


def _jsonable(obj):
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    return obj
