"""KarigarService: the transport-free core of the Phase 7 service.

Adapters (all thin): the OpenAI-compatible `/v1/chat/completions` (and `/<agent>/v1/...`), the
JSON HTTP API (`/api/...`) and the CLI (`run.py ask`) call these methods only:

- `start_order(text, conversation=None, idem=None)`  → Ticket
- `continue_conversation(conversation, text, idem=None)` → Ticket (answers a question, picks a
  variant, edits, or fetches results — the worker decides which, see worker.py)
- `edit(order_id, text, idem=None)` → Ticket
- `chat(messages, agent)` → Ticket (OpenAI history → conversation key, convo.py)
- `wait(ticket, budget_s, on_progress)` → reply text (code-written, replies.py)
- `status(job_id)`, `quote(order_id)` → dicts
- worker side: `claim`, `progress`, `stage_solved`, `upload_file`, `finish`, `fail`

The service never runs the pipeline or an LLM: it only queues jobs. A worker (karigar/service/
worker.py, on the laptop in WSL) claims them, runs the Orchestrator (bpy + `claude` CLI) and
uploads results. Stdlib only, so the Render service needs no bpy, pydantic or anthropic.
"""
from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass
from pathlib import Path

from ..core.stagelog import log_stage
from . import convo, replies
from .jobs import Job, JobStore

REPLY_BUDGET_S = 50.0       # a chat request answers within this (Nonilion waited 60 s fine)
LEASE_S = 300.0             # a claimed job's lease; progress/stage uploads extend it
RENDER_TIMEOUT_S = 900.0    # solved but no renders for this long → numbers only, job done
WORKER_STALE_S = 90.0       # no claim poll for this long → the worker counts as offline
POLL_S = 0.25
MAX_FILE = 25 * 1024 * 1024
FILE_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".stl": "model/stl",
              ".glb": "model/gltf-binary", ".json": "application/json",
              ".md": "text/markdown; charset=utf-8", ".txt": "text/plain; charset=utf-8"}
_SAFE_NAME = re.compile(r"[A-Za-z0-9._-]{1,80}")


HEARTBEAT_S = 15.0          # a streamed "still working" line when nothing else was sent
STAGE_TEXT = {
    "intake": "Sakhi read your request",
    "plan": "Jauhari worked out the gold target",
    "design": "Naqqash drew the designs",
    "solve": "Karigar solved each design to the gold",
    "solved": "weights and quote ready",
    "deliver": "photos, STL and job card made",
    "done": "all done",
}


def friendly(progress: list) -> list[str]:
    """Customer-facing progress: stage names only (the raw solver lines carry intermediate
    numbers, which must never reach the chat)."""
    out = []
    for p in progress:
        t = p.get("text", "") if isinstance(p, dict) else str(p)
        if t.startswith("stage: ") and t[7:] in STAGE_TEXT:
            out.append(STAGE_TEXT[t[7:]])
    return out


@dataclass
class Ticket:
    conv_key: str | None
    job_id: str | None = None
    agent: str = "karigar"
    reply: str | None = None        # an immediate reply (no job to wait on)
    created: bool = False           # this call created the job (False on a retry)


def default_dir() -> Path:
    env = os.environ.get("KARIGAR_SERVICE_DIR")
    return Path(env) if env else Path(__file__).resolve().parents[2] / "data" / "service"


class KarigarService:
    def __init__(self, data_dir: Path | str | None = None, clock=time.time, sleep=time.sleep,
                 reply_budget_s: float = REPLY_BUDGET_S, lease_s: float = LEASE_S,
                 render_timeout_s: float = RENDER_TIMEOUT_S, worker_stale_s: float = WORKER_STALE_S):
        self.dir = Path(data_dir) if data_dir is not None else default_dir()
        self.files_dir = self.dir / "files"
        self.files_dir.mkdir(parents=True, exist_ok=True)
        self.jobs = JobStore(self.dir / "service.sqlite3", clock=clock)
        self.clock, self.sleep = clock, sleep
        self.reply_budget_s, self.lease_s = reply_budget_s, lease_s
        self.render_timeout_s, self.worker_stale_s = render_timeout_s, worker_stale_s

    # ------------------------------------------------------------------ customer side
    def chat(self, messages, agent: str | None = "karigar") -> Ticket:
        """One OpenAI-style call: the full history (Nonilion sends it every time)."""
        agent = agent if agent in replies.AGENTS else "karigar"
        users = convo.user_texts(messages)
        if not users or not users[-1].strip():
            return Ticket(None, agent=agent, reply=f"**{replies.AGENTS[agent]}**: Namaste! "
                          "Tell me what you'd like made: the piece, karat, weight or budget, and size.")
        key = convo.ref_in_history(messages) or self._first_key(messages, len(users))
        return self.continue_conversation(key, users[-1], idem=convo.idem_key(key, messages),
                                          agent=agent)

    def _first_key(self, messages, n_users: int) -> str:
        """Derived key for a history without our ref (convo.py): salted when an identical
        opening was first seen longer ago than a retry could be."""
        for salt in range(50):
            key = convo.derived_key(messages, salt)
            seen = self.jobs.conv_first_seen(key)
            if seen is None or n_users > 1 or self.clock() - seen <= convo.RETRY_WINDOW_S:
                return key
        return convo.derived_key(messages, 50)

    def start_order(self, text: str, conversation: str | None = None, idem: str | None = None,
                    agent: str = "karigar") -> Ticket:
        key = conversation or ("K-" + os.urandom(8).hex())
        return self.continue_conversation(key, text, idem=idem, agent=agent, new_order=True)

    def continue_conversation(self, conversation: str, text: str, idem: str | None = None,
                              agent: str = "karigar", new_order: bool = False) -> Ticket:
        text = str(text)[:convo.MAX_TEXT]
        self.jobs.reap(self.render_timeout_s)
        if idem is not None:
            m = self.jobs.message(idem)
            if m is not None:                           # a retried request: same job, no new build
                log_stage("request", event="service", conv=conversation, retry=True)
                return Ticket(conversation, m["job_id"], agent, m["reply"])
        self.jobs.conv_touch(conversation)
        last = self.jobs.latest_for_conv(conversation)
        if last is not None and not new_order and (last.active or last.delivered < 2):
            # Work still running, or results not shown yet: this message fetches them.
            if idem is not None:
                self.jobs.add_message(idem, conversation, last.job_id)
            log_stage("request", event="service", conv=conversation, job=last.job_id, fetch=True)
            return Ticket(conversation, last.job_id, agent)
        payload = {"text": text, "conversation": conversation}
        prev = None if new_order else self.jobs.latest_order_for_conv(conversation)
        if prev is not None and prev.result and prev.result.get("status") == "done":
            payload["order_id"] = prev.order_id
        elif last is not None and not new_order and last.result \
                and last.result.get("status") == "needs_info":
            # An answer to the counter's questions: the worker reads it with the earlier request.
            payload["pending_text"] = last.payload.get("request_text", last.payload.get("text", ""))
        payload["request_text"] = (payload.get("pending_text", "") + "\n" + text).strip() \
            if "pending_text" in payload else text
        job, created = self.jobs.enqueue("continue", payload, conversation, agent, idem)
        log_stage("enqueue", event="service", conv=conversation, job=job.job_id,
                  created=created, edit="order_id" in payload, answer="pending_text" in payload)
        return Ticket(conversation, job.job_id, agent, created=created)

    def edit(self, order_id: str, text: str, idem: str | None = None, agent: str = "karigar") -> Ticket:
        jobs = self.jobs.jobs_for_order(order_id)
        conv = jobs[-1].conv_key if jobs else None
        job, created = self.jobs.enqueue("edit", {"text": str(text)[:convo.MAX_TEXT], "order_id": order_id,
                                                  "conversation": conv}, conv, agent, idem)
        log_stage("enqueue", event="service", job=job.job_id, created=created, edit=True)
        return Ticket(conv, job.job_id, agent, created=created)

    def worker_online(self) -> bool:
        seen = self.jobs.worker_seen()
        return seen is not None and self.clock() - seen <= self.worker_stale_s

    def wait(self, ticket: Ticket, base_url: str, budget_s: float | None = None,
             on_progress=None) -> str:
        """Block (≤ budget) until the job has something to show; returns the reply text and
        records what was delivered. `on_progress(line)` gets each new progress line (SSE)."""
        if ticket.reply is not None or ticket.job_id is None:
            return (ticket.reply or "") + (replies.footer(ticket.conv_key) if ticket.conv_key else "")
        budget = self.reply_budget_s if budget_s is None else budget_s
        deadline = self.clock() + budget
        sent, last_line = 0, self.clock()
        self.jobs.reap(self.render_timeout_s)      # a silent worker's solved job ends here
        while True:
            job = self.jobs.get(ticket.job_id)
            if on_progress is not None:
                for line in friendly(job.progress[sent:]):
                    on_progress(line)
                    last_line = self.clock()
                sent = len(job.progress)
                if self.clock() - last_line >= HEARTBEAT_S:
                    on_progress("still working…")
                    last_line = self.clock()
            if job.status in ("done", "failed"):
                break
            if self.clock() >= deadline:
                break
            if job.status == "queued" and not self.worker_online() and self.clock() + 5 < deadline:
                deadline = self.clock() + min(5.0, budget)   # worker offline: answer quickly
            self.sleep(POLL_S)
        text = self._reply_for(job, ticket.agent, base_url)
        log_stage("reply", event="service", job=job.job_id, status=job.status,
                  delivered=self.jobs.get(job.job_id).delivered)
        return text + replies.footer(ticket.conv_key or job.conv_key or "")

    def _reply_for(self, job: Job, agent: str, base: str) -> str:
        if job.status == "done" and job.result is not None:
            note = ""
            if job.error == "renders_timeout":
                note = "Photos and files could not be made this time; ask again to retry them."
            self.jobs.mark_delivered(job.job_id, 2)
            return replies.render(job.result, base, agent, note=note)
        if job.status == "failed":
            self.jobs.mark_delivered(job.job_id, 2)
            if job.partial is not None:
                return replies.render(job.partial, base, agent,
                                      note="Photos and files failed this time; ask again to retry them.")
            return (f"**{replies.AGENTS.get(agent, 'Karigar')}**: Sorry, the workshop hit a problem "
                    "with this request. Please send it again.")
        if job.status == "solved" and job.partial is not None:
            self.jobs.mark_delivered(job.job_id, 1)
            return replies.render(job.partial, base, agent, files_pending=True,
                                  note="Photos, STL and job card are still rendering: "
                                       "send any message in a minute or two to get the links.")
        return replies.status_text(job, base, agent, self.worker_online())

    def status(self, job_id: str) -> dict | None:
        j = self.jobs.get(job_id)
        if j is None:
            return None
        return {"job_id": j.job_id, "conversation": j.conv_key, "status": j.status,
                "order_id": j.order_id, "progress": [p["text"] for p in j.progress],
                "result": j.result, "partial": j.partial, "error": j.error}

    def quote(self, order_id: str) -> dict | None:
        """The latest stored quotes of an order: per version, the quote the worker computed."""
        out: dict = {}
        for j in self.jobs.jobs_for_order(order_id):
            res = j.result or j.partial or {}
            for r in res.get("results") or []:
                out[str(r.get("version"))] = {"variant": r.get("variant"), "quote": r.get("quote"),
                                              "weights": r.get("weights")}
        return {"order_id": order_id, "versions": out} if out else None

    # ------------------------------------------------------------------ console (Phase 10)
    def order(self, order_id: str) -> dict | None:
        """Everything the worker reported for an order, merged across its jobs (newest wins per
        version). Numbers are the worker's, never recomputed here."""
        jobs = self.jobs.jobs_for_order(order_id)
        if not jobs:
            return None
        versions: dict = {}
        head: dict = {}
        for j in jobs:
            res = j.result or j.partial or {}
            is_edit = j.kind == "edit" or "order_id" in j.payload
            if not is_edit and not head:
                head = {k: res.get(k) for k in ("status", "lang", "brief", "explanation", "infeasible")}
                head["request"] = j.payload.get("request_text") or j.payload.get("text")
            for r in res.get("results") or []:
                versions[str(r.get("version"))] = {**r, "job_status": j.status,
                                                   "edit_text": j.payload.get("text") if is_edit else None,
                                                   "edit": res.get("edit") if is_edit else None}
        last = jobs[-1]
        return {"order_id": order_id, "created": jobs[0].created, "updated": last.updated,
                "status": last.status, **head,
                "versions": [versions[k] for k in sorted(versions, key=lambda v: int(v) if v.isdigit() else 0)]}

    def orders(self, limit: int = 200) -> list[dict]:
        out = []
        for oid in self.jobs.order_ids(limit):
            o = self.order(oid) or {}
            v = o.get("versions") or []
            brief = o.get("brief") or {}
            out.append({"order_id": oid, "created": o.get("created"), "status": o.get("status"),
                        "piece": brief.get("piece_type"), "karat": brief.get("karat"),
                        "versions": len(v),
                        "finished_g": [((x.get("weights") or {}).get("finished_g")) for x in v],
                        "total_inr": [((x.get("quote") or {}).get("total")) for x in v]})
        return out

    def shop(self, action: str, **data) -> Ticket:
        """A shop job for the worker (which holds the gold rate and calibration): `snapshot`,
        `refresh_rate` (run the MCX rate job now) or `calibrate` (record one cast weight)."""
        job, created = self.jobs.enqueue("shop", {"action": action, **data})
        log_stage("enqueue", event="service", job=job.job_id, shop=action)
        return Ticket(None, job.job_id, created=created)

    def shop_state(self) -> dict | None:
        j = self.jobs.latest_done("shop")
        return {**(j.result or {}).get("shop", {}), "reported_at": j.updated} if j else None

    def system(self) -> dict:
        seen = self.jobs.worker_seen()
        return {"worker_online": self.worker_online(), "worker_last_seen": seen, **self.jobs.counts()}

    # ------------------------------------------------------------------ worker side
    def claim(self) -> dict | None:
        self.jobs.reap(self.render_timeout_s)
        j = self.jobs.claim(self.lease_s)
        if j is None:
            return None
        log_stage("claim", event="service", job=j.job_id, attempt=j.attempts)
        return {"job_id": j.job_id, "kind": j.kind, "payload": j.payload}

    def progress(self, job_id: str, lines: list[str]) -> None:
        self.jobs.progress(job_id, [str(x) for x in lines][:20], self.lease_s)

    def stage_solved(self, job_id: str, partial: dict) -> None:
        self.jobs.solved(job_id, partial, self.lease_s)
        log_stage("solved", event="service", job=job_id)

    def upload_file(self, job_id: str, name: str, data: bytes) -> str:
        """Store one output file; returns its unguessable path `/files/<token>/<name>`."""
        if not _SAFE_NAME.fullmatch(name or "") or name.startswith("."):
            raise ValueError("bad file name")
        ext = Path(name).suffix.lower()
        if ext not in FILE_TYPES:
            raise ValueError("file type not allowed")
        if len(data) > MAX_FILE:
            raise ValueError("file too large")
        if self.jobs.get(job_id) is None:
            raise KeyError(job_id)
        sub = self.files_dir / job_id
        sub.mkdir(parents=True, exist_ok=True)
        path = sub / (os.urandom(6).hex() + "-" + name)
        path.write_bytes(data)
        token = self.jobs.add_file(job_id, name, path, FILE_TYPES[ext], len(data))
        return f"/files/{token}/{name}"

    def file(self, token: str, name: str) -> tuple[Path, str] | None:
        f = self.jobs.file(token)
        if f is None or f["name"] != name:
            return None
        return Path(f["path"]), f["ctype"]

    def finish(self, job_id: str, result: dict) -> None:
        self.jobs.finish(job_id, result)
        log_stage("done", event="service", job=job_id, status=str(result.get("status")))

    def fail(self, job_id: str, error: str) -> None:
        self.jobs.fail(job_id, error)
        log_stage("failed", event="service", job=job_id, error=str(error)[:60])
