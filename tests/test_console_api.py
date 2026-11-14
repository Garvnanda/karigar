"""Phase 10: console data endpoints. Every number shown comes from the worker's JobResult (no bpy)."""
import json
import threading
import urllib.request

import pytest

from karigar.service.core import KarigarService
from karigar.service.http import make_server
from karigar.service.worker import LocalClient, Worker
from service_fakes import QUOTES, WEIGHTS, Script, make_factory


@pytest.fixture
def svc(tmp_path):
    return KarigarService(tmp_path / "svc")


@pytest.fixture
def worker(svc, tmp_path):
    return Worker(LocalClient(svc), out_dir=tmp_path / "out", quality="draft",
                  orchestrator_factory=make_factory(Script()), sleep=lambda s: None)


def run(worker):
    while worker.run_once() is not None:
        pass


def test_orders_list_and_detail_carry_the_workers_numbers(svc, worker):
    t = svc.start_order("22K ring 5g size 12")
    run(worker)
    oid = svc.status(t.job_id)["order_id"]
    rows = svc.orders()
    assert [r["order_id"] for r in rows] == [oid]
    assert rows[0]["finished_g"] == [w["finished_g"] for w in WEIGHTS]
    assert rows[0]["total_inr"] == [q["total"] for q in QUOTES]
    o = svc.order(oid)
    assert o["request"] == "22K ring 5g size 12" and len(o["versions"]) == 3
    assert o["versions"][1]["quote"]["total"] == QUOTES[1]["total"]
    assert svc.order("ORD-missing") is None


def test_system_reports_worker_and_queue(svc, worker):
    assert svc.system()["worker_online"] is False
    svc.start_order("22K ring 5g size 12")
    assert svc.system()["by_status"] == {"queued": 1}
    run(worker)
    s = svc.system()
    assert s["worker_online"] is True and s["by_status"] == {"done": 1}


def test_console_routes_need_the_owner_token(svc, worker, tmp_path):
    (tmp_path / "c").mkdir()
    (tmp_path / "c" / "index.html").write_text("<title>Karigar</title>")
    srv = make_server("127.0.0.1", 0, svc, "api-key-1", "worker-tok-1", owner_token="owner-tok-1",
                      console_dir=tmp_path / "c")
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    try:
        svc.start_order("22K ring 5g size 12")
        run(worker)

        def get(path, tok=None):
            req = urllib.request.Request(base + path, headers={"Authorization": f"Bearer {tok}"} if tok else {})
            try:
                with urllib.request.urlopen(req, timeout=5) as r:
                    return r.status, r.read()
            except urllib.error.HTTPError as e:
                return e.code, e.read()
        assert get("/api/orders")[0] == 401
        code, body = get("/api/orders", "owner-tok-1")
        assert code == 200 and len(json.loads(body)["orders"]) == 1
        assert get("/api/system", "owner-tok-1")[0] == 200
        assert get("/console/")[0] == 200            # static page itself needs no key; its data does
    finally:
        srv.shutdown()


def test_demo_console_chat_flow_end_to_end_over_http(svc, tmp_path):
    """What console/app.js does in "Try it": question → answer → designs, over the real server."""
    srv = make_server("127.0.0.1", 0, svc, "api-key-1", "worker-tok-1", owner_token="owner-tok-1")
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    w = Worker(LocalClient(svc), out_dir=tmp_path / "out", quality="draft",
               orchestrator_factory=make_factory(Script()), sleep=lambda s: None)
    stop = threading.Event()

    def work():
        while not stop.is_set():
            if w.run_once() is None:
                stop.wait(0.05)
    threading.Thread(target=work, daemon=True).start()

    def post(path, body):
        req = urllib.request.Request(base + path, json.dumps(body).encode(), method="POST",
                                     headers={"Authorization": "Bearer owner-tok-1",
                                              "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read())
    try:
        r1 = post("/api/orders", {"text": "22K ring 5g", "agent": "karigar", "wait_s": 10})
        assert "ring size" in r1["reply"].lower()
        r2 = post(f"/api/conversations/{r1['conversation']}/messages", {"text": "size 12", "wait_s": 10})
        assert r2["conversation"] == r1["conversation"]
        assert "₹61,234" in r2["reply"] and "4.97 g" in r2["reply"]
    finally:
        stop.set()
        srv.shutdown()


def test_shop_snapshot_and_calibration_come_from_the_worker(svc, tmp_path, monkeypatch):
    from karigar.core.calibration import CalibrationStore
    from karigar.service import worker as W
    cal = CalibrationStore(tmp_path / "cal.json")
    real = W.shop_action
    monkeypatch.setattr(W, "shop_action", lambda p, ws: real(p, ws, calibration=cal))
    w = Worker(LocalClient(svc), out_dir=tmp_path / "out", quality="draft",
               orchestrator_factory=make_factory(Script()), sleep=lambda s: None)
    assert svc.shop_state() is None
    svc.shop("calibrate", workshop="w1", designed_g=10.0, actual_g=9.6)
    run(w)
    st = svc.shop_state()
    assert st["calibration"]["records"] == 1 and st["calibration"]["loss_pct"] == 4.0
    r22 = next(r for r in st["rates"] if r["karat"] == 22)
    assert r22["status"] == "ok" and r22["per_g"] == 12971.2          # conftest seed rate
    assert cal.loss_pct("w1") == pytest.approx(4.0)                   # really recorded


def test_shop_api_validates_calibration_input(svc, tmp_path):
    srv = make_server("127.0.0.1", 0, svc, "api-key-1", "worker-tok-1", owner_token="owner-tok-1")
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"

    def post(body):
        req = urllib.request.Request(base + "/api/shop", json.dumps(body).encode(), method="POST",
                                     headers={"Authorization": "Bearer owner-tok-1"})
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                return r.status
        except urllib.error.HTTPError as e:
            return e.code
    try:
        assert post({"action": "calibrate", "workshop": "w1", "designed_g": -1, "actual_g": 9}) == 400
        assert post({"action": "calibrate", "workshop": "../x", "designed_g": 10, "actual_g": 9}) == 400
        assert post({"action": "rm -rf"}) == 400
        assert post({"action": "snapshot"}) == 202
    finally:
        srv.shutdown()
