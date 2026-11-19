"""Customer studio (public, no key): a clickable form → request text → the usual job queue.

The customer never types a request. `request_text(form)` writes the order sentence in code from
validated choices, so the worker's brief parser reads exactly what was clicked; follow-up
questions come back with option lists (`QUESTION_OPTIONS`), never free text. Each design gets an
unguessable order code (the capability, like file tokens); "My orders" is the codes this device
remembers. Checkout is a **demo payment**: nothing is charged and no card data is accepted.
Stdlib only (runs on Render).
"""
from __future__ import annotations

import json
import re
import secrets
import threading
import time
from collections import deque

PIECES = {   # piece → the word the brief parser reads
    "ring": "ring", "bangle": "bangle", "pendant": "pendant", "chain": "chain",
    "earring": "earrings", "nosepin": "nose pin", "coin": "coin",
}
# Catalogue families a style word selects (brief.FAMILY_WORDS); "" = Karigar's own pick.
STYLES = {
    "ring": {"": "", "ring_three_stone": "three stone", "ring_halo_solitaire": "halo",
             "ring_butterfly": "butterfly", "floral": "floral"},
    "pendant": {"": "", "pendant_heart_halo": "halo", "pendant_paisley": "paisley",
                "pendant_temple_lotus": "temple lotus"},
    "chain": {"": "", "chain_rope": "rope", "chain_curb": "curb"},
    "bangle": {"": "", "bangle_temple_kada": "temple", "bangle_twisted_rope": "twisted rope"},
    "earring": {"": "", "earring_jhumka": "jhumka", "earring_chandbali": "chandbali",
                "earring_bali_hoop": "bali"},
    "nosepin": {"": ""},
    "coin": {"": "", "coin_lotus_10g": "lotus"},
}
KARATS = (22, 18, 14)
OLD_KARATS = (24, 22, 18, 14)
METALS = ("yellow", "rose", "white")
GEMS = ("none", "diamond", "ruby", "emerald", "sapphire")
STONE_CT = (0.1, 0.25, 0.5, 0.75, 1.0)
RING_SIZES = tuple(range(1, 31))
BANGLE_SIZES = ("2-2", "2-4", "2-6", "2-8", "2-10", "2-12")
CHAIN_IN = (16, 18, 20, 22, 24)
BUDGETS = (15000, 25000, 40000, 60000, 80000, 100000, 150000, 200000, 300000)
MAX_GRAMS = 200.0
# Viewer tint per metal (the linear base colours render.py's METAL_RGB gives the 22K alloys); a
# colour for the 3D preview only, never a number shown to the customer.
METAL_TINT = {"yellow": (1.0, 0.70, 0.29), "rose": (0.97, 0.62, 0.46), "white": (0.86, 0.85, 0.80)}

QUESTION_OPTIONS = {
    "ring_size": [f"size {n}" for n in RING_SIZES],
    "bangle_size": [f"size {s}" for s in BANGLE_SIZES],
    "chain_length": [f"{n} inch" for n in CHAIN_IN],
    "karat": [f"{k}K" for k in KARATS],
    "old_karat": [f"old gold is {k}K" for k in OLD_KARATS],
}


class FormError(ValueError):
    pass


def options(catalogue: list | None = None) -> dict:
    """Everything the form can offer, so the page never invents a choice."""
    fams = {f.get("family"): f for f in (catalogue or [])}
    styles = {p: [{"id": k, "word": w,
                   "title": (fams.get(k) or {}).get("title") or
                            ("Karigar's pick" if not k else w.title()),
                   "picture": (fams.get(k) or {}).get("picture"),
                   "weights_g": (fams.get(k) or {}).get("weights_g")} for k, w in s.items()]
              for p, s in STYLES.items()}
    return {"pieces": list(PIECES), "styles": styles, "karats": list(KARATS), "old_karats": list(OLD_KARATS),
            "metals": list(METALS), "gems": list(GEMS), "stone_ct": list(STONE_CT),
            "ring_sizes": list(RING_SIZES), "bangle_sizes": list(BANGLE_SIZES), "chain_in": list(CHAIN_IN),
            "budgets": list(BUDGETS), "max_grams": MAX_GRAMS, "metal_tint": METAL_TINT, "question_options": QUESTION_OPTIONS}


def _pick(form: dict, key: str, allowed, required=True):
    v = form.get(key)
    if v is None and not required:
        return None
    if isinstance(v, bool) or v not in allowed:
        raise FormError(f"choose a valid {key.replace('_', ' ')}")
    return v


def _grams(v, what: str) -> float:
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not 0 < v <= MAX_GRAMS:
        raise FormError(f"{what} must be between 0 and {MAX_GRAMS:g} g")
    return round(float(v), 2)


def request_text(form: dict) -> str:
    """The order sentence, built from validated choices only (no customer free text)."""
    if not isinstance(form, dict):
        raise FormError("form must be an object")
    piece = _pick(form, "piece", PIECES)
    style = form.get("style") or ""
    if style not in STYLES[piece]:
        raise FormError("choose a style for this piece")
    karat = _pick(form, "karat", KARATS)
    metal = _pick(form, "metal", METALS)
    gem = _pick(form, "gem", GEMS)
    ct = _pick(form, "stone_ct", STONE_CT, required=False) if gem != "none" else None
    words = [f"{karat}K {metal} gold", STYLES[piece][style], PIECES[piece]]
    if gem != "none":
        words.append(f"with a {ct:g} ct {gem}" if ct else f"with a {gem}")
    t = form.get("target") or {}
    kind = t.get("kind") if isinstance(t, dict) else None
    if kind == "weight":
        words.append(f"of {_grams(t.get('grams'), 'the weight'):g} g")
    elif kind == "budget":
        words.append(f"budget {_pick(t, 'inr', BUDGETS)}")
    elif kind == "exchange":
        g, ok = _grams(t.get("grams"), "the old gold"), _pick(t, "karat", OLD_KARATS)
        words = [f"old {g:g} g {ok}K gold exchange, new"] + words
    else:
        raise FormError("choose how the piece is paid for: a weight, a budget or old gold")
    if piece == "ring":
        words.append(f"size {_pick(form, 'size', RING_SIZES)}")
    elif piece == "bangle":
        words.append(f"size {_pick(form, 'size', BANGLE_SIZES)}")
    elif piece == "chain":
        words.append(f"{_pick(form, 'size', CHAIN_IN)} inch")
    return re.sub(r"\s+", " ", " ".join(w for w in words if w)).strip()


def answer_text(topic: str, value: str) -> str:
    if topic not in QUESTION_OPTIONS or value not in QUESTION_OPTIONS[topic]:
        raise FormError("choose one of the offered answers")
    return value


class RateLimit:
    """At most `n` public jobs per client per `window_s` (ponytail: in-memory, per process;
    a shared store if the service ever runs more than one instance)."""

    def __init__(self, n: int = 20, window_s: float = 3600.0, clock=time.monotonic):
        self.n, self.window, self.clock = n, window_s, clock
        self.hits: dict[str, deque] = {}
        self.lock = threading.Lock()

    def allow(self, who: str) -> bool:
        now = self.clock()
        with self.lock:
            q = self.hits.setdefault(who, deque())
            while q and now - q[0] > self.window:
                q.popleft()
            if len(q) >= self.n:
                return False
            q.append(now)
            if len(self.hits) > 10000:              # forget idle clients
                for k in [k for k, v in self.hits.items() if not v][:5000]:
                    self.hits.pop(k, None)
            return True


SCHEMA = """
CREATE TABLE IF NOT EXISTS shop_codes (
    code TEXT PRIMARY KEY, conv_key TEXT NOT NULL, form_json TEXT NOT NULL, created REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS purchases (
    code TEXT PRIMARY KEY, order_id TEXT, version INTEGER NOT NULL, variant TEXT,
    name TEXT NOT NULL, phone TEXT NOT NULL, method TEXT NOT NULL, total_inr REAL, due_inr REAL,
    status TEXT NOT NULL, created REAL NOT NULL
);
"""
_PHONE = re.compile(r"\+?[0-9][0-9 -]{8,15}")
METHODS = ("upi", "card", "pay_at_store")


class Shop:
    def __init__(self, service):
        self.s = service
        with self.s.jobs._tx() as con:
            for stmt in SCHEMA.strip().split(";"):
                if stmt.strip():
                    con.execute(stmt)

    def start(self, form: dict) -> dict:
        text = request_text(form)
        code = secrets.token_urlsafe(18)
        t = self.s.start_order(text, conversation="S-" + secrets.token_hex(8), agent="karigar", channel="studio")
        with self.s.jobs._tx() as con:
            con.execute("INSERT INTO shop_codes (code, conv_key, form_json, created) VALUES (?, ?, ?, ?)",
                        (code, t.conv_key, json.dumps(form), time.time()))
        return {"code": code, "request": text}

    def _conv(self, code: str):
        with self.s.jobs._tx() as con:
            return con.execute("SELECT * FROM shop_codes WHERE code = ?", (code,)).fetchone()

    def answer(self, code: str, topic: str, value: str) -> dict | None:
        row = self._conv(code)
        if row is None:
            return None
        text = answer_text(topic, value)
        last = self.s.jobs.latest_for_conv(row["conv_key"])
        if last is None or last.active or (last.result or {}).get("status") != "needs_info":
            raise FormError("this order is not waiting for an answer")
        self.s.jobs.mark_delivered(last.job_id, 2)     # the question was shown on the page
        self.s.continue_conversation(row["conv_key"], text, agent="karigar", channel="studio")
        return self.view(code)

    def view(self, code: str) -> dict | None:
        """What the customer sees for one order code. Numbers are the worker's, passed through."""
        row = self._conv(code)
        if row is None:
            return None
        job = self.s.jobs.latest_for_conv(row["conv_key"])
        res = (job.result or job.partial or {}) if job else {}
        out = {"code": code, "form": json.loads(row["form_json"]), "created": row["created"],
               "status": job.status if job else "queued", "worker_online": self.s.worker_online(),
               "steps": [p.get("text", "")[7:] for p in (job.progress if job else [])
                         if isinstance(p, dict) and str(p.get("text", "")).startswith("stage: ")],
               "result_status": res.get("status"), "order_id": res.get("order_id")}
        if res.get("status") == "needs_info":
            out["questions"] = [{"text": q, "topic": t, "options": QUESTION_OPTIONS.get(t, [])}
                                for q, t in zip(res.get("questions") or [], res.get("topics") or [])]
        if res.get("status") == "infeasible":
            out["infeasible"] = res.get("infeasible")
            out["explanation"] = res.get("explanation")
        if res.get("status") in ("out_of_scope",):
            out["explanation"] = res.get("reply")
        out["designs"] = [{k: r.get(k) for k in ("variant", "version", "weights", "files", "quote")}
                          for r in res.get("results") or []]
        out["purchase"] = self.purchase(code, public=True)
        return out

    def checkout(self, code: str, body: dict) -> dict:
        v = self.view(code)
        if v is None:
            raise KeyError(code)
        if v["purchase"]:
            return v["purchase"]                     # paying twice changes nothing
        design = next((d for d in v["designs"] if d.get("version") == body.get("version")), None)
        if design is None or v["status"] != "done":
            raise FormError("choose one of this order's finished designs")
        name = body.get("name")
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 80:
            raise FormError("enter your name (up to 80 characters)")
        phone = body.get("phone")
        if not isinstance(phone, str) or not _PHONE.fullmatch(phone.strip()):
            raise FormError("enter a phone number (digits, 9 to 16)")
        method = body.get("method")
        if method not in METHODS:
            raise FormError("choose a payment method")
        q = design.get("quote") or {}
        total = q.get("total")
        due = q.get("to_pay") if isinstance(q.get("to_pay"), (int, float)) else total   # after old gold
        with self.s.jobs._tx() as con:
            con.execute("INSERT OR IGNORE INTO purchases (code, order_id, version, variant, name, phone, method,"
                        " total_inr, due_inr, status, created) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (code, v["order_id"], design["version"], design.get("variant"), name.strip(),
                         phone.strip(), method, total, due,
                         "reserved" if method == "pay_at_store" else "paid (demo)", time.time()))
        return self.purchase(code, public=True)

    def purchase(self, code: str, public: bool = False) -> dict | None:
        with self.s.jobs._tx() as con:
            r = con.execute("SELECT * FROM purchases WHERE code = ?", (code,)).fetchone()
        if r is None:
            return None
        d = dict(r)
        if public:                                     # the customer sees their own name, not the phone
            d.pop("phone", None)
        return d

    def purchases(self) -> list[dict]:
        """Owner area: every placed order, newest first, with the design's numbers."""
        with self.s.jobs._tx() as con:
            rows = [dict(r) for r in con.execute("SELECT * FROM purchases ORDER BY created DESC LIMIT 500")]
        for r in rows:
            v = self.view(r["code"]) or {}
            d = next((x for x in v.get("designs", []) if x.get("version") == r["version"]), {})
            r["weights"], r["files"], r["form"] = d.get("weights"), d.get("files"), v.get("form")
        return rows
