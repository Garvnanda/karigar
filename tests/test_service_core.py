"""Phase 7 KarigarService (transport-free core) + worker, both in-process (LocalClient).

No bpy, no LLM (a scripted fake shop floor, tests/service_fakes.py), service files in tmp_path.
"""
import threading
import time

import pytest

from karigar.service import convo
from karigar.service.core import KarigarService, Ticket
from karigar.service.worker import LocalClient, Worker
from service_fakes import Script, make_factory

SYSTEM = {"role": "system", "content": "Nonilion room Gold Street. You are Karigar."}


@pytest.fixture
def svc(tmp_path):
    return KarigarService(tmp_path / "svc")


@pytest.fixture
def script():
    return Script()


@pytest.fixture
def worker(svc, script, tmp_path):
    return Worker(LocalClient(svc), out_dir=tmp_path / "out", quality="draft",
                  orchestrator_factory=make_factory(script), sleep=lambda s: None)


def hist(*turns):
    """[system, user, assistant, user, ...] from alternating strings."""
    out = [SYSTEM]
    for i, t in enumerate(turns):
        out.append({"role": "user" if i % 2 == 0 else "assistant", "content": t})
    return out


def say(svc, worker, messages, agent="karigar", budget=0.0):
    t = svc.chat(messages, agent)
    while worker.run_once() is not None:
        pass
    return t, svc.wait(t, "https://k.example", budget_s=budget)


# --------------------------------------------------------------- conversation → order
def test_first_message_key_from_system_and_first_user(svc):
    a = svc.chat(hist("22K ring 5g size 12"))
    b = svc.chat(hist("22K ring 5g size 12"))               # a retry: same key, same job
    assert a.conv_key == b.conv_key and a.job_id == b.job_id and a.created and not b.created
    other_room = [{"role": "system", "content": "Nonilion room Silver Lane. You are Karigar."},
                  {"role": "user", "content": "22K ring 5g size 12"}]
    assert svc.chat(other_room).conv_key != a.conv_key


def test_same_opening_much_later_gets_a_new_conversation(tmp_path):
    now = [1000.0]
    svc = KarigarService(tmp_path / "svc", clock=lambda: now[0])
    a = svc.chat(hist("22K ring 5g size 12"))
    now[0] += convo.RETRY_WINDOW_S + 1
    b = svc.chat(hist("22K ring 5g size 12"))
    assert a.conv_key != b.conv_key and a.job_id != b.job_id


def test_reply_carries_ref_and_ref_pins_the_conversation(svc, worker):
    t, text = say(svc, worker, hist("22K ring 5g size 12"))
    assert convo.ref_line(t.conv_key) in text
    t2 = svc.chat(hist("22K ring 5g size 12", text, "middle one"))
    assert t2.conv_key == t.conv_key


def test_answer_to_question_continues_the_same_request(svc, worker, script):
    t, text = say(svc, worker, hist("22K ring 5g"))
    assert "Which ring size?" in text
    t2, text2 = say(svc, worker, hist("22K ring 5g", text, "size 12"))
    assert t2.conv_key == t.conv_key
    assert script.calls[-1] == ("handle", "22K ring 5g\nsize 12", t.conv_key)
    assert "Plain" in text2 and "Floral" in text2


def test_pick_and_edit_continue_the_same_order(svc, worker, script):
    _, r1 = say(svc, worker, hist("22K ring 5g size 12"))
    _, r2 = say(svc, worker, hist("22K ring 5g size 12", r1, "middle one"))
    assert script.calls[-1] == ("edit", "ORD-2026-0001", "middle one") and "Picked v2" in r2
    _, r3 = say(svc, worker, hist("22K ring 5g size 12", r1, "middle one", r2, "middle one, lighter"))
    assert script.calls[-1][0] == "edit" and "v4 (from v2)" in r3


def test_unparsed_edit_that_reads_as_new_order_becomes_new_order(svc, worker, script):
    _, r1 = say(svc, worker, hist("22K ring 5g size 12"))
    _, r2 = say(svc, worker, hist("22K ring 5g size 12", r1, "another 18K ring size 14"))
    assert [c[0] for c in script.calls[-2:]] == ["edit", "handle"]
    assert "ORD-2026-0002" in r2


# --------------------------------------------------------------- idempotency
def test_retried_request_never_builds_twice(svc, worker, script):
    h = hist("22K ring 5g size 12")
    t1, r1 = say(svc, worker, h)
    t2, r2 = say(svc, worker, h)                            # Nonilion retries the same call
    assert t1.job_id == t2.job_id
    assert [c for c in script.calls if c[0] == "handle"] == [("handle", "22K ring 5g size 12", t1.conv_key)]


def test_concurrent_retries_share_one_job(svc):
    h = hist("22K ring 5g size 12")
    tickets = []
    ts = [threading.Thread(target=lambda: tickets.append(svc.chat(h))) for _ in range(8)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert len({t.job_id for t in tickets}) == 1 and sum(t.created for t in tickets) == 1


def test_worker_reupload_changes_nothing(svc, worker):
    t, _ = say(svc, worker, hist("22K ring 5g size 12"))
    before = svc.status(t.job_id)
    svc.finish(t.job_id, {"status": "done", "order_id": "X", "results": []})
    assert svc.status(t.job_id)["result"] == before["result"]


# --------------------------------------------------------------- timeouts, worker down
def test_reply_within_budget_while_work_runs(svc):
    t = svc.chat(hist("22K ring 5g size 12"))
    svc.claim()                                            # a worker took it, nothing solved yet
    t0 = time.monotonic()
    text = svc.wait(t, "https://k.example", budget_s=0.5)
    assert time.monotonic() - t0 < 2
    assert "Still working" in text and "Send any message" in text


def test_worker_offline_says_so_quickly(svc):
    t = svc.chat(hist("22K ring 5g size 12"))
    t0 = time.monotonic()
    text = svc.wait(t, "https://k.example", budget_s=30)
    assert time.monotonic() - t0 < 7
    assert "offline" in text and "saved" in text
    assert svc.status(t.job_id)["status"] == "queued"


def test_render_timeout_numbers_first_renders_on_next_message(svc, worker, script):
    script.gate = threading.Event()
    h = hist("22K ring 5g size 12")
    t = svc.chat(h)
    th = threading.Thread(target=worker.run_once)
    th.start()
    deadline = time.time() + 5
    while svc.status(t.job_id)["status"] != "solved" and time.time() < deadline:
        time.sleep(0.05)
    text = svc.wait(t, "https://k.example", budget_s=0.3)
    assert "4.97 g" in text and "₹61,234" in text           # spec, weight and quote first
    assert "still rendering" in text and "](" not in text      # no links yet
    script.gate.set()
    th.join(5)
    t2 = svc.chat(hist("22K ring 5g size 12", text, "ok?"))
    assert t2.job_id == t.job_id                               # the next message fetches them
    text2 = svc.wait(t2, "https://k.example", budget_s=1)
    assert "[photo](https://k.example/files/" in text2 and "[STL](" in text2


def test_render_failure_still_sends_numbers(svc, worker, script):
    script.fail_render = True
    t, text = say(svc, worker, hist("22K ring 5g size 12"))
    assert svc.status(t.job_id)["status"] == "failed"
    assert "₹61,234" in text and "failed" in text


def test_worker_vanishes_after_solving_reaped_to_numbers(tmp_path):
    now = [1000.0]
    svc = KarigarService(tmp_path / "svc", clock=lambda: now[0], sleep=lambda s: now.__setitem__(0, now[0] + s))
    t = svc.chat(hist("22K ring 5g size 12"))
    job = svc.claim()
    svc.stage_solved(job["job_id"], {"status": "done", "order_id": "O1", "results": [
        {"variant": "Plain", "version": 1, "weights": {"finished_g": 4.97}, "quote": {"total": 61234}}]})
    now[0] += 10_000
    text = svc.wait(Ticket(t.conv_key, t.job_id), "https://k.example", budget_s=1)
    assert "₹61,234" in text and "could not be made" in text
    assert svc.status(t.job_id)["status"] == "done"


def test_worker_lost_before_solving_is_retried_once_then_failed(tmp_path):
    now = [1000.0]
    svc = KarigarService(tmp_path / "svc", clock=lambda: now[0])
    t = svc.chat(hist("22K ring 5g size 12"))
    assert svc.claim()["job_id"] == t.job_id
    now[0] += svc.lease_s + 1
    assert svc.claim()["job_id"] == t.job_id                  # lease expired: second attempt
    now[0] += svc.lease_s + 1
    assert svc.claim() is None
    assert svc.status(t.job_id)["status"] == "failed"


# --------------------------------------------------------------- core API (transport-free)
def test_start_status_edit_quote(svc, worker):
    t = svc.start_order("22K ring 5g size 12", conversation="K-demo")
    worker.run_once()
    st = svc.status(t.job_id)
    assert st["status"] == "done" and st["order_id"] == "ORD-2026-0001"
    q = svc.quote("ORD-2026-0001")
    assert q["versions"]["2"]["quote"]["total"] == 72345
    e = svc.edit("ORD-2026-0001", "middle one, lighter")
    worker.run_once()
    assert svc.status(e.job_id)["result"]["edit"]["to_version"] == 4
    assert svc.quote("ORD-2026-0001")["versions"]["4"]["quote"]["total"] == 65000
    assert svc.status("J-none") is None and svc.quote("nope") is None


def test_files_uploaded_with_unguessable_paths_and_only_outputs(svc, worker):
    t, _ = say(svc, worker, hist("22K ring 5g size 12"))
    files = svc.status(t.job_id)["result"]["results"][0]["files"]
    assert set(files) == {"render_hero", "stl"}                # order_json etc. not uploaded
    path = files["render_hero"]
    token, name = path.split("/")[2:4]
    assert len(token) >= 32 and name == "v1-render_hero.png"
    p, ctype = svc.file(token, name)
    assert p.read_bytes().startswith(b"\x89PNG") and ctype == "image/png"
    assert svc.file(token, "other.png") is None and svc.file("x" * 32, name) is None


@pytest.mark.parametrize("name", ["../x.png", ".hidden.png", "a.exe", "", "a/b.png"])
def test_upload_rejects_bad_names(svc, name):
    t = svc.chat(hist("22K ring 5g size 12"))
    with pytest.raises(ValueError):
        svc.upload_file(t.job_id, name, b"x")


def test_empty_message_gets_a_greeting_without_a_job(svc):
    t = svc.chat([SYSTEM, {"role": "user", "content": "  "}])
    assert t.job_id is None and "Namaste" in svc.wait(t, "")


def test_llm_runs_only_in_the_worker_thread(svc, script, tmp_path):
    """The request side (chat + wait) never runs the shop floor or an LLM: with no worker
    running, nothing is called; the worker thread makes the calls."""
    t = svc.chat(hist("22K ring 5g size 12"))
    svc.wait(t, "", budget_s=0.2)
    assert script.calls == [] and script.llm_threads == []
    w = Worker(LocalClient(svc), out_dir=tmp_path / "out", orchestrator_factory=make_factory(script))
    th = threading.Thread(target=w.run_once, name="karigar-worker")
    th.start()
    th.join(10)
    assert script.llm_threads == ["karigar-worker"]
