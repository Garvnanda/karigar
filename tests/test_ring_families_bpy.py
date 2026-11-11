"""Phase 2 ring families: plain band (several profiles), solitaire (4 and 6 prongs)
and a floral motif ring. Every family at three scales must give one watertight,
manifold, outward-facing, self-intersection-free piece of gold, and the finger
hole measured on the mesh must match the size-table inner diameter to 0.05 mm."""
import pytest

from karigar.packs.jewellery.schema import DesignSpec

ID_TOL_MM = 0.05
HERO_A_ID = 16.5   # Indian size 12 (PNG Jewellers chart)

FAMILIES = {
    "band_comfort": DesignSpec(name="Comfort Band", piece_type="ring", profile="comfort",
                               inner_d_mm=17.3, width_mm=3.5, thickness_mm=1.8),
    "band_flat": DesignSpec(name="Flat Band", piece_type="ring", profile="flat",
                            inner_d_mm=HERO_A_ID, width_mm=4.0, thickness_mm=1.6),
    "band_knife": DesignSpec(name="Knife Edge", piece_type="ring", profile="knife",
                             inner_d_mm=19.0, width_mm=2.5, thickness_mm=2.0),
    "band_faceted": DesignSpec(name="Faceted Band", piece_type="ring", profile="faceted",
                               inner_d_mm=22.0, width_mm=3.0, thickness_mm=1.8),
    "solitaire_4": DesignSpec(name="Four Claw", piece_type="ring", karat=18, inner_d_mm=HERO_A_ID,
                              width_mm=2.4, thickness_mm=1.7, gem="diamond", gem_d_mm=5.2, prongs=4),
    "solitaire_6": DesignSpec(name="Six Claw", piece_type="ring", karat=18, inner_d_mm=18.1,
                              width_mm=2.6, thickness_mm=1.7, gem="diamond", gem_d_mm=6.5, prongs=6),
    "floral": DesignSpec(name="Phool Ring", piece_type="ring", motif="floral", petals=6, size_mm=9.0,
                         inner_d_mm=HERO_A_ID, width_mm=2.5, thickness_mm=1.6),
    "floral_stone": DesignSpec(name="Phool Ruby", piece_type="ring", motif="floral", petals=8,
                               size_mm=10.0, inner_d_mm=17.3, width_mm=2.5, thickness_mm=1.6,
                               gem="ruby", gem_d_mm=3.0),
}
SCALES = (0.8, 1.0, 1.35)


@pytest.fixture(scope="module")
def gm():
    from karigar.packs.jewellery import geometry, mesh_check
    return geometry, mesh_check


@pytest.fixture(scope="module")
def built(gm):
    """Build each family x scale once; keep only the measurements (the scene is cleared)."""
    geometry, mc = gm
    out = {}
    for fam, spec in FAMILIES.items():
        for s in SCALES:
            geometry.clear_scene()
            b = geometry.build(spec, s)
            zmax = max((b.gold.matrix_world @ v.co).z for v in b.gold.data.vertices)
            out[fam, s] = {"report": mc.check(b.gold), "inner_d": mc.ring_inner_diameter(b.gold),
                           "volume": b.volume_mm3, "dims": b.dims, "gems": len(b.gems), "zmax": zmax}
    geometry.clear_scene()
    return out


CASES = [(f, s) for f in FAMILIES for s in SCALES]


@pytest.mark.parametrize("fam,s", CASES)
def test_every_family_is_one_clean_solid(built, fam, s):
    rep = built[fam, s]["report"]
    assert rep.ok, f"{fam} @ {s}: {rep.problems()}"
    assert rep.self_intersections == 0          # actually checked, not skipped
    assert rep.components == 1 and rep.boundary_edges == 0 and rep.non_manifold_verts == 0


@pytest.mark.parametrize("fam,s", CASES)
def test_inner_diameter_matches_size_table(built, fam, s):
    got = built[fam, s]["inner_d"]
    want = FAMILIES[fam].inner_d_mm
    assert abs(got - want) <= ID_TOL_MM, f"{fam} @ {s}: inner diameter {got:.4f} mm, target {want}"


def test_at_least_two_band_profiles_build(built):
    profiles = {FAMILIES[f].profile for f, _ in built if f.startswith("band_")}
    assert len(profiles) >= 2


@pytest.mark.parametrize("fam", list(FAMILIES))
def test_scale_grows_metal_monotonically(built, fam):
    vols = [built[fam, s]["volume"] for s in SCALES]
    assert vols == sorted(vols) and vols[0] < vols[-1], f"{fam}: {vols}"


def test_solitaires_carry_one_stone(built):
    for fam in ("solitaire_4", "solitaire_6", "floral_stone"):
        assert built[fam, 1.0]["gems"] == 1
    assert built["floral", 1.0]["gems"] == 0


def test_six_prongs_use_more_metal_than_four(gm):
    geometry, _ = gm
    four = FAMILIES["solitaire_4"].model_copy(update={"inner_d_mm": 18.1, "gem_d_mm": 6.5, "width_mm": 2.6})
    six = FAMILIES["solitaire_6"]
    assert geometry.gold_volume(six, 1.0) > geometry.gold_volume(four, 1.0)


def test_floral_top_sits_on_the_ring_and_scales_with_it(built):
    for s in SCALES:
        d = built["floral", s]["dims"]
        assert d["flower_d_mm"] == pytest.approx(9.0 * s, abs=0.01)
        assert d["petals"] == 6
        band_top = HERO_A_ID / 2 + d["thickness_mm"]
        assert built["floral", s]["zmax"] > band_top + 0.5   # the flower stands proud of the band


def test_floral_adds_metal_over_the_plain_band(gm, built):
    geometry, _ = gm
    plain = FAMILIES["floral"].model_copy(update={"motif": "plain"})
    assert built["floral", 1.0]["volume"] > geometry.gold_volume(plain, 1.0) + 5.0


def test_petal_count_and_flower_size_are_parametric(gm):
    geometry, mc = gm
    base = FAMILIES["floral"]
    v6 = geometry.gold_volume(base, 1.0)
    v10 = geometry.gold_volume(base.model_copy(update={"petals": 10}), 1.0)
    big = base.model_copy(update={"size_mm": 13.0, "petals": 12})
    v_big = geometry.gold_volume(big, 1.0)
    assert v6 != pytest.approx(v10, rel=1e-3)
    assert v_big > v6
    geometry.clear_scene()
    b = geometry.build(big, 1.0)
    assert mc.check(b.gold).ok
    assert abs(mc.ring_inner_diameter(b.gold) - HERO_A_ID) <= ID_TOL_MM
    geometry.clear_scene()


def test_floral_is_a_valid_ring_motif():
    spec = DesignSpec(name="x", piece_type="ring", motif="floral")
    assert spec.motif == "floral"
    with pytest.raises(Exception):
        DesignSpec(name="x", piece_type="ring", motif="paisley")
