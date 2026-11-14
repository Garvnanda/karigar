"""Phase 7 end to end with the real shop floor (bpy, draft renders): a chat goes through the
service, the worker runs the real Orchestrator + jewellery pack, the reply's numbers match the
worker's order store, and the files are served. LLM off (conftest), everything in tmp_path."""
from karigar.core.calibration import CalibrationStore
from karigar.core.orchestrator import Orchestrator
from karigar.core.orders import OrderStore
from karigar.core import registry
from karigar.service.core import KarigarService
from karigar.service.worker import LocalClient, Worker
import karigar.packs.jewellery  # noqa: F401

from test_service_replies import assert_numbers_from_record


def test_chat_to_real_pipeline_and_back(tmp_path):
    store = OrderStore(tmp_path / "orders.sqlite3")

    def factory(tr, on_stage, out_dir, quality):
        return Orchestrator(registry.get("jewellery"), transport=tr, out_dir=out_dir, quality=quality,
                            calibration=CalibrationStore(tmp_path / "c.json"), store=store,
                            n_variants=2, on_stage=on_stage)
    svc = KarigarService(tmp_path / "svc")
    w = Worker(LocalClient(svc), out_dir=tmp_path / "out", quality="draft", orchestrator_factory=factory)
    msgs = [{"role": "system", "content": "You are Karigar."},
            {"role": "user", "content": "22K plain ring of 5g, size 12"}]
    t = svc.chat(msgs)
    w.run_once()
    text = svc.wait(t, "https://k.example", budget_s=1)
    job = svc.status(t.job_id)
    assert job["status"] == "done", job
    res = job["result"]
    assert res["status"] == "done", res
    order = store.get(res["order_id"])
    assert order.conversation_key == t.conv_key
    # the reply's numbers are the stored order's numbers
    record = {"versions": [{"finished_g": v.finished_g, "modelled_g": v.modelled_g, "quote": v.quote}
                           for v in order.versions], "results": res["results"]}
    assert_numbers_from_record(text, record)
    for r, v in zip(res["results"], order.versions):
        assert r["quote"]["total"] == v.quote["total"]
        assert abs(r["weights"]["finished_g"] - v.finished_g) < 0.001
    assert "[photo](https://k.example/files/" in text
    path = res["results"][0]["files"]["render_hero"]
    token, name = path.split("/")[2:4]
    assert svc.file(token, name)[0].stat().st_size > 0
