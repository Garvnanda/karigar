"""Jewellery pack: weight-locked gold design for old-gold exchange, weight or budget."""
from __future__ import annotations

import json
from pathlib import Path

from karigar.core import gold as G
from karigar.core.registry import DomainPack, Plan, Solved, register
from karigar.core.solver import solve_monotone

from . import brief as B
from . import designer, dfm, pricing
from .schema import Brief, DesignSpec


class JewelleryPack(DomainPack):
    name = "jewellery"
    title = "Jeweller's Shop"

    def parse_brief(self, text, attachments=None):
        return B.parse(text)

    def describe_brief(self, brief: Brief) -> str:
        return B.describe(brief)

    def plan(self, brief: Brief, loss_pct: float) -> Plan:
        return pricing.plan(brief, loss_pct)

    def propose(self, brief: Brief, n: int = 3) -> list[DesignSpec]:
        return designer.propose(brief, pricing.requested_ct(brief), n)

    def solve(self, spec: DesignSpec, plan: Plan, on_iter=None) -> Solved:
        from . import geometry  # bpy is imported only when geometry is needed

        lo, hi = dfm.scale_bounds(spec)
        if lo > hi:
            return Solved(spec, False, lo, 0, plan.target_value, 0,
                          explanation="This combination of stone and proportions can't be cast safely.")
        f = lambda s: G.mm3_to_grams(geometry.gold_volume(spec, s), spec.karat)
        r = solve_monotone(f, plan.target_value, lo, hi, on_iter=on_iter)
        loss = plan.detail["casting_loss_pct"]
        fin = lambda g: g * (1 - loss / 100)
        expl = ""
        if r.reason == "below_min":
            expl = (f"too little gold for this design. Its lightest castable version finishes at "
                    f"{fin(r.value):.2f} g; you have {fin(r.target):.2f} g. Try a slimmer design, "
                    f"a smaller stone, or add {fin(r.value - r.target):.2f} g of gold.")
        elif r.reason == "above_max":
            expl = (f"this design tops out at {fin(r.value):.2f} g; you have {fin(r.target):.2f} g. "
                    f"Pick a bolder design, make a matching set (ring + pendant), or keep "
                    f"{fin(r.target - r.value):.2f} g as credit.")
        return Solved(spec, r.ok, r.scale, r.value, r.target, len(r.iterations),
                      issues=dfm.check(spec, r.scale) if r.ok else [], explanation=expl)

    def deliver(self, solved: Solved, brief: Brief, plan: Plan, out_dir: Path, quality: str):
        from . import geometry, render

        spec: DesignSpec = solved.spec
        out_dir.mkdir(parents=True, exist_ok=True)
        geometry.clear_scene()
        b = geometry.build(spec, solved.scale)
        files = {
            "stl": render.export_stl(b.gold, out_dir / "casting.stl"),
        }
        c, S = render.stage(b.gold, b.gems, spec.metal, spec.karat, spec.gem,
                            float_up=spec.piece_type == "pendant")
        files["glb"] = render.export_glb([b.gold, *b.gems], out_dir / "model.glb")
        files.update(render.render_views(c, S, out_dir, quality))
        loss = plan.detail["casting_loss_pct"]
        job = {
            "design": spec.name, "piece": spec.piece_type, "karat": spec.karat, "metal": spec.metal,
            "modelled_weight_g": round(solved.value, 3),
            "expected_finished_weight_g": round(solved.value * (1 - loss / 100), 3),
            "assumed_casting_loss_pct": round(loss, 2),
            "tolerance_note": "Weigh after polishing and record it: `run.py calibrate` sharpens the next prediction.",
            "dimensions_mm": b.dims,
            "stone": {"type": spec.gem, "diameter_mm": spec.gem_d_mm, "approx_ct": round(spec.gem_ct, 2),
                      "setting": f"{spec.prongs}-claw" if spec.piece_type == "ring" else "bezel"}
                     if spec.gem != "none" else None,
            "checks_passed": solved.issues,
            "spec": spec.model_dump(),
            "solver": {"scale": round(solved.scale, 4), "passes": solved.iterations},
        }
        (out_dir / "job_card.json").write_text(json.dumps(job, indent=2, ensure_ascii=False))
        files["job_card"] = out_dir / "job_card.json"
        geometry.clear_scene()
        return files

    def quote(self, solved: Solved, brief: Brief, plan: Plan) -> dict:
        return pricing.quote(solved.spec, solved.value, brief, plan)


PACK = register(JewelleryPack())
