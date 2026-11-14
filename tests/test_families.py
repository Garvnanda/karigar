"""Phase 2.5 catalogue: generic checks run for EVERY registered design family, so each
family added under karigar/packs/jewellery/families/ is tested without new test code:

- builds at scales 0.85 / 1.0 / 1.15; the gold is watertight, manifold, outward-facing,
  free of loose geometry and self-intersections, and one piece (chains: every link closed,
  links may be separate solids because they interlock);
- gold volume rises strictly with scale (so the solver can hit a gram target);
- the designer proposes lighter / balanced / statement with weights >= 15% apart;
- earrings are built and weighed as a mirrored pair.

Two throwaway families (`test_toy_*`) are registered here so the scaffold itself is
exercised before any catalogue family exists; they are unregistered after this module.

`test_all_catalogue_families_registered` fails until all 19 catalogue builders land.
That is intended (Phase 2.5 gate: every family builds); do not skip it.
"""
import math

import pytest

from karigar.packs.jewellery import designer, families, pricing
from karigar.packs.jewellery.families import CATALOGUE, FAMILIES, LABELS
from karigar.packs.jewellery.schema import Brief, DesignSpec

SCALES = (0.85, 1.0, 1.15)
SPREAD = 1.15


# ------------------------------------------------------------ throwaway families
def _toy_earring(spec, s):
    from karigar.packs.jewellery import geometry as g
    R = spec.size_mm * s / 2
    dome = g.sphere((0, 0, 0), (R, R, R * 0.5), "dome", 32, 16)
    post = g.cylinder((0, 0), spec.gauge_mm / 2, -10.0, 0.0, "post", 16)
    gold = g.union([dome, post], "gold")
    return g.Built(gold, [], g.mesh_volume(gold), {"size_mm": round(2 * R, 2),
                                                   "post_d_mm": spec.gauge_mm})


def _toy_chain(spec, s):
    from karigar.packs.jewellery import geometry as g
    major = spec.length_in * 25.4 / (2 * math.pi)
    gold = g.torus(major, spec.link_w_mm * s / 2, "gold", 128, 12)
    return g.Built(gold, [], g.mesh_volume(gold), {"length_in": spec.length_in})


TOYS = ("test_toy_earring", "test_toy_chain")
for _n in TOYS:
    families.unregister(_n)
families.register("test_toy_earring", "earring", _toy_earring, {"size_mm": 10.0},
                  {"size_mm": (0.8, 1.0, 1.3)}, scale_bounds=(0.8, 1.3))
families.register("test_toy_chain", "chain", _toy_chain, {"length_in": 18, "link_w_mm": 3.0},
                  {"link_w_mm": (0.8, 1.0, 1.3)}, scale_bounds=(0.8, 1.3))
NAMES = sorted(FAMILIES)          # toys + every catalogue family registered so far


@pytest.fixture(scope="module", autouse=True)
def _drop_toys():
    yield
    for n in TOYS:
        families.unregister(n)


@pytest.fixture(scope="module")
def geometry():
    from karigar.packs.jewellery import geometry
    return geometry


@pytest.fixture(scope="module")
def mesh_check():
    from karigar.packs.jewellery import mesh_check
    return mesh_check


def _spec(name, **kw) -> DesignSpec:
    fam = FAMILIES[name]
    return DesignSpec(**{"name": fam.title, "piece_type": fam.piece_type, "family": name,
                         **fam.default_spec, **kw})


def _brief(name) -> Brief:
    fam = FAMILIES[name]
    return Brief(piece_type=fam.piece_type, karat=22, family=name,
                 length_in=fam.default_spec.get("length_in", 18) if fam.piece_type == "chain" else None)


# ------------------------------------------------------------ the catalogue
def test_all_catalogue_families_registered():
    """Phase 2.5: all 19 catalogue designs (18 + the convertible nose/ear stud) are registered."""
    assert len(CATALOGUE) == len(set(CATALOGUE)) == 19
    missing = [n for n in CATALOGUE if n not in FAMILIES]
    assert not missing, f"{len(missing)} catalogue families have no builder yet: {missing}"


def test_catalogue_family_names_start_with_their_piece_type():
    for n in CATALOGUE:
        if n in FAMILIES:
            assert n.startswith(FAMILIES[n].piece_type + "_"), n


# ------------------------------------------------------------ per family
@pytest.mark.parametrize("name", NAMES)
def test_family_builds_clean_solid_at_three_scales(name, geometry, mesh_check):
    spec = _spec(name)
    for s in SCALES:
        geometry.clear_scene()
        b = geometry.build(spec, s)
        rep = mesh_check.check(b.gold)
        problems = rep.problems()
        if spec.piece_type == "chain":      # interlocking links are separate closed solids
            problems = [p for p in problems if not p.startswith("components=")]
        assert not problems, f"{name} at scale {s}: {problems}"
        assert b.volume_mm3 > 0
    geometry.clear_scene()


@pytest.mark.parametrize("name", NAMES)
def test_family_volume_rises_strictly_with_scale(name, geometry):
    spec = _spec(name)
    v = [geometry.gold_volume(spec, s) for s in SCALES]
    assert all(b > a for a, b in zip(v, v[1:])), f"{name}: volumes {v} at scales {SCALES}"


@pytest.mark.parametrize("name", NAMES)
def test_family_scale_bounds_cover_the_test_scales(name):
    from karigar.packs.jewellery import dfm
    lo, hi = dfm.scale_bounds(_spec(name))
    assert 0 < lo < hi, (name, lo, hi)


@pytest.mark.parametrize("name", NAMES)
def test_designer_gives_three_family_variants_15pct_apart(name, geometry):
    b = _brief(name)
    specs = designer.propose(b, pricing.requested_ct(b), 3)
    assert len(specs) == 3
    for s, lab in zip(specs, LABELS):
        assert s.family == name and s.piece_type == b.piece_type and s.karat == b.karat
        assert s.name.endswith(f"({lab})"), s.name
    w = [geometry.gold_volume(s, 1.0) for s in specs]
    for a, c in zip(w, w[1:]):
        assert c >= SPREAD * a, f"{name}: variant volumes {w}"


@pytest.mark.parametrize("name", [n for n in NAMES if FAMILIES[n].piece_type == "earring"])
def test_earring_is_built_and_weighed_as_a_mirrored_pair(name, geometry, mesh_check):
    geometry.clear_scene()
    one = geometry.build(_spec(name, pair=False), 1.0)
    v_one = one.volume_mm3
    assert one.mirror == [] and "pieces" not in one.dims
    geometry.clear_scene()
    two = geometry.build(_spec(name, pair=True), 1.0)
    assert two.volume_mm3 == pytest.approx(2 * v_one, rel=1e-6)
    assert two.dims["pieces"] == 2 and len(two.mirror) == 1 + len(two.gems)
    copy = two.mirror[0]
    rep = mesh_check.check(copy)
    assert rep.ok, rep.problems()                     # mirrored winding fixed: normals outward
    assert rep.signed_volume == pytest.approx(geometry.mesh_volume(two.gold), rel=1e-6)
    xmax = max(v.co.x for v in two.gold.data.vertices)
    assert min(v.co.x for v in copy.data.vertices) > xmax   # the two earrings don't touch
    geometry.clear_scene()


# ------------------------------------------------------------ dispatch
def test_build_dispatches_to_the_family_builder(geometry):
    geometry.clear_scene()
    b = geometry.build(_spec("test_toy_chain", length_in=24), 1.0)
    assert b.dims == {"length_in": 24}
    geometry.clear_scene()


def test_build_refuses_a_family_of_another_piece_type(geometry):
    spec = DesignSpec(name="x", piece_type="ring", family="test_toy_earring")
    with pytest.raises(ValueError, match="builds a earring"):
        geometry.build(spec, 1.0)


def test_spec_without_family_still_uses_the_original_builders(geometry):
    geometry.clear_scene()
    b = geometry.build(DesignSpec(name="band", piece_type="ring"), 1.0)
    assert b.mirror == [] and b.dims["inner_d_mm"] == 17.3
    geometry.clear_scene()


def test_chain_variants_keep_the_customers_length():
    b = Brief(piece_type="chain", karat=22, family="test_toy_chain", length_in=22)
    assert {s.length_in for s in designer.propose(b, 0.0, 3)} == {22}
