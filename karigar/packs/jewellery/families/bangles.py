"""Bangle families: B1 antique temple kada, B2 twisted rope bangle, B3 leaf-vine bangle.

Original parametric designs in traditional Indian styles. Each bangle is ONE swept
surface built with numpy (no booleans), so it is watertight, one piece and free of
self-intersections by construction:

- kada / leaf-vine: a comfort band profile whose OUTER half is pushed out by a relief
  height field h(S, Z) (S = arc length on the outer face, Z = across the band). The outer
  half stays a graph x(z) in every section, so no relief can fold over itself, and the
  inner (wrist) half is never touched: the inner diameter is exactly spec.inner_d_mm.
- rope: section radius r(theta) = envelope of n round strands that rotate with the angle
  around the wrist (a twisted bar of n strands), plus collars; every section is
  star-shaped about its centre. The centre circle is set so the innermost point sits
  exactly on inner_d_mm / 2.

Build frame: the wrist circle lies in XY (axis Z) and is then turned like
`geometry.ROT_UPRIGHT` (axis -> -Y, +Z up, the front motif at the top). A stone named in
the brief goes in a bezel at the front (one priced stone, as pricing assumes).
Scale bounds come from dfm.RULES["bangle"] (width / thickness, which every builder uses
as its cross-section).
"""
from __future__ import annotations

import math

from . import register

TAU = 2 * math.pi


# ------------------------------------------------------------------ shared numpy helpers
def _np():
    import numpy as np
    return np


def _wrap(d, period):
    """Signed distance folded into [-period/2, period/2)."""
    return (d + period / 2) % period - period / 2


def _dome(d2, R, H):
    """Height of a rounded boss of radius R and height H at squared distance d2."""
    np = _np()
    return H * np.sqrt(np.clip(1.0 - d2 / (R * R), 0.0, 1.0))


def _upright(V):
    """(x, y, z) -> (x, -z, y): geometry.ROT_UPRIGHT done on arrays."""
    np = _np()
    return np.stack([V[..., 0], -V[..., 2], V[..., 1]], -1)


def band_profile(a: float, b: float, n_out: float, n_in: float, ko: int, ki: int):
    """Closed band cross-section (x radial from the section centre, z across the band).
    Outer half: z = b sin v, uniform v (dense at the edges, even across the face), so
    z rises monotonically and the outer half is a graph x(z). Returns x, z, w where w
    (0..1) is how much relief a point may take: 1 on the outer face, 0 on the inner half
    and at the two edge points."""
    np = _np()
    v = -math.pi / 2 + math.pi * np.arange(ko + 1) / ko
    zo = b * np.sin(v)
    xo = a * (1 - np.abs(np.sin(v)) ** n_out) ** (1 / n_out)
    vi = math.pi / 2 + math.pi * np.arange(1, ki) / ki
    zi = b * np.sin(vi)
    xi = -a * (1 - np.abs(np.sin(vi)) ** n_in) ** (1 / n_in)
    wo = np.clip((b - np.abs(zo)) / (0.04 * b), 0.0, 1.0)
    return (np.concatenate([xo, xi]), np.concatenate([zo, zi]),
            np.concatenate([wo, np.zeros(ki - 1)]))


def relief_band(inner_d: float, width: float, thick: float, height_fn, m: int, ko: int,
                ki: int = 16, n_out: float = 4.0, n_in: float = 2.6):
    """Bangle with a relief outer face: (V, F) arrays in the worn frame.
    height_fn(S, Z) -> mm of relief (>= 0) on the outer face; S = arc length at the outer
    radius from phi = 0, Z across the band."""
    np = _np()
    from ._bc_mesh import grid_faces, orient
    a, b = thick / 2, width / 2
    r_in = inner_d / 2
    R_o = r_in + thick
    x, z, w = band_profile(a, b, n_out, n_in, ko, ki)
    phi = TAU * np.arange(m) / m
    S = np.broadcast_to((phi * R_o)[:, None], (m, len(z)))
    Z = np.broadcast_to(z[None, :], (m, len(z)))
    H = np.maximum(height_fn(S, Z), 0.0)
    X = r_in + a + x[None, :] + H * w[None, :]
    V = np.stack([X * np.cos(phi)[:, None], X * np.sin(phi)[:, None], Z], -1).reshape(-1, 3)
    return orient(_upright(V), grid_faces(m, len(z)))


def _gem_at_top(gem_d: float, z_girdle: float):
    """The priced stone, crown up, girdle at height z_girdle on the bangle's top (worn frame)."""
    from mathutils import Matrix
    from .. import geometry as g
    st, _, _ = g.gem(gem_d, "stone")
    st.data.transform(Matrix.Translation((0, 0, z_girdle)))
    return st


def _stone_d(spec) -> float:
    return spec.gem_d_mm if spec.gem != "none" and spec.gem_d_mm > 0 else 0.0


def _finish(V, F, gems, dims):
    from .. import geometry as g
    from ._bc_mesh import to_object
    gold = to_object(V, F, "gold")
    return g.Built(gold, gems, g.mesh_volume(gold), dims)


def _band_checks(extra):
    def checks(spec, s):
        from ..dfm import RULES
        r = RULES["bangle"]
        out = [f"thickness {spec.thickness_mm * s:.2f} mm ≥ {r['min_thickness']} mm",
               f"width {spec.width_mm * s:.2f} mm ≥ {r['min_width']} mm",
               f"inner diameter {spec.inner_d_mm:.1f} mm kept clear (relief on the outer face only)"]
        return out + list(extra(spec, s))
    return checks


def _seat(rho, Rs: float, rt: float, top: float):
    """Bezel for the front stone: a rounded collar ring at radius Rs + rt and a flat
    platform inside it rt * 0.6 below the collar top. (heights, inside-mask)."""
    np = _np()
    ring = _dome((rho - (Rs + rt)) ** 2, rt, top)
    inside = rho < Rs + rt
    return np.where(inside, np.maximum(ring, top - 0.6 * rt), ring), inside


# ------------------------------------------------------------------ B1 temple kada
def _petals(X, Y, n, r0, r1, half_w, top, offset=0.0):
    """n pointed petals radiating from the medallion centre between radii r0 and r1."""
    np = _np()
    out = np.zeros_like(X)
    rm, L = (r0 + r1) / 2, (r1 - r0) / 2
    for k in range(n):
        ang = TAU * (k + offset) / n
        c, s = math.cos(ang), math.sin(ang)
        al, ac = X * c + Y * s, -X * s + Y * c
        u = (al - rm) / L
        taper = 1 - 0.5 * np.clip(u, 0, 1)
        q = u * u + (ac / (half_w * taper)) ** 2
        out = np.maximum(out, top * np.sqrt(np.clip(1 - q, 0, 1)))
    return out


def _medallion_frame(X, Y, Rm, H0):
    """Raised round plate with a ring of 16 rim beads (shared by both medallions)."""
    np = _np()
    rho = np.hypot(X, Y)
    plate = H0 * np.clip((0.88 * Rm - rho) / (0.05 * Rm), 0, 1)
    nr, rr, pr = 16, 0.1 * Rm, 0.9 * Rm
    psi = np.round(np.arctan2(Y, X) / (TAU / nr)) * (TAU / nr)
    d2 = (X - pr * np.cos(psi)) ** 2 + (Y - pr * np.sin(psi)) ** 2
    return np.maximum(plate, _dome(d2, rr, H0 + 0.9 * rr)), rho


def lotus_medallion(X, Y, Rm, t, seat_d=0.0):
    """Two rings of eight petals around a centre bud (or the stone's bezel)."""
    np = _np()
    H0 = 0.15 * t
    h, rho = _medallion_frame(X, Y, Rm, H0)
    hw = 0.49 * Rm * math.tan(math.pi / 8) * 0.95
    h = np.maximum(h, _petals(X, Y, 8, 0.2 * Rm, 0.8 * Rm, hw, H0 + 0.3 * t))
    h = np.maximum(h, _petals(X, Y, 8, 0.12 * Rm, 0.56 * Rm, hw * 0.75, H0 + 0.42 * t, 0.5))
    if seat_d > 0:
        seat, inside = _seat(rho, seat_d / 2, max(0.3, 0.06 * Rm), H0 + 0.5 * t)
        h = np.where(inside, seat, np.maximum(h, seat))
    else:
        h = np.maximum(h, _dome(X * X + Y * Y, 0.2 * Rm, H0 + 0.55 * t))
    return np.where(rho < Rm, h, 0.0)


# buta (mango) outline in units of the medallion radius: round body + tapering curled tip
BUTA_BODY = ((0.0, -0.18), 0.5)
BUTA_TAIL = ((-0.32, 0.05, 0.30), (-0.36, 0.30, 0.24), (-0.22, 0.52, 0.18),
             (0.02, 0.62, 0.13), (0.22, 0.56, 0.09), (0.30, 0.42, 0.06))


def mango_medallion(X, Y, Rm, t):
    """Buta (keri): domed round body, tapering tail curling over it, a seed bead inside."""
    np = _np()
    H0 = 0.15 * t
    h, rho = _medallion_frame(X, Y, Rm, H0)
    x, y = X / Rm, Y / Rm
    (cx, cy), r0 = BUTA_BODY
    top = H0 + 0.32 * t
    h = np.maximum(h, _dome((x - cx) ** 2 + (y - cy) ** 2, r0, top))
    for (x0, y0, ra), (x1, y1, rb) in zip(BUTA_TAIL, BUTA_TAIL[1:]):
        dx, dy = x1 - x0, y1 - y0
        tt = np.clip(((x - x0) * dx + (y - y0) * dy) / (dx * dx + dy * dy), 0, 1)
        d2 = (x - x0 - tt * dx) ** 2 + (y - y0 - tt * dy) ** 2
        r = ra + (rb - ra) * tt
        h = np.maximum(h, top * (r / r0) ** 0.25 * np.sqrt(np.clip(1 - d2 / (r * r), 0, 1)))
    h = np.maximum(h, _dome((x - 0.02) ** 2 + (y + 0.2) ** 2, 0.17, H0 + 0.48 * t))
    return np.where(rho < Rm, h, 0.0)


def kada_layout(spec, s):
    """Numbers of the kada relief at scale s (shared by the builder, dims and checks)."""
    w, t = spec.width_mm * s, spec.thickness_mm * s
    R_o = spec.inner_d_mm / 2 + t
    C = TAU * R_o
    panels = max(8, 2 * round(spec.params.get("panels", 24) / 2))     # even: lotus / mango
    Lp = C / panels
    rb = 0.07 * w
    Zb = w / 2 - 1.15 * rb
    nb = max(24, round(C / (2.3 * rb)))
    Rm = min(Zb - rb - 0.04 * w, 0.4 * Lp)
    return dict(w=w, t=t, R_o=R_o, C=C, panels=panels, Lp=Lp, rb=rb, Zb=Zb, nb=nb, Rm=Rm)


def kada_height(spec, s):
    np = _np()
    L = kada_layout(spec, s)
    C, Lp, rb, Zb, Rm, t = L["C"], L["Lp"], L["rb"], L["Zb"], L["Rm"], L["t"]
    S0 = L["R_o"] * math.pi / 2                     # the front (top when worn)
    seat_d = _stone_d(spec)

    def h(S, Z):
        H = np.zeros_like(S)
        sb = C / L["nb"]
        dS = _wrap(S - S0, sb)
        for zc in (Zb, -Zb):                          # beaded borders
            H = np.maximum(H, _dome(dS ** 2 + (Z - zc) ** 2, rb, 0.85 * rb))
        Xs = _wrap(S - S0 - Lp / 2, Lp)               # bead columns between the panels
        for zc in (-0.55 * Rm, 0.0, 0.55 * Rm):
            H = np.maximum(H, _dome(Xs ** 2 + (Z - zc) ** 2, 0.5 * rb, 0.42 * rb))
        q = S - S0 + Lp / 2
        idx = np.floor(q / Lp).astype(int) % L["panels"]
        X = q % Lp - Lp / 2
        med = np.where(idx % 2 == 0, lotus_medallion(X, Z, Rm, t), mango_medallion(X, Z, Rm, t))
        if seat_d > 0:
            med = np.where(idx == 0, lotus_medallion(X, Z, Rm, t, seat_d), med)
        return np.maximum(H, med)
    return h


def build_temple_kada(spec, s):
    """Broad kada: flat outer face with beaded borders, alternating lotus and mango (buta)
    medallions on raised beaded plates, bead columns between the panels; comfort inside."""
    L = kada_layout(spec, s)
    V, F = relief_band(spec.inner_d_mm, L["w"], L["t"], kada_height(spec, s), m=2400, ko=72,
                       n_out=4.0)
    gems = []
    gd = _stone_d(spec)
    if gd > 0:
        gems.append(_gem_at_top(gd, L["R_o"] + 0.15 * L["t"] + 0.5 * L["t"] - 0.1))
    dims = {"width_mm": round(L["w"], 2), "thickness_mm": round(L["t"], 2),
            "inner_d_mm": spec.inner_d_mm, "panels": L["panels"], "border_beads": 2 * L["nb"]}
    return _finish(V, F, gems, dims)


register(
    "bangle_temple_kada", "bangle", build_temple_kada,
    {"inner_d_mm": 60.3, "width_mm": 6.0, "thickness_mm": 1.7, "profile": "comfort",
     "params": {"panels": 24}},
    {"width_mm": (0.8, 1.0, 1.2), "thickness_mm": (0.85, 1.0, 1.15)},
    checks=_band_checks(lambda sp, s: [
        f"{kada_layout(sp, s)['panels']} relief panels (lotus / mango), relief "
        f"{0.15 * sp.thickness_mm * s:.2f}-{0.7 * sp.thickness_mm * s:.2f} mm on the outer face",
        "comfort-fit inner edge"]),
    title="Temple Kada")


# ------------------------------------------------------------------ B2 twisted rope
def rope_section(theta, phi, n: int, K: int, q: float = 0.6):
    """Section radius (max 1) of n round strands of radius 1/(1+q) whose centres sit
    q/(1+q) from the axis and turn by K * phi / n around the wrist."""
    np = _np()
    rs = 1 / (1 + q)
    d = q * rs
    env = None
    for i in range(n):
        rel = theta - (TAU * i / n + K * phi / n)
        r = d * np.cos(rel) + np.sqrt(rs * rs - (d * np.sin(rel)) ** 2)
        env = r if env is None else np.maximum(env, r)
    return env


def rope_layout(spec, s):
    w, t = spec.width_mm * s, spec.thickness_mm * s
    n = 3 if spec.params.get("strands", 3) >= 2.5 else 2
    lay = spec.params.get("lay", 3.2) * (w + t) / 2       # mm per full turn of a strand
    C = TAU * (spec.inner_d_mm / 2 + t / 2)
    K = max(1, round(n * C / lay))
    return dict(w=w, t=t, n=n, K=K, collar_l=0.55 * (w + t) / 2)


def rope_radius(spec, s, theta, phi, R_c):
    """Section radius r(theta, phi) of the rope with its two collars (and the stone cup)."""
    np = _np()
    L = rope_layout(spec, s)
    r = rope_section(theta, phi, L["n"], L["K"])
    l = L["collar_l"]
    a = L["t"] / 2
    gd = _stone_d(spec)
    for pc in (math.pi / 2, 3 * math.pi / 2):          # front and back collars
        ds = np.abs(_wrap(phi - pc, TAU) * R_c)
        base = np.where(ds < l, 1.0 + 0.07 * np.sqrt(np.clip(1 - (ds / l) ** 6, 0, 1)), 0.0)
        ridge = sum(np.where(np.abs(ds - e) < 0.18 * l,
                             1.0 + 0.15 * np.sqrt(np.clip(1 - ((ds - e) / (0.18 * l)) ** 2, 0, 1)), 0.0)
                    for e in (0.72 * l,))
        r = np.maximum(r, np.maximum(base, ridge))
        if gd > 0 and pc == math.pi / 2:
            Rc = gd / 2 + 0.45
            rho = np.hypot(_wrap(phi - pc, TAU) * R_c, (L["w"] / 2) * np.sin(theta))
            cup = np.where((np.cos(theta) > 0) & (rho < Rc),
                           1.15 + 0.5 / a * np.sqrt(np.clip(1 - (rho / Rc) ** 4, 0, 1)), 0.0)
            r = np.maximum(r, cup)
    return r


def build_twisted_rope(spec, s):
    """Two or three round strands twisted together all round the wrist (one solid),
    with a beaded collar at the front and the back."""
    np = _np()
    from ._bc_mesh import grid_faces, orient
    L = rope_layout(spec, s)
    a, b = L["t"] / 2, L["w"] / 2
    m, k = 960, 48
    phi = TAU * np.arange(m) / m
    th = TAU * np.arange(k) / k
    R_c0 = spec.inner_d_mm / 2 + a
    r = rope_radius(spec, s, th[None, :], phi[:, None], R_c0)
    R_c = spec.inner_d_mm / 2 - (a * r * np.cos(th)[None, :]).min()   # innermost point on inner_d/2
    X = R_c + a * r * np.cos(th)[None, :]
    Z = b * r * np.sin(th)[None, :]
    V = np.stack([X * np.cos(phi)[:, None], X * np.sin(phi)[:, None], Z], -1).reshape(-1, 3)
    V, F = orient(_upright(V), grid_faces(m, k))
    gems = []
    gd = _stone_d(spec)
    if gd > 0:
        gems.append(_gem_at_top(gd, R_c + a * 1.15 + 0.5 - 0.1))
    dims = {"width_mm": round(L["w"], 2), "thickness_mm": round(L["t"], 2),
            "inner_d_mm": spec.inner_d_mm, "strands": L["n"], "twists": L["K"]}
    return _finish(V, F, gems, dims)


register(
    "bangle_twisted_rope", "bangle", build_twisted_rope,
    {"inner_d_mm": 60.3, "width_mm": 2.85, "thickness_mm": 2.85, "profile": "comfort",
     "params": {"strands": 3, "lay": 3.2}},
    {"width_mm": (0.85, 1.0, 1.15), "thickness_mm": (0.85, 1.0, 1.15)},
    checks=_band_checks(lambda sp, s: [
        f"{rope_layout(sp, s)['n']} strands twisted as one solid, front and back collars"]),
    title="Twisted Rope Bangle")


# ------------------------------------------------------------------ B3 leaf vine
def vine_layout(spec, s):
    w, t = spec.width_mm * s, spec.thickness_mm * s
    b = w / 2
    R_o = spec.inner_d_mm / 2 + t
    C = TAU * R_o
    ang = math.radians(15)
    As = 0.1 * b
    L = 2.2 * b                                     # leaf length: blade stays inside ~0.95 b
    spacing = L / 1.1
    nl = max(12, 2 * round(C / (2 * spacing)))      # even: leaves alternate sides
    return dict(w=w, t=t, b=b, R_o=R_o, C=C, ang=ang, As=As, L=L, W=0.38 * L,
                nl=nl, sp=C / nl)


def vine_height(spec, s):
    np = _np()
    V = vine_layout(spec, s)
    C, sp, L, W, t, b = V["C"], V["sp"], V["L"], V["W"], V["t"], V["b"]
    S0 = V["R_o"] * math.pi / 2
    gd = _stone_d(spec)

    def h(S, Z):
        dS0 = _wrap(S - S0, C)
        zs = V["As"] * np.cos(math.pi * dS0 / sp)
        rs = 0.07 * V["w"]
        H = _dome((Z - zs) ** 2, rs, 0.28 * t)                         # the vine stem
        Hb, Hr, rr = 0.3 * t, 0.12 * t, 0.06 * V["w"]
        for j in range(V["nl"]):
            sig = 1 if j % 2 == 0 else -1
            ga = sig * V["ang"]
            dS = _wrap(S - (S0 + j * sp), C)
            dz = Z - sig * V["As"]
            u = dS * math.cos(ga) + dz * math.sin(ga)
            v = -dS * math.sin(ga) + dz * math.cos(ga)
            un = np.clip(u / L, 0, 1)
            hw = np.maximum(W / 2 * np.sin(math.pi * un) ** 0.7, 1e-6)
            qv = v / hw
            on = (u > 0) & (u < L) & (np.abs(qv) < 1)
            blade = Hb * np.sqrt(np.clip(1 - qv * qv, 0, 1)) * (0.55 + 0.45 * np.sin(math.pi * un))
            blade = blade * (1 - 0.3 * np.exp(-(qv / 0.3) ** 2))          # soft groove by the rib
            rib = np.where(u < 0.9 * L, (Hb * 0.7 + Hr) * np.clip(1 - np.abs(v) / rr, 0, 1), 0.0)
            H = np.maximum(H, np.where(on, np.maximum(blade, rib), 0.0))
        if gd > 0:                                                      # flower holding the stone
            X = _wrap(S - S0, C)
            rho = np.hypot(X, Z)
            Rs, rt = gd / 2, 0.3
            pr = Rs + rt + 0.55 * b * 0.5
            fl = np.zeros_like(H)
            for k in range(5):
                a = TAU * k / 5 + math.pi / 2
                fl = np.maximum(fl, _dome((X - pr * math.cos(a)) ** 2 + (Z - pr * math.sin(a)) ** 2,
                                          0.55 * b * 0.5 + 0.25, 0.35 * t))
            seat, inside = _seat(rho, Rs, rt, 0.5 * t)
            zone = rho < pr + 0.55 * b * 0.5 + 0.25
            H = np.where(zone, np.maximum(fl, seat), H)
            H = np.where(inside, seat, H)
        return H
    return h


def build_leaf_vine(spec, s):
    """Slim bangle: a wavy vine on the outer face with leaves (pointed blade + raised
    midrib) branching off alternately to each side all round the wrist."""
    V = vine_layout(spec, s)
    Vv, F = relief_band(spec.inner_d_mm, V["w"], V["t"], vine_height(spec, s), m=2400, ko=56,
                        n_out=3.0)
    gems = []
    gd = _stone_d(spec)
    if gd > 0:
        gems.append(_gem_at_top(gd, V["R_o"] + 0.5 * V["t"] - 0.6 * 0.3 - 0.05))
    dims = {"width_mm": round(V["w"], 2), "thickness_mm": round(V["t"], 2),
            "inner_d_mm": spec.inner_d_mm, "leaves": V["nl"]}
    return _finish(Vv, F, gems, dims)


register(
    "bangle_leaf_vine", "bangle", build_leaf_vine,
    {"inner_d_mm": 60.3, "width_mm": 4.0, "thickness_mm": 1.4, "profile": "comfort",
     "params": {}},
    {"width_mm": (0.8, 1.0, 1.2), "thickness_mm": (0.85, 1.0, 1.15)},
    checks=_band_checks(lambda sp, s: [
        f"{vine_layout(sp, s)['nl']} leaves (blade + midrib) alternating along the vine"]),
    title="Leaf Vine Bangle")
