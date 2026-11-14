"""One structured log line per pipeline stage (Phase 7).

`log_stage("plan", order_id=..., ms=..., ok=True)` writes one JSON line to the `karigar.stage`
logger (stderr by default), e.g. {"ts": "...", "event": "stage", "stage": "plan", ...}.
Values are short scalars only (ids, counts, flags, error class names): never request text, keys
or customer data. Stdlib only, so the service (no bpy, no pydantic) can use it too.
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone

logger = logging.getLogger("karigar.stage")
if not logger.handlers:
    _h = logging.StreamHandler(sys.stderr)
    _h.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(_h)
    logger.setLevel(logging.INFO)
    logger.propagate = False

_SCALARS = (str, int, float, bool, type(None))


def stage_line(stage: str, event: str = "stage", **fields) -> str:
    """The JSON line for one stage; non-scalar values become their type name, strings are cut."""
    out = {"ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"), "event": event,
           "stage": stage}
    for k, v in fields.items():
        if not isinstance(v, _SCALARS):
            v = type(v).__name__
        elif isinstance(v, str):
            v = v[:120]
        out[k] = v
    return json.dumps(out, ensure_ascii=True)


def log_stage(stage: str, event: str = "stage", **fields) -> None:
    logger.info(stage_line(stage, event, **fields))
