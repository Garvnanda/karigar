"""The office: five agents hand one order through the shop floor.

Sakhi (counter) -> Jauhari (pricing) -> Naqqash (studio) -> Karigar (workshop)
-> Chitrakar (photo studio) -> Jauhari (quote) -> Sakhi (hands it over).
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Callable

from .stagelog import log_stage

from .calibration import CalibrationStore
from .lang import detect
from .orders import OrderStore, UnknownOrder
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
        store: OrderStore | None = None,
        on_stage: Callable[[str, dict], None] | None = None,
    ):
        self.pack = pack
        self.t = transport or ConsoleTransport()
        self.out_dir = Path(out_dir)
        self.workshop = workshop
        self.quality = quality
        self.n = n_variants
        self.calib = calibration or CalibrationStore()
        self.store = store or OrderStore()     # $KARIGAR_ORDERS_DB or data/orders.sqlite3
        # Phase 7: called as on_stage(stage, data) at each pipeline stage. The worker uses the
        # "solved" stage (spec, weights, quote, no files yet) to send numbers before renders.
        self.on_stage = on_stage

    def _stage(self, stage: str, order_id: str, t0: float, data: dict | None = None, **kv) -> None:
        """One structured log line per pipeline stage (core/stagelog.py), then the hook."""
        log_stage(stage, order_id=order_id, ms=round((time.time() - t0) * 1000), **kv)
        if self.on_stage is not None:
            self.on_stage(stage, data if data is not None else {"order_id": order_id})

    def _a(self, role: str) -> str:
        return self.pack.agents[role]

    def handle(self, text: str, attachments: list[Path] | None = None,
               sender: str | None = None, conversation: str | None = None) -> dict:
        """Run one message from `sender` (chat identity, None if unknown). `conversation` is an
        optional external conversation key stored with the order (Phase 7 derives it).
        Returns `JobResult(...).model_dump()` (core/result.py). An order with a brief is saved in
        the order store: request, brief, plan, and each solved variant as versions 1..n."""
        t0 = time.time()
        order_id = self.store.new_order_id()
        S, N, K, J, C = (self._a(r) for r in ("brief", "design", "build", "price", "render"))

        # 1. Counter: a non-order (rate update), a scope reply, questions, or a brief.
        self.t.move_to(S, "counter")
        intake = self.pack.intake(text, attachments, sender=sender)
        lang = intake.lang
        self._stage("intake", order_id, t0, status=intake.status, lang=lang)
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
        if plan.ok:
            plan.detail["tolerance"] = self.calib.tolerance(self.workshop)
        self._stage("plan", order_id, t0, ok=bool(plan.ok))

        def save(status: str) -> None:
            self.store.create_order(order_id, request=text, brief=_jsonable(brief),
                                    plan=_plan_json(plan), lang=lang, status=status,
                                    conversation_key=conversation)
        if not plan.ok:
            self.t.say(J, plan.explanation)
            save("infeasible")
            return _infeasible(order_id, lang, brief, plan.explanation, plan)
        self.t.say(J, plan.summary)

        # 3. Studio: design variants.
        self.t.move_to(N, "design studio")
        specs = self.pack.propose(brief, self.n)
        self._stage("design", order_id, t0, variants=len(specs))
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
        self._stage("solve", order_id, t0, solved=len(solved), failed=len(failed))
        if not solved:
            msg = "None of the designs can carry exactly this gold within casting rules. " \
                  "Options are listed above for each design."
            self.t.say(K, msg)
            save("infeasible")
            return _infeasible(order_id, lang, brief, msg, *failed)
        save("done")

        # 5. Quote every solved design and store it as a version before any rendering, so the
        # spec, weight and quote exist (and reach the customer) even if rendering fails.
        quotes = [self.pack.quote(r, brief, plan) for r in solved]
        results = []
        for r, q in zip(solved, quotes):
            loss = plan.detail.get("casting_loss_pct", 0.0)
            fin = r.value * (1 - loss / 100)
            n = self.store.add_version(order_id, spec=_jsonable(r.spec), scale=r.scale,
                                       modelled_g=r.value, finished_g=fin, target_g=r.target, quote=q)
            results.append({"variant": r.spec.name, "version": n,
                            "weights": self.pack.weights(r, plan), "files": {}, "quote": q})
        self._stage("solved", order_id, t0, data=JobResult(
            status="done", order_id=order_id, lang=lang, brief=_jsonable(brief), plan=plan.detail,
            results=results).model_dump(), versions=len(results))

        # 6. Photo studio + production files. A failure marks the order failed (Phase 6 review).
        self.t.move_to(C, "photo studio")
        try:
            for i, (r, q, res) in enumerate(zip(solved, quotes, results), 1):
                vdir = out / f"v{i}"
                self.t.progress(C, f"Rendering {r.spec.name} ({self.quality})…")
                files = self.pack.deliver(r, brief, plan, vdir, self.quality)
                (vdir / "quote.json").write_text(json.dumps(q, indent=2, ensure_ascii=False))
                files["quote"] = vdir / "quote.json"
                for k, p in files.items():
                    if k.startswith("render"):
                        self.t.send_image(C, p, f"{r.spec.name} · {k}")
                for k in ("stl", "glb", "job_card", "job_card_md", "quote"):
                    if k in files:
                        self.t.send_file(J if k == "quote" else K, files[k], r.spec.name)
                self.t.say(J, q.get("summary", ""))
                self.store.add_outputs(order_id, res["version"], files)
                res["files"] = {k: str(v) for k, v in files.items()}
        except Exception as e:
            self.store.set_status(order_id, "failed")
            log_stage("deliver_failed", order_id=order_id, ms=round((time.time() - t0) * 1000),
                      error=type(e).__name__)
            raise
        self._stage("deliver", order_id, t0, versions=len(results))

        self.t.move_to(S, "counter")
        self.t.say(S, f"{len(results)} design{'s' if len(results) != 1 else ''} ready in {time.time() - t0:.0f}s. "
                      "Tell me which one you like, or ask Karigar to make any of them lighter.")
        summary = JobResult(status="done", order_id=order_id, lang=lang, brief=_jsonable(brief),
                            plan=plan.detail, results=results).model_dump()
        (out / "order.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False))
        self.store.add_outputs(order_id, results[0]["version"], {"order_json": out / "order.json"})
        self._stage("done", order_id, t0, data=summary)
        return summary

    def handle_edit(self, order_id: str, text: str) -> dict:
        """Phase 6: an edit is a patch to one stored version's spec. The patched spec is
        re-solved (gold target kept unless the edit is about weight), checked, delivered and
        quoted, stored as the next version, and the v_base -> v_new difference is reported."""
        S, K, J, C = (self._a(r) for r in ("brief", "build", "price", "render"))
        t0 = time.time()
        lang = detect(text)
        self.t.move_to(S, "counter")

        def ask(q: str, topic: str, oid: str = order_id) -> dict:
            self.t.ask(S, q)
            return JobResult(status="needs_info", order_id=oid, lang=lang, reply=q, question=q,
                             questions=[q], topics=[topic]).model_dump()
        try:
            o = self.store.get(order_id)
        except UnknownOrder:
            oid = order_id[:40]
            return ask(f"Order {oid} nahi mila." if lang == "hinglish" else f"I can't find order {oid}.",
                       "order_id", oid)
        if not o.versions:
            return ask("Is order mein abhi koi design nahi hai." if lang == "hinglish"
                       else "This order has no design to change yet.", "version")
        req = self.pack.parse_edit(text)
        if req is None:
            return ask(self.pack.edit_text("help", lang), "edit")
        originals = [v for v in o.versions if v.parent is None]
        if req.pick:
            base = originals[self.pack.pick_index(req.pick, len(originals))]
        elif o.chosen is not None:
            base = o.version(o.chosen)
        elif len(o.versions) == 1:
            base = o.versions[0]
        else:
            return ask(self.pack.edit_text("which", lang), "variant")
        if req.empty:                    # only a pick: remember it as the base of the next edit
            self.store.choose(order_id, base.version)
            name = base.spec.get("name", "")
            msg = f"v{base.version} chuna: {name}." if lang == "hinglish" else f"Picked v{base.version}: {name}."
            self.t.say(S, msg)
            return JobResult(status="done", order_id=order_id, lang=lang, reply=msg,
                             brief=o.brief).model_dump()

        brief = self.pack.load_brief(o.brief)
        self.t.move_to(J, "pricing desk")
        plan = self.pack.plan(brief, self.calib.loss_pct(self.workshop))   # today's rate (RateSource)
        if plan.ok:
            plan.detail["tolerance"] = self.calib.tolerance(self.workshop)
        self._stage("plan", order_id, t0, ok=bool(plan.ok), edit=True)
        if not plan.ok:
            self.t.say(J, plan.explanation)
            return _infeasible(order_id, lang, brief, plan.explanation, plan)
        self.t.move_to(K, "workshop")
        name = base.spec.get("name", "design")
        out = self.pack.apply_edit(
            base.spec, base.scale, base.modelled_g, req, plan, lang,
            on_iter=lambda i, s, v: self.t.progress(K, f"{name}: pass {i}, scale {s:.3f} → {v:.2f} g"))
        if out.status == "refused":
            return ask(out.reply, "edit")
        if out.status != "solved":
            self.t.say(K, f"✗ {name}: {out.solved.explanation}")
            return _infeasible(order_id, lang, brief, out.solved.explanation, out.solved)

        self._stage("solve", order_id, t0, edit=True)
        n = self.store.reserve_version(order_id)    # allocated in a store transaction
        vdir = self.out_dir / order_id / f"v{n}"
        rep = self.pack.edit_report({"version": base.version}, n, out, brief, lang)
        q = rep.pop("quote")
        fin = out.solved.value * (1 - out.plan.detail["casting_loss_pct"] / 100)
        result = {"variant": out.solved.spec.name, "version": n,
                  "weights": self.pack.weights(out.solved, out.plan), "files": {}, "quote": q}
        self._stage("solved", order_id, t0, data=JobResult(
            status="done", order_id=order_id, lang=lang, reply=rep["summary"], brief=o.brief,
            plan=out.plan.detail, edit={**rep, "to_version": n}, results=[result]).model_dump(),
            edit=True, version=n)
        self.t.move_to(C, "photo studio")
        self.t.progress(C, f"Rendering {out.solved.spec.name} v{n} ({self.quality})…")
        try:
            files = self.pack.deliver(out.solved, brief, out.plan, vdir, self.quality)
        except Exception as e:
            log_stage("deliver_failed", order_id=order_id, ms=round((time.time() - t0) * 1000),
                      error=type(e).__name__, version=n)
            raise
        (vdir / "quote.json").write_text(json.dumps(q, indent=2, ensure_ascii=False))
        (vdir / "edit.json").write_text(json.dumps(rep, indent=2, ensure_ascii=False))
        files["quote"], files["edit"] = vdir / "quote.json", vdir / "edit.json"
        for k, p in files.items():
            if k.startswith("render"):
                self.t.send_image(C, p, f"{out.solved.spec.name} v{n} · {k}")
        stored = self.store.add_version(
            order_id, spec=_jsonable(out.solved.spec), scale=out.solved.scale,
            modelled_g=out.solved.value, finished_g=fin, target_g=out.solved.target, quote=q,
            parent=base.version, edit_text=text, patch=rep["spec_diff"], outputs=files, version=n)
        self.store.choose(order_id, stored)
        self.t.move_to(S, "counter")
        self.t.say(J, rep["summary"])
        rep["to_version"] = stored
        result["files"] = {k: str(v) for k, v in files.items()}
        final = JobResult(
            status="done", order_id=order_id, lang=lang, reply=rep["summary"], brief=o.brief,
            plan=out.plan.detail, edit=rep, results=[result]).model_dump()
        self._stage("done", order_id, t0, data=final, edit=True, version=stored)
        return final


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


def _plan_json(plan) -> dict:
    from dataclasses import asdict, is_dataclass
    return asdict(plan) if is_dataclass(plan) else _jsonable(plan)


def _jsonable(obj):
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    return obj
