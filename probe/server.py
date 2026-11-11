"""Nonilion probe: a tiny OpenAI-compatible endpoint that logs everything it is sent (Phase 6.5).

Import it into a Nonilion room as "Other" to learn what Nonilion actually calls: which paths, headers,
history, ids, stream flag, timeout. Standard library only, so it runs anywhere (Render, WSL, a laptop).

Config (env): PROBE_API_KEY (required), PORT (8080), PROBE_LOG (probe/requests.jsonl),
PROBE_DELAY_S (0), PROBE_STREAM_LINES (3). Per request, the last user message can say
"probe delay 30" and/or "probe stream 10".

Base paths: no prefix, `/v1`, or `/<agent>/v1` (agent slug [a-z0-9_-]{1,32}), so several Nonilion
agents can import the same probe under different URLs and be told apart in the log.

Safety (docs/security/6.5.md): auth is checked before any body is read or parsed; unauthenticated
requests are logged as a summary (body length only). Authenticated bodies are capped in bytes, JSON
nodes and depth. Log entries are capped, rotated across several files, and read back from the end.
Sockets time out; delayed/streaming replies and connections are capped.
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
from urllib.parse import parse_qs, quote, unquote_plus, urlsplit

MODEL_ID = "karigar-probe"
DEFAULT_LOG = Path(__file__).resolve().parent / "requests.jsonl"
MAX_BODY = 8 * 1024 * 1024         # authenticated bodies (images arrive as base64 data URIs); bigger -> 413
MAX_JSON_NODES = 100_000           # containers + commas in a body; chat requests use a few hundred
MAX_JSON_DEPTH = 64                # nesting; OpenAI chat bodies use < 10
UNAUTH_DRAIN = 64 * 1024           # an unauthenticated body up to this is read and discarded; bigger -> close
MAX_LOG_BYTES = 10 * 1024 * 1024   # rotate the log past this ...
LOG_KEEP = 5                       # ... keeping this many old files (.1 newest), so <= 60 MB on disk
MAX_LOG_ENTRY = 64 * 1024          # one JSONL line; bigger entries are replaced by a truncated summary
READ_TIMEOUT_S = 30.0              # socket timeout while reading a request (and writing a reply)
MAX_SLOW = 8                       # concurrent delayed or streaming replies; more -> 429
MAX_CONNS = 64                     # concurrent connections; more -> 503 and close
MAX_DELAY_S = 900.0
MAX_STREAM_LINES = 200
MAX_STR = 2000                     # logged strings longer than this are truncated
REDACTED = "[redacted]"
SECRET_WORDS = ("auth", "key", "token", "cookie", "secret", "password", "passwd", "pwd", "credential", "bearer")
NOT_SECRET = {"max_tokens", "max_completion_tokens", "max_output_tokens"}

# A number of at most 6 digits (+3 decimals) that is not the start of a longer number.
_DIRECTIVE = re.compile(r"\bprobe\s+(delay|stream)\s+(\d{1,6}(?:\.\d{1,3})?)(?!\d)(?!\.\d)", re.IGNORECASE)
_ID_NAME = re.compile(r"(^|[_\-.])ids?($|[_\-.])|user|conversation|room|session|thread|chat|org|agent")
_AGENT_PATH = re.compile(r"^/([^/]+)/v1(?=/|$)")
_AGENT_SLUG = re.compile(r"[a-z0-9_-]{1,32}")
_SCHEME_VALUE = re.compile(r"(?i)\b(bearer|basic|token)\s+\S+")
_JSON_STRING = re.compile(rb'"[^"\\]*(?:\\.[^"\\]*)*"')
_JSON_BRACKET = re.compile(rb"[\[\]{}]")


def _is_secret(name: str) -> bool:
    n = str(name).lower()
    return n not in NOT_SECRET and any(w in n for w in SECRET_WORDS)


def _is_id(name: str) -> bool:
    return bool(_ID_NAME.search(name.lower()) or name.endswith("Id"))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _png_1px() -> bytes:
    """A 1x1 gold pixel, served at /probe/image.png to test Markdown image rendering."""
    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    idat = zlib.compress(b"\x00\xd4\xaf\x37")
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", idat) + chunk(b"IEND", b"")


PNG = _png_1px()


def _list(v) -> list:
    return v if isinstance(v, list) else []


def text_of(content) -> str:
    """Message content is a string or a list of parts ({type: text, text: ...}); anything else is ''."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(p["text"] for p in content
                        if isinstance(p, dict) and p.get("type") == "text" and isinstance(p.get("text"), str))
    return ""


def parse_directives(messages) -> dict:
    """'probe delay N' / 'probe stream N' in the last user message override the env defaults."""
    last = next((m for m in reversed(_list(messages)) if isinstance(m, dict) and m.get("role") == "user"), None)
    out: dict = {}
    if last is None:
        return out
    for word, num in _DIRECTIVE.findall(text_of(last.get("content"))):
        if word.lower() == "delay":
            out["delay_s"] = min(float(num), MAX_DELAY_S)
        else:
            out["stream_lines"] = min(int(float(num)), MAX_STREAM_LINES)
    return out


def _redact_text(s, secret: str) -> str:
    """The API key (raw or URL-encoded) replaced anywhere in a string."""
    s = str(s)
    if secret:
        for form in {secret, quote(secret, safe="")}:
            if form in s:
                s = s.replace(form, REDACTED)
    return s


def _cut(s: str) -> str:
    return s if len(s) <= MAX_STR else s[:MAX_STR] + f"...[truncated, {len(s)} chars]"


def _scrub_query(query: str, secret: str) -> str:
    """Query string for the log: values of secret-named params redacted, the key replaced everywhere."""
    out = []
    for part in query.split("&"):
        if not part:
            continue
        name, sep, value = part.partition("=")
        name = unquote_plus(name)
        value = REDACTED if _is_secret(name) else unquote_plus(value)
        out.append(_redact_text(name, secret) + sep + _redact_text(value, secret))
    return _cut("&".join(out))


def _scrub_header(name: str, value: str, secret: str) -> str:
    if _is_secret(name):
        return REDACTED
    return _cut(_SCHEME_VALUE.sub(lambda m: f"{m.group(1)} {REDACTED}", _redact_text(value, secret)))


def scrub(value, secret: str, key: str = "", depth: int = 0):
    """Copy of a parsed body that is safe to log: secrets out (by key name, in keys and in values),
    data: URIs as type+length, long strings cut, nesting past MAX_JSON_DEPTH replaced."""
    if key and _is_secret(key):
        return REDACTED
    if isinstance(value, (dict, list)) and depth >= MAX_JSON_DEPTH:
        return "[too deep]"
    if isinstance(value, dict):
        return {_redact_text(k, secret): scrub(v, secret, str(k), depth + 1) for k, v in value.items()}
    if isinstance(value, list):
        return [scrub(v, secret, "", depth + 1) for v in value]
    if isinstance(value, str):
        value = _redact_text(value, secret)
        if value.startswith("data:"):
            return {"data_uri": value[5:].split(";", 1)[0].split(",", 1)[0][:100], "length": len(value)}
        return _cut(value)
    return value


class BadBody(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code, self.message = code, message


def _parse_json(raw: bytes):
    """json.loads, but only after a cheap scan (C-speed regex/count) caps node count and depth, so a
    small hostile body cannot blow up memory or recursion."""
    bare = _JSON_STRING.sub(b'""', raw)
    opens = bare.count(b"[") + bare.count(b"{")
    if opens + bare.count(b",") > MAX_JSON_NODES or bare.count(b"]") + bare.count(b"}") > MAX_JSON_NODES:
        raise BadBody("json_too_complex", f"JSON has more than {MAX_JSON_NODES} nodes")
    depth = 0
    for ch in _JSON_BRACKET.findall(bare):
        depth += 1 if ch in (b"[", b"{") else -1
        if depth > MAX_JSON_DEPTH:
            raise BadBody("json_too_complex", f"JSON nested deeper than {MAX_JSON_DEPTH}")
    try:
        return json.loads(raw)
    except (ValueError, RecursionError):  # JSONDecodeError, UnicodeDecodeError, int-too-long are ValueErrors
        raise BadBody("invalid_json", "Body is not valid JSON") from None


class RequestLog:
    """Thread-safe JSONL log: ASCII-only lines, each capped, rotated across `keep` old files."""

    def __init__(self, path: Path, max_bytes: int = MAX_LOG_BYTES, keep: int = LOG_KEEP):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.max_bytes, self.keep = max_bytes, keep
        self.lock = threading.Lock()

    def _old(self, k: int) -> Path:
        return self.path.with_name(f"{self.path.name}.{k}")

    def _rotate(self) -> None:
        self._old(self.keep).unlink(missing_ok=True)
        for k in range(self.keep - 1, 0, -1):
            if self._old(k).exists():
                self._old(k).replace(self._old(k + 1))
        self.path.replace(self._old(1))

    def write(self, entry: dict) -> None:
        # ensure_ascii: lone surrogates can't break the write, and U+2028/U+2029/\x85 stay escaped
        line = json.dumps(entry, ensure_ascii=True, default=str)
        if len(line) > MAX_LOG_ENTRY:
            line = json.dumps({"event": entry.get("event"), "ts": entry.get("ts"), "truncated": True,
                               "original_bytes": len(line), "head": line[:MAX_LOG_ENTRY // 2 - 512]},
                              ensure_ascii=True, default=str)
        data = (line + "\n").encode("ascii")
        with self.lock:
            if self.path.exists() and self.path.stat().st_size + len(data) > self.max_bytes:
                self._rotate()
            with self.path.open("ab") as f:
                f.write(data)

    @staticmethod
    def _last_lines(path: Path, n: int) -> list:
        """The last n non-empty lines of a file, read backwards in blocks (never the whole file)."""
        try:
            f = path.open("rb")
        except FileNotFoundError:
            return []
        with f:
            end = f.seek(0, os.SEEK_END)
            buf, pos = b"", end
            while pos > 0 and buf.count(b"\n") <= n:
                step = min(65536, pos)
                pos -= step
                f.seek(pos)
                buf = f.read(step) + buf
        lines = [ln for ln in buf.split(b"\n") if ln.strip()]
        if pos > 0:
            lines = lines[1:]  # first piece may be a partial line
        return lines[-n:]

    def tail(self, n: int) -> list:
        lines: list = []
        with self.lock:
            for path in [self.path] + [self._old(k) for k in range(1, self.keep + 1)]:
                if len(lines) >= n:
                    break
                lines = self._last_lines(path, n - len(lines)) + lines
        out = []
        for line in lines[-n:]:
            try:
                out.append(json.loads(line))
            except ValueError:
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


def _image_desc(part: dict) -> str:
    iu = part.get("image_url")
    url = iu.get("url") if isinstance(iu, dict) else iu
    if not isinstance(url, str):
        return f"url of type {type(url).__name__}"
    return f"data URI {url[5:].split(';')[0][:60]}, {len(url)} chars" if url.startswith("data:") else f"url {url[:80]}"


def describe(body: dict, headers: dict, path: str, prefix: str, delay_s: float, lines: int, base_url: str,
             agent: str | None = None) -> str:
    """The reply text: what the probe saw, readable inside the Nonilion chat. Tolerates any field types."""
    msgs = [m for m in _list(body.get("messages")) if isinstance(m, dict)]
    roles = [str(m.get("role", "?"))[:32] for m in msgs]
    images = [_image_desc(p) for m in msgs for p in _list(m.get("content"))
              if isinstance(p, dict) and p.get("type") == "image_url"]
    system = [text_of(m.get("content")) for m in msgs if m.get("role") == "system"]
    tools = _list(body.get("tools"))
    tool_names = [str(t["function"].get("name")) if isinstance(t.get("function"), dict) else "?"
                  for t in tools if isinstance(t, dict)]
    ids = _found_ids(body, headers)
    other = sorted(str(k) for k in body if k not in ("messages", "model", "stream", "tools"))
    hdrs = sorted(k for k in headers)
    lines_out = [
        "**Karigar probe** received:",
        f"- path: `{path}` (prefix `{prefix or 'none'}`)",
        f"- agent: `{agent or 'none'}`",
        f"- model: `{str(body.get('model'))[:100]}`",
        f"- stream requested: {'yes' if body.get('stream') else 'no'}",
        f"- messages: {len(roles)} ({', '.join(roles)})",
        f"- system prompt: {f'yes, {sum(len(s) for s in system)} chars' if system else 'no'}",
        f"- image parts: {len(images)}" + (f" ({'; '.join(images)})" if images else ""),
        f"- tools: {len(tools)}" + (f" ({', '.join(tool_names)})" if tools else ""),
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


def split_path(path: str) -> tuple[str, str | None, str, bool]:
    """(prefix, agent, route, ok): '', '/v1' or '/<agent>/v1'; ok is False for a bad agent slug."""
    if path == "/v1" or path.startswith("/v1/"):
        return "/v1", None, path[3:] or "/", True
    m = _AGENT_PATH.match(path)
    if m:
        name = m.group(1)
        if not _AGENT_SLUG.fullmatch(name):
            return "", None, path, False
        prefix = f"/{name}/v1"
        return prefix, name, path[len(prefix):] or "/", True
    return "", None, path, True


class ProbeServer(ThreadingHTTPServer):
    """ThreadingHTTPServer with a connection cap and one-line error logging (no tracebacks)."""
    daemon_threads = True
    block_on_close = False

    def __init__(self, addr, handler, log: RequestLog, max_conns: int):
        super().__init__(addr, handler)
        self.log = log
        self._conns = threading.BoundedSemaphore(max_conns)

    def process_request(self, request, client_address):
        if not self._conns.acquire(blocking=False):
            self._refuse(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self._conns.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._conns.release()

    def _refuse(self, request) -> None:
        body = json.dumps({"error": {"message": "Too many connections", "type": "server_error",
                                     "param": None, "code": "too_many_connections"}}).encode()
        try:
            request.settimeout(0.05)
            request.sendall(b"HTTP/1.1 503 Service Unavailable\r\nContent-Type: application/json\r\n"
                            b"Connection: close\r\nContent-Length: " + str(len(body)).encode() + b"\r\n\r\n" + body)
            request.recv(65536)  # take what the client already sent, so close() sends FIN, not RST
        except OSError:
            pass
        self.log.write({"event": "refused", "ts": _now(), "reason": "too_many_connections"})
        self.shutdown_request(request)

    def handle_error(self, request, client_address):
        e = sys.exc_info()[1]
        try:
            self.log.write({"event": "error", "ts": _now(), "error": f"{type(e).__name__}: {e}"[:500]})
        except Exception:
            pass


def make_server(host: str, port: int, api_key: str, log_path=DEFAULT_LOG,
                delay_s: float = 0.0, stream_lines: int = 3, read_timeout: float = READ_TIMEOUT_S,
                max_slow: int = MAX_SLOW, max_conns: int = MAX_CONNS) -> ThreadingHTTPServer:
    if not api_key:
        raise ValueError("PROBE_API_KEY is required")
    log = RequestLog(log_path)
    slow = threading.BoundedSemaphore(max_slow)

    class Handler(BaseHTTPRequestHandler):
        server_version = "KarigarProbe/1"
        timeout = read_timeout  # applied to the socket in setup(): idle / half-sent requests are dropped

        def log_message(self, fmt, *args):  # our own JSONL log replaces stderr access logs
            pass

        # --- helpers --------------------------------------------------------------------
        def _client_ip(self) -> str:
            # Render's proxy appends the real client as the LAST hop; earlier hops are client-supplied.
            fwd = self.headers.get("X-Forwarded-For", "")
            return fwd.split(",")[-1].strip()[:64] if fwd else self.client_address[0]

        def _base_url(self) -> str:
            proto = self.headers.get("X-Forwarded-Proto", "http")
            return f"{proto}://{self.headers.get('Host', 'localhost')}"

        def _start(self, status: int, ctype: str, length: int | None = None) -> None:
            self._responded = True
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            if length is not None:
                self.send_header("Content-Length", str(length))
            if self.close_connection:
                self.send_header("Connection", "close")

        def _json(self, status: int, obj) -> None:
            data = json.dumps(obj).encode()
            self._start(status, "application/json", len(data))
            self.end_headers()
            self.wfile.write(data)

        def _error(self, status: int, code: str, message: str, etype: str = "invalid_request_error") -> None:
            self._json(status, {"error": {"message": message, "type": etype, "param": None, "code": code}})

        def _authed(self) -> bool:
            got = self.headers.get("Authorization", "")
            if not got.lower().startswith("bearer "):
                return False
            return hmac.compare_digest(got[7:].strip().encode(), api_key.encode())

        def _read_body(self, length: int) -> bytes:
            """Read exactly `length` bytes (or until EOF) within one overall deadline."""
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

        # --- dispatch -------------------------------------------------------------------
        def do_GET(self):
            self._handle("GET")

        def do_POST(self):
            self._handle("POST")

        def _handle(self, method: str) -> None:
            self._responded = False
            try:
                self._route(method, time.monotonic())
            except Exception as e:  # never a traceback on stderr, never a silent hang-up
                self._fail(e)

        def _fail(self, e: Exception) -> None:
            gone = isinstance(e, (BrokenPipeError, ConnectionResetError, ConnectionAbortedError))
            timed_out = isinstance(e, TimeoutError)
            event = "disconnected" if gone else "timeout" if timed_out else "error"
            self.close_connection = True
            log.write({"event": event, "ts": _now(), "path": _cut(_redact_text(self.path, api_key)),
                       "error": _redact_text(f"{type(e).__name__}: {e}", api_key)[:500]})
            if self._responded or gone:
                return
            try:
                if timed_out:
                    self._error(408, "request_timeout", "Request not received in time")
                else:
                    self._error(500, "internal_error", "The probe hit an unexpected error; it is logged.",
                                "server_error")
            except OSError:
                pass

        def _route(self, method: str, t0: float) -> None:
            parts = urlsplit(self.path)
            path = parts.path.rstrip("/") or "/"
            prefix, agent, route, path_ok = split_path(path)
            authed = self._authed()
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                length = -1
            entry = {
                "event": "request", "ts": _now(), "method": method,
                "path": _cut(_redact_text(path, api_key)), "prefix": _redact_text(prefix, api_key),
                "agent": _redact_text(agent, api_key) if agent else None,
                "query": _scrub_query(parts.query, api_key),
                "client_ip": self._client_ip(),
                "forwarded_for": _cut(self.headers.get("X-Forwarded-For", "")) or None,
                "headers": {_redact_text(k, api_key): _scrub_header(k, v, api_key) for k, v in self.headers.items()},
                "auth_ok": authed, "body_bytes": length if length >= 0 else None, "body": None,
            }

            body, bad = None, None
            if not authed:
                # Never parse or keep what an unauthenticated client sends: log its size only.
                if 0 < length <= UNAUTH_DRAIN:
                    self._read_body(length)
                elif length:
                    self.close_connection = True
            elif length < 0:
                bad, self.close_connection = (400, "bad_length", "Invalid Content-Length"), True
            elif length > MAX_BODY:
                bad, self.close_connection = (413, "body_too_large", f"Body over {MAX_BODY} bytes"), True
            elif length:
                raw = self._read_body(length)
                try:
                    body = _parse_json(raw)
                    entry["body"] = scrub(body, api_key)
                except BadBody as b:
                    bad = (400, b.code, b.message)
                    entry["body"] = f"[unparsed, {len(raw)} bytes]"
            log.write(entry)

            if method == "GET" and route == "/" and not prefix:
                return self._json(200, {"ok": True, "service": "karigar-probe"})
            if method == "GET" and path == "/probe/image.png":
                self._start(200, "image/png", len(PNG))
                self.end_headers()
                self.wfile.write(PNG)
                return
            if not authed:
                return self._error(401, "invalid_api_key", "Incorrect API key provided.")
            if bad:
                return self._error(*bad)
            if not path_ok:
                return self._error(404, "not_found", "Agent name in the path must match [a-z0-9_-]{1,32}")
            if method == "GET" and path == "/probe/log":
                q = parse_qs(parts.query)
                try:
                    n = max(1, min(500, int(q.get("n", ["50"])[0][:6])))
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
                return self._chat(body, path, prefix, agent, t0)
            return self._error(404, "not_found", f"No route for {method} {_cut(path)}")

        def _chat(self, body: dict, path: str, prefix: str, agent, t0: float) -> None:
            ctl = {"delay_s": delay_s, "stream_lines": stream_lines, **parse_directives(body["messages"])}
            d, n = ctl["delay_s"], ctl["stream_lines"]
            stream = bool(body.get("stream"))
            text = describe(body, dict(self.headers.items()), path, prefix, d, n, self._base_url(), agent)
            is_slow = stream or d > 0
            if is_slow and not slow.acquire(blocking=False):
                log.write({"event": "throttled", "ts": _now(), "reason": "too_many_slow_requests"})
                return self._error(429, "too_many_slow_requests",
                                   f"At most {max_slow} delayed or streaming replies at once", "rate_limit_error")
            try:
                cid = "chatcmpl-" + uuid.uuid4().hex[:24]
                created = int(time.time())
                model = body["model"] if isinstance(body.get("model"), str) else MODEL_ID
                msgs = [m for m in body["messages"] if isinstance(m, dict)]
                prompt_tokens = sum(len(text_of(m.get("content")).split()) for m in msgs)
                usage = {"prompt_tokens": prompt_tokens, "completion_tokens": len(text.split()),
                         "total_tokens": prompt_tokens + len(text.split())}
                opts = body.get("stream_options")
                include_usage = isinstance(opts, dict) and bool(opts.get("include_usage"))
                try:
                    if stream:
                        self._stream(cid, created, model, text, d, n, usage, include_usage, t0)
                    else:
                        if d:
                            time.sleep(d)
                        self._json(200, {
                            "id": cid, "object": "chat.completion", "created": created, "model": model,
                            "choices": [{"index": 0, "message": {"role": "assistant", "content": text},
                                         "finish_reason": "stop", "logprobs": None}],
                            "usage": usage,
                        })
                except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, TimeoutError) as e:
                    self.close_connection = True
                    log.write({"event": "disconnected", "ts": _now(), "id": cid,
                               "elapsed_s": round(time.monotonic() - t0, 3), "error": type(e).__name__})
                    return
                log.write({"event": "done", "ts": _now(), "id": cid,
                           "stream": stream, "elapsed_s": round(time.monotonic() - t0, 3)})
            finally:
                if is_slow:
                    slow.release()

        def _stream(self, cid, created, model, text, d, n, usage, include_usage, t0) -> None:
            self._start(200, "text/event-stream")
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

    return ProbeServer((host, port), Handler, log, max_conns)


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
