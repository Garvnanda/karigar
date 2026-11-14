"""Phase 6 end to end: order → store → edit (Orchestrator.handle_edit and run.py), draft quality.

Output, calibration and the order store all live in tmp_path; LLM off; seeded rate (conftest).
"""
import json
from pathlib import Path

import run
from karigar.core import registry
from karigar.core.calibration import CalibrationStore
from karigar.core.orchestrator import Orchestrator
from karigar.core.orders import OrderStore
import karigar.packs.jewellery  # noqa: F401

HERO_A = ("Purani 8.4g 22K chain exchange karni hai, uske badle 22K ladies ring chahiye, "
          "size 12, chhota floral design")


def test_order_then_edit_is_stored_and_reported(tmp_path, capsys):
    db = tmp_path / "orders-e2e.sqlite3"
    store = OrderStore(db)
    orch = Orchestrator(registry.get("jewellery"), out_dir=tmp_path / "out", quality="draft",
                        calibration=CalibrationStore(tmp_path / "c.json"), store=store)
    res = orch.handle(HERO_A, conversation="test-convo")
    assert res["status"] == "done"
    oid = res["order_id"]
    assert [r["version"] for r in res["results"]] == [1, 2, 3]

    o = store.get(oid)          # the brief, every spec version and every output path
    assert o.brief == res["brief"] and o.request == HERO_A and o.conversation_key == "test-convo"
    assert o.plan["ok"] is True and o.plan["target_value"] > 0
    assert [v.version for v in o.versions] == [1, 2, 3] and all(v.parent is None for v in o.versions)
    for v, r in zip(o.versions, res["results"]):
        assert v.spec["name"] == r["variant"] and v.quote["total"] == r["quote"]["total"]
        assert {"stl", "glb", "job_card", "job_card_md", "quote", "render_hero"} <= set(v.outputs)
        assert all(Path(p).is_file() for p in v.outputs.values())

    # No variant named and none chosen yet: ask which one.
    ask = orch.handle_edit(oid, "make it 0.5 mm thinner")
    assert ask["status"] == "needs_info" and ask["topics"] == ["variant"]
    # Nothing understood: ask, with examples.
    assert orch.handle_edit(oid, "hmm theek hai")["topics"] == ["edit"]

    ed = orch.handle_edit(oid, "Middle one, but make the flower slightly bigger")
    assert ed["status"] == "done", ed
    rep = ed["edit"]
    assert rep["from_version"] == 2 and rep["to_version"] == 4
    assert list(rep["spec_diff"]) == ["size_mm"] and rep["kept_gold_target"]
    assert {"from", "to", "delta"} <= set(rep["weight_g"]) and {"from", "to", "delta"} <= set(rep["price_inr"])
    assert ed["reply"] == rep["summary"]

    o = store.get(oid)
    v4 = o.version(4)
    assert v4.parent == 2 and v4.edit_text.startswith("Middle one") and o.chosen == 4
    assert v4.patch == rep["spec_diff"]
    assert {"stl", "render_hero", "job_card", "quote", "edit"} <= set(v4.outputs)
    assert all(Path(p).is_file() for p in v4.outputs.values())
    assert Path(v4.outputs["stl"]).parent.name == "v4"
    assert json.loads(Path(v4.outputs["edit"]).read_text())["spec_diff"] == rep["spec_diff"]

    # A pick on its own only changes the base of the next edit.
    pick = orch.handle_edit(oid, "pehla wala")
    assert pick["status"] == "done" and store.get(oid).chosen == 1
    # An edit the design can't take is refused with a reason, and nothing is stored.
    no = orch.handle_edit(oid, "bigger stone")
    assert no["status"] == "needs_info" and len(store.get(oid).versions) == 4

    # CLI: orders show prints every version, the edit and its outputs.
    capsys.readouterr()
    assert run.main(["orders", "show", oid, "--db", str(db)]) == 0
    shown = capsys.readouterr().out
    assert "v4" in shown and "edit of v2" in shown and "size_mm" in shown and "casting.stl" in shown
    assert run.main(["orders", "list", "--db", str(db)]) == 0
    assert oid in capsys.readouterr().out


def test_cli_edit_unknown_order_and_show_unknown(tmp_path, capsys):
    db = tmp_path / "o.sqlite3"
    assert run.main(["edit", "ORD-nope", "make it thinner", "--db", str(db),
                     "--out", str(tmp_path / "out")]) == 1
    assert "can't find order" in capsys.readouterr().out
    assert run.main(["orders", "show", "ORD-nope", "--db", str(db)]) == 1


def test_edit_on_cli_uses_the_store(tmp_path, capsys):
    """`run.py edit` patches a stored order (seeded directly: a solved comfort band)."""
    from karigar.packs.jewellery import PACK
    from karigar.packs.jewellery.schema import Brief

    db = tmp_path / "o.sqlite3"
    store = OrderStore(db)
    brief = Brief(piece_type="ring", karat=22, target_weight_g=5.0, ring_inner_d_mm=17.3)
    plan = PACK.plan(brief, 3.0)
    v = PACK.solve(PACK.propose(brief, 1)[0], plan)
    oid = store.new_order_id()
    store.create_order(oid, request="5 g band", brief=brief.model_dump(), plan={}, lang="en", status="done")
    store.add_version(oid, spec=v.spec.model_dump(), scale=v.scale, modelled_g=v.value,
                      finished_g=v.value * 0.97, target_g=v.target, quote=PACK.quote(v, brief, plan))
    code = run.main(["edit", oid, "make it 1 g lighter", "--db", str(db), "--quality", "draft",
                     "--out", str(tmp_path / "out")])
    out = capsys.readouterr().out
    assert code == 0, out
    assert '"version": 2' in out and "Weight" in out
    v2 = store.get(oid).version(2)
    assert v2.parent == 1 and v2.finished_g < store.get(oid).version(1).finished_g


def test_default_orchestrator_store_is_the_temp_db(tmp_path, tmp_orders_db):
    """No --db and no store argument: conftest's KARIGAR_ORDERS_DB, never data/orders.sqlite3."""
    orch = Orchestrator(registry.get("jewellery"), out_dir=tmp_path / "out",
                        calibration=CalibrationStore(tmp_path / "c.json"))
    assert orch.store.path == tmp_orders_db
    res = orch.handle("kuch sundar sa bana do")          # needs_info: nothing stored
    assert res["status"] == "needs_info" and not tmp_orders_db.exists()
