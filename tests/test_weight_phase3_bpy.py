"""Phase 3 — weight and solver honesty, measured on built meshes (bpy): stone seats cut before
weighing for every builder and family, builds cached by spec hash, every design solved within
±0.1 g / 2% under the iteration cap, the infeasible contracts (below_min, above_max,
stone-too-big), Hero D's refusal, Hero B's joint stone + gold budget solve, the coin stamp."""
import pytest

from karigar.core import gold as G
from karigar.core.registry import Plan, Solved
from karigar.core.solver import MAX_ITER, accept_window
from karigar.packs.jewellery import PACK, designer, dfm, families, pricing
from karigar.packs.jewellery import brief as B
from karigar.packs.jewellery.schema import Brief, DesignSpec

LOSS = 3.0


@pytest.fixture(scope="module")
def geometry():
    from karigar.packs.jewellery import geometry
    yield geometry
    geometry.clear_scene()


def _fam_spec(name, label="balanced", **kw):
    fam = families.get(name)
    f = {**fam.variant_fields(label), "name": fam.title, "piece_type": fam.piece_type, "family": name}
    if fam.piece_type == "chain":
        f.setdefault("length_in", 18)
    return DesignSpec(**{**f, **kw})


LEGACY_STONES = {
    "solitaire": DesignSpec(name="s", piece_type="ring", gem="diamond", gem_d_mm=5.2, width_mm=2.0, thickness_mm=1.5),
    "floral_ruby": DesignSpec(name="f", piece_type="ring", motif="floral", gem="ruby", gem_d_mm=3.5,
                              size_mm=10.5, petals=6, width_mm=3.5, thickness_mm=2.0),
    "disc_pendant": DesignSpec(name="d", piece_type="pendant", shape="disc", gem="diamond", gem_d_mm=4.0,
                               size_mm=15, thickness_mm=1.1),
    "lotus_pendant": DesignSpec(name="l", piece_type="pendant", shape="lotus", gem="ruby", gem_d_mm=4.0,
                                size_mm=18, thickness_mm=1.2),
}
STONE_FAMILIES = ["ring_floral_cluster", "ring_three_stone", "ring_halo_solitaire", "ring_butterfly",
                  "pendant_heart_halo", "pendant_paisley", "pendant_temple_lotus", "earring_jhumka",
                  "earring_chandbali", "earring_floral_stud", "nosepin_flower", "nosepin_convertible_stud"]
BANGLE_STONE = {n: _fam_spec(n, gem="ruby", gem_d_mm=4.0) for n in ("bangle_twisted_rope",)}


def _raw(geometry, spec, s):
    """The builder's body before the seats are cut (what was weighed before Phase 3)."""
    if spec.family:
        b = families.get(spec.family).builder(spec, s)
    else:
        b = geometry.BUILDERS[spec.piece_type](spec, s)
    return b


def _cases():
    out = [(k, v) for k, v in LEGACY_STONES.items()]
    out += [(n, _fam_spec(n, pair=False) if families.get(n).piece_type == "earring" else _fam_spec(n))
            for n in STONE_FAMILIES]
    out += list(BANGLE_STONE.items())
    return out


# ----------------------------------------------------------- stone seats cut
def _overlap(geometry, raw) -> float:
    """Volume of gold inside the stones (boolean INTERSECT of the raw body and each stone)."""
    import bpy
    tot = 0.0
    for gm in raw.gems:
        cp = bpy.data.objects.new("probe", raw.gold.data.copy())
        bpy.context.scene.collection.objects.link(cp)
        mod = cp.modifiers.new("x", "BOOLEAN")
        mod.operation, mod.object, mod.solver = "INTERSECT", gm, "MANIFOLD"
        dg = bpy.context.evaluated_depsgraph_get()
        dg.update()
        me = bpy.data.meshes.new_from_object(cp.evaluated_get(dg))
        ob = bpy.data.objects.new("ov", me)
        bpy.context.scene.collection.objects.link(ob)
        tot += geometry.mesh_volume(ob) if len(me.polygons) else 0.0
        bpy.data.objects.remove(ob, do_unlink=True)
        bpy.data.objects.remove(cp, do_unlink=True)
    return tot


@pytest.mark.parametrize("key,spec", _cases(), ids=[k for k, _ in _cases()])
def test_metal_is_weighed_after_the_stone_seats_are_cut(geometry, key, spec):
    geometry.clear_scene()
    raw = _raw(geometry, spec, 1.0)
    if not raw.gems:
        pytest.fail(f"{key}: expected stones")
    v_raw = geometry.mesh_volume(raw.gold)
    overlap = _overlap(geometry, raw)
    assert overlap > 0.05, key                     # the stones really sit in metal
    geometry.clear_scene()
    b = geometry.build(spec, 1.0)
    # the weighed volume is the raw body minus the gold inside the stones
    assert b.volume_mm3 == pytest.approx(v_raw - overlap, abs=max(0.05, 0.01 * overlap)), key
    assert b.seat_cut_mm3 == pytest.approx(overlap, abs=max(0.05, 0.01 * overlap))
    if b.seats_in_model:                           # the casting body itself has the seats cut
        assert b.volume_mm3 == pytest.approx(geometry.mesh_volume(b.gold), rel=1e-9)
        assert geometry.cut_seats(b).seat_cut_mm3 < 0.05, key     # no gold left inside a stone
    # and the solver probe weighs exactly this
    geometry.clear_volume_cache()
    assert geometry.gold_volume(spec, 1.0) == pytest.approx(b.volume_mm3, abs=0.05)
    geometry.clear_scene()


@pytest.mark.parametrize("key,spec", [c for c in _cases() if c[0] != "lotus_pendant"],
                         ids=[k for k, _ in _cases() if k != "lotus_pendant"])
def test_cut_body_is_still_one_clean_solid(geometry, key, spec):
    """lotus_pendant is left out: its uncut body already crosses itself (a Phase 4 mesh item)."""
    from karigar.packs.jewellery import mesh_check
    geometry.clear_scene()
    b = geometry.build(spec, 1.0)
    assert mesh_check.check(b.gold).ok, (key, mesh_check.check(b.gold).problems())
    geometry.clear_scene()


def test_earring_pair_weighs_two_cut_earrings(geometry):
    one = _fam_spec("earring_floral_stud", pair=False)
    geometry.clear_volume_cache()
    assert geometry.gold_volume(one.model_copy(update={"pair": True}), 1.0) == pytest.approx(
        2 * geometry.gold_volume(one, 1.0), rel=1e-6)


def test_plain_pieces_are_untouched_by_the_seat_cut(geometry):
    geometry.clear_scene()
    spec = DesignSpec(name="b", piece_type="ring")
    b = geometry.build(spec, 1.0)
    assert b.seat_cut_mm3 == 0.0 and not b.gems
    geometry.clear_scene()


def _empty_seat_try(geometry):
    """A seat cut whose every boolean returns empty geometry (the MANIFOLD solver giving up)."""
    import bpy

    def empty(gold, gems, grow, nudge, turn, tri, name):
        ob = bpy.data.objects.new(name, bpy.data.meshes.new(name))
        bpy.context.scene.collection.objects.link(ob)
        return ob
    return empty


@pytest.mark.parametrize("key", ["solitaire", "ring_three_stone"])
def test_failed_boolean_still_weighs_without_the_gold_under_the_stones(geometry, monkeypatch, key):
    """Every DIFFERENCE try empty: the gold inside the stones is measured by INTERSECT and
    subtracted; the body is left uncut (seats_in_model False) and the job card says so."""
    from karigar.packs.jewellery import job_card
    spec = dict(_cases())[key]
    geometry.clear_scene()
    raw = _raw(geometry, spec, 1.0)
    v_raw, overlap = geometry.mesh_volume(raw.gold), _overlap(geometry, raw)
    assert overlap > 0.05
    geometry.clear_scene()
    monkeypatch.setattr(geometry, "_seat_try", _empty_seat_try(geometry))
    b = geometry.build(spec, 1.0)
    assert not b.seats_in_model
    assert b.volume_mm3 == pytest.approx(v_raw - overlap, abs=max(0.05, 0.01 * overlap))
    assert b.seat_cut_mm3 == pytest.approx(overlap, abs=max(0.05, 0.01 * overlap))
    brief = Brief(piece_type=spec.piece_type, karat=22, target_weight_g=5.0, gem=spec.gem, gem_ct=0.3)
    plan = Plan(True, target_value=5.0, detail={"casting_loss_pct": LOSS})
    card = job_card(spec, Solved(spec, True, 1.0, 5.0, 5.0, 3), brief, plan, {}, 1, pricing.rate_card(),
                    seats_in_model=b.seats_in_model)
    assert any("seats are NOT cut" in w for w in card["warnings"])
    geometry.clear_scene()


def test_failed_boolean_and_failed_intersect_fall_back_to_sampling(geometry, monkeypatch):
    """Both booleans empty: the overlap is grid-sampled, still close to the true overlap."""
    spec = LEGACY_STONES["solitaire"]
    geometry.clear_scene()
    raw = _raw(geometry, spec, 1.0)
    v_raw, overlap = geometry.mesh_volume(raw.gold), _overlap(geometry, raw)
    geometry.clear_scene()
    monkeypatch.setattr(geometry, "_seat_try", _empty_seat_try(geometry))
    monkeypatch.setattr(geometry, "_intersect_mm3", lambda gold, gem: None)
    b = geometry.build(spec, 1.0)
    assert not b.seats_in_model
    assert b.seat_cut_mm3 == pytest.approx(overlap, rel=0.1)
    assert b.volume_mm3 == pytest.approx(v_raw - b.seat_cut_mm3, rel=1e-9)
    geometry.clear_scene()


def test_sampled_overlap_is_zero_for_a_stone_clear_of_the_metal(geometry):
    import bmesh
    from mathutils import Matrix
    geometry.clear_scene()
    obs = []
    for name, at in (("g", (0, 0, 0)), ("s", (5, 0, 0))):
        bm = bmesh.new()
        bmesh.ops.create_cube(bm, size=2.0, matrix=Matrix.Translation(at))
        obs.append(geometry._obj_from_bm(bm, name))
    assert geometry.gold_in_stones_mm3(obs[0], [obs[1]]) == 0.0
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=2.0, matrix=Matrix.Translation((1, 0, 0)))
    half = geometry._obj_from_bm(bm, "h")
    assert geometry._sampled_overlap_mm3(obs[0], half) == pytest.approx(4.0, rel=0.05)
    geometry.clear_scene()


# ----------------------------------------------------------- cache by spec hash
def test_builds_are_cached_by_spec_hash(geometry):
    spec = DesignSpec(name="b", piece_type="ring", width_mm=3.1)
    assert geometry.spec_hash(spec, 1.0) == geometry.spec_hash(spec.model_copy(), 1.0)
    assert geometry.spec_hash(spec, 1.0) != geometry.spec_hash(spec, 1.01)
    assert geometry.spec_hash(spec, 1.0) != geometry.spec_hash(spec.model_copy(update={"width_mm": 3.2}), 1.0)
    geometry.clear_volume_cache()
    v1 = geometry.gold_volume(spec, 1.0)
    v2 = geometry.gold_volume(spec.model_copy(), 1.0)
    assert v1 == v2 and geometry.CACHE_STATS == {"hits": 1, "builds": 1}


def test_solving_the_same_design_twice_builds_nothing_new(geometry):
    brief = Brief(piece_type="ring", karat=22, target_weight_g=5.0)
    plan = PACK.plan(brief, LOSS)
    spec = PACK.propose(brief, 3)[1]
    geometry.clear_volume_cache()
    a = PACK.solve(spec, plan)
    builds = geometry.CACHE_STATS["builds"]
    b = PACK.solve(spec, plan)
    assert geometry.CACHE_STATS["builds"] == builds and (a.scale, a.value) == (b.scale, b.value)


# ----------------------------------------------------------- solver accuracy, every design
def _all_designs():
    out = [(n, _fam_spec(n)) for n in families.CATALOGUE if n in families.FAMILIES]
    out += [("legacy_" + s.name, s) for s in designer.fallback(Brief(piece_type="ring", gem="diamond"), 0.5)]
    out += [("legacy_" + s.name, s) for s in designer.fallback(Brief(piece_type="bangle"), 0.0)]
    out += [("legacy_" + s.name, s) for s in designer.fallback(Brief(piece_type="pendant"), 0.0)]
    return out


@pytest.mark.parametrize("key,spec", _all_designs(), ids=[k for k, _ in _all_designs()])
def test_every_design_solves_within_0_1_g_or_2_pct_under_the_cap(geometry, key, spec):
    lo, hi = dfm.scale_bounds(spec)
    s_mid = lo + 0.4 * (hi - lo)
    grams = G.mm3_to_grams(geometry.gold_volume(spec, s_mid), spec.karat) * 1.004   # off-grid target
    plan = Plan(True, target_value=grams, detail={"casting_loss_pct": LOSS, "finished_gross_g": grams * 0.97})
    r = PACK.solve(spec, plan)
    assert r.ok, (key, r.explanation)
    assert abs(r.value - grams) <= accept_window(grams), key
    assert r.iterations <= MAX_ITER + 2


# ----------------------------------------------------------- infeasible contracts
def _contract(r, unit):
    assert not r.ok and r.explanation
    assert r.binding_constraint and r.best_achievable["unit"] == unit and r.best_achievable["value"] > 0
    assert len(r.alternatives) >= 2


def test_below_min_names_the_shank_rule_and_the_lightest_weight(geometry):
    spec = DesignSpec(name="b", piece_type="ring", width_mm=3.0, thickness_mm=1.8)
    r = PACK.solve(spec, Plan(True, target_value=0.5, detail={"casting_loss_pct": LOSS}))
    _contract(r, "g")
    assert r.binding_constraint == "minimum ring shank thickness 1.5 mm"
    lo, _ = dfm.scale_bounds(spec)
    lightest = G.mm3_to_grams(geometry.gold_volume(spec, lo), 22) * 0.97
    assert r.best_achievable["value"] == pytest.approx(lightest, abs=0.01)


def test_above_max_names_the_rule_and_the_heaviest_weight(geometry):
    spec = DesignSpec(name="b", piece_type="ring", width_mm=3.0, thickness_mm=1.8)
    r = PACK.solve(spec, Plan(True, target_value=200.0, detail={"casting_loss_pct": LOSS}))
    _contract(r, "g")
    assert r.binding_constraint.startswith("maximum ring shank")
    _, hi = dfm.scale_bounds(spec)
    assert r.best_achievable["value"] == pytest.approx(G.mm3_to_grams(geometry.gold_volume(spec, hi), 22) * 0.97,
                                                       abs=0.01)


def test_family_below_min_names_the_family(geometry):
    r = PACK.solve(_fam_spec("pendant_paisley"), Plan(True, target_value=0.05, detail={"casting_loss_pct": LOSS}))
    _contract(r, "g")
    assert "Paisley" in r.binding_constraint


def test_stone_too_big_names_the_stone_and_the_largest_that_fits(geometry):
    spec = DesignSpec(name="s", piece_type="ring", width_mm=2.0, thickness_mm=3.0, gem="diamond", gem_d_mm=12.0)
    r = PACK.solve(spec, Plan(True, target_value=5.0, detail={"casting_loss_pct": LOSS}))
    _contract(r, "ct")
    assert "stone size" in r.binding_constraint
    d = dfm.max_stone_d(spec)
    fits = PACK.solve(spec.model_copy(update={"gem_d_mm": d}),
                      Plan(True, target_value=12.0, detail={"casting_loss_pct": LOSS}))
    assert fits.binding_constraint != r.binding_constraint      # the suggested stone is castable


# ----------------------------------------------------------- Hero D
HERO_D = "22K ring, size 14, under 1.2 g, with a 1 ct diamond"


def test_hero_d_is_refused_with_the_minimum_achievable_weight_and_two_options(geometry):
    brief, q = B.parse(HERO_D)
    assert q is None and brief.gem_ct == 1.0
    p = PACK.plan(brief, LOSS)
    assert not p.ok and "minimum" in p.binding_constraint
    # the minimum achievable: the lightest castable design holding the 1 ct stone, measured
    lightest = min(G.mm3_to_grams(geometry.gold_volume(s, dfm.scale_bounds(s)[0]), 22) * 0.97
                   for s in designer.deterministic(brief, 1.0) if dfm.scale_bounds(s)[0] <= dfm.scale_bounds(s)[1])
    best = max(1.8, lightest)
    assert p.best_achievable == {"value": round(best, 2), "unit": "g"} and best > 1.2
    assert len(p.alternatives) >= 2
    assert p.alternatives[0].startswith(f"a {best:.2f} g 22K ring with the 1 ct diamond")
    assert any("smaller" in a and "ct diamond" in a for a in p.alternatives)
    assert f"{best:.2f} g" in p.explanation


# ----------------------------------------------------------- Hero B: budget, stone + gold together
HERO_B = "₹60,000 all-in for an 18K solitaire with a lab-grown diamond, size 14"


def _hero_b(text=HERO_B):
    brief, q = B.parse(text)
    assert q is None and brief.gem_ct is None
    plan = PACK.plan(brief, LOSS)
    assert plan.ok and plan.detail["joint_stone"]
    return brief, plan, PACK.propose(brief, 3)


def test_hero_b_solves_stone_and_gold_together_to_the_budget(geometry):
    brief, plan, specs = _hero_b()
    d0 = specs[0].gem_d_mm
    cts = []
    for spec in specs:
        r = PACK.solve(spec, plan)
        assert r.ok, r.explanation
        q = PACK.quote(r, brief, plan)
        assert 60000 * 0.99 <= q["total"] <= 60000                 # lands on the budget, never over
        assert r.spec.gem_d_mm == pytest.approx(d0 * r.scale, rel=1e-3)   # the stone grew with the band
        assert any("solved with the budget" in a for a in q["assumptions"])
        cts.append(r.spec.gem_ct)
    assert len({round(c, 2) for c in cts}) == 3                     # each design its own balance
    assert all(abs(c - pricing.requested_ct(brief)) > 0.02 for c in cts)   # not the fixed 0.5 ct


def test_a_bigger_budget_buys_both_a_bigger_stone_and_more_gold(geometry):
    _, p60, specs = _hero_b()
    _, p90, _ = _hero_b(HERO_B.replace("60,000", "90,000"))
    a, b = PACK.solve(specs[1], p60), PACK.solve(specs[1], p90)
    assert a.ok and b.ok
    assert b.spec.gem_ct > a.spec.gem_ct and b.value > a.value


def test_a_named_stone_size_stays_fixed_in_budget_mode(geometry):
    brief, q = B.parse("₹60,000 all-in for an 18K solitaire with a 0.5 ct lab-grown diamond, size 14")
    assert q is None and brief.gem_ct == 0.5
    plan = PACK.plan(brief, LOSS)
    assert plan.ok and not plan.detail.get("joint_stone")
    spec = PACK.propose(brief, 3)[1]
    r = PACK.solve(spec, plan)
    assert r.ok and r.spec.gem_d_mm == spec.gem_d_mm


# ----------------------------------------------------------- coin stamp
def test_a_5_g_coin_brief_stamps_5_g(geometry):
    from karigar.packs.jewellery.families import coin
    brief = Brief(piece_type="coin", karat=22, target_weight_g=5.0)
    plan = PACK.plan(brief, LOSS)
    assert plan.ok
    spec = PACK.propose(brief, 3)[1]
    assert coin.stamp_lines(spec) == ("22K 916", "5 g")
    r = PACK.solve(spec, plan)
    assert r.ok and coin.stamp_lines(r.spec) == ("22K 916", "5 g")
    assert abs(r.value * 0.97 - 5.0) <= 0.05


def test_an_exchange_coin_stamps_the_weight_it_is_made_to(geometry):
    from karigar.packs.jewellery.families import coin
    brief = Brief(piece_type="coin", karat=22, old_gold={"weight_g": 6.0, "karat": 22})
    plan = PACK.plan(brief, LOSS)
    spec = PACK.propose(brief, 3)[1]
    r = PACK.solve(spec, plan)
    assert r.ok
    assert coin.stamp_lines(r.spec)[1] == f"{round(plan.detail['finished_gross_g'], 2):g} g"


def _stepped_volume(geometry, monkeypatch, step_g=0.16):
    """gold_volume whose weights only come in step_g steps, offset so 10.0 g is step_g/2 away."""
    import math

    def vol(spec, s):
        g = 10.0 + (math.floor((s - 1.0) * 10.0 / step_g) + 0.5) * step_g   # ..., 9.92, 10.08, ...
        return G.grams_to_mm3(g, spec.karat)
    monkeypatch.setattr(geometry, "gold_volume", vol)


def test_coin_is_accepted_only_within_0_05_g(geometry, monkeypatch):
    """Nearest reachable weight 0.08 g off: a ring accepts it (0.1 g window), a coin does not."""
    _stepped_volume(geometry, monkeypatch)
    from karigar.packs.jewellery import COIN_ACCEPT_G
    assert COIN_ACCEPT_G == 0.05
    plan = Plan(True, target_value=10.0, detail={"casting_loss_pct": LOSS})
    coin = _fam_spec("coin_lotus_10g", stamp=False)
    ring = DesignSpec(name="b", piece_type="ring", width_mm=3.0, thickness_mm=1.8)
    assert PACK._solve_core(ring, plan).ok
    r = PACK._solve_core(coin, plan)
    assert not r.ok and r.best_achievable["unit"] == "g"


def test_coin_solve_lands_within_0_05_g_of_a_20_g_target(geometry):
    coin = _fam_spec("coin_lotus_10g", stamp=False)
    r = PACK._solve_core(coin, Plan(True, target_value=20.0, detail={"casting_loss_pct": LOSS}))
    assert r.ok and abs(r.value - 20.0) <= 0.05


def test_budget_solve_never_returns_ok_over_the_budget(geometry, monkeypatch):
    """The quote always tops the budget (rupee rounding gone wrong): infeasible, never ok."""
    import sys
    from karigar.core.solver import SolveResult
    mod = sys.modules["karigar.packs.jewellery"]
    monkeypatch.setattr(mod, "solve_monotone",
                        lambda f, target, lo, hi, **kw: SolveResult(True, hi, target, target, [(hi, target)]))
    monkeypatch.setattr(pricing, "quote", lambda spec, g, brief, plan: {"total": 60001.0})
    brief, plan, specs = _hero_b()
    r = PACK._solve_budget(specs[1], plan)
    assert not r.ok and r.best_achievable["unit"] == "INR" and r.best_achievable["value"] > 60000
