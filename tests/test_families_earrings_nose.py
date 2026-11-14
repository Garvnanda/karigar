"""Phase 2.5 earring + nose families (families/earrings.py, families/nose.py, helpers in
families/_ornament.py): the family-specific gate items, measured on the built mesh.
The generic checks (clean solid at three scales, volume rising with scale, three
variants 15% apart, earrings as a mirrored pair) live in tests/test_families.py.

Worn frame: +Z up, the face looks along -Y, posts / pins go in along +Y.
"""
import math

import pytest

from karigar.core import gold
from karigar.packs.jewellery import dfm
from karigar.packs.jewellery.families import FAMILIES, nose
from karigar.packs.jewellery.families._ornament import MIN_POST_D, MIN_WALL, post_d
from karigar.packs.jewellery.schema import DesignSpec

EARRINGS = ("earring_jhumka", "earring_chandbali", "earring_floral_stud", "earring_bali_hoop")
NOSE = ("nosepin_flower", "nosepin_convertible_stud")


@pytest.fixture(scope="module")
def geometry():
    from karigar.packs.jewellery import geometry
    yield geometry
    geometry.clear_scene()


def _spec(name, **kw) -> DesignSpec:
    fam = FAMILIES[name]
    return DesignSpec(**{"name": fam.title, "piece_type": fam.piece_type, "family": name,
                         **fam.default_spec, **kw})


def _build(geometry, name, s=1.0, **kw):
    geometry.clear_scene()
    return geometry.build(_spec(name, pair=False, **kw), s)


def _verts(ob):
    return [ob.matrix_world @ v.co for v in ob.data.vertices]


def _hits(ob, origin, direction, far=200.0):
    """Distances along a ray to every surface crossing of `ob` (world space)."""
    from mathutils import Vector
    from mathutils.bvhtree import BVHTree
    tree = BVHTree.FromObject(ob, __import__("bpy").context.evaluated_depsgraph_get())
    o, d = Vector(origin), Vector(direction).normalized()
    out, t = [], 0.0
    while True:
        loc, _, _, dist = tree.ray_cast(o + d * t, d, far)
        if loc is None:
            return out
        t += dist + 1e-4
        out.append(t)


def _inside(ob, p) -> bool:
    return len(_hits(ob, p, (0.31, 0.17, 0.93))) % 2 == 1


def _posts_ok(dims):
    return dims["post_d_mm"] >= MIN_POST_D


# ------------------------------------------------------------ all six
@pytest.mark.parametrize("name", EARRINGS + NOSE)
def test_earrings_nose_registered_with_scale_bounds(name):
    fam = FAMILIES[name]
    assert fam.piece_type == ("earring" if name.startswith("earring") else "nosepin")
    assert fam.scale_bounds is not None
    lo, hi = dfm.scale_bounds(_spec(name))
    assert 0 < lo < 1.0 < hi


@pytest.mark.parametrize("name", EARRINGS + NOSE)
def test_earrings_nose_post_never_below_0_8_and_does_not_scale(name, geometry):
    lo, hi = dfm.scale_bounds(_spec(name, gauge_mm=0.6))
    for s in (lo, hi):
        b = _build(geometry, name, s, gauge_mm=0.6)     # schema allows 0.6; we cast 0.8
        key = "wire_d_mm" if name == "earring_bali_hoop" else "post_d_mm"
        assert b.dims[key] == MIN_POST_D
    assert post_d(_spec(name, gauge_mm=1.0)) == 1.0


@pytest.mark.parametrize("name", EARRINGS + NOSE)
def test_earrings_nose_job_card_checks_name_the_findings(name):
    fam = FAMILIES[name]
    text = " ".join(fam.checks(_spec(name), 1.0))
    if name == "earring_bali_hoop":
        assert "latch" in text and "pair" in text
    elif name == "nosepin_flower":
        assert "L-pin" in text and "0.80 mm" in text
    elif name == "nosepin_convertible_stud":
        assert "screw-back" in text and "not in the gold weight" in text
    else:
        assert "butterfly back" in text and "not in the gold weight" in text and "pair" in text


@pytest.mark.parametrize("name", EARRINGS + NOSE)
def test_earrings_nose_default_carries_its_stone(name, geometry):
    b = _build(geometry, name)
    assert len(b.gems) == (0 if name == "earring_bali_hoop" else 1)


# ------------------------------------------------------------ E1 jhumka
def test_jhumka_bell_is_hollow_open_and_walled(geometry):
    sp = _spec("earring_jhumka")
    lo, _ = dfm.scale_bounds(sp)
    assert sp.thickness_mm * lo >= MIN_WALL - 1e-9          # thinnest castable wall
    for s in (lo, 1.0):
        b = _build(geometry, "earring_jhumka", s)
        assert b.dims["wall_mm"] >= MIN_WALL - 1e-6 and b.dims["drops"] >= 6
        vs = _verts(b.gold)
        low = [v for v in vs if v.z < min(w.z for w in vs) + 3.0]
        y_ax = (min(v.y for v in low) + max(v.y for v in low)) / 2   # drops ring the axis
        z0 = min(v.z for v in vs) - 5
        up = _hits(b.gold, (0, y_ax, z0), (0, 0, 1))
        z_top = z0 + up[0]                                  # first gold above: inside the bell top
        p = (0, y_ax, z_top - 0.4 * b.dims["bell_h_mm"])
        assert not _inside(b.gold, p)                       # cavity
        assert _hits(b.gold, p, (0, 0, -1)) == []           # open at the bottom
        side = _hits(b.gold, p, (1, 0, 0))                  # enclosed by the bell wall
        assert side and side[0] < b.dims["bell_d_mm"] / 2
        assert side[1] - side[0] >= b.dims["wall_mm"] - 0.05


# ------------------------------------------------------------ E2 chandbali
def test_chandbali_crescent_is_openwork_with_drops(geometry):
    b = _build(geometry, "earring_chandbali")
    d = b.dims
    assert d["jaali_openings"] >= 5 and d["drops"] == 7
    Ro = d["width_mm"] / 2
    Rc = Ro - d["band_w_mm"] / 2
    # bottom of the crescent: the centre of a jaali ring is open, its outer edge wire is gold
    assert not _inside(b.gold, (0, 0, -Rc))
    assert _inside(b.gold, (0, 0, -(Ro - d["depth_mm"] / 2)))
    # the open gap between the horns at the top
    assert not _inside(b.gold, (0, 0, Rc))
    assert _posts_ok(d)


# ------------------------------------------------------------ E3 floral stud
def test_floral_stud_flower_and_post(geometry):
    b = _build(geometry, "earring_floral_stud")
    vs = _verts(b.gold)
    assert b.dims["petals"] == 7
    assert max(v.y for v in vs) == pytest.approx(b.dims["post_len_mm"], abs=0.05)
    width = max(v.x for v in vs) - min(v.x for v in vs)
    assert width == pytest.approx(b.dims["flower_d_mm"], rel=0.1)


# ------------------------------------------------------------ E4 bali
@pytest.mark.parametrize("label", ("lighter", "balanced", "statement"))
def test_bali_hoop_is_15_to_20_mm_and_its_fit_does_not_scale(label, geometry):
    f = FAMILIES["earring_bali_hoop"].variant_fields(label)
    sp = DesignSpec(**{"name": "Bali", "piece_type": "earring", "family": "earring_bali_hoop", **f})
    lo, hi = dfm.scale_bounds(sp)
    centre = []
    for s in (lo, hi):
        geometry.clear_scene()
        b = geometry.build(sp.model_copy(update={"pair": False}), s)
        centre.append(b.dims["hoop_d_mm"] - b.dims["tube_d_mm"])
        vs = _verts(b.gold)
        length = max(v.z for v in vs) - min(v.z for v in vs)
        assert b.dims["length_mm"] == pytest.approx(length, abs=0.01)
        # thin ear wire at the top, full tube (+ granules) at the bottom
        lo_len = centre[-1] + b.dims["wire_d_mm"] / 2 + b.dims["tube_d_mm"] / 2
        assert lo_len - 0.05 <= length <= lo_len + b.dims["tube_d_mm"]
        assert b.dims["inner_d_mm"] > 10
    assert centre[0] == pytest.approx(centre[1], abs=0.01)
    assert 15.0 <= centre[0] <= 20.0


def test_bali_tapers_from_ear_wire_to_full_tube(geometry):
    b = _build(geometry, "earring_bali_hoop")
    vs = _verts(b.gold)
    top = [v for v in vs if v.z > b.dims["hoop_d_mm"] / 2 - 1.5]
    th_top = max(v.y for v in top) - min(v.y for v in top)
    assert th_top == pytest.approx(b.dims["wire_d_mm"], abs=0.15)
    bot = [v for v in vs if abs(v.x) < 0.3 and v.z < 0]
    th_bot = max(v.y for v in bot) - min(v.y for v in bot)
    assert th_bot >= 0.95 * b.dims["tube_d_mm"]


# ------------------------------------------------------------ N1 flower nosepin
def test_nose_flower_is_tiny_with_a_1_5mm_stone_and_an_l_pin(geometry):
    sp = _spec("nosepin_flower")
    assert sp.petals == 5 and sp.gem_d_mm == 1.5 and sp.gauge_mm == 0.8
    b = _build(geometry, "nosepin_flower")
    g22 = gold.mm3_to_grams(b.volume_mm3, 22)
    assert 0.2 <= g22 <= 0.5, g22
    vs = _verts(b.gold)
    stem, leg = b.dims["stem_mm"], b.dims["leg_mm"]
    assert max(v.y for v in vs) == pytest.approx(stem + b.dims["post_d_mm"] / 2, abs=0.15)
    back = [v for v in vs if v.y > stem - 0.6]              # the leg, behind the nostril wall
    assert min(v.z for v in back) <= -(leg - 0.1)
    assert max(v.x for v in back) - min(v.x for v in back) == pytest.approx(b.dims["post_d_mm"], abs=0.1)


# ------------------------------------------------------------ N2 convertible stud
def test_convertible_stud_fits_nose_and_ear(geometry):
    sp = _spec("nosepin_convertible_stud")
    f = nose.fit(sp)
    assert sp.gauge_mm == 0.8
    assert 6.0 <= f["post_len_mm"] <= 8.0                   # nose (~6 mm) and ear lobe (6-8 mm)
    assert f["grip_min_mm"] <= nose.NOSE_WALL_MM <= f["grip_max_mm"]
    assert f["grip_min_mm"] <= nose.EAR_LOBE_MM <= f["grip_max_mm"]
    b = _build(geometry, "nosepin_convertible_stud")
    vs = _verts(b.gold)
    L, thr = f["post_len_mm"], f["thread_len_mm"]
    assert max(v.y for v in vs) == pytest.approx(L, abs=0.05)     # measured post length
    plain = [math.hypot(v.x, v.z) for v in vs if 0.2 < v.y < L - thr + 0.01]   # unthreaded shank
    assert max(plain) == pytest.approx(0.4, abs=0.02)            # 0.8 mm gauge
    thread = [math.hypot(v.x, v.z) for v in vs if L - thr + 0.2 < v.y < L - 0.5]
    assert max(thread) - min(thread) >= 0.04                     # grooves for the screw-back
    assert max(thread) <= 0.4 + 1e-6
    assert 0.2 <= gold.mm3_to_grams(b.volume_mm3, 22) <= 0.5


# ------------------------------------------------------------ _ornament.solid
def test_solid_retries_with_a_micron_nudge_when_the_check_fails(geometry, monkeypatch):
    from karigar.packs.jewellery.families import _ornament as o
    geometry.clear_scene()
    parts = [geometry.sphere((0, 0, 0), (2, 2, 2), "a", 24, 12),
             geometry.sphere((2.5, 0, 0), (1.5, 1.5, 1.5), "b", 24, 12)]
    ref = o.solid(parts, "ref")
    v_ref = geometry.mesh_volume(ref)
    assert all(len(p.vertices) == 3 for p in ref.data.polygons)      # triangulated
    calls = []
    real = o._problems

    def flaky(ob, mirror):
        calls.append(ob.name)
        return ["non_manifold_edges=1"] if len(calls) == 1 else real(ob, mirror)

    monkeypatch.setattr(o, "_problems", flaky)
    parts = [geometry.sphere((0, 0, 0), (2, 2, 2), "a", 24, 12),
             geometry.sphere((2.5, 0, 0), (1.5, 1.5, 1.5), "b", 24, 12)]
    out = o.solid(parts, "gold2", mirror=True)
    assert len(calls) == 2 and out.name == "gold2"
    assert geometry.mesh_volume(out) == pytest.approx(v_ref, rel=1e-3)
    import bpy
    assert "gold2_try1" not in bpy.data.objects
    geometry.clear_scene()
