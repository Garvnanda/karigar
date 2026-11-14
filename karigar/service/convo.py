"""Conversation keys and idempotency keys from an OpenAI-style message history (Phase 7).

Nonilion sends the full history every call and no conversation / room / user ID (Phase 6.5
probe, docs/nonilion.md). So:

1. **Ref marker.** Every Karigar reply ends with `ref K-<16 hex>` (`ref_line`). Once a
   conversation has one assistant reply, its history carries that ref and the ref *is* the
   conversation key: unique per conversation even when two rooms open with the same words.
2. **First message** (no ref in the history yet): `derived_key` = sha256 of the system prompt +
   the first user message. Nonilion's system prompt includes its own room text and our agent's
   instructions, so two rooms usually differ already. When they do not, the service salts the key
   if that conversation was first seen more than `RETRY_WINDOW_S` ago (a retry comes within
   seconds; a different room with identical first words much later gets a fresh key). Limit: two
   rooms sending the identical first message with an identical system prompt inside the retry
   window share one order (documented in decisions.md).
3. **Idempotency key** = conversation key + number of user messages + hash of the last user
   message: a retried request (same history) maps to the same job and never builds twice.

Stdlib only (the Render service has no bpy/pydantic).
"""
from __future__ import annotations

import hashlib
import re

REF_RE = re.compile(r"ref (K-[0-9a-f]{16})(?![0-9a-f])")
RETRY_WINDOW_S = 120.0
MAX_TEXT = 4000            # one user message, as stored/forwarded to the worker


def text_of(content) -> str:
    """Message content is a string or a list of parts ({type: text, text: ...}); else ''."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(p["text"] for p in content
                        if isinstance(p, dict) and p.get("type") == "text" and isinstance(p.get("text"), str))
    return ""


def _msgs(messages) -> list[dict]:
    return [m for m in (messages if isinstance(messages, list) else []) if isinstance(m, dict)]


def user_texts(messages) -> list[str]:
    return [text_of(m.get("content"))[:MAX_TEXT] for m in _msgs(messages) if m.get("role") == "user"]


def system_text(messages) -> str:
    return "\n".join(text_of(m.get("content")) for m in _msgs(messages) if m.get("role") == "system")


def ref_in_history(messages) -> str | None:
    """The most recent Karigar ref found in an assistant message, or None."""
    for m in reversed(_msgs(messages)):
        if m.get("role") == "assistant":
            found = REF_RE.findall(text_of(m.get("content")))
            if found:
                return found[-1]
    return None


def _h(*parts: str) -> str:
    d = hashlib.sha256()
    for p in parts:
        d.update(p.encode("utf-8", "replace"))
        d.update(b"\x00")
    return d.hexdigest()


def derived_key(messages, salt: int = 0) -> str:
    """K-<16 hex> from the system prompt + first user message (+ salt for a later reuse)."""
    users = user_texts(messages)
    return "K-" + _h(system_text(messages), users[0] if users else "", str(salt))[:16]


def idem_key(conv_key: str, messages) -> str:
    users = user_texts(messages)
    return f"{conv_key}:{len(users)}:{_h(users[-1] if users else '')[:16]}"


def ref_line(conv_key: str) -> str:
    return f"_ref {conv_key}_"
