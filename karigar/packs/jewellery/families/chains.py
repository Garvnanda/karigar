"""Chain families: C1 rope, C2 curb (link-by-link, weight scales with length_in).

A chain is built link by link: one link's centreline is computed once, every link is a
rigid copy placed along the necklace path, and all parts are swept as numpy tubes into
ONE mesh object (no booleans; links are separate closed solids that interlock). The
necklace lies as an open circle of circumference length_in with the clasp at the top:
end A carries a jump ring + lobster clasp, end B a larger tag ring the lobster catches.

- rope: oval links whose planes contain the chain axis, each turned ALPHA about the
  axis and advanced one pitch; every link threads through the next two, which reads as
  a twisted rope. Proportions were searched numerically so that no two links come
  closer than CLEAR x their wire diameter (tests/test_families_bangles_chains.py).
- curb: oval links twisted about their long axis (ends turned +-TAU0), so the chain lies
  flat; wire flattened (diamond-cut look).

`layout(spec, s)` is pure numpy (no Blender) so tests can check interlock (Gauss linking
number) and clearance on the exact centrelines the builder sweeps.
Build frame: path in XY, then turned like geometry.ROT_UPRIGHT (faces -Y, clasp on top).
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from . import register

MIN_WIRE = 0.5            # mm, thinnest link wire we make
CLEAR = 1.15              # centreline gap >= CLEAR * (r_i + r_j) between parts, by design
TAU = 2 * math.pi

# rope link, in units of the pitch p (searched: maximise wire / chain diameter)
ROPE_A, ROPE_B, ROPE_R, ROPE_ALPHA = 1.3, 0.6, 0.4 / 2 / CLEAR, math.radians(50)
ROPE_D = 2 * (ROPE_B + ROPE_R)          # chain diameter / p
# curb link, in units of the pitch p
CURB_A, CURB_B, CURB_R, CURB_TAU0, CURB_FLAT = 0.8, 0.5, 0.4 / 2 / CLEAR, math.radians(55), 0.72
CURB_W = 2 * (CURB_B + CURB_R)          # chain width / p


@dataclass
class Part:
    """One closed tube: centreline C (m, 3), section axes N, B (m, 3), radii rn, rb."""
    kind: str
    C: object
    N: object
    B: object
    rn: object
    rb: object
    expo: float = 2.0

    @property
    def r_max(self) -> float:
        import numpy as np
        return float(np.max(np.maximum(self.rn, self.rb)))


def _np():
    import numpy as np
    return np


def _rot_x(ang):
    """Rotation matrices about local x for an array of angles: (n, 3, 3)."""
    np = _np()
    ang = np.asarray(ang, float)
    c, s = np.cos(ang), np.sin(ang)
    M = np.zeros(ang.shape + (3, 3))
    M[..., 0, 0] = 1
    M[..., 1, 1], M[..., 1, 2], M[..., 2, 1], M[..., 2, 2] = c, -s, s, c
    return M


def _ellipse(a, b, m, r, rb=None):
    """Oval centreline in the local x-y plane (x along the chain), outward normals."""
    np = _np()
    t = TAU * np.arange(m) / m
    C = np.stack([a * np.cos(t), b * np.sin(t), np.zeros(m)], 1)
    N = np.stack([np.cos(t) / a, np.sin(t) / b, np.zeros(m)], 1)
    N /= np.linalg.norm(N, axis=1, keepdims=True)
    B = np.tile([0.0, 0.0, 1.0], (m, 1))
    return C, N, B, np.full(m, r), np.full(m, r if rb is None else rb)


def _ring(R, r, m, about_x):
    """Round ring of centreline radius R in the local x-y plane turned about x."""
    C, N, B, rn, rb = _ellipse(R, R, m, r)
    M = _rot_x(about_x)
    return C @ M.T, N @ M.T, B @ M.T, rn, rb


def _lobster(Ll, Hl, r_eye, r_body, m):
    """Lobster-clasp loop in the local x-y plane: narrow round eye at x = 0, egg-shaped
    body to x = Ll, tube thickening towards the body, a small trigger bump on one side."""
    np = _np()
    t = TAU * np.arange(m) / m
    g = (1 - np.cos(t)) / 2                          # 0 at the eye, 1 at the far end
    C = np.stack([Ll * g, Hl / 2 * np.sin(t) * (0.75 + 0.25 * g), np.zeros(m)], 1)
    T = np.roll(C, -1, 0) - np.roll(C, 1, 0)             # periodic central difference
    T /= np.linalg.norm(T, axis=1, keepdims=True)
    B = np.tile([0.0, 0.0, 1.0], (m, 1))
    N = np.cross(T, B)
    if np.mean(np.einsum("ij,ij->i", N, C - C.mean(0))) < 0:
        N = -N
    rn = r_eye + (r_body - r_eye) * g ** 1.2
    bump = np.exp(-((t - 0.62 * math.pi) / 0.18) ** 2) * 0.35 * r_body   # trigger
    return C, N, B, rn + bump, (rn + bump) * 0.8


def _place(C, N, B, R, o):
    """Rigid placement: local -> world with rotation R (3x3) and origin o."""
    return C @ R.T + o, N @ R.T, B @ R.T


def chain_dims(spec, s):
    """(pitch, wire radius, chain width) in mm at scale s."""
    D = spec.link_w_mm * s
    if spec.family == "chain_rope":
        p = D / ROPE_D
        return p, ROPE_R * p, D
    p = D / CURB_W
    return p, CURB_R * p, D


def _rope_link(i, p, m):
    """Rope link i in the chain-axis frame (axis = local x)."""
    np = _np()
    C, N, B, rn, rb = _ellipse(ROPE_A * p, ROPE_B * p, m, ROPE_R * p)
    M = _rot_x(i * ROPE_ALPHA)
    return C @ M.T, N @ M.T, B @ M.T, rn, rb


def _curb_link(p, m):
    """Curb link in the chain-axis frame: oval twisted +-TAU0 at its two ends."""
    np = _np()
    A = CURB_A * p
    C, N, B, rn, rb = _ellipse(A, CURB_B * p, m, CURB_R * p, CURB_R * p * CURB_FLAT)
    M = _rot_x(CURB_TAU0 * C[:, 0] / A)
    tw = lambda X: np.einsum("nij,nj->ni", M, X)
    return tw(C), tw(N), tw(B), rn, rb


def layout(spec, s, m_link: int = 0) -> list[Part]:
    """Every part of the chain (links, jump ring, lobster, tag ring) in the worn frame."""
    np = _np()
    rope = spec.family == "chain_rope"
    p, r, D = chain_dims(spec, s)
    m_link = m_link or (24 if rope else 28)
    L = spec.length_in * 25.4
    Rp = L / TAU
    half = (ROPE_A if rope else CURB_A) * p             # link centre -> end-loop tip (centreline)
    gap = lambda r1, r2: CLEAR * (r1 + r2) + 0.03 * p   # centreline offset where two parts thread
    # clasp parts, in the end link's chain-axis frame
    Rj, rj = 0.55 * D, r                                # jump ring
    Rt, rt = 0.9 * D, r                                 # tag ring
    Ll, Hl = 3.0 * D, 1.5 * D                           # lobster
    re_, rbody = max(r, 0.12 * D), max(1.3 * r, 0.3 * D)
    # end-loop orientation (angle about the chain axis of the plane the next part threads)
    clasp_len = (half - gap(r, rj) + 2 * Rj) + (Ll - gap(rj, re_)) \
        + (half - gap(r, rt) + 2 * Rt) + 0.6 * D
    n = max(8, int((L - clasp_len) / p))
    span = (n - 1) * p
    s_mid = Rp * math.pi / 2                             # clasp centred at the top
    s0 = s_mid + (L - span) / 2                          # first link, going round
    parts: list[Part] = []

    def frame(sa):
        ph = sa / Rp
        T = np.array([-math.sin(ph), math.cos(ph), 0.0])
        Nr = np.array([math.cos(ph), math.sin(ph), 0.0])
        return np.stack([T, Nr, [0.0, 0.0, 1.0]], 1), Rp * Nr     # columns: local x, y, z

    curb = None if rope else _curb_link(p, m_link)
    for i in range(n):
        R, o = frame(s0 + i * p)
        C, N, B, rn, rb = _rope_link(i, p, m_link) if rope else curb
        parts.append(Part("link", *_place(C, N, B, R, o), rn, rb, 2.0 if rope else 3.0))

    def end_angle(i, sign):
        return i * ROPE_ALPHA if rope else sign * CURB_TAU0

    # end A (after the last link): jump ring then lobster, along +local x
    R, o = frame(s0 + (n - 1) * p)
    a_end = end_angle(n - 1, +1)
    cj = half - gap(r, rj) + Rj
    C, N, B, rn, rb = _ring(Rj, rj, 40, a_end + math.pi / 2)
    C = C + [cj, 0, 0]
    parts.append(Part("jump_ring", *_place(C, N, B, R, o), rn, rb))
    C, N, B, rn, rb = _lobster(Ll, Hl, re_, rbody, 72)
    M = _rot_x(a_end)
    C, N, B = C @ M.T, N @ M.T, B @ M.T
    C = C + [cj + Rj - gap(rj, re_), 0, 0]
    parts.append(Part("lobster", *_place(C, N, B, R, o), rn, rb))
    # end B (before the first link): tag ring along -local x
    R, o = frame(s0)
    b_end = end_angle(0, -1)
    C, N, B, rn, rb = _ring(Rt, rt, 48, b_end + math.pi / 2)
    C = C - [half - gap(r, rt) + Rt, 0, 0]
    parts.append(Part("tag_ring", *_place(C, N, B, R, o), rn, rb))
    up = lambda X: np.stack([X[:, 0], -X[:, 2], X[:, 1]], 1)
    return [Part(q.kind, up(q.C), up(q.N), up(q.B), q.rn, q.rb, q.expo) for q in parts]


def build_chain(spec, s):
    from .. import geometry as g
    from ._bc_mesh import Soup, sweep, to_object
    parts = layout(spec, s)
    soup = Soup()
    for q in parts:
        k = 8 if q.kind == "link" else 12
        soup.add(*sweep(q.C, q.N, q.B, q.rn, q.rb, k, q.expo))
    gold = to_object(*soup.arrays(), "gold")
    p, r, D = chain_dims(spec, s)
    links = sum(q.kind == "link" for q in parts)
    dims = {"length_in": spec.length_in, "link_w_mm": round(D, 2), "wire_mm": round(2 * r, 2),
            "links": links, "clasp": "lobster + jump rings"}
    return g.Built(gold, [], g.mesh_volume(gold), dims)


def _wire_1(spec) -> float:
    """Thinnest wire dimension at scale 1.0 (curb: the flattened thickness)."""
    p, r, D = chain_dims(spec, 1.0)
    return 2 * r * (1.0 if spec.family == "chain_rope" else CURB_FLAT)


def _bounds(spec):
    lo = max(MIN_WIRE / _wire_1(spec), 0.8 / spec.link_w_mm)
    hi = min(12.0 / spec.link_w_mm, 2.0)
    return lo, hi


def _checks(spec, s):
    p, r, D = chain_dims(spec, s)
    n = sum(q.kind == "link" for q in layout(spec, s, 8))
    return [f"{n} links, wire {_wire_1(spec) * s:.2f} mm ≥ {MIN_WIRE} mm",
            f"links interlock with a designed clearance ≥ {(CLEAR - 1) * 2 * r:.3f} mm (no fused links)",
            "lobster clasp + jump ring at one end, tag ring at the other",
            f"length {spec.length_in} in including the clasp"]


register(
    "chain_rope", "chain", build_chain,
    {"length_in": 18, "link_w_mm": 3.0},
    {"link_w_mm": (0.8, 1.0, 1.3)},
    scale_bounds=_bounds, checks=_checks, title="Rope Chain")

register(
    "chain_curb", "chain", build_chain,
    {"length_in": 18, "link_w_mm": 3.5},
    {"link_w_mm": (0.8, 1.0, 1.3)},
    scale_bounds=_bounds, checks=_checks, title="Curb Chain")
