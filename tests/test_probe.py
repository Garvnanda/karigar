"""Phase 6.5: the Nonilion probe (an OpenAI-compatible endpoint that logs what it is sent)."""
import json
import threading
import time
import urllib.error
import urllib.request

import pytest

from probe.server import make_server, parse_directives

KEY = "sk-probe-test-0123456789"


@pytest.fixture
def probe(tmp_path):
    log = tmp_path / "requests.jsonl"
    srv = make_server("127.0.0.1", 0, api_key=KEY, log_path=log, delay_s=0, stream_lines=2)
    t = threading.Thread(target=srv.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
    t.start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    yield base, log
    srv.shutdown()
    srv.server_close()


def call(base, path, body=None, key=KEY, method=None, headers=None):
    data = json.dumps(body).encode() if body is not None else None
    h = {"Content-Type": "application/json", **(headers or {})}
    if key is not None:
        h["Authorization"] = f"Bearer {key}"
    req = urllib.request.Request(base + path, data=data, headers=h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, dict(r.headers), r.read().decode(errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read().decode()


def entries(log):
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines() if line.strip()]


def chat(text="hello", **extra):
    return {"model": "karigar-probe", "messages": [{"role": "system", "content": "be Sakhi"},
                                                   {"role": "user", "content": text}], **extra}


# --- auth -----------------------------------------------------------------------------------

def test_missing_or_wrong_key_gets_openai_style_401(probe):
    base, _ = probe
    for key in (None, "wrong-key"):
        status, _, body = call(base, "/v1/models", key=key)
        assert status == 401
        err = json.loads(body)["error"]
        assert err["code"] == "invalid_api_key" and err["type"] and err["message"]


def test_right_key_passes(probe):
    base, _ = probe
    status, _, _ = call(base, "/v1/models")
    assert status == 200


def test_server_refuses_to_start_without_key(tmp_path):
    with pytest.raises(ValueError):
        make_server("127.0.0.1", 0, api_key="", log_path=tmp_path / "l.jsonl")


# --- models / health / 404 -------------------------------------------------------------------

def test_models_lists_probe_model_with_and_without_v1(probe):
    base, log = probe
    for path, prefix in (("/v1/models", "/v1"), ("/models", "")):
        status, _, body = call(base, path)
        assert status == 200
        data = json.loads(body)
        assert data["object"] == "list"
        assert [m["id"] for m in data["data"]] == ["karigar-probe"]
        assert data["data"][0]["object"] == "model"
    prefixes = [e["prefix"] for e in entries(log) if e.get("event") == "request"]
    assert prefixes == ["/v1", ""]


def test_health_needs_no_key(probe):
    base, _ = probe
    status, _, body = call(base, "/", key=None)
    assert status == 200 and json.loads(body)["ok"] is True


def test_unknown_path_is_404_json_and_logged(probe):
    base, log = probe
    status, _, body = call(base, "/v1/embeddings", body={"input": "x"})
    assert status == 404
    assert json.loads(body)["error"]["code"] == "not_found"
    assert any(e.get("path") == "/v1/embeddings" for e in entries(log))


# --- chat completions -----------------------------------------------------------------------

def test_non_stream_completion_is_valid_and_echoes_what_it_saw(probe):
    base, _ = probe
    body = chat("hi", user="u-42", metadata={"conversation_id": "c-9"}, tools=[{"type": "function",
                "function": {"name": "f", "parameters": {}}}])
    status, headers, raw = call(base, "/v1/chat/completions", body=body,
                                headers={"X-Conversation-Id": "conv-7"})
    assert status == 200 and headers["Content-Type"].startswith("application/json")
    data = json.loads(raw)
    assert data["object"] == "chat.completion" and data["id"].startswith("chatcmpl-")
    assert isinstance(data["created"], int) and data["model"] == "karigar-probe"
    choice = data["choices"][0]
    assert choice["index"] == 0 and choice["finish_reason"] == "stop"
    assert choice["message"]["role"] == "assistant"
    text = choice["message"]["content"]
    assert "messages: 2 (system, user)" in text
    assert "stream requested: no" in text
    assert "u-42" in text and "c-9" in text and "conv-7" in text
    assert "tools: 1" in text
    assert set(data["usage"]) == {"prompt_tokens", "completion_tokens", "total_tokens"}


def test_chat_without_v1_prefix_works(probe):
    base, log = probe
    status, _, raw = call(base, "/chat/completions", body=chat())
    assert status == 200 and json.loads(raw)["object"] == "chat.completion"
    req = [e for e in entries(log) if e.get("event") == "request"][-1]
    assert req["prefix"] == "" and req["path"] == "/chat/completions"


def test_bad_json_is_400(probe):
    base, _ = probe
    req = urllib.request.Request(base + "/v1/chat/completions", data=b"{not json",
                                 headers={"Authorization": f"Bearer {KEY}"}, method="POST")
    with pytest.raises(urllib.error.HTTPError) as e:
        urllib.request.urlopen(req, timeout=5)
    assert e.value.code == 400


def _sse_events(raw):
    assert raw.endswith("data: [DONE]\n\n")
    events = [blk for blk in raw.split("\n\n") if blk]
    assert all(blk.startswith("data: ") for blk in events)
    return [json.loads(blk[6:]) for blk in events[:-1]]


def test_stream_is_sse_chunks_ending_in_done(probe):
    base, _ = probe
    status, headers, raw = call(base, "/v1/chat/completions", body=chat(stream=True))
    assert status == 200 and headers["Content-Type"].startswith("text/event-stream")
    chunks = _sse_events(raw)
    assert all(c["object"] == "chat.completion.chunk" for c in chunks)
    assert len({c["id"] for c in chunks}) == 1
    assert chunks[0]["choices"][0]["delta"]["role"] == "assistant"
    assert chunks[-1]["choices"][0]["finish_reason"] == "stop"
    text = "".join(c["choices"][0]["delta"].get("content", "") for c in chunks)
    assert text.count("progress ") == 2          # PROBE_STREAM_LINES=2 from the fixture
    assert "stream requested: yes" in text


def test_stream_include_usage_sends_usage_chunk(probe):
    base, _ = probe
    _, _, raw = call(base, "/v1/chat/completions",
                     body=chat(stream=True, stream_options={"include_usage": True}))
    chunks = _sse_events(raw)
    assert chunks[-1]["choices"] == [] and chunks[-1]["usage"]["total_tokens"] > 0


# --- delay / stream control -----------------------------------------------------------------

def test_parse_directives_from_last_user_message():
    msgs = [{"role": "user", "content": "probe delay 99"},
            {"role": "assistant", "content": "ok"},
            {"role": "user", "content": [{"type": "text", "text": "Probe Delay 1.5 and probe stream 7"}]}]
    assert parse_directives(msgs) == {"delay_s": 1.5, "stream_lines": 7}
    assert parse_directives([{"role": "user", "content": "hello"}]) == {}
    assert parse_directives([{"role": "user", "content": "probe delay 99999"}])["delay_s"] <= 900


def test_delay_directive_delays_non_stream_reply(probe):
    base, _ = probe
    t0 = time.monotonic()
    status, _, raw = call(base, "/v1/chat/completions", body=chat("probe delay 0.4"))
    assert status == 200 and time.monotonic() - t0 >= 0.4
    assert "delay: 0.4 s" in json.loads(raw)["choices"][0]["message"]["content"]


def test_stream_directive_sets_progress_line_count_and_spreads_delay(probe):
    base, log = probe
    t0 = time.monotonic()
    _, _, raw = call(base, "/v1/chat/completions", body=chat("probe stream 4 probe delay 0.4", stream=True))
    assert time.monotonic() - t0 >= 0.4
    text = "".join(c["choices"][0]["delta"].get("content", "") for c in _sse_events(raw))
    assert text.count("progress ") == 4
    done = [e for e in entries(log) if e.get("event") == "done"]
    assert done and done[-1]["elapsed_s"] >= 0.4


def test_env_default_delay(tmp_path):
    srv = make_server("127.0.0.1", 0, api_key=KEY, log_path=tmp_path / "l.jsonl", delay_s=0.3)
    threading.Thread(target=srv.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True).start()
    try:
        t0 = time.monotonic()
        status, _, _ = call(f"http://127.0.0.1:{srv.server_address[1]}", "/v1/chat/completions", body=chat())
        assert status == 200 and time.monotonic() - t0 >= 0.3
    finally:
        srv.shutdown()
        srv.server_close()


# --- logging and redaction ------------------------------------------------------------------

def test_log_has_request_fields_and_never_the_key(probe):
    base, log = probe
    call(base, "/v1/chat/completions?x=1", body=chat("hi", api_key=KEY),
         headers={"Cookie": "session=s3cr3t", "X-Api-Token": "tok-abc", "X-Room": "r1"})
    raw = log.read_text(encoding="utf-8")
    assert KEY not in raw and "s3cr3t" not in raw and "tok-abc" not in raw
    req = [e for e in entries(log) if e.get("event") == "request"][-1]
    for field in ("ts", "method", "path", "query", "headers", "body", "client_ip", "prefix", "auth_ok"):
        assert field in req
    assert req["method"] == "POST" and req["query"] == "x=1" and req["auth_ok"] is True
    h = {k.lower(): v for k, v in req["headers"].items()}
    assert h["authorization"] == "[redacted]" and h["cookie"] == "[redacted]"
    assert h["x-api-token"] == "[redacted]" and h["x-room"] == "r1"
    assert req["body"]["messages"][1]["content"] == "hi"


def test_failed_auth_is_logged_without_the_bad_key(probe):
    base, log = probe
    call(base, "/v1/models", key="guess-123")
    req = entries(log)[-1]
    assert req["auth_ok"] is False and "guess-123" not in log.read_text(encoding="utf-8")


def test_image_data_uri_logs_only_type_and_length(probe):
    base, log = probe
    blob = "A" * 50_000
    uri = f"data:image/png;base64,{blob}"
    body = {"model": "m", "messages": [{"role": "user", "content": [
        {"type": "text", "text": "see photo"},
        {"type": "image_url", "image_url": {"url": uri}}]}]}
    status, _, raw = call(base, "/v1/chat/completions", body=body)
    assert status == 200
    assert "image parts: 1" in json.loads(raw)["choices"][0]["message"]["content"]
    text = log.read_text(encoding="utf-8")
    assert blob[:200] not in text
    part = entries(log)[0]["body"]["messages"][0]["content"][1]["image_url"]["url"]
    assert part == {"data_uri": "image/png", "length": len(uri)}


def test_huge_text_fields_are_truncated(probe):
    base, log = probe
    call(base, "/v1/chat/completions", body=chat("x" * 20_000))
    logged = entries(log)[0]["body"]["messages"][1]["content"]
    assert len(logged) < 5_000 and "truncated" in logged


def test_probe_log_endpoint_needs_key_and_returns_recent_entries(probe):
    base, _ = probe
    for i in range(3):
        call(base, "/v1/models")
    status, _, _ = call(base, "/probe/log?n=2", key=None)
    assert status == 401
    status, _, raw = call(base, "/probe/log?n=2")
    assert status == 200
    got = json.loads(raw)["entries"]
    assert len(got) == 2 and all(isinstance(e, dict) for e in got)
    assert KEY not in raw


def test_reply_carries_markdown_and_image_check_and_png_is_served(probe):
    base, _ = probe
    _, _, raw = call(base, "/v1/chat/completions", body=chat())
    text = json.loads(raw)["choices"][0]["message"]["content"]
    assert "| col A | col B |" in text and f"![gold pixel]({base}/probe/image.png)" in text
    with urllib.request.urlopen(base + "/probe/image.png", timeout=5) as r:
        assert r.status == 200 and r.headers["Content-Type"] == "image/png"
        assert r.read()[1:4] == b"PNG"


def test_max_tokens_is_logged_not_redacted(probe):
    base, log = probe
    call(base, "/v1/chat/completions", body=chat(max_tokens=256))
    assert entries(log)[0]["body"]["max_tokens"] == 256


def test_main_refuses_to_start_without_key(monkeypatch):
    from probe import server
    monkeypatch.delenv("PROBE_API_KEY", raising=False)
    with pytest.raises(SystemExit):
        server.main()


def test_python_m_probe_starts_from_env(tmp_path):
    """The Render start command: `python -m probe` with PORT / PROBE_* env vars."""
    import os
    import socket
    import subprocess
    import sys
    from pathlib import Path
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    log = tmp_path / "env.jsonl"
    env = {**os.environ, "PROBE_API_KEY": KEY, "PORT": str(port), "PROBE_LOG": str(log),
           "PROBE_DELAY_S": "0", "PROBE_STREAM_LINES": "5"}
    proc = subprocess.Popen([sys.executable, "-m", "probe"], env=env, cwd=Path(__file__).resolve().parents[1],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        base = f"http://127.0.0.1:{port}"
        for _ in range(100):
            try:
                urllib.request.urlopen(base + "/", timeout=1).close()
                break
            except OSError:
                time.sleep(0.02)
        _, _, raw = call(base, "/v1/chat/completions", body=chat(stream=True))
        assert "".join(c["choices"][0]["delta"].get("content", "") for c in _sse_events(raw)).count("progress ") == 5
        assert log.exists() and KEY not in log.read_text(encoding="utf-8")
    finally:
        proc.terminate()
        proc.wait(timeout=5)
