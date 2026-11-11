"""JobResult contract (core/result.py) and the infeasible payload filled from what exists."""
import pytest
from pydantic import ValidationError

from karigar.core import registry
from karigar.core.calibration import CalibrationStore
from karigar.core.orchestrator import Orchestrator
from karigar.core.registry import DomainPack, Intake, Plan, Solved
from karigar.core.result import JobResult
from karigar.core.solver import SolveResult
from karigar.packs.jewellery import pricing, solve_failure
from karigar.packs.jewellery.schema import Brief


def test_infeasible_needs_two_alternatives():
    base = dict(status="infeasible", order_id="X", explanation="no")
    with pytest.raises(ValidationError):
        JobResult(**base, infeasible={"binding_constraint": "w", "best_achievable": {"value": 1, "unit": "g"},
                                      "alternatives": ["only one"]})
    with pytest.raises(ValidationError):
        JobResult(**base)
    ok = JobResult(**base, infeasible={"binding_constraint": "w", "best_achievable": {"value": 1, "unit": "g"},
                                       "alternatives": ["a", "b"]})
    assert ok.model_dump()["infeasible"]["alternatives"] == ["a", "b"]


def test_needs_info_needs_a_question():
    with pytest.raises(ValidationError):
        JobResult(status="needs_info", order_id="X")


def test_unknown_status_rejected():
    with pytest.raises(ValidationError):
        JobResult(status="maybe", order_id="X")


@pytest.mark.parametrize("brief,unit", [
    (Brief(piece_type="ring", karat=22, budget_inr=10000, gem="diamond", gem_ct=1.0), "ct"),   # stone > budget
    (Brief(piece_type="ring", karat=22, target_weight_g=1.0), "g"),                            # below min weight
    (Brief(piece_type="ring", karat=22, target_weight_g=1.2, gem="diamond", gem_ct=1.0), "g"),  # hero D
    (Brief(piece_type="pendant", karat=22, target_weight_g=0.3), "g"),
    (Brief(piece_type="ring", karat=18, budget_inr=15000), "g"),                                # budget below min
    (Brief(piece_type="ring"), "g"),                                                            # no target
])
def test_every_plan_failure_fills_the_contract(brief, unit):
    p = pricing.plan(brief, 3.0)
    assert not p.ok and p.explanation
    assert p.binding_constraint and p.best_achievable["unit"] == unit
    assert len(p.alternatives) >= 2


@pytest.mark.parametrize("reason", ["below_min", "above_max", "no_convergence"])
def test_solver_failures_fill_the_contract(reason):
    f = solve_failure(SolveResult(False, 1.0, 5.0, 4.0, [], reason), 3.0)
    assert f["binding_constraint"] and f["explanation"]
    assert f["best_achievable"] == {"value": round(5.0 * 0.97, 2), "unit": "g"}
    assert len(f["alternatives"]) >= 2


def test_orchestrator_infeasible_plan_returns_contract(tmp_path):
    orch = Orchestrator(registry.get("jewellery"), out_dir=tmp_path,
                        calibration=CalibrationStore(tmp_path / "c.json"))
    res = orch.handle("22K ring, size 14, under 1.2 g, with a 1 ct diamond")   # hero D
    assert res["status"] == "infeasible" and res["explanation"]
    JobResult.model_validate(res)
    inf = res["infeasible"]
    assert "minimum" in inf["binding_constraint"] and inf["best_achievable"]["unit"] == "g"
    assert len(inf["alternatives"]) >= 2


class AllFailPack(DomainPack):
    """No bpy: every variant misses, so the orchestrator must pool the failures."""
    name = "allfail"

    def intake(self, text, attachments=None):
        return Intake("brief", brief={"piece": "x"})

    def describe_brief(self, brief, lang="en"):
        return "x"

    def plan(self, brief, loss_pct):
        return Plan(True, target_value=4.0, detail={"casting_loss_pct": 3.0})

    def propose(self, brief, n=3):
        return ["a", "b"]

    def solve(self, spec, plan, on_iter=None):
        reason = "below_min" if spec == "a" else "above_max"
        value = 6.0 if spec == "a" else 4.2
        return Solved(spec, False, 1.0, value, 4.0, 2,
                      **{k: v for k, v in solve_failure(SolveResult(False, 1, value, 4.0, [], reason), 3.0).items()})


def test_orchestrator_all_variants_fail_returns_contract(tmp_path):
    res = Orchestrator(AllFailPack(), out_dir=tmp_path, calibration=CalibrationStore(tmp_path / "c.json")).handle("x")
    JobResult.model_validate(res)
    assert res["status"] == "infeasible"
    inf = res["infeasible"]
    assert inf["binding_constraint"].startswith("maximum")   # closest miss (4.2 vs 4.0) binds
    assert "a slimmer design" in inf["alternatives"] and "a bolder design" in inf["alternatives"]


def test_needs_info_and_scope_results_validate(tmp_path):
    orch = Orchestrator(registry.get("jewellery"), out_dir=tmp_path,
                        calibration=CalibrationStore(tmp_path / "c.json"))
    q = orch.handle("22K ring of 6g")
    assert q["status"] == "needs_info" and q["topics"] == ["ring_size"] and q["question"]
    s = orch.handle("I want a 22K gold necklace, 20 g")
    assert s["status"] == "out_of_scope" and s["suggestion"] == "pendant" and s["reply"]
    for r in (q, s):
        JobResult.model_validate(r)
