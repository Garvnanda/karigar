"""Phase 4: manufacturability measured on the built mesh (ray-cast thickness, meshdfm).

Each rule gets a deliberately bad design that must trigger it, and a good one that must not."""
import time

import pytest

from karigar.packs.jewellery.meshdfm import FAIL, PASS, WARN
from karigar.packs.jewellery.schema import DesignSpec


@pytest.fixture(scope="module")
def gm():
    from karigar.packs.jewellery import geometry, meshdfm
    return geometry, meshdfm


def _rule(rep, rule):
    return next(r for r in rep.results if r.rule == rule)


def _plate(geometry, t, name="plate"):
    """A 10 x t x 10 mm slab (thickness along Y, the worn view's depth)."""
    import bmesh
    from mathutils import Matrix
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.transform(bm, matrix=Matrix.Diagonal((10.0, t, 10.0, 1.0)), verts=bm.verts)
    gold = geometry._obj_from_bm(bm, name)
    return geometry.Built(gold, [], geometry.mesh_volume(gold), {})


PENDANT = DesignSpec(name="p", piece_type="pendant", shape="disc", size_mm=18, thickness_mm=1.2)


# ------------------------------------------------------------------ wall thickness (ray cast)
def test_ray_cast_thickness_measures_a_plate(gm):
    geometry, mdfm = gm
    geometry.clear_scene()
    smp = mdfm.thickness_samples(_plate(geometry, 1.3).gold, 400)
    faces = [t for p, t, n in smp if abs(n.y) > 0.99]     # the two big faces
    assert faces and all(t == pytest.approx(1.3, abs=1e-3) for t in faces)


@pytest.mark.parametrize("t,status", [(0.6, FAIL), (0.84, WARN), (1.2, PASS)])
def test_wall_rule_on_plates(gm, t, status):
    geometry, mdfm = gm
    geometry.clear_scene()
    r = _rule(mdfm.check_built(PENDANT, _plate(geometry, t)), "wall")
    assert r.status == status
    assert r.measured_mm == pytest.approx(t, abs=0.02)
    assert r.min_mm == 0.8 and r.location and "mm" in r.location


def test_rule_values_come_from_config(gm):
    geometry, mdfm = gm
    geometry.clear_scene()
    cfg = {**mdfm.rules(), "min_mm": {**mdfm.rules()["min_mm"], "wall": 1.5}}
    assert _rule(mdfm.check_built(PENDANT, _plate(geometry, 1.2), cfg), "wall").status == FAIL


# ------------------------------------------------------------------ deliberately bad specs
def test_thin_ring_shank_fails_with_clock_location(gm):
    geometry, mdfm = gm
    thin = DesignSpec(name="b", piece_type="ring", karat=22, profile="flat", inner_d_mm=17.3,
                      width_mm=3.0, thickness_mm=1.2)
    geometry.clear_scene()
    r = _rule(mdfm.check_built(thin, geometry.build(thin, 1.0)), "ring_shank")
    assert r.status == FAIL and r.measured_mm == pytest.approx(1.2, abs=0.05)
    assert r.location.endswith("o'clock") and "< 1.5 mm" in r.text
    ok = thin.model_copy(update={"thickness_mm": 1.9})
    geometry.clear_scene()
    assert _rule(mdfm.check_built(ok, geometry.build(ok, 1.0)), "ring_shank").status == PASS


SOLITAIRE = DesignSpec(name="s", piece_type="ring", karat=18, profile="comfort", inner_d_mm=16.5,
                       width_mm=2.4, thickness_mm=1.8, gem="diamond", gem_d_mm=5.2, prongs=4)


def test_thin_prongs_fail(gm, monkeypatch):
    geometry, mdfm = gm
    from karigar.packs.jewellery import dfm
    geometry.clear_scene()
    good = mdfm.check_built(SOLITAIRE, geometry.build(SOLITAIRE, 1.0))
    assert _rule(good, "prong").status in (PASS, WARN)
    monkeypatch.setattr(dfm, "PRONG_D", 0.5)              # a builder that made 0.5 mm claws
    geometry.clear_scene()
    r = _rule(mdfm.check_built(SOLITAIRE, geometry.build(SOLITAIRE, 1.0)), "prong")
    assert r.status == FAIL and r.measured_mm < 0.7 and "claw" in r.text


def test_thin_wall_pendant_fails(gm):
    geometry, mdfm = gm
    thin = PENDANT.model_copy(update={"thickness_mm": 0.6})
    geometry.clear_scene()
    assert _rule(mdfm.check_built(thin, geometry.build(thin, 1.0)), "wall").status == FAIL


def test_thin_chain_wire_fails_per_link(gm):
    geometry, mdfm = gm
    from karigar.packs.jewellery.families import chains
    spec = DesignSpec(name="c", piece_type="chain", family="chain_rope", length_in=18, link_w_mm=3.0)
    s_thin = 0.4 / chains._wire_1(spec)                     # 0.4 mm link wire
    geometry.clear_scene()
    r = _rule(mdfm.check_built(spec, geometry.build(spec, s_thin)), "wall")
    assert r.status == FAIL and r.min_mm == 0.5 and "chain wire" in r.text
    geometry.clear_scene()
    r = _rule(mdfm.check_built(spec, geometry.build(spec, 0.8 / chains._wire_1(spec))), "wall")
    assert r.status == PASS


@pytest.mark.parametrize("karat,gem_d,flagged", [(22, 6.0, True), (18, 6.0, False), (22, 4.0, False)])
def test_prong_setting_with_large_stone_in_22k_is_flagged(gm, karat, gem_d, flagged):
    geometry, mdfm = gm
    spec = SOLITAIRE.model_copy(update={"karat": karat, "gem_d_mm": gem_d})
    geometry.clear_scene()
    rep = mdfm.check_built(spec, geometry.build(spec, 1.0))
    soft = [r for r in rep.results if r.rule == "soft_gold_claws"]
    assert bool(soft) == flagged
    if flagged:
        assert soft[0].status == WARN and "22K" in soft[0].text and soft[0].location == "centre stone"


def test_bezel_set_large_stone_in_22k_is_not_a_claw_flag(gm):
    geometry, mdfm = gm
    spec = DesignSpec(name="f", piece_type="ring", karat=22, motif="floral", size_mm=14, petals=6,
                      inner_d_mm=16.5, width_mm=2.4, thickness_mm=1.8, gem="ruby", gem_d_mm=6.0)
    geometry.clear_scene()
    rep = mdfm.check_built(spec, geometry.build(spec, 1.0))
    assert not any(r.rule in ("soft_gold_claws", "prong") for r in rep.results)


# ------------------------------------------------------------------ every family, speed
def test_earring_pair_is_checked_on_one_earring(gm):
    geometry, mdfm = gm
    from karigar.packs.jewellery import families
    f = families.get("earring_floral_stud")
    pair = DesignSpec(name="e", piece_type="earring", family=f.name, **f.variant_fields("balanced"))
    one = pair.model_copy(update={"pair": False})
    geometry.clear_scene()
    bp = geometry.build(pair, 1.0)
    assert bp.mirror                                # the pair exists, but only `gold` is measured
    a = mdfm.check_built(pair, bp).results
    geometry.clear_scene()
    b = mdfm.check_built(one, geometry.build(one, 1.0)).results
    key = lambda rs: [(r.rule, r.status, round(r.measured_mm, 2), r.location) for r in rs]
    assert key(a) == key(b)


def test_every_family_is_checked_fast_with_located_results(gm):
    geometry, mdfm = gm
    from karigar.packs.jewellery import dfm, families
    for name in families.CATALOGUE:
        f = families.get(name)
        spec = DesignSpec(name=f.title, piece_type=f.piece_type, family=name, **f.variant_fields("balanced"))
        lo, hi = dfm.scale_bounds(spec)
        geometry.clear_scene()
        b = geometry.build(spec, min(max(1.0, lo), hi))
        t0 = time.perf_counter()
        rep = mdfm.check_built(spec, b)
        assert time.perf_counter() - t0 < 2.0, name
        assert rep.results, name
        for r in rep.results:
            assert r.status in (PASS, WARN, FAIL) and r.location and r.text, (name, r)
    geometry.clear_scene()


def test_failed_build_is_a_failed_rule_not_a_crash(gm, monkeypatch):
    geometry, mdfm = gm
    mdfm.clear_cache()

    def boom(spec, scale):
        raise RuntimeError("union lost the shank")
    monkeypatch.setattr(geometry, "build", boom)
    rep = mdfm.check_spec(PENDANT, 1.0)
    assert not rep.ok and rep.failed[0].rule == "build" and "union lost the shank" in rep.failed[0].text
    mdfm.clear_cache()


# ------------------------------------------------------------------ solve + deliver, real meshes
def _plan_for(spec, scale, karat=22):
    from karigar.core import gold as G
    from karigar.core.registry import Plan
    from karigar.packs.jewellery import geometry
    g = G.mm3_to_grams(geometry.gold_volume(spec, scale), karat)
    return Plan(True, target_value=g, detail={"casting_loss_pct": 3.0})


def test_real_thin_design_retries_once_relaxed(gm):
    """The original eight-petal lotus pendant solved at its lightest castable scale has petal
    walls under 0.8 mm (measured): solve() checks it, retries once with a less spread-out lotus
    at the same gold, and either passes (warning says it retried) or reports the failing rule
    naming the thin part. (Was the paisley statement at 1.0 until its backing plate got the
    0.8 mm wall floor, decisions.md 2026-11-14.)"""
    geometry, mdfm = gm
    from karigar.packs.jewellery import PACK, dfm
    spec = DesignSpec(name="Kamal Pendant", piece_type="pendant", shape="lotus", petals=8,
                      size_mm=21.0, thickness_mm=1.3)
    lo, _ = dfm.scale_bounds(spec)
    first = mdfm.check_spec(spec, lo)
    assert not first.ok                                    # bad as designed at this weight
    s = PACK.solve(spec, _plan_for(spec, lo))
    if s.ok:
        assert s.spec.size_mm < spec.size_mm
        assert any("retried once with a less spread-out design" in w for w in s.warnings)
        assert all(m["status"] != FAIL for m in s.mesh_checks)
    else:
        assert s.binding_constraint.startswith("mesh check: ")
        assert "Retried once with a less spread-out design" in s.explanation
        assert any(m["status"] == FAIL for m in s.mesh_checks)


def test_good_design_solves_with_mesh_results_and_job_card(gm, tmp_path):
    import json
    geometry, mdfm = gm
    from karigar.packs.jewellery import PACK
    from karigar.packs.jewellery.schema import Brief
    spec = DesignSpec(name="Band", piece_type="ring", karat=22, profile="comfort", inner_d_mm=17.3,
                      width_mm=3.5, thickness_mm=1.8)
    plan = _plan_for(spec, 1.0)
    plan.detail["tolerance"] = {"pct": 4.0, "source": "default"}
    s = PACK.solve(spec, plan)
    assert s.ok and {m["rule"] for m in s.mesh_checks} == {"ring_shank", "wall"}
    assert all(m["status"] == PASS for m in s.mesh_checks)
    brief = Brief(piece_type="ring", karat=22, target_weight_g=round(s.value * 0.97, 2))
    files = PACK.deliver(s, brief, plan, tmp_path / "v1", "draft")
    job = json.loads(files["job_card"].read_text(encoding="utf-8"))
    assert [m["rule"] for m in job["mesh_checks"]] == [m["rule"] for m in s.mesh_checks]
    assert any(c.startswith("mesh: ring shank at") for c in job["checks_passed"])
    md = files["job_card_md"].read_text(encoding="utf-8")
    assert "## Manufacturability (measured on the mesh)" in md and "- PASS ring shank at" in md


# ------------------------------------------------------------------ the catalogue at its own weight
def _variant(name, label):
    from karigar.packs.jewellery import families
    f = families.get(name)
    fl = {**f.variant_fields(label), "name": f.title, "piece_type": f.piece_type, "family": name}
    if f.piece_type == "chain":
        fl.setdefault("length_in", 18)
    return DesignSpec(**fl)


def _default_scale(spec):
    from karigar.packs.jewellery import dfm
    lo, hi = dfm.scale_bounds(spec)
    return min(max(1.0, lo), hi)


def _catalogue():
    from karigar.packs.jewellery import families
    return list(families.CATALOGUE)


@pytest.mark.parametrize("name", _catalogue())
def test_every_catalogue_variant_passes_the_mesh_check_at_the_default_weight(gm, name):
    """The family's default weight = its balanced design at scale 1.0 (or its lightest castable
    scale when 1.0 is under it). Lighter / balanced / statement solved to that weight are never
    refused by the mesh check, and pass it first time (no relaxed retry)."""
    geometry, mdfm = gm
    from karigar.packs.jewellery import PACK
    bal = _variant(name, "balanced")
    plan = _plan_for(bal, _default_scale(bal))
    plan.detail["finished_gross_g"] = plan.target_value * 0.97
    for label in ("lighter", "balanced", "statement"):
        s = PACK.solve(_variant(name, label), plan)
        assert not s.binding_constraint.startswith("mesh check"), (name, label, s.binding_constraint)
        if s.ok:
            assert all(m["status"] != FAIL for m in s.mesh_checks), (name, label, s.mesh_checks)
            assert not any("first mesh check failed" in w for w in s.warnings), (name, label, s.warnings)
    geometry.clear_scene()


@pytest.mark.parametrize("name,label", [(n, lab) for n in ("ring_three_stone", "ring_butterfly",
                                                            "pendant_paisley", "pendant_temple_lotus")
                                         for lab in ("lighter", "balanced", "statement")])
def test_thin_catalogue_parts_hold_the_minimum_at_the_lightest_castable_scale(gm, name, label):
    """Claws, wing wires and backing plates are built at >= the prong / wall minimum, so even
    the lightest castable version of each variant is not failed by the mesh check."""
    geometry, mdfm = gm
    from karigar.packs.jewellery import dfm
    spec = _variant(name, label)
    lo, _ = dfm.scale_bounds(spec)
    rep = mdfm.check_spec(spec, lo)
    assert rep.ok, (name, label, [r.text for r in rep.failed])


def test_three_stone_side_claws_are_built_at_the_prong_minimum(gm, monkeypatch):
    geometry, _ = gm
    from karigar.packs.jewellery import dfm
    from karigar.packs.jewellery.families import _gemwork
    seen = []
    real = _gemwork.claw_head
    monkeypatch.setattr(_gemwork, "claw_head", lambda d, n, wr, *a, **k: seen.append(wr) or real(d, n, wr, *a, **k))
    spec = _variant("ring_three_stone", "statement")
    geometry.clear_scene()
    geometry.build(spec, dfm.scale_bounds(spec)[0])
    assert len(seen) == 3 and min(seen) * 2 >= dfm.PRONG_D - 1e-9
    geometry.clear_scene()


def test_default_catalogue_weights_stay_in_the_user_range(gm):
    """User rule: every family's default (balanced) design is under 20 g, the temple kada ~34 g."""
    geometry, _ = gm
    from karigar.core import gold as G
    for name in _catalogue():
        spec = _variant(name, "balanced")
        g = G.mm3_to_grams(geometry.gold_volume(spec, _default_scale(spec)), spec.karat)
        if name == "bangle_temple_kada":
            assert 30.0 < g < 38.0, (name, g)
        else:
            assert g < 20.0, (name, g)
