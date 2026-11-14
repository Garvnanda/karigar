"""Phase 7 HTTP adapters with both sides local: the service on an ephemeral loopback port and the
worker polling it over HTTP (HttpClient), exactly as the laptop polls Render. No tunnel, no bpy,
no LLM (scripted fake shop floor), files in tmp_path."""
import http.client
import json
import socket
import threading
import time

import pytest

from karigar.service.core import KarigarService
from karigar.service.http import make_server, validate_chat
from karigar.service.worker import HttpClient, ServiceError, Worker
from service_fakes import Script, make_factory

KEY, WTOK, OWNER = "api-key-123456", "worker-token-987654", "owner-token-555"
SYSTEM = {"role": "system", "content": "You are Karigar."}
TOOLS = [{"type": "function", "function": {"name": f"tool_{i}", "parameters": {"type": "object"}}}
         for i in range(103)]


@pytest.fixture
def env(tmp_path):
    svc = KarigarService(tmp_path / "svc", reply_budget_s=3.0)
    console = tmp_path / "console"
    console.mkdir()
    (console / "index.html").write_text("<h1>console</h1>")
    (tmp_path / "outside.txt").write_text("secret")
    srv = make_server("127.0.0.1", 0, svc, KEY, WTOK, owner_token=OWNER, console_dir=console)
    th = threading.Thread(target=srv.serve_forever, daemon=True)
    th.start()
    port = srv.server_address[1]
    script = Script()
    worker = Worker(HttpClient(f"http://127.0.0.1:{port}", WTOK), out_dir=tmp_path / "out",
                    orchestrator_factory=make_factory(script), poll_s=0.05)
    yield type("Env", (), {"svc": svc, "port": port, "script": script, "worker": worker,
                           "base": f"http://127.0.0.1:{port}"})
    worker.stop.set()
    srv.shutdown()
    srv.server_close()


def req(env, method, path, body=None, token=KEY, headers=None, raw=None):
    c = http.client.HTTPConnection("127.0.0.1", env.port, timeout=20)
    h = dict(headers or {})
    if token:
        h["Authorization"] = f"Bearer {token}"
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
    if data is not None:
        h.setdefault("Content-Type", "application/json")
    c.request(method, path, body=data, headers=h)
    r = c.getresponse()
    out = r.read()
    c.close()
    try:
        return r.status, json.loads(out), r
    except ValueError:
        return r.status, out, r


def start_worker(env):
    th = threading.Thread(target=env.worker.run_forever, daemon=True, name="karigar-worker")
    th.start()
    return th


def chat(env, messages, path="/v1/chat/completions", stream=False, **extra):
    return req(env, "POST", path, {"model": "karigar", "messages": messages, "stream": stream, **extra})


def sse(env, messages, path="/v1/chat/completions"):
    c = http.client.HTTPConnection("127.0.0.1", env.port, timeout=30)
    c.request("POST", path, body=json.dumps({"model": "karigar", "stream": True, "messages": messages,
                                             "tools": TOOLS, "tool_choice": "auto"}),
              headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"})
    r = c.getresponse()
    assert r.status == 200 and r.getheader("Content-Type") == "text/event-stream"
    events = [x[6:] for x in r.read().decode().split("\n\n") if x.startswith("data: ")]
    c.close()
    assert events[-1] == "[DONE]"
    chunks = [json.loads(e) for e in events[:-1]]
    assert chunks[0]["choices"][0]["delta"]["role"] == "assistant"
    assert chunks[-1]["choices"][0]["finish_reason"] == "stop"
    return "".join(ch["choices"][0]["delta"].get("content", "") for ch in chunks)


# --------------------------------------------------------------- models, auth, validation
@pytest.mark.parametrize("prefix", ["/v1", "/sakhi/v1", "/karigar/v1"])
def test_models(env, prefix):
    st, body, _ = req(env, "GET", prefix + "/models")
    assert st == 200 and body["data"][0]["id"] == "karigar"
    assert req(env, "GET", prefix + "/models/karigar")[0] == 200
    assert req(env, "GET", prefix + "/models/other")[0] == 404


def test_auth_required_and_checked_before_body(env, monkeypatch):
    import karigar.service.http as H
    parsed = []
    monkeypatch.setattr(H, "_parse_json", lambda raw: parsed.append(raw) or {})
    assert req(env, "GET", "/v1/models", token=None)[0] == 401
    assert req(env, "GET", "/v1/models", token="wrong")[0] == 401
    assert req(env, "GET", "/v1/models", token=WTOK)[0] == 401          # worker token ≠ API key
    parsed.clear()
    st, _, _ = req(env, "POST", "/v1/chat/completions", {"messages": []}, token="wrong")
    assert st == 401 and parsed == []
    assert req(env, "GET", "/worker/jobs", token=KEY)[0] == 401          # API key ≠ worker token
    assert req(env, "GET", "/api/jobs/J-1", token=WTOK)[0] == 401


def test_health_needs_no_key(env):
    st, body, _ = req(env, "GET", "/", token=None)
    assert st == 200 and body["service"] == "karigar" and body["worker_online"] is False


@pytest.mark.parametrize("body,ok", [
    ({"messages": [{"role": "user", "content": "x"}]}, True),
    ({"messages": [{"role": "user", "content": [{"type": "text", "text": "x"}]}], "tools": TOOLS,
      "tool_choice": "auto", "metadata": {"a": 1}, "temperature": 0.2, "user": "u"}, True),
    ({"messages": []}, False),
    ({"messages": "hi"}, False),
    ({"messages": [{"content": "x"}]}, False),
    ({"messages": [{"role": "boss", "content": "x"}]}, False),
    ({"messages": [{"role": "user", "content": 5}]}, False),
    ({"messages": [{"role": "user", "content": "x"}], "stream": "yes"}, False),
    ({"messages": [{"role": "user", "content": "x"}], "model": 3}, False),
    ([1, 2], False),
])
def test_validate_chat(body, ok):
    assert (validate_chat(body) is None) == ok


def test_invalid_chat_is_400_and_bad_json_400(env):
    assert chat(env, [])[0] == 400
    st, body, _ = req(env, "POST", "/v1/chat/completions", raw=b"{not json")
    assert st == 400 and body["error"]["code"] == "invalid_json"
    assert req(env, "POST", "/other/v1/chat/completions", {"messages": [{"role": "user", "content": "x"}]})[0] == 404


def test_tools_and_unknown_fields_ignored(env):
    start_worker(env)
    st, body, _ = chat(env, [SYSTEM, {"role": "user", "content": "22K ring 5g size 12"}],
                       tools=TOOLS, tool_choice="auto", parallel_tool_calls=True, metadata={"x": 1})
    assert st == 200 and body["object"] == "chat.completion"
    msg = body["choices"][0]["message"]
    assert "tool_calls" not in msg and "Plain" in msg["content"]


# --------------------------------------------------------------- streaming, conversation
def test_stream_progress_then_result_with_links(env):
    start_worker(env)
    text = sse(env, [SYSTEM, {"role": "user", "content": "22K ring 5g size 12"}])
    assert "_weights and quote ready…_" in text                  # live stage lines
    assert "[photo](http://127.0.0.1" in text and "/files/" in text and "![" not in text
    link = text.split("[photo](")[1].split(")")[0]
    path = link.split(str(env.port))[1]
    st, data, r = req(env, "GET", path, token=None)               # unguessable link, no key
    assert st == 200 and data.startswith(b"\x89PNG") and r.getheader("Content-Type") == "image/png"
    tok = path.split("/")[2]
    assert req(env, "GET", path.replace(tok, tok[:-2] + "xx"), token=None)[0] == 404


def test_two_agents_share_one_service(env):
    start_worker(env)
    h = [SYSTEM, {"role": "user", "content": "22K ring 5g size 12"}]
    k = sse(env, h, "/karigar/v1/chat/completions")
    assert k.lstrip("\n_").count("**Karigar**") == 1 and "[STL](" in k
    h2 = [{"role": "system", "content": "You are Sakhi."}, {"role": "user", "content": "22K ring 6g size 14"}]
    s = sse(env, h2, "/sakhi/v1/chat/completions")
    assert "**Sakhi**" in s and "[STL](" not in s and "[photo](" in s   # counter: photo + quote


def test_conversation_continues_over_http(env):
    start_worker(env)
    h = [SYSTEM, {"role": "user", "content": "22K ring 5g"}]
    r1 = sse(env, h)
    assert "Which ring size?" in r1
    h += [{"role": "assistant", "content": r1}, {"role": "user", "content": "size 12"}]
    r2 = sse(env, h)
    assert "Floral" in r2
    h += [{"role": "assistant", "content": r2}, {"role": "user", "content": "middle one"}]
    assert "Picked v2" in sse(env, h)


def test_retried_http_request_never_builds_twice(env):
    start_worker(env)
    h = [SYSTEM, {"role": "user", "content": "22K ring 5g size 12"}]
    a = sse(env, h)
    b = sse(env, h)
    assert len([c for c in env.script.calls if c[0] == "handle"]) == 1
    assert a.split("_ref ")[1] == b.split("_ref ")[1]


def test_worker_down_reply_returns_fast_and_job_waits(env):
    t0 = time.monotonic()
    text = sse(env, [SYSTEM, {"role": "user", "content": "22K ring 5g size 12"}])
    assert time.monotonic() - t0 < 8 and "offline" in text
    start_worker(env)
    deadline = time.time() + 10
    while not env.script.calls and time.time() < deadline:
        time.sleep(0.05)
    h = [SYSTEM, {"role": "user", "content": "22K ring 5g size 12"},
         {"role": "assistant", "content": text}, {"role": "user", "content": "any news?"}]
    assert "Plain" in sse(env, h)                                 # same job, result fetched


def test_llm_never_called_in_request_handler(env):
    """Requests are answered with no worker running: nothing (shop floor, LLM) ran in the
    handler. Once the worker runs, every LLM call is on the worker's thread."""
    sse(env, [SYSTEM, {"role": "user", "content": "22K ring 5g size 12"}])
    assert env.script.llm_threads == []
    start_worker(env)
    deadline = time.time() + 10
    while not env.script.llm_threads and time.time() < deadline:
        time.sleep(0.05)
    assert env.script.llm_threads == ["karigar-worker"]


# --------------------------------------------------------------- JSON API adapter
def test_json_api(env):
    st, body, _ = req(env, "POST", "/api/orders", {"text": "22K ring 5g size 12", "conversation": "K-api"},
                      headers={"Idempotency-Key": "abc"})
    assert st == 202 and body["conversation"] == "K-api" and body["status"] == "queued"
    st2, body2, _ = req(env, "POST", "/api/orders", {"text": "22K ring 5g size 12", "conversation": "K-api"},
                        headers={"Idempotency-Key": "abc"})
    assert st2 == 200 and body2["job_id"] == body["job_id"]       # idempotent retry
    start_worker(env)
    st, job, _ = req(env, "GET", f"/api/jobs/{body['job_id']}")
    deadline = time.time() + 10
    while job["status"] != "done" and time.time() < deadline:
        time.sleep(0.05)
        st, job, _ = req(env, "GET", f"/api/jobs/{body['job_id']}")
    oid = job["order_id"]
    st, q, _ = req(env, "GET", f"/api/orders/{oid}/quote", token=OWNER)   # owner token works too
    assert st == 200 and q["versions"]["1"]["quote"]["total"] == 61234
    st, e, _ = req(env, "POST", f"/api/orders/{oid}/edits", {"text": "middle one, lighter", "wait_s": 5})
    assert "v4 (from v2)" in e["reply"]
    st, m, _ = req(env, "POST", "/api/conversations/K-api/messages", {"text": "middle one", "wait_s": 5})
    assert "Picked v2" in m["reply"]
    assert req(env, "POST", "/api/orders", {"text": ""})[0] == 400
    assert req(env, "POST", "/api/orders", {"text": "x", "conversation": "../../x"})[0] == 400
    assert req(env, "GET", "/api/jobs/J-nope")[0] == 404


# --------------------------------------------------------------- worker API
def test_worker_api_validation(env):
    assert req(env, "GET", "/worker/jobs", token=WTOK)[1] == {"job": None}
    assert req(env, "POST", "/worker/jobs/J-nope/progress", {"lines": []}, token=WTOK)[0] == 404
    req(env, "POST", "/api/orders", {"text": "22K ring 5g size 12"})
    job = req(env, "GET", "/worker/jobs", token=WTOK)[1]["job"]
    jid = job["job_id"]
    assert req(env, "POST", f"/worker/jobs/{jid}/result", {"result": "x"}, token=WTOK)[0] == 400
    st, body, _ = req(env, "POST", f"/worker/jobs/{jid}/files?name=..%2Fevil.png", token=WTOK, raw=b"x",
                      headers={"Content-Type": "application/octet-stream"})
    assert st == 400
    st, body, _ = req(env, "POST", f"/worker/jobs/{jid}/files?name=v1-a.png", token=WTOK, raw=b"\x89PNG",
                      headers={"Content-Type": "application/octet-stream"})
    assert st == 200 and body["path"].startswith("/files/")


def test_http_client_refuses_plain_http_off_localhost():
    with pytest.raises(ValueError):
        HttpClient("http://example.com", WTOK)
    with pytest.raises(ValueError):
        HttpClient("https://example.com", "")
    HttpClient("https://karigar.onrender.com", WTOK)


def test_worker_survives_service_down():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    c = HttpClient(f"http://127.0.0.1:{port}", WTOK, timeout=1)
    with pytest.raises(ServiceError):
        c.claim()
    sleeps = []
    w = Worker(c, poll_s=0.01, sleep=lambda s: (sleeps.append(s), w.stop.set() if len(sleeps) > 2 else None))
    w.run_forever()                                                # backs off, never raises
    assert sleeps[1] > sleeps[0]


# --------------------------------------------------------------- console (Phase 10 hook)
def test_console_static_files_and_traversal(env):
    st, data, _ = req(env, "GET", "/console/", token=None)
    assert st == 200 and b"console" in data
    assert req(env, "GET", "/console/../outside.txt", token=None)[0] == 404
    assert req(env, "GET", "/console/%2e%2e/outside.txt", token=None)[0] == 404


def test_server_refuses_missing_or_equal_secrets(tmp_path):
    svc = KarigarService(tmp_path / "s")
    with pytest.raises(ValueError):
        make_server("127.0.0.1", 0, svc, "", WTOK)
    with pytest.raises(ValueError):
        make_server("127.0.0.1", 0, svc, KEY, KEY)
