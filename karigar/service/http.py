"""Karigar's HTTP service (Phase 7): OpenAI-compatible endpoint, JSON API, worker API, files.

Stdlib `ThreadingHTTPServer` with the Phase 6.5 probe's hardening reused (probe/server.py:
bounded `HeadReader` deadline + byte budget for the request head, connection cap that evicts the
oldest half-sent head, JSON node/depth pre-scan, auth checked before any body is read).

Routes (`<p>` = `/v1`, `/sakhi/v1` or `/karigar/v1`; Sakhi = counter, Karigar = workshop, both
backed by the same KarigarService):
- `GET /`                                 health, no key
- `GET <p>/models`, `GET <p>/models/<id>` API key
- `POST <p>/chat/completions`             API key; stream (SSE) or not; unknown fields
                                          (`tools`, `tool_choice`, `metadata`, …) ignored
- `POST /api/orders`, `POST /api/conversations/<key>/messages`, `POST /api/orders/<id>/edits`,
  `GET /api/jobs/<id>`, `GET /api/orders/<id>/quote`, `GET /api/orders`, `GET /api/orders/<id>`,
  `GET /api/system`   API key or owner token (Phase 10 console)
- `GET /worker/jobs`, `POST /worker/jobs/<id>/{progress,solved,files,result,fail}`  worker token
- `GET /files/<token>/<name>`             no key: the 192-bit token is the capability
- `GET /console/<path>`                   static files from KARIGAR_CONSOLE_DIR (Phase 10), default console/

Env: KARIGAR_API_KEY (required; the key Nonilion's "Other" import uses), KARIGAR_WORKER_TOKEN
(required), KARIGAR_OWNER_TOKEN (optional), KARIGAR_SERVICE_DIR (jobs DB + files),
KARIGAR_PUBLIC_URL (else Render's RENDER_EXTERNAL_URL, else the request's Host), PORT.
"""
from __future__ import annotations

import hmac
import json
import os
import re
import sys
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

from probe.server import (BadBody, Evicted, HeadReader, HeadTooLarge, ProbeServer, _parse_json,
                          split_path)

from ..core.stagelog import log_stage
from .core import MAX_FILE, KarigarService
from .replies import AGENTS
from .shop import FormError, RateLimit, Shop

MODEL_ID = "karigar"
MAX_BODY = 8 * 1024 * 1024          # chat bodies carry ~100 Nonilion tools; bigger → 413
READ_TIMEOUT_S = 30.0
HEADER_TIMEOUT_S = 10.0
MAX_HEAD_BYTES = 32 * 1024
MAX_CONNS = 64
MAX_WAITING = 16                    # chat/API calls waiting on a job at once; more → 429
UNAUTH_DRAIN = 64 * 1024
MAX_WAIT_S = 50.0
_ID = re.compile(r"[A-Za-z0-9_-]{1,64}")
_CODE = re.compile(r"[A-Za-z0-9_-]{24}")
_ROLES = {"system", "user", "assistant", "tool", "developer", "function"}


class _EventLog:
    """ProbeServer's event sink → one structured log line each (no request content)."""

    def write(self, entry: dict) -> None:
        log_stage(str(entry.get("event", "http")), event="http",
                  reason=entry.get("reason"), error=str(entry.get("error", ""))[:120] or None)


def validate_chat(body) -> str | None:
    """None if `body` is a usable chat request, else the reason. Unknown fields are ignored."""
    if not isinstance(body, dict):
        return "Expected a JSON object"
    msgs = body.get("messages")
    if not isinstance(msgs, list) or not msgs:
        return "'messages' must be a non-empty list"
    for m in msgs:
        if not isinstance(m, dict) or not isinstance(m.get("role"), str) or m["role"] not in _ROLES:
            return "each message needs a 'role' (system, user, assistant, tool)"
        c = m.get("content")
        if c is not None and not isinstance(c, (str, list)):
            return "message 'content' must be a string or a list of parts"
    if "model" in body and not isinstance(body["model"], str):
        return "'model' must be a string"
    if "stream" in body and not isinstance(body["stream"], bool):
        return "'stream' must be true or false"
    return None


def make_server(host: str, port: int, service: KarigarService, api_key: str, worker_token: str,
                owner_token: str = "", public_url: str = "", console_dir: Path | None = None,
                read_timeout: float = READ_TIMEOUT_S, header_timeout: float = HEADER_TIMEOUT_S,
                max_conns: int = MAX_CONNS, max_waiting: int = MAX_WAITING,
                studio_dir: Path | None = None, shop_limit: int = 20):
    if not api_key or not worker_token:
        raise ValueError("KARIGAR_API_KEY and KARIGAR_WORKER_TOKEN are required")
    if hmac.compare_digest(api_key, worker_token):
        raise ValueError("KARIGAR_WORKER_TOKEN must differ from KARIGAR_API_KEY")
    waiting = threading.BoundedSemaphore(max_waiting)
    console = Path(console_dir).resolve() if console_dir else None
    studio = Path(studio_dir).resolve() if studio_dir else None
    shop = Shop(service)
    limiter = RateLimit(shop_limit)

    class Handler(BaseHTTPRequestHandler):
        server_version = "Karigar/1"
        protocol_version = "HTTP/1.1"
        timeout = read_timeout

        def log_message(self, fmt, *args):
            pass

        # --- request head: one deadline + a byte budget (probe hardening) -------------
        def handle_one_request(self):
            self._real_rfile = self.rfile
            reader = HeadReader(self.rfile, self.connection, time.monotonic() + header_timeout,
                                MAX_HEAD_BYTES, read_timeout)
            self.rfile = reader
            self.server.reading_started(self.connection, reader)
            try:
                super().handle_one_request()
            except HeadTooLarge:
                self.close_connection = True
                try:
                    self.connection.sendall(b"HTTP/1.1 431 Request Header Fields Too Large\r\n"
                                            b"Connection: close\r\nContent-Length: 0\r\n\r\n")
                except OSError:
                    pass
            except Evicted:
                self.close_connection = True
            finally:
                self._end_head()

        def parse_request(self):
            try:
                return super().parse_request()
            finally:
                self._end_head()

        def _end_head(self):
            if isinstance(self.rfile, HeadReader):
                self.rfile = self._real_rfile
                self.server.reading_done(self.connection)
                try:
                    self.connection.settimeout(read_timeout)
                except OSError:
                    pass

        # --- helpers -----------------------------------------------------------------
        def _base_url(self) -> str:
            if public_url:
                return public_url.rstrip("/")
            proto = self.headers.get("X-Forwarded-Proto", "http")
            return f"{proto}://{self.headers.get('Host', 'localhost')}"

        def _start(self, status: int, ctype: str, length: int | None = None, extra=None):
            self._responded = True
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            if length is not None:
                self.send_header("Content-Length", str(length))
            self.send_header("X-Content-Type-Options", "nosniff")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            if self.close_connection:
                self.send_header("Connection", "close")

        def _json(self, status: int, obj) -> None:
            data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
            self._start(status, "application/json; charset=utf-8", len(data))
            self.end_headers()
            self.wfile.write(data)

        def _error(self, status, code, message, etype="invalid_request_error"):
            self._json(status, {"error": {"message": message, "type": etype, "param": None, "code": code}})

        def _bearer(self) -> str:
            got = self.headers.get("Authorization", "")
            return got[7:].strip() if got.lower().startswith("bearer ") else ""

        def _is(self, secret: str) -> bool:
            got = self._bearer()
            return bool(secret) and bool(got) and hmac.compare_digest(got.encode(), secret.encode())

        def _read_body(self, length: int) -> bytes:
            deadline = time.monotonic() + read_timeout
            chunks, left = [], length
            while left > 0:
                if time.monotonic() > deadline:
                    raise TimeoutError("request body not received in time")
                chunk = self.rfile.read1(min(left, 65536))
                if not chunk:
                    break
                chunks.append(chunk)
                left -= len(chunk)
            return b"".join(chunks)

        # --- dispatch ----------------------------------------------------------------
        def do_GET(self):
            self._handle("GET")

        def do_POST(self):
            self._handle("POST")

        def _handle(self, method: str) -> None:
            self._responded = False
            try:
                self._route(method)
            except Exception as e:
                gone = isinstance(e, (BrokenPipeError, ConnectionResetError, ConnectionAbortedError))
                self.close_connection = True
                log_stage("http_error", event="http", error=type(e).__name__)
                if self._responded or gone:
                    return
                try:
                    if isinstance(e, TimeoutError):
                        self._error(408, "request_timeout", "Request not received in time")
                    else:
                        self._error(500, "internal_error", "Unexpected error; it is logged.", "server_error")
                except OSError:
                    pass

        def _route(self, method: str) -> None:
            parts = urlsplit(self.path)
            path = parts.path.rstrip("/") or "/"
            # Which credential does this path need? Decided before any body byte is read.
            if (path == "/" or path.startswith("/files/") or path.startswith("/console")
                    or path.startswith("/studio") or path.startswith("/shop/")):
                need = None
            elif path.startswith("/worker/"):
                need = "worker"
            elif path.startswith("/api/"):
                need = "api"
            else:
                need = "chat"
            ok = (need is None or (need == "worker" and self._is(worker_token))
                  or (need == "api" and (self._is(api_key) or self._is(owner_token)))
                  or (need == "chat" and self._is(api_key)))
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                length = -1
            if not ok:
                if 0 < length <= UNAUTH_DRAIN:
                    self._read_body(length)
                elif length:
                    self.close_connection = True
                log_stage("unauthorized", event="http", route=need)
                return self._error(401, "invalid_api_key", "Incorrect API key provided.")
            cap = MAX_FILE if "/files" in path and need == "worker" else MAX_BODY
            if length < 0:
                self.close_connection = True
                return self._error(400, "bad_length", "Invalid Content-Length")
            if length > cap:
                self.close_connection = True
                return self._error(413, "body_too_large", f"Body over {cap} bytes")
            raw = self._read_body(length) if length else b""

            if method == "GET" and path == "/":
                return self._json(200, {"ok": True, "service": "karigar",
                                        "worker_online": service.worker_online()})
            if need is None and path.startswith("/files/") and method == "GET":
                return self._file(path)
            if need is None and path.startswith("/console") and method == "GET":
                return self._static(console, "/console", path)
            if need is None and path.startswith("/studio") and method == "GET":
                return self._static(studio, "/studio", path)
            if need is None and path.startswith("/shop/"):
                body = None
                if raw:
                    try:
                        body = _parse_json(raw)
                    except BadBody as b:
                        return self._error(400, b.code, b.message)
                return self._shop_public(method, path, body)
            if need == "worker":
                return self._worker(method, path, parts.query, raw)
            body = None
            if raw:
                try:
                    body = _parse_json(raw)
                except BadBody as b:
                    return self._error(400, b.code, b.message)
            if need == "api":
                return self._api(method, path, body)
            prefix, agent, route, path_ok = split_path(path)
            if not prefix or not path_ok or (agent is not None and agent not in AGENTS):
                return self._error(404, "not_found", f"No route for {method} {path[:100]}")
            agent = agent or "karigar"
            if method == "GET" and route == "/models":
                return self._json(200, {"object": "list", "data": [_model()]})
            if method == "GET" and route.startswith("/models/"):
                if route[8:] != MODEL_ID:
                    return self._error(404, "model_not_found", "No such model")
                return self._json(200, _model())
            if method == "POST" and route == "/chat/completions":
                why = validate_chat(body)
                if why:
                    return self._error(400, "invalid_request", why)
                return self._chat(body, agent)
            return self._error(404, "not_found", f"No route for {method} {path[:100]}")

        # --- OpenAI-compatible chat ----------------------------------------------------
        def _chat(self, body: dict, agent: str) -> None:
            if not waiting.acquire(blocking=False):
                return self._error(429, "too_many_requests", "Too many replies in progress",
                                   "rate_limit_error")
            try:
                t0 = time.monotonic()
                ticket = service.chat(body["messages"], agent)     # queues work, never runs it
                log_stage("request", event="http", agent=agent, job=ticket.job_id,
                          stream=bool(body.get("stream")), created=ticket.created)
                cid = "chatcmpl-" + uuid.uuid4().hex[:24]
                created, model = int(time.time()), body.get("model") or MODEL_ID
                if body.get("stream"):
                    self._stream(ticket, cid, created, model)
                else:
                    text = service.wait(ticket, self._base_url())
                    self._json(200, {"id": cid, "object": "chat.completion", "created": created,
                                     "model": model, "choices": [{
                                         "index": 0, "message": {"role": "assistant", "content": text},
                                         "finish_reason": "stop", "logprobs": None}],
                                     "usage": {"prompt_tokens": 0, "completion_tokens": 0,
                                               "total_tokens": 0}})
                log_stage("reply_sent", event="http", job=ticket.job_id,
                          ms=round((time.monotonic() - t0) * 1000))
            finally:
                waiting.release()

        def _stream(self, ticket, cid, created, model) -> None:
            self.close_connection = True                 # SSE: no Content-Length, end on close
            self._start(200, "text/event-stream", extra={"Cache-Control": "no-cache",
                                                         "X-Accel-Buffering": "no"})
            self.end_headers()

            def send(delta: dict, finish=None) -> None:
                chunk = {"id": cid, "object": "chat.completion.chunk", "created": created, "model": model,
                         "choices": [{"index": 0, "delta": delta, "finish_reason": finish}]}
                self.wfile.write(b"data: " + json.dumps(chunk, ensure_ascii=False).encode("utf-8") + b"\n\n")
                self.wfile.flush()

            send({"role": "assistant", "content": ""})
            any_line = {"v": False}

            def line(text: str) -> None:
                any_line["v"] = True
                send({"content": f"_{text}…_\n"})
            text = service.wait(ticket, self._base_url(), on_progress=line)
            send({"content": ("\n" if any_line["v"] else "") + text})
            send({}, finish="stop")
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()

        # --- JSON API ------------------------------------------------------------------
        def _api(self, method: str, path: str, body) -> None:
            seg = path.split("/")[2:]               # after /api
            b = body if isinstance(body, dict) else {}
            idem = self.headers.get("Idempotency-Key")
            idem = f"api:{idem[:128]}" if idem else None
            if method == "GET" and len(seg) == 2 and seg[0] == "jobs" and _ID.fullmatch(seg[1]):
                st = service.status(seg[1])
                return self._json(200, st) if st else self._error(404, "not_found", "No such job")
            if method == "GET" and len(seg) == 3 and seg[0] == "orders" and seg[2] == "quote" \
                    and _ID.fullmatch(seg[1]):
                q = service.quote(seg[1])
                return self._json(200, q) if q else self._error(404, "not_found", "No quote for that order")
            if method == "GET" and seg == ["orders"]:
                return self._json(200, {"orders": service.orders()})
            if method == "GET" and len(seg) == 2 and seg[0] == "orders" and _ID.fullmatch(seg[1]):
                o = service.order(seg[1])
                return self._json(200, o) if o else self._error(404, "not_found", "No such order")
            if method == "GET" and seg == ["system"]:
                return self._json(200, service.system())
            if method == "GET" and seg == ["activity"]:
                return self._json(200, {"activity": service.activity(), "base_url": self._base_url()})
            if method == "GET" and seg == ["shop"]:
                return self._json(200, {"shop": service.shop_state()})
            if method == "POST" and seg == ["shop"]:
                return self._shop(b)
            if method == "GET" and seg == ["purchases"]:
                return self._json(200, {"purchases": shop.purchases()})
            if method != "POST":
                return self._error(404, "not_found", "No such route")
            text = b.get("text")
            if not isinstance(text, str) or not text.strip():
                return self._error(400, "invalid_request", "'text' must be a non-empty string")
            conv = b.get("conversation")
            if conv is not None and (not isinstance(conv, str) or not _ID.fullmatch(conv)):
                return self._error(400, "invalid_request", "'conversation' must match [A-Za-z0-9_-]{1,64}")
            agent = b.get("agent") if b.get("agent") in AGENTS else "karigar"
            if seg == ["orders"]:
                t = service.start_order(text, conversation=conv, idem=idem, agent=agent)
            elif len(seg) == 3 and seg[0] == "conversations" and seg[2] == "messages" and _ID.fullmatch(seg[1]):
                t = service.continue_conversation(seg[1], text, idem=idem, agent=agent)
            elif len(seg) == 3 and seg[0] == "orders" and seg[2] == "edits" and _ID.fullmatch(seg[1]):
                t = service.edit(seg[1], text, idem=idem, agent=agent)
            else:
                return self._error(404, "not_found", "No such route")
            out = {"conversation": t.conv_key, "job_id": t.job_id, "created": t.created}
            w = b.get("wait_s", 0)
            if isinstance(w, (int, float)) and not isinstance(w, bool) and w > 0:
                if not waiting.acquire(blocking=False):
                    return self._error(429, "too_many_requests", "Too many waits in progress",
                                       "rate_limit_error")
                try:
                    out["reply"] = service.wait(t, self._base_url(), budget_s=min(float(w), MAX_WAIT_S))
                finally:
                    waiting.release()
            if t.job_id:
                out["status"] = service.status(t.job_id)["status"]
            return self._json(202 if t.created else 200, out)

        def _shop(self, b: dict) -> None:
            """Owner console: gold rate and workshop calibration live on the worker (Phase 10)."""
            action = b.get("action")
            data: dict = {}
            if action == "calibrate":
                ws, d, a = b.get("workshop"), b.get("designed_g"), b.get("actual_g")
                if not isinstance(ws, str) or not _ID.fullmatch(ws):
                    return self._error(400, "invalid_request", "'workshop' must match [A-Za-z0-9_-]{1,64}")
                for name, v in (("designed_g", d), ("actual_g", a)):
                    if isinstance(v, bool) or not isinstance(v, (int, float)) or not 0 < v <= 2000:
                        return self._error(400, "invalid_request", f"'{name}' must be grams in (0, 2000]")
                data = {"workshop": ws, "designed_g": float(d), "actual_g": float(a)}
            elif action == "set_rate":
                rs = b.get("rates")
                if not isinstance(rs, dict) or not rs or any(
                        k not in ("24", "22", "18", "14") or isinstance(v, bool) or not isinstance(v, (int, float))
                        or not 0 < v < 10_000_000 for k, v in rs.items()):
                    return self._error(400, "invalid_request", "'rates' must map 24/22/18/14 to rupees per gram")
                data = {"rates": {k: float(v) for k, v in rs.items()}}
            elif action not in ("snapshot", "refresh_rate"):
                return self._error(400, "invalid_request", "'action' must be snapshot, refresh_rate, set_rate or calibrate")
            t = service.shop(action, **data)
            w = b.get("wait_s", 0)
            if isinstance(w, (int, float)) and not isinstance(w, bool) and w > 0:
                deadline = time.monotonic() + min(float(w), MAX_WAIT_S)
                while time.monotonic() < deadline and service.status(t.job_id)["status"] in ("queued", "running"):
                    time.sleep(0.25)
            st = service.status(t.job_id)
            return self._json(202, {"job_id": t.job_id, "status": st["status"],
                                    "shop": (st["result"] or {}).get("shop"), "error": st["error"]})

        # --- worker API ----------------------------------------------------------------
        def _worker(self, method: str, path: str, query: str, raw: bytes) -> None:
            seg = path.split("/")[2:]               # after /worker
            if method == "GET" and seg == ["jobs"]:
                return self._json(200, {"job": service.claim()})
            if method != "POST" or len(seg) != 3 or seg[0] != "jobs" or not _ID.fullmatch(seg[1]):
                return self._error(404, "not_found", "No such route")
            job_id, action = seg[1], seg[2]
            if service.jobs.get(job_id) is None:
                return self._error(404, "not_found", "No such job")
            if action == "files":
                name = unquote(parse_qs(query).get("name", [""])[0])
                try:
                    p = service.upload_file(job_id, name, raw)
                except ValueError as e:
                    return self._error(400, "bad_file", str(e))
                return self._json(200, {"path": p})
            try:
                body = _parse_json(raw) if raw else {}
            except BadBody as b:
                return self._error(400, b.code, b.message)
            if not isinstance(body, dict):
                return self._error(400, "invalid_request", "Expected a JSON object")
            if action == "progress" and isinstance(body.get("lines"), list):
                service.progress(job_id, body["lines"])
            elif action in ("solved", "result") and isinstance(body.get("result"), dict) \
                    and isinstance(body["result"].get("status"), str):
                (service.stage_solved if action == "solved" else service.finish)(job_id, body["result"])
            elif action == "fail":
                service.fail(job_id, str(body.get("error", "failed")))
            else:
                return self._error(400, "invalid_request", "Bad worker call")
            return self._json(200, {"ok": True})

        # --- files ---------------------------------------------------------------------
        def _file(self, path: str) -> None:
            seg = path.split("/")
            if len(seg) != 4:
                return self._error(404, "not_found", "No such file")
            found = service.file(seg[2], unquote(seg[3]))
            if found is None or not found[0].is_file():
                return self._error(404, "not_found", "No such file")
            p, ctype = found
            data = p.read_bytes()
            disp = "inline" if ctype.startswith(("image/", "text/")) else "attachment"
            self._start(200, ctype, len(data), {"Cache-Control": "private, max-age=86400",
                                                "Content-Disposition": f'{disp}; filename="{seg[3][:80]}"',
                                                "Referrer-Policy": "no-referrer"})
            self.end_headers()
            self.wfile.write(data)

        def _static(self, root: Path | None, prefix: str, path: str) -> None:
            """Static files: the owner console (/console, data via /api + owner token) and the
            customer studio (/studio, data via /shop)."""
            if root is None:
                return self._error(404, "not_found", "Not configured")
            rel = unquote(path[len(prefix):]).lstrip("/") or "index.html"
            p = (root / rel).resolve()
            if root not in p.parents and p != root or not p.is_file():
                return self._error(404, "not_found", "No such file")
            data = p.read_bytes()
            ctype = {".html": "text/html; charset=utf-8", ".js": "text/javascript",
                     ".css": "text/css", ".svg": "image/svg+xml", ".png": "image/png",
                     ".json": "application/json", ".glb": "model/gltf-binary",
                     ".woff2": "font/woff2"}.get(p.suffix.lower(), "application/octet-stream")
            self._start(200, ctype, len(data), {"Cache-Control": "no-cache"})
            self.end_headers()
            self.wfile.write(data)

        def _client(self) -> str:
            fwd = self.headers.get("X-Forwarded-For", "")
            return fwd.split(",")[-1].strip() if fwd else self.client_address[0]

        def _shop_public(self, method: str, path: str, body) -> None:
            """Customer studio API (no key). Order codes are capabilities; POSTs are rate-limited."""
            seg = path.split("/")[2:]               # after /shop
            b = body if isinstance(body, dict) else {}
            catalogue = []
            if studio is not None and (studio / "catalogue.json").is_file():
                try:
                    catalogue = json.loads((studio / "catalogue.json").read_text()).get("families", [])
                except ValueError:
                    catalogue = []
            if method == "GET" and seg == ["options"]:
                from .shop import options
                return self._json(200, {**options(catalogue), "worker_online": service.worker_online()})
            if method == "POST" and not limiter.allow(self._client()):
                return self._error(429, "too_many_requests", "Too many designs from here this hour; try later.",
                                   "rate_limit_error")
            try:
                if method == "POST" and seg == ["designs"]:
                    return self._json(201, shop.start(b.get("form")))
                if len(seg) >= 2 and seg[0] == "orders" and _CODE.fullmatch(seg[1]):
                    code = seg[1]
                    if method == "GET" and len(seg) == 2:
                        v = shop.view(code)
                        return self._json(200, v) if v else self._error(404, "not_found", "No such order code")
                    if method == "POST" and seg[2:] == ["answer"]:
                        v = shop.answer(code, b.get("topic"), b.get("value"))
                        return self._json(200, v) if v else self._error(404, "not_found", "No such order code")
                    if method == "POST" and seg[2:] == ["checkout"]:
                        return self._json(200, {"purchase": shop.checkout(code, b)})
            except FormError as e:
                return self._error(400, "invalid_choice", str(e))
            except KeyError:
                return self._error(404, "not_found", "No such order code")
            return self._error(404, "not_found", "No such route")

    srv = ProbeServer((host, port), Handler, _EventLog(), max_conns)
    srv.service = service
    return srv


def _model() -> dict:
    return {"id": MODEL_ID, "object": "model", "created": 0, "owned_by": "karigar"}


def main() -> int:
    """`run.py serve` / `python -m karigar.service`: env per the module docstring."""
    from ..core.llm import load_env_file
    load_env_file()
    def e(name, default=None):   # secrets pasted with quotes or spaces still match what people type
        v = os.environ.get(name, default)
        return v.strip().strip("\"'").strip() if isinstance(v, str) else v
    key, wtok = e("KARIGAR_API_KEY", ""), e("KARIGAR_WORKER_TOKEN", "")
    if not key or not wtok:
        print("Set KARIGAR_API_KEY and KARIGAR_WORKER_TOKEN; refusing to start an open service.",
              file=sys.stderr)
        return 2
    port = int(e("PORT", "8080"))
    svc = KarigarService(e("KARIGAR_SERVICE_DIR") or None)
    srv = make_server("0.0.0.0", port, svc, key, wtok, owner_token=e("KARIGAR_OWNER_TOKEN", ""),
                      public_url=e("KARIGAR_PUBLIC_URL") or e("RENDER_EXTERNAL_URL") or "",
                      console_dir=Path(e("KARIGAR_CONSOLE_DIR") or Path(__file__).resolve().parents[2] / "console"),
                      studio_dir=Path(e("KARIGAR_STUDIO_DIR") or Path(__file__).resolve().parents[2] / "studio"))
    print(f"karigar service listening on :{port}", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()
    return 0
