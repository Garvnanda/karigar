"""Chat reply text from a worker's JobResult dict (Phase 7). Code only, no LLM.

Every number in a reply is read from the result record (weights, quote totals, versions,
dimensions inside code-written summaries); the fixed wording around them has no digits. The
service has no LLM path at all (LLM calls run only in the worker), so nothing can restate a
number (tests/test_service_replies.py checks each number against the record).

Nonilion does not render Markdown images (Phase 6.5), so renders and files go out as HTTPS links.
Two characters share one service: **Sakhi** (counter: brief, questions, quote) and **Karigar**
(workshop: designs, weights, production files, edits).
"""
from __future__ import annotations

from .convo import ref_line

AGENTS = {"sakhi": "Sakhi", "karigar": "Karigar"}
FILE_LABELS = (("render_hero", "photo"), ("stl", "STL"), ("glb", "3D model"),
               ("job_card_md", "job card"), ("quote", "quote"))
SAKHI_FILES = ("render_hero", "quote")


def inr(n) -> str:
    """₹1,23,456 (Indian grouping) from a stored rupee amount."""
    try:
        v = int(round(float(n)))
    except (TypeError, ValueError):
        return "₹?"
    s, neg = str(abs(v)), v < 0
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        s = ",".join(parts + [tail])
    return ("-₹" if neg else "₹") + s


def _url(path: str, base: str) -> str:
    return path if path.startswith(("http://", "https://")) else base.rstrip("/") + path


def _weight(w: dict) -> str:
    fin, cast = w.get("finished_g"), w.get("casting_g", w.get("modelled_g"))
    out = f"{fin:.2f} g finished" if isinstance(fin, (int, float)) else "weight pending"
    tol = w.get("tolerance_g")
    if isinstance(fin, (int, float)) and isinstance(tol, (int, float)):
        out = f"{fin:.2f} g ± {tol:.2f} g finished"
    if isinstance(cast, (int, float)):
        out += f" (cast {cast:.2f} g)"
    return out


def _variant(r: dict, base: str, agent: str, files_pending: bool) -> list[str]:
    head = f"**v{r.get('version')} · {r.get('variant', 'design')}**" if r.get("version") is not None \
        else f"**{r.get('variant', 'design')}**"
    q = r.get("quote") or {}
    line = f"{head}: {_weight(r.get('weights') or {})}"
    if "total" in q:
        line += f", total {inr(q['total'])}"
    if "to_pay" in q:
        line += f", to pay {inr(q['to_pay'])}"
    out = [line]
    files = r.get("files") or {}
    keys = SAKHI_FILES if agent == "sakhi" else tuple(k for k, _ in FILE_LABELS)
    links = [f"[{label}]({_url(files[k], base)})" for k, label in FILE_LABELS if k in keys and k in files]
    if links:
        out.append("  " + " · ".join(links))
    elif files_pending:
        out.append("  photos and files: still being made")
    return out


def render(result: dict, base: str, agent: str = "karigar", files_pending: bool = False,
           note: str = "") -> str:
    """The reply for a finished (or solved, `files_pending`) job."""
    who = AGENTS.get(agent or "karigar", "Karigar")
    st = result.get("status")
    lines: list[str] = []
    if st in ("needs_info", "rate_set", "out_of_scope"):
        lines.append(result.get("reply") or result.get("question") or "")
    elif st == "infeasible":
        inf = result.get("infeasible") or {}
        best = inf.get("best_achievable") or {}
        lines.append(result.get("explanation") or "This can't be made as asked.")
        if inf.get("binding_constraint"):
            lines.append(f"Limit: {inf['binding_constraint']}.")
        if "value" in best:
            lines.append(f"Closest possible: {best['value']:g} {best.get('unit', '')}".rstrip() + ".")
        if inf.get("alternatives"):
            lines.append("Options: " + "; ".join(inf["alternatives"]) + ".")
    elif st == "done":
        edit = result.get("edit")
        if edit:
            lines.append(edit.get("summary") or result.get("reply") or "")
        elif result.get("results"):
            lines.append(f"Order {result.get('order_id')}: here are the designs.")
        elif result.get("reply"):
            lines.append(result["reply"])
        for r in result.get("results") or []:
            lines += _variant(r, base, agent, files_pending)
        if result.get("results") and not edit:
            if who == "Sakhi":
                lines.append("Tell me which one you like. Karigar can change any of them.")
            else:
                lines.append("Pick one (first, middle or last) or ask for a change, "
                             "e.g. \"middle one, a little lighter\".")
    else:
        lines.append("Something went wrong on our side; please send your request again.")
    if note:
        lines.append(note)
    return f"**{who}**: " + "\n".join(x for x in lines if x)


def status_text(job, base: str, agent: str, worker_online: bool) -> str:
    """Reply while a job is not finished: what is running, how the next message gets it."""
    who = AGENTS.get(agent or "karigar", "Karigar")
    if job.status == "queued" and not worker_online:
        body = ("The workshop computer is offline right now. Your request is saved and "
                "will start as soon as it is back; send any message later to get the result.")
    else:
        from .core import friendly
        steps = friendly(job.progress)
        last = steps[-1] if steps else "starting"
        body = (f"Still working on it (last step: {last}). "
                "Send any message in a minute or two to get the result.")
    return f"**{who}**: {body}"


def footer(conv_key: str) -> str:
    return "\n\n" + ref_line(conv_key)
