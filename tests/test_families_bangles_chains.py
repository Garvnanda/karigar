"""Family-specific checks for the bangle (B1-B3) and chain (C1-C2) catalogue families.

The generic checks (clean solid at 3 scales, volume rises with scale, 3 variants 15% apart)
live in tests/test_families.py; these cover what is particular to each design:
bangles keep the wrist hole exactly at inner_d and carry their motif; chains are built
link by link with real interlocks (Gauss linking number) and no two parts touching,
weight scales with length, and a full chain builds well under 20 s.
"""
import math
import time

import numpy as np
import pytest

from karigar.packs.jewellery import designer, pricing
from karigar.packs.jewellery.families import FAMILIES, bangles, chains
from karigar.packs.jewellery.schema import Brief, DesignSpec

BANGLES = ("bangle_temple_kada", "bangle_twisted_rope", "bangle_leaf_vine")
CHAINS = ("chain_rope", "chain_curb")


def _spec(name, **kw) -> DesignSpec:
    fam = FAMILIES[name]
    return DesignSpec(**{"name": fam.title, "piece_type": fam.piece_type, "family": name,
                         **fam.default_spec, **kw})


@pytest.fixture(scope="module")
def geometry():
    from karigar.packs.jewellery import geometry
    return geometry


@pytest.fixture(scope="module")
def mesh_check():
    from karigar.packs.jewellery import mesh_check
    return mesh_check


def _verts(ob) -> np.ndarray:
    a = np.empty(len(ob.data.vertices) * 3)
    ob.data.vertices.foreach_get("co", a)
    return a.reshape(-1, 3)


def test_all_five_families_are_registered_with_their_piece_type():
    for n in BANGLES:
        assert FAMILIES[n].piece_type == "bangle"
    for n in CHAINS:
        assert FAMILIES[n].piece_type == "chain"
        assert FAMILIES[n].scale_bounds is not None


# ------------------------------------------------------------------ bangles
@pytest.mark.parametrize("name", BANGLES)
@pytest.mark.parametrize("inner_d", (55.0, 60.3, 66.7))
def test_bangle_wrist_hole_is_exactly_inner_d(name, inner_d, geometry):
    """Nothing intrudes into the wrist hole; the hole is not bigger than asked either.
    Worn frame: axis along Y, so the distance from the axis is hypot(x, z)."""
    geometry.clear_scene()
    b = geometry.build(_spec(name, inner_d_mm=inner_d), 1.0)
    V = _verts(b.gold)
    r = np.hypot(V[:, 0], V[:, 2])
    assert r.min() == pytest.approx(inner_d / 2, abs=0.01)
    assert b.dims["inner_d_mm"] == inner_d
    geometry.clear_scene()


@pytest.mark.parametrize("name", BANGLES)
def test_bangle_stands_upright_with_its_axis_on_y(name, geometry):
    geometry.clear_scene()
    b = geometry.build(_spec(name), 1.0)
    V = _verts(b.gold)
    span = V.max(0) - V.min(0)
    assert span[1] < 0.2 * span[0] and span[1] < 0.2 * span[2]
    assert span[1] == pytest.approx(b.dims["width_mm"], rel=0.25)
    geometry.clear_scene()


@pytest.mark.parametrize("name", BANGLES)
def test_bangle_with_a_stone_sets_one_stone_at_the_top_and_stays_clean(name, geometry, mesh_check):
    geometry.clear_scene()
    plain = geometry.build(_spec(name), 1.0)
    assert plain.gems == []
    v_plain = plain.volume_mm3
    geometry.clear_scene()
    b = geometry.build(_spec(name, gem="ruby", gem_d_mm=4.0), 1.0)
    assert len(b.gems) == 1
    assert mesh_check.check(b.gold).ok
    G = _verts(b.gems[0])
    top = _verts(b.gold)[:, 2].max()
    assert abs(G[:, 0].mean()) < 0.05 and abs(G[:, 1].mean()) < 0.05      # front centre
    assert G[:, 2].max() > top - 0.5                                         # sits on the top
    assert b.volume_mm3 != pytest.approx(v_plain, rel=1e-6)                  # a real bezel seat
    geometry.clear_scene()


def test_kada_has_relief_panels_alternating_lotus_and_mango():
    sp = _spec("bangle_temple_kada")
    L = bangles.kada_layout(sp, 1.0)
    assert L["panels"] == 24 and L["panels"] % 2 == 0
    h = bangles.kada_height(sp, 1.0)
    S0 = L["R_o"] * math.pi / 2
    xs = np.linspace(-L["Rm"], L["Rm"], 41)
    X, Z = np.meshgrid(xs, xs)
    lotus = h(S0 + X, Z)
    mango = h(S0 + L["Lp"] + X, Z)
    lotus2 = h(S0 + 2 * L["Lp"] + X, Z)
    assert lotus.max() > 0.5 * L["t"] and mango.max() > 0.4 * L["t"]          # real relief
    assert np.abs(lotus - mango).max() > 0.2 * L["t"]                         # two motifs
    assert np.allclose(lotus, lotus2, atol=1e-6)                              # alternating
    assert np.allclose(lotus, lotus[::-1, :], atol=1e-6)                      # lotus is symmetric
    assert not np.allclose(mango, mango[:, ::-1], atol=1e-3)                  # buta is not
    # beaded borders: a row of bumps near each edge
    s = np.linspace(0, L["Lp"], 400)
    row = h(S0 + s, np.full_like(s, L["Zb"]))
    assert ((row[1:-1] > row[:-2]) & (row[1:-1] > row[2:])).sum() >= 3


def test_kada_relief_never_touches_the_inner_half():
    sp = _spec("bangle_temple_kada")
    L = bangles.kada_layout(sp, 1.0)
    x, z, w = bangles.band_profile(L["t"] / 2, L["w"] / 2, 4.0, 2.6, 72, 16)
    assert (w[x < 0] == 0).all()                          # relief weight 0 on the inner half
    zo = z[: 73]
    assert (np.diff(zo) > 0).all()                        # outer half is a graph x(z): cannot fold


def test_plain_kada_order_designs_the_temple_kada():
    b = Brief(piece_type="bangle", karat=22, family="bangle_temple_kada", target_weight_g=25)
    specs = designer.propose(b, pricing.requested_ct(b), 3)
    assert {s.family for s in specs} == {"bangle_temple_kada"}
    assert all(s.inner_d_mm == b.bangle_inner_d_mm for s in specs)


@pytest.mark.parametrize("n", (2, 3))
def test_rope_section_has_one_lobe_per_strand_and_twists(n):
    th = np.linspace(0, 2 * math.pi, 720, endpoint=False)
    r = bangles.rope_section(th, 0.0, n, 40)
    peaks = ((r > np.roll(r, 1)) & (r > np.roll(r, -1))).sum()
    assert peaks == n
    assert r.max() == pytest.approx(1.0, abs=1e-3) and 0.45 < r.min() < 0.95          # grooves between strands
    turned = bangles.rope_section(th, math.pi / 80, n, 40)     # lobes turn K*phi/n = pi/(2n)
    assert np.argmax(turned) != np.argmax(r)
    assert np.allclose(bangles.rope_section(th, 2 * math.pi, n, 40), r)  # closes up round the wrist


def test_rope_strands_param_picks_two_or_three_strands(geometry):
    assert bangles.rope_layout(_spec("bangle_twisted_rope"), 1.0)["n"] == 3
    sp2 = _spec("bangle_twisted_rope", params={"strands": 2, "lay": 3.2})
    assert bangles.rope_layout(sp2, 1.0)["n"] == 2
    geometry.clear_scene()
    assert geometry.build(sp2, 1.0).dims["strands"] == 2
    geometry.clear_scene()


def test_leaf_vine_leaves_alternate_and_stay_on_the_face():
    sp = _spec("bangle_leaf_vine")
    V = bangles.vine_layout(sp, 1.0)
    assert V["nl"] % 2 == 0 and V["nl"] >= 24
    h = bangles.vine_height(sp, 1.0)
    S0 = V["R_o"] * math.pi / 2
    zs = np.linspace(-V["b"], V["b"], 201)
    # half way along leaf 0 (one side) and leaf 1 (the other side), relief sits on opposite halves
    u = V["L"] * 0.5
    for j, sign in ((0, 1), (1, -1)):
        S = S0 + j * V["sp"] + u * math.cos(V["ang"])
        col = h(np.full_like(zs, S), zs)
        z_peak = zs[np.argmax(col)]
        assert sign * z_peak > 0.25 * V["b"], (j, z_peak)
    # midrib: along the leaf axis the relief is higher than just beside it
    ga = V["ang"]
    base = np.array([S0, V["As"]])
    ax = np.array([math.cos(ga), math.sin(ga)])
    nv = np.array([-math.sin(ga), math.cos(ga)])
    on = base + 0.5 * V["L"] * ax
    off = on + 0.09 * V["w"] * nv
    assert h(np.array([on[0]]), np.array([on[1]]))[0] > h(np.array([off[0]]), np.array([off[1]]))[0]
    # nothing in the outer 5% of the face edge
    S = S0 + np.linspace(0, 4 * V["sp"], 800)
    for z in (0.97 * V["b"], -0.97 * V["b"]):
        assert h(S, np.full_like(S, z)).max() == 0.0


# ------------------------------------------------------------------ chains
def _linking(P, Q) -> float:
    """Gauss linking number of two closed polylines (+-1 = interlocked, 0 = free)."""
    dP = np.roll(P, -1, 0) - P
    dQ = np.roll(Q, -1, 0) - Q
    r = (P + dP / 2)[:, None] - (Q + dQ / 2)[None]
    c = np.cross(dP[:, None], dQ[None])
    return float((np.einsum("ijk,ijk->ij", r, c) / np.linalg.norm(r, axis=-1) ** 3).sum() / (4 * math.pi))


def _gap_ratio(P, Q) -> float:
    """min over point pairs of centreline distance / (sum of the local tube radii)."""
    rp, rq = np.maximum(P.rn, P.rb), np.maximum(Q.rn, Q.rb)
    d = np.sqrt(((P.C[:, None] - Q.C[None]) ** 2).sum(-1))
    return float((d / (rp[:, None] + rq[None])).min())


@pytest.mark.parametrize("name", CHAINS)
@pytest.mark.parametrize("length", (16, 24))
@pytest.mark.parametrize("s", (0.85, 1.15))
def test_chain_links_interlock_and_never_touch(name, length, s):
    parts = chains.layout(_spec(name, length_in=length), s, 72)
    links = [q for q in parts if q.kind == "link"]
    kinds = [q.kind for q in parts[len(links):]]
    assert kinds == ["jump_ring", "lobster", "tag_ring"]
    jump, lob, tag = parts[len(links):]
    threads = 2 if name == "chain_rope" else 1        # a rope link passes through the next two
    worst = math.inf
    for i, a in enumerate(links):
        for k in range(1, 5):
            if i + k >= len(links):
                break
            b = links[i + k]
            lk = abs(_linking(a.C, b.C))
            if k <= threads:
                assert lk == pytest.approx(1.0, abs=0.05), (i, k, lk)
            else:
                assert lk == pytest.approx(0.0, abs=0.05), (i, k, lk)
            worst = min(worst, _gap_ratio(a, b))
    assert abs(_linking(links[-1].C, jump.C)) == pytest.approx(1.0, abs=0.05)
    assert abs(_linking(jump.C, lob.C)) == pytest.approx(1.0, abs=0.05)
    assert abs(_linking(tag.C, links[0].C)) == pytest.approx(1.0, abs=0.05)
    assert abs(_linking(lob.C, tag.C)) == pytest.approx(0.0, abs=0.05)     # clasp laid open
    for a, b in ((links[-1], jump), (links[-2], jump), (jump, lob), (links[-1], lob),
                 (tag, links[0]), (tag, links[1]), (lob, tag)):
        worst = min(worst, _gap_ratio(a, b))
    assert worst >= 1.08, f"{name}: parts come within {worst:.3f} x their wire radii"


@pytest.mark.parametrize("name", CHAINS)
def test_chain_weight_scales_with_length(name, geometry):
    v = {L: geometry.gold_volume(_spec(name, length_in=L), 1.0) for L in (16, 18, 20, 22, 24)}
    assert all(v[b] > v[a] for a, b in zip(sorted(v), sorted(v)[1:]))
    assert v[24] / v[16] == pytest.approx(24 / 16, rel=0.06)


@pytest.mark.parametrize("name", CHAINS)
def test_longest_chain_builds_fast_and_clean(name, geometry, mesh_check):
    """24 in at the smallest test scale (most links): every link a closed solid, no part
    crossing another, built well under 20 s."""
    geometry.clear_scene()
    t0 = time.time()
    b = geometry.build(_spec(name, length_in=24), 0.85)
    took = time.time() - t0
    rep = mesh_check.check(b.gold)
    assert took < 20, took
    assert [p for p in rep.problems() if not p.startswith("components=")] == []
    assert rep.components == b.dims["links"] + 3            # links + jump ring, lobster, tag ring
    assert b.dims["length_in"] == 24 and b.dims["clasp"] == "lobster + jump rings"
    geometry.clear_scene()


@pytest.mark.parametrize("name", CHAINS)
def test_chain_lies_in_the_display_plane_with_the_clasp_on_top(name):
    parts = chains.layout(_spec(name), 1.0, 24)
    allc = np.concatenate([q.C for q in parts])
    span = allc.max(0) - allc.min(0)
    L = 18 * 25.4
    assert span[0] == pytest.approx(L / math.pi, rel=0.05)          # an open circle in XZ
    assert span[1] < 0.05 * span[0]
    clasp = np.concatenate([q.C for q in parts if q.kind != "link"])
    assert clasp[:, 2].mean() > 0.9 * allc[:, 2].max()


@pytest.mark.parametrize("name", CHAINS)
def test_chain_scale_bounds_keep_the_wire_castable(name):
    sp = _spec(name)
    lo, hi = FAMILIES[name].bounds(sp)
    assert 0 < lo < 1.0 < hi
    p, r, D = chains.chain_dims(sp, lo)
    thin = 2 * r * (1.0 if name == "chain_rope" else chains.CURB_FLAT)
    assert thin >= chains.MIN_WIRE - 1e-9
    assert D * hi / lo > D            # sanity: range is non-empty
    assert chains.chain_dims(sp, hi)[2] <= 12.0 + 1e-9


@pytest.mark.parametrize("name", BANGLES + CHAINS)
def test_job_card_checks_name_the_design_specifics(name):
    from karigar.packs.jewellery import dfm
    out = dfm.check(_spec(name), 1.0)
    assert len(out) >= 3 and all(isinstance(x, str) and x for x in out)
    if name in CHAINS:
        assert any("links" in x for x in out) and any("lobster" in x for x in out)
    else:
        assert any("inner diameter" in x for x in out)
