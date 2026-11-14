"""Phase 6: the SQLite order store (stdlib sqlite3; tmp paths only, never data/orders.sqlite3)."""
import sqlite3

import pytest

from karigar.core import orders
from karigar.core.orders import OrderStore, UnknownOrder

BRIEF = {"piece_type": "ring", "karat": 22, "ring_inner_d_mm": 16.5, "style": ["floral"]}
PLAN = {"ok": True, "target_value": 7.6, "unit": "g", "detail": {"casting_loss_pct": 3.0}}


def _spec(name, t=2.0):
    return {"name": name, "piece_type": "ring", "thickness_mm": t, "width_mm": 3.5}


def _seed(store, conversation=None):
    oid = store.new_order_id()
    store.create_order(oid, request="ring chahiye", brief=BRIEF, plan=PLAN, lang="hinglish",
                       status="done", conversation_key=conversation)
    for i in (1, 2, 3):
        store.add_version(oid, spec=_spec(f"V{i}"), scale=1.0 + i / 100, modelled_g=7.6,
                          finished_g=7.37, target_g=7.6, quote={"total": 1000 * i},
                          outputs={"stl": f"/tmp/{oid}/v{i}/casting.stl",
                                   "render_hero": f"/tmp/{oid}/v{i}/render_hero.png"})
    return oid


def test_store_holds_brief_every_version_and_every_output(tmp_path):
    db = tmp_path / "orders.sqlite3"
    store = OrderStore(db)
    oid = _seed(store)
    v4 = store.add_version(oid, spec=_spec("V2", t=1.5), scale=1.05, modelled_g=7.6, finished_g=7.37,
                           target_g=7.6, quote={"total": 2100}, parent=2,
                           edit_text="make it 0.5 mm thinner", patch={"thickness_mm": [2.0, 1.5]},
                           outputs={"stl": f"/tmp/{oid}/v4/casting.stl"})
    assert v4 == 4

    again = OrderStore(db)          # reopened from disk: everything is still there
    o = again.get(oid)
    assert o.brief == BRIEF and o.plan == PLAN and o.request == "ring chahiye" and o.lang == "hinglish"
    assert [v.version for v in o.versions] == [1, 2, 3, 4]
    v = o.version(4)
    assert v.parent == 2 and v.edit_text == "make it 0.5 mm thinner"
    assert v.spec["thickness_mm"] == 1.5 and v.patch == {"thickness_mm": [2.0, 1.5]}
    assert v.quote == {"total": 2100} and v.scale == 1.05
    assert o.version(1).outputs == {"stl": f"/tmp/{oid}/v1/casting.stl",
                                    "render_hero": f"/tmp/{oid}/v1/render_hero.png"}
    assert v.outputs == {"stl": f"/tmp/{oid}/v4/casting.stl"}


def test_versions_number_per_order_and_chosen_version(tmp_path):
    store = OrderStore(tmp_path / "o.sqlite3")
    a, b = _seed(store), _seed(store)
    assert a != b                               # ids are unique even within one second
    assert [v.version for v in store.get(b).versions] == [1, 2, 3]
    assert store.get(a).chosen is None
    store.choose(a, 2)
    assert store.get(a).chosen == 2
    with pytest.raises(UnknownOrder):
        store.choose(a, 9)


def test_add_outputs_to_an_existing_version(tmp_path):
    store = OrderStore(tmp_path / "o.sqlite3")
    oid = _seed(store)
    store.add_outputs(oid, 1, {"job_card": "/tmp/x/job_card.json"})
    assert store.get(oid).version(1).outputs["job_card"] == "/tmp/x/job_card.json"


def test_unknown_order_raises(tmp_path):
    with pytest.raises(UnknownOrder):
        OrderStore(tmp_path / "o.sqlite3").get("ORD-nope")


def test_conversation_key_finds_the_latest_order(tmp_path):
    store = OrderStore(tmp_path / "o.sqlite3")
    _seed(store, conversation="nonilion:abc")
    second = _seed(store, conversation="nonilion:abc")
    _seed(store, conversation="nonilion:other")
    assert store.find_by_conversation("nonilion:abc").order_id == second
    assert store.find_by_conversation("missing") is None
    assert store.get(second).conversation_key == "nonilion:abc"


def test_store_is_plain_sqlite_with_parameterised_values(tmp_path):
    """Hostile text is stored as data (parameters, never SQL)."""
    db = tmp_path / "o.sqlite3"
    store = OrderStore(db)
    oid = store.new_order_id()
    evil = "x'); DROP TABLE orders; --"
    store.create_order(oid, request=evil, brief=BRIEF, plan=PLAN, lang="en", status="done")
    assert store.get(oid).request == evil
    tables = {r[0] for r in sqlite3.connect(db).execute("select name from sqlite_master")}
    assert {"orders", "versions", "outputs"} <= tables


def test_default_path_is_data_orders_sqlite3_and_env_overrides(monkeypatch, tmp_path):
    assert orders.DEFAULT_PATH.name == "orders.sqlite3" and orders.DEFAULT_PATH.parent.name == "data"
    monkeypatch.setenv("KARIGAR_ORDERS_DB", str(tmp_path / "env.sqlite3"))
    assert orders.db_path() == tmp_path / "env.sqlite3"


def test_tests_never_touch_the_real_order_db(tmp_path):
    """conftest points the default store at a temp file for every test."""
    assert orders.db_path() != orders.DEFAULT_PATH
    assert tmp_path in orders.db_path().parents or orders.db_path().parent == tmp_path
