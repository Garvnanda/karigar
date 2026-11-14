"""Phase 2.5 family-specific checks for the rings, pendants and the lotus coin
(families/rings.py, pendants.py, coin.py and their helpers in families/_gemwork.py).

tests/test_families.py already runs the generic checks on every family (clean single
solid at three scales, volume rising with scale, three variants >= 15% apart). This file
covers what is particular to these families:

- rings: the finger hole measured on the mesh is spec.inner_d_mm +- 0.05 mm at both ends of
  the scale range and for small / large sizes, and no gold or stone comes inside it;
- stone layouts (petal / side / halo / shoulder / wing stones);
- pendants: the bail hole measured on the mesh lets a chain through (>= dfm.MIN_BAIL_HOLE);
- coin: the back stamp is built from code (karat -> fineness from core.gold.PURITY, the
  stamped weight from spec.params), the solver hits a stated weight to +-0.05 g;
- build hygiene: no stray objects left in the scene, builds deterministic, and the
  _gemwork helpers (relax, sliver-free plates, union retry) do what they promise.
Nothing here writes data/ or out/; no model is called.
"""
import math

import pytest

from karigar.core import gold as G
from karigar.core.solver import solve_monotone
from karigar.packs.jewellery import dfm
from karigar.packs.jewellery.families import FAMILIES
from karigar.packs.jewellery.schema import DesignSpec

RINGS = ("ring_floral_cluster", "ring_three_stone", "ring_halo_solitaire", "ring_butterfly")
PENDANTS = ("pendant_heart_halo", "pendant_paisley", "pendant_temple_lotus")
COIN = "coin_lotus_10g"
MINE = RINGS + PENDANTS + (COIN,)
ID_TOL_MM = 0.05


@pytest.fixture(scope="module")
def gm():
    from karigar.packs.jewellery import geometry, mesh_check
    return geometry, mesh_check


def _spec(name, **kw) -> DesignSpec:
    fam = FAMILIES[name]
    params = {**fam.default_spec.get("params", {}), **kw.pop("params", {})}
    return DesignSpec(**{"name": fam.title, "piece_type": fam.piece_type, "family": name,
                         **fam.default_spec, "params": params, **kw})


def _build(geometry, spec, s):
    geometry.clear_scene()
    return geometry.build(spec, s)


def test_my_families_are_registered():
    for n in MINE:
        assert n in FAMILIES, n
        assert FAMILIES[n].piece_type == n.split("_")[0]


# ------------------------------------------------------------------ rings
def _min_axis_dist_of(obs) -> float:
    """Smallest distance from the ring axis (world Y) to any edge of the objects."""
    from karigar.packs.jewellery.mesh_check import ring_inner_diameter
    return min(ring_inner_diameter(o) for o in obs) / 2


@pytest.mark.parametrize("name", RINGS)
@pytest.mark.parametrize("inner_d", (14.0, 17.3, 21.0))
def test_ring_finger_hole_is_exact_and_clear_across_the_scale_range(gm, name, inner_d):
    geometry, mc = gm
    spec = _spec(name, inner_d_mm=inner_d)
    lo, hi = dfm.scale_bounds(spec)
    assert lo < hi
    for s in (lo, hi):
        b = _build(geometry, spec, s)
        rep = mc.check(b.gold)
        assert rep.ok, (name, inner_d, s, rep.problems())
        d = mc.ring_inner_diameter(b.gold)
        assert abs(d - inner_d) <= ID_TOL_MM, (name, inner_d, s, d)
        # no stone reaches into the finger hole either
        assert _min_axis_dist_of(b.gems) > inner_d / 2, (name, inner_d, s)
        assert b.dims["inner_d_mm"] == inner_d
    geometry.clear_scene()


def test_floral_cluster_has_one_stone_per_petal_plus_the_centre(gm):
    geometry, mc = gm
    for n in (5, 6, 8):
        b = _build(geometry, _spec("ring_floral_cluster", params={"petal_stones": n}), 1.0)
        assert len(b.gems) == n + 1 and b.dims["petal_stones"] == n
        assert mc.check(b.gold).ok
    b = _build(geometry, _spec("ring_floral_cluster", gem="none", gem_d_mm=0.0), 1.0)
    assert len(b.gems) == 6                 # gold bead in the middle, petal stones stay
    geometry.clear_scene()


def test_floral_cluster_petal_cups_stand_apart_bridged_by_grain(gm):
    """Neighbouring petal cups are never near-tangent (that sealed voids = extra mesh
    components); the cluster stays one solid from the bottom to the top of the range."""
    geometry, mc = gm
    for n in (6, 8):                        # 8 petals: the widest cluster, centre seat highest
        spec = _spec("ring_floral_cluster", params={"petal_stones": n})
        lo, hi = dfm.scale_bounds(spec)
        for s in (lo, (lo + hi) / 2, hi):
            b = _build(geometry, spec, s)
            assert mc.check(b.gold).components == 1, (n, s)
    geometry.clear_scene()


def test_three_stone_and_halo_and_butterfly_stone_counts(gm):
    geometry, _ = gm
    b = _build(geometry, _spec("ring_three_stone"), 1.0)
    assert len(b.gems) == 3 and b.dims["centre_d_mm"] == 4.5 and b.dims["side_d_mm"] == 3.0
    b = _build(geometry, _spec("ring_halo_solitaire"), 1.0)
    assert len(b.gems) == 1 + b.dims["halo_stones"] + b.dims["shoulder_stones"]
    assert b.dims["halo_stones"] >= 8 and b.dims["shoulder_stones"] == 8
    b = _build(geometry, _spec("ring_butterfly"), 1.0)
    assert len(b.gems) == 4                 # one stone per wing
    geometry.clear_scene()


def test_ring_stone_follows_the_spec(gm):
    geometry, _ = gm
    b = _build(geometry, _spec("ring_three_stone", gem_d_mm=5.5, gem="ruby"), 1.0)
    assert b.dims["centre_d_mm"] == 5.5
    geometry.clear_scene()


def test_ring_checks_name_the_shank_and_finger_hole():
    for n in RINGS:
        spec = _spec(n)
        out = dfm.check(spec, 1.0)
        assert any("shank top" in c for c in out) and any("finger hole" in c for c in out), n


# ------------------------------------------------------------------ pendants
def _bail_hole(geometry, b, spec, s) -> float:
    """Diameter of the free hole through the bail, measured on the mesh: the chain runs
    along world X through a loop standing at the top. Loop centre from construction
    (_gemwork.bail): tube t, loop radius r = MIN_BAIL_HOLE/2 + t, top of the loop at
    centre + r + t, face offset -0.35 th (after ROT_UPRIGHT)."""
    th = spec.thickness_mm * s
    t = max(0.6, th * 0.45)
    r = dfm.MIN_BAIL_HOLE / 2 + t
    co = [b.gold.matrix_world @ v.co for v in b.gold.data.vertices]
    zmax = max(p.z for p in co)
    top = [p.x for p in co if p.z > zmax - 0.05]
    xc = sum(top) / len(top)
    yc, zc = -0.35 * th, zmax - (r + t)
    best = math.inf
    for e in b.gold.data.edges:
        p, q = co[e.vertices[0]], co[e.vertices[1]]
        if abs(p.x - xc) > t + 0.2 or abs(q.x - xc) > t + 0.2:
            continue
        ay, az, by, bz = p.y - yc, p.z - zc, q.y - yc, q.z - zc
        dy, dz = by - ay, bz - az
        L2 = dy * dy + dz * dz
        u = 0.0 if L2 == 0 else max(0.0, min(1.0, -(ay * dy + az * dz) / L2))
        best = min(best, math.hypot(ay + u * dy, az + u * dz))
    return 2 * best


@pytest.mark.parametrize("name", PENDANTS)
def test_pendant_bail_lets_a_chain_through(gm, name):
    geometry, _ = gm
    spec = _spec(name)
    lo, hi = dfm.scale_bounds(spec)
    for s in (lo, 1.0, hi):
        b = _build(geometry, spec, s)
        # the loop's polygon facets sag 0.2% inside its circle and the jitter tilts it by
        # 1.5e-3 rad: 0.03 mm under the nominal hole is facet geometry, not a smaller hole
        assert _bail_hole(geometry, b, spec, s) >= dfm.MIN_BAIL_HOLE - 0.03, (name, s)
    geometry.clear_scene()


def test_heart_halo_with_and_without_a_centre_stone(gm):
    geometry, mc = gm
    b = _build(geometry, _spec("pendant_heart_halo"), 1.0)
    assert len(b.gems) == b.dims["halo_stones"] >= 20
    b = _build(geometry, _spec("pendant_heart_halo", gem_d_mm=3.0), 1.0)
    assert len(b.gems) == b.dims["halo_stones"] + 1
    assert mc.check(b.gold).ok
    geometry.clear_scene()


def test_paisley_stone_line_and_wire_floor():
    from karigar.packs.jewellery.families import pendants
    spec = _spec("pendant_paisley")
    lo, _ = dfm.scale_bounds(spec)
    # the lightest castable paisley still has 0.6 mm filigree wire
    assert 2 * pendants._paisley_wire_r(spec, lo) == pytest.approx(pendants.WIRE_MIN_D)
    assert any("filigree wire" in c for c in dfm.check(spec, lo))


def test_paisley_line_stones_follow_params(gm):
    geometry, mc = gm
    for n in (3, 7):
        b = _build(geometry, _spec("pendant_paisley", params={"line_stones": n}), 1.0)
        assert len(b.gems) == n and b.dims["line_stones"] == n and mc.check(b.gold).ok
    geometry.clear_scene()


def test_temple_lotus_carries_the_customers_stone_or_a_gold_dome(gm):
    geometry, mc = gm
    b = _build(geometry, _spec("pendant_temple_lotus"), 1.0)
    assert len(b.gems) == 1 and b.dims["petals"] == 8
    b = _build(geometry, _spec("pendant_temple_lotus", gem="none", gem_d_mm=0.0, petals=10), 1.0)
    assert b.gems == [] and b.dims["petals"] == 10 and mc.check(b.gold).ok
    geometry.clear_scene()


def test_lotus_pendant_brief_maps_to_temple_lotus():
    from karigar.packs.jewellery import brief as B
    b, _ = B.parse("purani 22K chain 6.2g se 22K ruby lotus pendant banao")
    assert b is not None and b.family == "pendant_temple_lotus" and b.gem == "ruby"


# ------------------------------------------------------------------ coin
def test_coin_stamp_lines_come_from_code_data():
    from karigar.packs.jewellery.families import coin
    assert coin.stamp_lines(_spec(COIN)) == ("22K 916", "10 g")
    assert coin.stamp_lines(_spec(COIN, karat=18, params={"stamp_g": 8.0})) == ("18K 750", "8 g")
    assert coin.stamp_lines(_spec(COIN, karat=14, params={"stamp_g": 2.5})) == ("14K 585", "2.5 g")
    for k, p in G.PURITY.items():
        assert coin.fineness(k) == round(p * 1000)
    # every character the stamp can need has a glyph
    for k in (14, 18, 22):
        for w in (1.0, 2.5, 8.0, 10.0, 20.0, 50.0):
            for line in coin.stamp_lines(_spec(COIN, karat=k, params={"stamp_g": w})):
                assert all(ch == " " or ch in coin.GLYPHS for ch in line), line


def test_coin_stamp_is_embossed_on_the_back(gm):
    geometry, mc = gm
    b = _build(geometry, _spec(COIN), 1.0)
    v_stamp = b.volume_mm3
    assert b.dims["stamp"] == "22K 916 / 10 g" and b.gems == []
    # the lettering is raised on the back (world +Y after ROT_UPRIGHT): it stands proud
    # of the back face beyond where the plain coin's back sits, inside the rim
    ys = [(b.gold.matrix_world @ v.co) for v in b.gold.data.vertices]
    inner = [p.y for p in ys if math.hypot(p.x, p.z) < 6.0]
    b0 = _build(geometry, _spec(COIN, stamp=False), 1.0)
    inner0 = [p.y for p in ((b0.gold.matrix_world @ v.co) for v in b0.gold.data.vertices)
              if math.hypot(p.x, p.z) < 6.0]
    assert max(inner) > max(inner0) + 0.2
    assert v_stamp > b0.volume_mm3 and "stamp" not in b0.dims
    # a different stamped weight is different lettering (so different gold)
    b8 = _build(geometry, _spec(COIN, params={"stamp_g": 8.0}), 1.0)
    assert b8.dims["stamp"] == "22K 916 / 8 g" and b8.volume_mm3 != pytest.approx(v_stamp, rel=1e-4)
    assert mc.check(b8.gold).ok
    geometry.clear_scene()


@pytest.mark.parametrize("karat,grams", [(22, 10.0), (18, 5.0)])
def test_coin_solves_to_the_stated_weight(gm, karat, grams):
    geometry, mc = gm
    spec = _spec(COIN, karat=karat, params={"stamp_g": grams})
    lo, hi = dfm.scale_bounds(spec)
    r = solve_monotone(lambda s: G.mm3_to_grams(geometry.gold_volume(spec, s), karat), grams, lo, hi)
    assert r.ok and abs(r.value - grams) <= 0.05, (r.value, r.reason)
    b = _build(geometry, spec, r.scale)
    assert mc.check(b.gold).ok
    assert abs(G.mm3_to_grams(b.volume_mm3, karat) - grams) <= 0.05
    geometry.clear_scene()


def test_coin_default_is_about_10_g_in_22k(gm):
    geometry, _ = gm
    g = G.mm3_to_grams(geometry.gold_volume(_spec(COIN), 1.0), 22)
    assert 9.0 < g < 11.0


def test_coin_bounds_and_checks():
    from karigar.packs.jewellery.families import coin
    spec = _spec(COIN)
    lo, hi = dfm.scale_bounds(spec)
    assert spec.thickness_mm * lo == pytest.approx(coin.MIN_BODY_T)
    D_hi = spec.size_mm * math.sqrt(hi)
    assert D_hi <= coin.MAX_D + 1e-9 and spec.thickness_mm * hi <= coin.MAX_BODY_T + 1e-9
    out = dfm.check(spec, 1.0)
    assert any("body thickness" in c for c in out)
    assert any("22K 916" in c and "10 g" in c for c in out)
    assert not any("stamped" in c for c in dfm.check(_spec(COIN, stamp=False), 1.0))


# ------------------------------------------------------------------ build hygiene
@pytest.mark.parametrize("name", MINE)
def test_build_leaves_only_gold_and_stones_in_the_scene(gm, name):
    import bpy
    geometry, _ = gm
    b = _build(geometry, _spec(name), 1.0)
    assert set(bpy.data.objects) == {b.gold, *b.gems}, sorted(o.name for o in bpy.data.objects)
    geometry.clear_scene()


@pytest.mark.parametrize("name", ("ring_halo_solitaire", "pendant_heart_halo"))
def test_builds_are_deterministic(gm, name):
    geometry, _ = gm
    v = [geometry.gold_volume(_spec(name), 1.07) for _ in range(2)]
    assert v[0] == pytest.approx(v[1], rel=1e-9)        # the boolean's own float noise only


# ------------------------------------------------------------------ _gemwork helpers
def test_relax_rounds_every_bend_tighter_than_the_wire():
    import bpy  # noqa: F401  (mathutils comes with the bpy module)
    from karigar.packs.jewellery.families._gemwork import _circumradius, relax
    pts = [(0, 0), (2, 0), (2.05, 1.5), (4, 1.6), (4, 0)]           # two sharp corners
    out = relax(pts, 0.5, closed=True)
    n = len(out)
    assert min(_circumradius(out[i - 1], out[i], out[(i + 1) % n]) for i in range(n)) >= 0.5
    op = relax(pts, 0.5, closed=False)
    assert tuple(op[0])[:2] == (0, 0) and tuple(op[-1])[:2] == (4, 0)   # open ends stay put


def test_plates_and_cushions_are_clean_and_sliver_free(gm):
    geometry, mc = gm
    from karigar.packs.jewellery.families._gemwork import cushion, disc, prism
    from karigar.packs.jewellery.families.pendants import heart_contour
    geometry.clear_scene()
    heart = heart_contour(4.0, 1.0)
    for ob in (prism(heart, 0.0, 0.7, "p"), disc(8.0, -0.3, 0.3, "d"),
               cushion(heart, (0, 0), 0.0, 1.5, "c", 10, 2.6)):
        assert mc.check(ob).ok, (ob.name, mc.check(ob).problems())
        worst = 0.0
        for poly in ob.data.polygons:
            vs = [ob.data.vertices[i].co for i in poly.vertices]
            edges = [(vs[i] - vs[i - 1]).length for i in range(len(vs))]
            worst = max(worst, max(edges) ** 2 / (2 * poly.area) if poly.area > 0 else math.inf)
        # longest edge / height on it: a fan of a 100-point outline is > 50
        assert worst < 25, (ob.name, worst)
    geometry.clear_scene()


def test_union_clean_retries_with_another_jitter_and_frees_its_copies(gm, monkeypatch):
    import bpy
    geometry, mc = gm
    from karigar.packs.jewellery.families import _gemwork
    geometry.clear_scene()
    real = mc.check
    calls = []

    def flaky(ob, *a, **k):
        rep = real(ob, *a, **k)
        calls.append(rep)
        if len(calls) == 1:                 # pretend the first boolean left a crossing
            rep.self_intersections = 3
        return rep
    monkeypatch.setattr(mc, "check", flaky)
    parts = [geometry.sphere((0, 0, 0), (2, 2, 1), "a"), geometry.sphere((1.5, 0, 0), (1, 1, 1), "b")]
    out = _gemwork.union_clean(parts)
    assert len(calls) == 2 and real(out).ok
    assert set(bpy.data.objects) == {out}
    geometry.clear_scene()


def test_jitter_never_moves_the_base_part(gm):
    geometry, _ = gm
    from karigar.packs.jewellery.families._gemwork import jitter
    geometry.clear_scene()
    a = geometry.sphere((0, 0, 0), (2, 2, 2), "a")
    b = geometry.sphere((3, 0, 0), (1, 1, 1), "b")
    ca, cb = [v.co.copy() for v in a.data.vertices], [v.co.copy() for v in b.data.vertices]
    jitter([a, b])
    assert all((v.co - c).length == 0 for v, c in zip(a.data.vertices, ca))
    moved = max((v.co - c).length for v, c in zip(b.data.vertices, cb))
    assert 0 < moved < 0.01
    geometry.clear_scene()


def test_drop_debris_removes_only_sub_0_05_mm_shards(gm):
    geometry, mc = gm
    from karigar.packs.jewellery.families._gemwork import drop_debris
    geometry.clear_scene()
    big = geometry.sphere((0, 0, 0), (2, 2, 2), "big")
    shard = geometry.sphere((5, 0, 0), (0.01, 0.01, 0.01), "shard", 8, 5)
    ob = geometry.union([big, shard], "gold")       # two islands, one of them debris
    assert mc.check(ob).components == 2
    assert drop_debris(ob) == 1
    rep = mc.check(ob)
    assert rep.ok and rep.components == 1
    assert drop_debris(ob) == 0                     # a real part is never touched
    geometry.clear_scene()


def test_temple_lotus_is_one_solid_for_any_petal_count(gm):
    geometry, mc = gm
    for n in (5, 10, 12):
        b = _build(geometry, _spec("pendant_temple_lotus", gem="none", gem_d_mm=0.0, petals=n), 1.159)
        assert mc.check(b.gold).ok, (n, mc.check(b.gold).problems())
    geometry.clear_scene()
