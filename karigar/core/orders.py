"""Order store (Phase 6, spec §11): every order's brief, every spec version and every output path.

Stdlib `sqlite3` only. One file, default `data/orders.sqlite3` (git-ignored); `KARIGAR_ORDERS_DB`
or an explicit path overrides it (tests always use a temp file).

An order is keyed by an `order_id` Karigar generates. `conversation_key` is optional: Nonilion
sends no conversation ID (decisions.md 2026-11-13 probe findings), so Phase 7 derives one from
the chat history and stores it here; the CLI leaves it empty.

Versions are numbered per order from 1. The first order's variants are versions 1..n (the
folders `v1..vn`); every edit adds the next number with `parent` = the version it patched,
`edit_text` = the customer's words and `patch` = {field: [old, new]}. Pack-agnostic: specs,
plans, quotes and patches are stored as JSON.
"""
from __future__ import annotations

import json
import os
import secrets
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_PATH = Path(__file__).resolve().parents[2] / "data" / "orders.sqlite3"
ENV = "KARIGAR_ORDERS_DB"

SCHEMA = """
CREATE TABLE IF NOT EXISTS orders (
    order_id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    conversation_key TEXT,
    request TEXT NOT NULL,
    lang TEXT NOT NULL,
    status TEXT NOT NULL,
    brief_json TEXT NOT NULL,
    plan_json TEXT NOT NULL,
    chosen_version INTEGER
);
CREATE INDEX IF NOT EXISTS orders_conversation ON orders(conversation_key, created_at);
CREATE TABLE IF NOT EXISTS versions (
    order_id TEXT NOT NULL REFERENCES orders(order_id),
    version INTEGER NOT NULL,
    parent INTEGER,
    created_at TEXT NOT NULL,
    spec_json TEXT NOT NULL,
    scale REAL NOT NULL,
    modelled_g REAL NOT NULL,
    finished_g REAL NOT NULL,
    target_g REAL NOT NULL,
    quote_json TEXT NOT NULL,
    edit_text TEXT,
    patch_json TEXT,
    PRIMARY KEY (order_id, version)
);
CREATE TABLE IF NOT EXISTS outputs (
    order_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    kind TEXT NOT NULL,
    path TEXT NOT NULL,
    PRIMARY KEY (order_id, version, kind),
    FOREIGN KEY (order_id, version) REFERENCES versions(order_id, version)
);
CREATE TABLE IF NOT EXISTS version_seq (
    order_id TEXT PRIMARY KEY REFERENCES orders(order_id),
    last INTEGER NOT NULL
);
"""


class UnknownOrder(KeyError):
    """No such order (or version) in the store."""


def db_path() -> Path:
    """The store's file: $KARIGAR_ORDERS_DB, else data/orders.sqlite3."""
    env = os.environ.get(ENV)
    return Path(env) if env else DEFAULT_PATH


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


@dataclass
class Version:
    version: int
    parent: int | None
    created_at: str
    spec: dict
    scale: float
    modelled_g: float
    finished_g: float
    target_g: float
    quote: dict
    edit_text: str | None = None
    patch: dict | None = None
    outputs: dict[str, str] = field(default_factory=dict)


@dataclass
class Order:
    order_id: str
    created_at: str
    conversation_key: str | None
    request: str
    lang: str
    status: str
    brief: dict
    plan: dict
    chosen: int | None
    versions: list[Version] = field(default_factory=list)

    def version(self, n: int) -> Version:
        for v in self.versions:
            if v.version == n:
                return v
        raise UnknownOrder(f"{self.order_id} has no version {n}")

    @property
    def latest(self) -> Version | None:
        return self.versions[-1] if self.versions else None


class OrderStore:
    def __init__(self, path: Path | str | None = None):
        self.path = Path(path) if path is not None else db_path()

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        con = sqlite3.connect(self.path, timeout=10, isolation_level=None)   # explicit BEGINs
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys = ON")
        con.executescript(SCHEMA)
        return con

    def _tx(self):
        """A connection used as `with self._tx() as con:` (commits, then closes)."""
        store = self

        class _Tx:
            def __enter__(self):
                self.con = store._connect()
                # IMMEDIATE: the write lock is taken at BEGIN, so two writers never read the
                # same MAX(version) (Phase 6 reviewer: version numbers allocated inside the tx).
                self.con.execute("BEGIN IMMEDIATE")
                return self.con

            def __exit__(self, et, e, tb):
                try:
                    if et is None:
                        self.con.commit()
                    else:
                        self.con.rollback()
                finally:
                    self.con.close()
                return False
        return _Tx()

    @staticmethod
    def new_order_id() -> str:
        """ORD-YYYYMMDD-HHMMSS-xxxx: sortable by time, unique within a second."""
        return time.strftime("ORD-%Y%m%d-%H%M%S-") + secrets.token_hex(2)

    # ------------------------------------------------------------- writes
    def create_order(self, order_id: str, *, request: str, brief: dict, plan: dict, lang: str,
                     status: str, conversation_key: str | None = None) -> str:
        with self._tx() as con:
            con.execute(
                "INSERT INTO orders (order_id, created_at, conversation_key, request, lang, status,"
                " brief_json, plan_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (order_id, _now(), conversation_key, request, lang, status,
                 json.dumps(brief, ensure_ascii=False), json.dumps(plan, ensure_ascii=False)))
        return order_id

    @staticmethod
    def _next_version(con, order_id: str) -> int:
        """Allocate the next version number of `order_id` inside the caller's transaction:
        one past both the stored versions and every number reserved before."""
        if con.execute("SELECT 1 FROM orders WHERE order_id = ?", (order_id,)).fetchone() is None:
            raise UnknownOrder(order_id)
        top = con.execute("SELECT COALESCE(MAX(version), 0) FROM versions WHERE order_id = ?",
                          (order_id,)).fetchone()[0]
        r = con.execute("SELECT last FROM version_seq WHERE order_id = ?", (order_id,)).fetchone()
        n = max(top, r[0] if r else 0) + 1
        con.execute("INSERT INTO version_seq (order_id, last) VALUES (?, ?)"
                    " ON CONFLICT(order_id) DO UPDATE SET last = excluded.last", (order_id, n))
        return n

    def reserve_version(self, order_id: str) -> int:
        """Reserve the next version number (an edit needs it for its folder and report before
        the version is stored). Concurrent callers always get different numbers."""
        with self._tx() as con:
            return self._next_version(con, order_id)

    def add_version(self, order_id: str, *, spec: dict, scale: float, modelled_g: float,
                    finished_g: float, target_g: float, quote: dict, parent: int | None = None,
                    edit_text: str | None = None, patch: dict | None = None,
                    outputs: dict | None = None, version: int | None = None) -> int:
        """Store a version of `order_id`; returns its number. `version` = a number from
        `reserve_version`; omitted, the next number is allocated in this transaction."""
        with self._tx() as con:
            n = self._next_version(con, order_id) if version is None else int(version)
            if version is not None and con.execute(
                    "SELECT 1 FROM orders WHERE order_id = ?", (order_id,)).fetchone() is None:
                raise UnknownOrder(order_id)
            con.execute(
                "INSERT INTO versions (order_id, version, parent, created_at, spec_json, scale,"
                " modelled_g, finished_g, target_g, quote_json, edit_text, patch_json)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (order_id, n, parent, _now(), json.dumps(spec, ensure_ascii=False), float(scale),
                 float(modelled_g), float(finished_g), float(target_g),
                 json.dumps(quote, ensure_ascii=False), edit_text,
                 None if patch is None else json.dumps(patch, ensure_ascii=False)))
            self._outputs(con, order_id, n, outputs or {})
        return n

    def set_status(self, order_id: str, status: str) -> None:
        """Change an order's status (e.g. 'failed' when delivery/export failed after solving)."""
        with self._tx() as con:
            if con.execute("UPDATE orders SET status = ? WHERE order_id = ?",
                           (status, order_id)).rowcount == 0:
                raise UnknownOrder(order_id)

    @staticmethod
    def _outputs(con, order_id: str, version: int, outputs: dict) -> None:
        con.executemany(
            "INSERT OR REPLACE INTO outputs (order_id, version, kind, path) VALUES (?, ?, ?, ?)",
            [(order_id, version, str(k), str(p)) for k, p in outputs.items()])

    def add_outputs(self, order_id: str, version: int, outputs: dict) -> None:
        with self._tx() as con:
            if con.execute("SELECT 1 FROM versions WHERE order_id = ? AND version = ?",
                           (order_id, version)).fetchone() is None:
                raise UnknownOrder(f"{order_id} v{version}")
            self._outputs(con, order_id, version, outputs)

    def choose(self, order_id: str, version: int) -> None:
        """Remember the version the customer picked (the base for the next edit)."""
        with self._tx() as con:
            if con.execute("SELECT 1 FROM versions WHERE order_id = ? AND version = ?",
                           (order_id, version)).fetchone() is None:
                raise UnknownOrder(f"{order_id} v{version}")
            con.execute("UPDATE orders SET chosen_version = ? WHERE order_id = ?", (version, order_id))

    # -------------------------------------------------------------- reads
    def get(self, order_id: str) -> Order:
        with self._tx() as con:
            r = con.execute("SELECT * FROM orders WHERE order_id = ?", (order_id,)).fetchone()
            if r is None:
                raise UnknownOrder(order_id)
            o = Order(r["order_id"], r["created_at"], r["conversation_key"], r["request"], r["lang"],
                      r["status"], json.loads(r["brief_json"]), json.loads(r["plan_json"]),
                      r["chosen_version"])
            outs: dict[int, dict] = {}
            for x in con.execute("SELECT version, kind, path FROM outputs WHERE order_id = ?"
                                 " ORDER BY version, kind", (order_id,)):
                outs.setdefault(x["version"], {})[x["kind"]] = x["path"]
            for v in con.execute("SELECT * FROM versions WHERE order_id = ? ORDER BY version",
                                 (order_id,)):
                o.versions.append(Version(
                    v["version"], v["parent"], v["created_at"], json.loads(v["spec_json"]), v["scale"],
                    v["modelled_g"], v["finished_g"], v["target_g"], json.loads(v["quote_json"]),
                    v["edit_text"], None if v["patch_json"] is None else json.loads(v["patch_json"]),
                    outs.get(v["version"], {})))
        return o

    def find_by_conversation(self, key: str) -> Order | None:
        """The most recent order of a conversation (Phase 7 derives the key from chat history)."""
        with self._tx() as con:
            r = con.execute("SELECT order_id FROM orders WHERE conversation_key = ?"
                            " ORDER BY created_at DESC, rowid DESC LIMIT 1", (key,)).fetchone()
        return None if r is None else self.get(r["order_id"])

    def list(self, limit: int = 20) -> list[dict]:
        with self._tx() as con:
            rows = con.execute(
                "SELECT o.order_id, o.created_at, o.status, o.request,"
                " (SELECT COUNT(*) FROM versions v WHERE v.order_id = o.order_id) AS n"
                " FROM orders o ORDER BY o.created_at DESC, o.rowid DESC LIMIT ?", (int(limit),))
            return [dict(r) for r in rows]
