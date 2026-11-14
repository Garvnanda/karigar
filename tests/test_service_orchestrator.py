"""Phase 7 orchestrator glue (no bpy): stage hook + one structured log line per stage, numbers
stored and sent before renders, delivery failure marks the order failed, edit versions allocated
in the store transaction, and the Phase 3 hand-over (workshop tolerance, pack.weights)."""
import json
import logging
import threading
from types import SimpleNamespace

import pytest

from karigar.core.calibration import CalibrationStore
from karigar.core.orchestrator import Orchestrator
from karigar.core.orders import OrderStore
from karigar.core.registry import DomainPack, EditOutcome, Intake, Plan, Solved
from karigar.core.result import JobResult
from karigar.core.stagelog import stage_line
from karigar.core.transport import Transport


class Quiet(Transport):
    def say(self, agent, text):
        pass

    def send_file(self, agent, path, caption=""):
        pass


class Spec(SimpleNamespace):
    def model_dump(self):
        return dict(self.__dict__)


class FakePack(DomainPack):
    """Two designs solve; deliver writes small files (or fails when told to)."""
    name = "fake"

    def __init__(self, fail_deliver=False):
        self.fail_deliver = fail_deliver
        self.calls = []

    def intake(self, text, attachments=None, sender=None):
        return Intake("brief", brief={"piece": "ring"})

    def describe_brief(self, brief, lang="en"):
        return "a ring"

    def plan(self, brief, loss_pct):
        return Plan(True, target_value=5.0, detail={"casting_loss_pct": 3.0})

    def propose(self, brief, n=3):
        return [Spec(name="Plain"), Spec(name="Floral")]

    def solve(self, spec, plan, on_iter=None):
        return Solved(spec, True, 1.0, 5.0, 5.0, 2)

    def weights(self, solved, plan):
        tol = plan.detail.get("tolerance") or {"pct": 4.0}
        return {"casting_g": solved.value, "finished_g": round(solved.value * 0.97, 3),
                "tolerance_pct": tol["pct"], "tolerance_g": round(solved.value * 0.97 * tol["pct"] / 100, 2)}

    def quote(self, solved, brief, plan):
        self.calls.append("quote")
        return {"total": 51234, "summary": "total"}

    def deliver(self, solved, brief, plan, out_dir, quality):
        self.calls.append("deliver")
        if self.fail_deliver:
            raise RuntimeError("render crashed")
        out_dir.mkdir(parents=True, exist_ok=True)
        p = out_dir / "render_hero.png"
        p.write_bytes(b"png")
        return {"render_hero": p}

    # edits
    def load_brief(self, data):
        return data

    def parse_edit(self, text):
        return SimpleNamespace(pick="first", empty=False)

    def pick_index(self, pick, n):
        return 0

    def edit_text(self, key, lang):
        return "which one?"

    def apply_edit(self, spec, scale, modelled_g, request, plan, lang="en", on_iter=None):
        return EditOutcome("solved", solved=Solved(Spec(**spec), True, 0.9, 4.0, 4.0, 2), plan=plan)

    def edit_report(self, base, new_version, outcome, brief, lang="en"):
        return {"quote": {"total": 40000}, "spec_diff": {"width_mm": [2, 1.8]},
                "summary": f"v{new_version} from v{base['version']}"}


def orch(tmp_path, pack=None, calib=None, **kw):
    return Orchestrator(pack or FakePack(), transport=Quiet(), out_dir=tmp_path / "out",
                        calibration=calib or CalibrationStore(tmp_path / "c.json"),
                        store=OrderStore(tmp_path / "o.sqlite3"), **kw)


@pytest.fixture
def stage_log():
    lines = []

    class H(logging.Handler):
        def emit(self, rec):
            lines.append(json.loads(rec.getMessage()))
    h = H()
    lg = logging.getLogger("karigar.stage")
    lg.addHandler(h)
    yield lines
    lg.removeHandler(h)


def test_one_structured_log_line_per_stage(tmp_path, stage_log):
    res = orch(tmp_path).handle("ring")
    stages = [x["stage"] for x in stage_log if x["event"] == "stage"]
    assert stages == ["intake", "plan", "design", "solve", "solved", "deliver", "done"]
    for x in stage_log:
        assert x["order_id"] == res["order_id"] and isinstance(x["ms"], int) and "ts" in x


def test_stage_line_keeps_only_short_scalars():
    d = json.loads(stage_line("plan", order_id="O" * 500, data={"secret": 1}, n=3))
    assert len(d["order_id"]) == 120 and d["data"] == "dict" and d["n"] == 3


def test_solved_stage_carries_numbers_before_any_render(tmp_path):
    pack = FakePack()
    seen = []

    def hook(stage, data):
        seen.append((stage, list(pack.calls), data))
    orch(tmp_path, pack, on_stage=hook).handle("ring")
    stage, calls, data = next(s for s in seen if s[0] == "solved")
    assert "deliver" not in calls                       # numbers first, renders after
    JobResult.model_validate(data)
    assert [r["version"] for r in data["results"]] == [1, 2]
    assert data["results"][0]["quote"]["total"] == 51234 and data["results"][0]["files"] == {}


def test_delivery_failure_marks_order_failed_and_keeps_numbers(tmp_path):
    o = orch(tmp_path, FakePack(fail_deliver=True))
    with pytest.raises(RuntimeError):
        o.handle("ring")
    [row] = o.store.list()
    stored = o.store.get(row["order_id"])
    assert stored.status == "failed"
    assert [v.version for v in stored.versions] == [1, 2]   # spec, weight, quote kept
    assert stored.versions[0].quote["total"] == 51234 and stored.versions[0].outputs == {}


def test_success_keeps_done_and_outputs(tmp_path):
    o = orch(tmp_path)
    res = o.handle("ring")
    stored = o.store.get(res["order_id"])
    assert stored.status == "done" and "render_hero" in stored.versions[0].outputs
    assert res["results"][0]["files"]["render_hero"].endswith("render_hero.png")


def test_phase3_workshop_tolerance_reaches_plan_and_weights(tmp_path):
    calib = CalibrationStore(tmp_path / "c.json")
    for designed, actual in ((10, 9.7), (10, 9.6), (10, 9.75)):
        calib.record("w1", designed, actual)
    o = orch(tmp_path, calib=calib, workshop="w1")
    res = o.handle("ring")
    tol = calib.tolerance("w1")
    assert res["plan"]["tolerance"] == tol
    w = res["results"][0]["weights"]
    assert w["tolerance_pct"] == tol["pct"] and "casting_g" in w   # from pack.weights, not inline


def test_phase3_edit_uses_workshop_tolerance_and_pack_weights(tmp_path):
    o = orch(tmp_path)
    oid = o.handle("ring")["order_id"]
    res = o.handle_edit(oid, "thinner")
    assert res["plan"]["tolerance"] == o.calib.tolerance(None)
    assert res["results"][0]["weights"]["casting_g"] == 4.0


def test_edit_version_reserved_in_store_and_folder_matches(tmp_path):
    o = orch(tmp_path)
    oid = o.handle("ring")["order_id"]
    o.store.reserve_version(oid)                          # a concurrent edit took v3 meanwhile
    res = o.handle_edit(oid, "thinner")
    assert res["edit"]["to_version"] == 4 and res["edit"]["summary"] == "v4 from v1"
    assert (tmp_path / "out" / oid / "v4" / "render_hero.png").is_file()
    assert o.store.get(oid).version(4).parent == 1


def test_concurrent_reservations_never_share_a_number(tmp_path):
    store = OrderStore(tmp_path / "o.sqlite3")
    store.create_order("ORD-1", request="r", brief={}, plan={}, lang="en", status="done")
    got, errs = [], []

    def go():
        try:
            for _ in range(10):
                got.append(store.reserve_version("ORD-1"))
        except Exception as e:      # pragma: no cover - the assertion below reports it
            errs.append(e)
    ts = [threading.Thread(target=go) for _ in range(4)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert not errs and sorted(got) == list(range(1, 41))
    n = store.add_version("ORD-1", spec={}, scale=1, modelled_g=1, finished_g=1, target_g=1, quote={})
    assert n == 41


def test_set_status_unknown_order(tmp_path):
    from karigar.core.orders import UnknownOrder
    with pytest.raises(UnknownOrder):
        OrderStore(tmp_path / "o.sqlite3").set_status("nope", "failed")
