"""Nonilion probe: a tiny OpenAI-compatible endpoint that logs everything it is sent (Phase 6.5).

Import it into a Nonilion room as "Other" to learn what Nonilion actually calls: which paths, headers,
history, ids, stream flag, timeout. Standard library only, so it runs anywhere (Render, WSL, a laptop).

Config (env): PROBE_API_KEY (required), PORT (8080), PROBE_LOG (probe/requests.jsonl),
PROBE_DELAY_S (0), PROBE_STREAM_LINES (3). Per request, the last user message can say
"probe delay 30" and/or "probe stream 10".
"""
from __future__ import annotations

import hmac
import json
import os
import re
import struct
import sys
import threading
import time
import uuid
import zlib
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

MODEL_ID = "karigar-probe"
DEFAULT_LOG = Path(__file__).resolve().parent / "requests.jsonl"
MAX_BODY = 25 * 1024 * 1024        # images arrive as base64; anything bigger is refused (413)
MAX_LOG_BYTES = 20 * 1024 * 1024   # rotate the log to .1 past this, so a free-plan disk never fills
MAX_DELAY_S = 900.0
MAX_STREAM_LINES = 200
MAX_STR = 2000                     # logged strings longer than this are truncated
REDACTED = "[redacted]"
SECRET_WORDS = ("authorization", "key", "token", "cookie", "secret", "password")

_DIRECTIVE = re.compile(r"\bprobe\s+(delay|stream)\s+(\d+(?:\.\d+)?)", re.IGNORECASE)


_ID_NAME = re.compile(r"(^|[_\-.])ids?($|[_\-.])|user|conversation|room|session|thread|chat|org|agent")


def _is_secret(name: str) -> bool:
    n = name.lower()
    return any(w in n for w in SECRET_WORDS) and not n.endswith("tokens")  # max_tokens is not a secret


def _is_id(name: str) -> bool:
    return bool(_ID_NAME.search(name.lower()) or name.endswith("Id"))


def _png_1px() -> bytes:
    """A 1x1 gold pixel, served at /probe/image.png to test Markdown image rendering."""
    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    idat = zlib.compress(b"\x00\xd4\xaf\x37")
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", idat) + chunk(b"IEND", b"")


PNG = _png_1px()


def text_of(content) -> str:
    """Message content is a string or a list of parts ({type: text, text: ...})."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(p.get("text", "") for p in content if isinstance(p, dict) and p.get("type") == "text")
    return ""


def parse_directives(messages) -> dict:
    """'probe delay N' / 'probe stream N' in the last user message override the env defaults."""
    last = next((m for m in reversed(messages or []) if isinstance(m, dict) and m.get("role") == "user"), None)
    out: dict = {}
    if last is None:
        return out
    for word, num in _DIRECTIVE.findall(text_of(last.get("content"))):
        if word.lower() == "delay":
            out["delay_s"] = min(float(num), MAX_DELAY_S)
        else:
            out["stream_lines"] = min(int(float(num)), MAX_STREAM_LINES)
    return out


def scrub(value, secret: str, key: str = ""):
    """Copy of a parsed body that is safe to log: secrets out, data: URIs as type+length, long strings cut."""
    if key and _is_secret(key) and not isinstance(value, (dict, list)):
        return REDACTED
    if isinstance(value, dict):
        return {k: scrub(v, secret, str(k)) for k, v in value.items()}
    if isinstance(value, list):
        return [scrub(v, secret, key) for v in value]
    if isinstance(value, str):
        if secret and secret in value:
            value = value.replace(secret, REDACTED)
        if value.startswith("data:"):
            return {"data_uri": value[5:].split(";", 1)[0].split(",", 1)[0], "length": len(value)}
        if len(value) > MAX_STR:
            return value[:MAX_STR] + f"...[truncated, {len(value)} chars]"
    return value


class RequestLog:
    """Thread-safe JSONL log with a size cap."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()

    def write(self, entry: dict) -> None:
        line = json.dumps(entry, ensure_ascii=False, default=str) + "\n"
        with self.lock:
            if self.path.exists() and self.path.stat().st_size > MAX_LOG_BYTES:
                self.path.replace(self.path.with_suffix(self.path.suffix + ".1"))
            with self.path.open("a", encoding="utf-8") as f:
                f.write(line)

    def tail(self, n: int) -> list:
        with self.lock:
            if not self.path.exists():
                return []
            lines = self.path.read_text(encoding="utf-8").splitlines()
        out = []
        for line in lines[-n:]:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return out


def _found_ids(body: dict, headers: dict) -> list[str]:
    """Anything that looks like a user / conversation / room id, from the body or non-secret headers."""
    found = []
    for k, v in (body or {}).items():
        if k in ("messages", "tools", "model") or _is_secret(k):
            continue
        if k == "metadata" and isinstance(v, dict):
            found += [f"metadata.{mk}={mv}" for mk, mv in v.items() if not _is_secret(mk)]
        elif _is_id(k):
            found.append(f"{k}={v}")
    for k, v in headers.items():
        lk = k.lower()
        if not _is_secret(lk) and lk.startswith("x-") and _is_id(lk):
            found.append(f"header {k}={v}")
    return found


def describe(body: dict, headers: dict, path: str, prefix: str, delay_s: float, lines: int, base_url: str) -> str:
    """The reply text: what the probe saw, readable inside the Nonilion chat."""
    msgs = body.get("messages") or []
    roles = [m.get("role", "?") for m in msgs if isinstance(m, dict)]
    images = []
    for m in msgs:
        if isinstance(m, dict) and isinstance(m.get("content"), list):
            for p in m["content"]:
                if isinstance(p, dict) and p.get("type") == "image_url":
                    url = (p.get("image_url") or {}).get("url", "") if isinstance(p.get("image_url"), dict) else ""
                    images.append(f"data URI {url[5:].split(';')[0]}, {len(url)} chars" if url.startswith("data:")
                                  else f"url {url[:80]}")
    system = [text_of(m.get("content")) for m in msgs if isinstance(m, dict) and m.get("role") == "system"]
    tools = body.get("tools") or []
    ids = _found_ids(body, headers)
    other = sorted(k for k in body if k not in ("messages", "model", "stream", "tools"))
    hdrs = sorted(k for k in headers)
    lines_out = [
        "**Karigar probe** received:",
        f"- path: `{path}` (prefix `{prefix or 'none'}`)",
        f"- model: `{body.get('model')}`",
        f"- stream requested: {'yes' if body.get('stream') else 'no'}",
        f"- messages: {len(roles)} ({', '.join(roles)})",
        f"- system prompt: {f'yes, {sum(len(s) for s in system)} chars' if system else 'no'}",
        f"- image parts: {len(images)}" + (f" ({'; '.join(images)})" if images else ""),
        f"- tools: {len(tools)}" + (f" ({', '.join(str((t.get('function') or {}).get('name')) for t in tools if isinstance(t, dict))})" if tools else ""),
        f"- ids seen: {'; '.join(ids) if ids else 'none'}",
        f"- other body keys: {', '.join(other) if other else 'none'}",
        f"- headers: {', '.join(hdrs)}",
        f"- delay: {delay_s:g} s, stream lines: {lines}",
        "",
        "Markdown test: **bold**, *italic*, `code`, [a link](https://example.com)",
        "",
        "| col A | col B |",
        "|---|---|",
        "| 1 | 2 |",
        "",
        f"Image test: ![gold pixel]({base_url}/probe/image.png)",
        "",
        "Try: `probe delay 30` or `probe stream 10` in your message.",
    ]
    return "\n".join(lines_out)


def make_server(host: str, port: int, api_key: str, log_path=DEFAULT_LOG,
                delay_s: float = 0.0, stream_lines: int = 3) -> ThreadingHTTPServer:
    if not api_key:
        raise ValueError("PROBE_API_KEY is required")
    log = RequestLog(log_path)

    class Handler(BaseHTTPRequestHandler):
        server_version = "KarigarProbe/1"

        def log_message(self, fmt, *args):  # our own JSONL log replaces stderr access logs
            pass

        # --- helpers --------------------------------------------------------------------
        def _client_ip(self) -> str:
            fwd = self.headers.get("X-Forwarded-For", "")
            return fwd.split(",")[0].strip() if fwd else self.client_address[0]

        def _base_url(self) -> str:
            proto = self.headers.get("X-Forwarded-Proto", "http")
            return f"{proto}://{self.headers.get('Host', 'localhost')}"

        def _json(self, status: int, obj) -> None:
            data = json.dumps(obj).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _error(self, status: int, code: str, message: str, etype: str = "invalid_request_error") -> None:
            self._json(status, {"error": {"message": message, "type": etype, "param": None, "code": code}})

        def _authed(self) -> bool:
            got = self.headers.get("Authorization", "")
            if not got.lower().startswith("bearer "):
                return False
            return hmac.compare_digest(got[7:].strip().encode(), api_key.encode())

        # --- dispatch -------------------------------------------------------------------
        def do_GET(self):
            self._handle("GET")

        def do_POST(self):
            self._handle("POST")

        def _handle(self, method: str) -> None:
            t0 = time.monotonic()
            parts = urlsplit(self.path)
            path = parts.path.rstrip("/") or "/"
            prefix = "/v1" if path == "/v1" or path.startswith("/v1/") else ""
            route = path[len(prefix):] or "/"

            raw, body, bad = b"", None, None
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                length = -1
            if length < 0:
                bad, length = (400, "bad_length", "Invalid Content-Length"), 0
            elif length > MAX_BODY:
                bad = (413, "body_too_large", f"Body over {MAX_BODY} bytes")
            elif length:
                raw = self.rfile.read(length)
                try:
                    body = json.loads(raw)
                except (json.JSONDecodeError, UnicodeDecodeError):
                    bad = (400, "invalid_json", "Body is not valid JSON")

            headers = {k: (REDACTED if _is_secret(k) else v) for k, v in self.headers.items()}
            authed = self._authed()
            entry = {
                "event": "request", "ts": datetime.now(timezone.utc).isoformat(), "method": method,
                "path": path, "prefix": prefix, "query": parts.query, "client_ip": self._client_ip(),
                "headers": headers, "auth_ok": authed,
                "body": scrub(body, api_key) if body is not None else (f"[unparsed, {len(raw)} bytes]" if raw else None),
            }
            log.write(entry)

            if method == "GET" and route == "/" and not prefix:
                return self._json(200, {"ok": True, "service": "karigar-probe"})
            if method == "GET" and path == "/probe/image.png":
                self.send_response(200)
                self.send_header("Content-Type", "image/png")
                self.send_header("Content-Length", str(len(PNG)))
                self.end_headers()
                self.wfile.write(PNG)
                return
            if not authed:
                return self._error(401, "invalid_api_key", "Incorrect API key provided.")
            if bad:
                return self._error(*bad)
            if method == "GET" and path == "/probe/log":
                q = parse_qs(parts.query)
                try:
                    n = max(1, min(500, int(q.get("n", ["50"])[0])))
                except ValueError:
                    n = 50
                return self._json(200, {"entries": log.tail(n)})
            if method == "GET" and route == "/models":
                return self._json(200, {"object": "list", "data": [_model()]})
            if method == "GET" and route == f"/models/{MODEL_ID}":
                return self._json(200, _model())
            if method == "POST" and route == "/chat/completions":
                if not isinstance(body, dict) or not isinstance(body.get("messages"), list):
                    return self._error(400, "invalid_request", "Expected a JSON object with a 'messages' list")
                return self._chat(body, path, prefix, t0)
            return self._error(404, "not_found", f"No route for {method} {path}")

        def _chat(self, body: dict, path: str, prefix: str, t0: float) -> None:
            ctl = {"delay_s": delay_s, "stream_lines": stream_lines, **parse_directives(body["messages"])}
            d, n = ctl["delay_s"], ctl["stream_lines"]
            text = describe(body, dict(self.headers.items()),
                            path, prefix, d, n, self._base_url())
            cid = "chatcmpl-" + uuid.uuid4().hex[:24]
            created = int(time.time())
            model = body.get("model") or MODEL_ID
            prompt_tokens = sum(len(text_of(m.get("content")).split()) for m in body["messages"] if isinstance(m, dict))
            usage = {"prompt_tokens": prompt_tokens, "completion_tokens": len(text.split()),
                     "total_tokens": prompt_tokens + len(text.split())}
            try:
                if body.get("stream"):
                    self._stream(cid, created, model, text, d, n, usage,
                                 bool((body.get("stream_options") or {}).get("include_usage")), t0)
                else:
                    if d:
                        time.sleep(d)
                    self._json(200, {
                        "id": cid, "object": "chat.completion", "created": created, "model": model,
                        "choices": [{"index": 0, "message": {"role": "assistant", "content": text},
                                     "finish_reason": "stop", "logprobs": None}],
                        "usage": usage,
                    })
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError) as e:
                log.write({"event": "disconnected", "ts": datetime.now(timezone.utc).isoformat(), "id": cid,
                           "elapsed_s": round(time.monotonic() - t0, 3), "error": type(e).__name__})
                return
            log.write({"event": "done", "ts": datetime.now(timezone.utc).isoformat(), "id": cid,
                       "stream": bool(body.get("stream")), "elapsed_s": round(time.monotonic() - t0, 3)})

        def _stream(self, cid, created, model, text, d, n, usage, include_usage, t0) -> None:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("X-Accel-Buffering", "no")
            self.end_headers()

            def send(delta: dict, finish=None) -> None:
                chunk = {"id": cid, "object": "chat.completion.chunk", "created": created, "model": model,
                         "choices": [{"index": 0, "delta": delta, "finish_reason": finish}]}
                self.wfile.write(b"data: " + json.dumps(chunk).encode() + b"\n\n")
                self.wfile.flush()

            send({"role": "assistant", "content": ""})
            step = d / n if n else 0.0
            for i in range(1, n + 1):
                if step:
                    time.sleep(step)
                send({"content": f"progress {i}/{n} (t={time.monotonic() - t0:.1f}s)\n"})
            if d and not n:
                time.sleep(d)
            send({"content": ("\n" if n else "") + text})
            send({}, finish="stop")
            if include_usage:
                tail = {"id": cid, "object": "chat.completion.chunk", "created": created, "model": model,
                        "choices": [], "usage": usage}
                self.wfile.write(b"data: " + json.dumps(tail).encode() + b"\n\n")
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()

    srv = ThreadingHTTPServer((host, port), Handler)
    srv.daemon_threads = True
    return srv


def _model() -> dict:
    return {"id": MODEL_ID, "object": "model", "created": 0, "owned_by": "karigar"}


def main() -> None:
    key = os.environ.get("PROBE_API_KEY", "")
    if not key:
        sys.exit("PROBE_API_KEY is not set; refusing to start an open endpoint.")
    port = int(os.environ.get("PORT", "8080"))
    srv = make_server("0.0.0.0", port, api_key=key,
                      log_path=Path(os.environ.get("PROBE_LOG") or DEFAULT_LOG),
                      delay_s=float(os.environ.get("PROBE_DELAY_S", "0")),
                      stream_lines=int(os.environ.get("PROBE_STREAM_LINES", "3")))
    print(f"karigar-probe listening on :{port}", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()


if __name__ == "__main__":
    main()
