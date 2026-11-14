"""Coin family: K1 lotus coin (~10 g), raised rim, lotus relief face, stamped back.

An original design in the style of Indian festival gold coins (no brand's coin is copied).
Built flat in the XY plane (front +Z, top +Y), then stood up with geometry.ROT_UPRIGHT so
the lotus faces the camera (-Y). The back carries the hallmark and weight as raised
lettering built FROM CODE: "<karat>K <fineness>" (fineness from core.gold.PURITY) over
"<stamp_g> g". The letters are a stroke font defined below (no font file, no LLM) and
are part of the gold, so the solver weighs them too.

Scale: diameter, rim and relief grow as sqrt(scale) and the body thickness as scale,
so a heavier coin is both wider and thicker and the volume rises strictly with scale.
Family knobs live in spec.params: stamp_g = the weight stamped on the back (grams).
No bpy at module level.
"""
from __future__ import annotations

import math

from . import register

MIN_BODY_T = 0.6        # mm, thinnest coin body we strike / cast
MAX_BODY_T = 3.0
MIN_D, MAX_D = 14.0, 40.0
TEXT_W = 0.62           # widest stamp line as a share of the diameter

# ------------------------------------------------------------------ stroke font
# Glyphs on a 4 x 6 cell (baseline y = 0, cap height 6; "g" descends to -1.6). A glyph is
# a list of strokes; a stroke is ("line", [pts]) (each segment its own capsule, so sharp
# corners never fold a wire), ("curve", [pts]) (one smooth wire), or ("ring", (cx, cy, rx, ry)).
ADVANCE, SPACE = 5.2, 3.0


def _arc(cx, cy, rx, ry, a0, a1, n=14):
    return [(cx + rx * math.cos(math.radians(a0 + (a1 - a0) * i / n)),
             cy + ry * math.sin(math.radians(a0 + (a1 - a0) * i / n))) for i in range(n + 1)]


GLYPHS = {
    "0": [("ring", (2.0, 3.0, 1.9, 2.9))],
    "1": [("line", [(0.9, 4.7), (2.2, 6.0), (2.2, 0.0)])],
    "2": [("curve", _arc(2.0, 4.1, 1.85, 1.75, 160, -35) + [(0.15, 0.25)]), ("line", [(0.15, 0.1), (3.9, 0.1)])],
    "3": [("curve", _arc(2.0, 4.55, 1.55, 1.35, 150, -90, 12)), ("curve", _arc(2.0, 1.65, 1.75, 1.55, 90, -150))],
    "4": [("line", [(2.9, 0.0), (2.9, 6.0), (0.1, 1.9), (3.9, 1.9)])],
    "5": [("line", [(3.7, 6.0), (0.6, 6.0), (0.4, 3.5)]),
          ("curve", [(0.4, 3.5)] + _arc(2.0, 1.95, 1.85, 1.85, 125, -145))],
    "6": [("ring", (2.0, 1.9, 1.8, 1.85)), ("curve", [(3.3, 6.0), (1.6, 5.0), (0.45, 3.2), (0.25, 1.9)])],
    "7": [("line", [(0.1, 5.9), (3.9, 5.9), (1.3, 0.0)])],
    "8": [("ring", (2.0, 4.5, 1.45, 1.4)), ("ring", (2.0, 1.6, 1.75, 1.6))],
    "9": [("ring", (2.0, 4.1, 1.8, 1.85)), ("curve", [(3.75, 4.1), (3.55, 2.8), (2.7, 1.1), (1.3, 0.0)])],
    "K": [("line", [(0.3, 0.0), (0.3, 6.0)]), ("line", [(3.8, 6.0), (0.35, 2.3)]),
          ("line", [(1.5, 3.5), (3.9, 0.0)])],
    "g": [("ring", (1.9, 2.3, 1.55, 1.65)), ("line", [(3.45, 4.0), (3.45, -0.4)]),
          ("curve", _arc(1.9, -0.4, 1.55, 1.2, 0, -165, 10))],
    ".": [("dot", (2.0, 0.35))],
}


def fineness(karat: int) -> int:
    """Hallmark fineness (parts per thousand) from code data: core.gold.PURITY."""
    from ....core.gold import PURITY
    return round(PURITY[karat] * 1000)


def stamp_lines(spec) -> tuple[str, str]:
    """The two lines embossed on the back, built from the spec (never from an LLM)."""
    g = spec.params.get("stamp_g", 10.0)
    return f"{spec.karat}K {fineness(spec.karat)}", f"{g:g} g"


def text_width(line: str) -> float:
    """Width of a stamped line in glyph units."""
    w = sum(SPACE if ch == " " else ADVANCE for ch in line)
    return w - (ADVANCE - 4.0) if line and line[-1] != " " else w


def _dims(spec, s):
    D = spec.size_mm * math.sqrt(s)
    T = spec.thickness_mm * s
    k = math.sqrt(s)                             # relief and rim grow gently
    return D, T, 0.42 * k, 0.30 * k, 1.1 * k     # diameter, body, rim height, relief height, rim width


def _dense(pts, step):
    """Open polyline with no segment longer than `step` (straight subdivision)."""
    out = [pts[0]]
    for a, b in zip(pts, pts[1:]):
        m = max(1, math.ceil((b - a).length / step))
        out += [a.lerp(b, j / m) for j in range(1, m + 1)]
    return out


def _glyph_parts(ch, ox, oy, u, r, zf, name):
    """Gold parts of one glyph: origin (ox, oy), unit u mm, wire radius r, z from zf(x, y).
    x is mirrored so the stamp reads correctly from behind the coin."""
    from ._gemwork import catmull, relax, tube, wire
    from .. import geometry as g
    P = lambda x, y: (-(ox + x * u), oy + y * u)
    out = []
    for kind, data in GLYPHS[ch]:
        if kind == "ring":
            cx, cy, rx, ry = data
            pts = [P(*q) for q in _arc(cx, cy, rx, ry, 0, 360, 40)[:-1]]
            out.append(tube([(x, y, zf(x, y)) for x, y in pts], r, f"{name}_ring", True, 10))
        elif kind == "dot":
            x, y = P(*data)
            out.append(g.sphere((x, y, zf(x, y)), (r * 1.5,) * 3, f"{name}_dot", 14, 9))
        elif kind == "line":
            pts = [P(*q) for q in data]
            for i, (a, b) in enumerate(zip(pts, pts[1:])):
                # short tube rings follow the crowned face (a long straight tube face over a
                # curved face left a crossing seam in the boolean)
                m = max(2, math.ceil(math.dist(a, b) / (0.8 * r)))
                seg = [(a[0] + (b[0] - a[0]) * j / m, a[1] + (b[1] - a[1]) * j / m) for j in range(m + 1)]
                out += wire([(x, y, zf(x, y)) for x, y in seg], r, f"{name}_s{i}", 10)
        else:
            pts = _dense(catmull([P(*q) for q in data], 4, closed=False), 0.8 * r)
            pts = relax(pts, 1.6 * r, closed=False)
            out += wire([(p.x, p.y, zf(p.x, p.y)) for p in pts], r, f"{name}_c", 10)
    return out


def build_lotus_coin(spec, s):
    """Round coin: crowned body, raised rim on both faces, a two-tier lotus in relief inside
    a beaded circle on the front, and the stamp (hallmark + weight) on the back."""
    from mathutils import Matrix
    from .. import geometry as g
    from ._gemwork import CROWN_MM, cushion, disc, place, ripple, union_clean
    from .pendants import lotus_petal
    D, T, rim_h, rel_h, rim_w = _dims(spec, s)
    R = D / 2
    Rf = R - rim_w                                  # inner edge of the rim: the field
    parts = [disc(R - rim_w * 0.5, -T / 2, T / 2, "body", 128)]
    # rim: a rounded annulus standing rim_h proud of both faces
    a, b = rim_w / 2, T / 2 + rim_h
    rim = g._obj_from_bm(g._revolve(g._profile(R - a, a, b, 4.0, 4.0, 28), 160), "rim")
    parts.append(rim)

    def front(x, y):                                # the front face's height at (x, y)
        f2 = (x * x + y * y) / (Rf * Rf)
        return T / 2 + CROWN_MM * max(0.0, 1 - f2) + ripple(x, y)

    def back(x, y):
        f2 = (x * x + y * y) / (Rf * Rf)
        return -T / 2 - CROWN_MM * max(0.0, 1 - f2) + ripple(x, y)

    # ---- front: two rings of lotus petals, seed pod, beaded circle
    n = spec.petals
    z_base = T / 2 - 0.15
    top = T / 2 + CROWN_MM + rel_h
    for layer, (r_in, r_tip, h, off) in enumerate(((0.16 * Rf, 0.70 * Rf, 1.0, 0.0),
                                                   (0.14 * Rf, 0.50 * Rf, 1.25, 0.5))):
        L = r_tip - r_in
        W = min(2 * (r_in + 0.55 * L) * math.sin(math.pi / n) * 1.2, 0.6 * L)
        for k in range(n):
            ang = 2 * math.pi * (k + off) / n
            pet = cushion(lotus_petal(L, W), (0.42 * L, 0), z_base, T / 2 + CROWN_MM + rel_h * h * 0.8,
                          f"petal{layer}_{k}", 8, 2.2)
            place([pet], Matrix.Rotation(ang, 4, "Z") @ Matrix.Translation((r_in, 0, 0)))
            parts.append(pet)
    pod_r = 0.18 * Rf
    pod = [(pod_r * math.cos(2 * math.pi * i / 48), pod_r * math.sin(2 * math.pi * i / 48)) for i in range(48)]
    parts.append(cushion(pod, (0, 0), z_base, top + rel_h * 0.25, "pod", 8, 3.0))
    for k in range(7):                              # seeds on the pod
        ang = 2 * math.pi * k / 7
        x, y = 0.55 * pod_r * math.cos(ang), 0.55 * pod_r * math.sin(ang)
        parts.append(g.sphere((x, y, top + rel_h * 0.15), (0.2 * pod_r,) * 2 + (0.12 * pod_r,), f"seed{k}", 14, 9))
    br = 0.22 * math.sqrt(s) + 0.05
    rb = Rf - 1.6 * br - 0.35
    nb = int(2 * math.pi * rb // (2.6 * br))
    for face, zfn, sgn in (("f", front, 1), ("b", back, -1)):
        for k in range(nb):
            ang = 2 * math.pi * (k + 0.5) / nb
            x, y = rb * math.cos(ang), rb * math.sin(ang)
            parts.append(g.sphere((x, y, zfn(x, y) + sgn * 0.3 * br), (br,) * 3, f"bead{face}{k}", 12, 9))
    # ---- back: the stamp, built from the spec
    stamp = {}
    if spec.stamp:
        l1, l2 = stamp_lines(spec)
        u = TEXT_W * D / max(text_width(l1), text_width(l2), 1e-9) * 0.98
        u = min(u, 0.105 * Rf)                      # short lines don't grow past the field
        r = 0.48 * u
        zf = lambda x, y: back(x, y) - 0.5 * r
        for li, (line, y0) in enumerate(((l1, 0.6 * u), (l2, -6.0 * u - 1.6 * u))):
            x0 = -text_width(line) * u / 2
            for ci, ch in enumerate(line):
                if ch != " ":
                    parts += _glyph_parts(ch, x0, y0, u, r, zf, f"l{li}c{ci}")
                x0 += (SPACE if ch == " " else ADVANCE) * u
        stamp = {"stamp": f"{l1} / {l2}", "letter_h_mm": round(6 * u, 2)}
    g._place(parts, g.ROT_UPRIGHT)
    gold = union_clean(parts)
    dims = {"diameter_mm": round(D, 2), "thickness_mm": round(T, 2), "rim_h_mm": round(rim_h, 2),
            "relief_h_mm": round(rel_h, 2), **stamp}
    return g.Built(gold, [], g.mesh_volume(gold), dims)


def coin_bounds(spec):
    """Castable range: body thickness MIN_BODY_T..MAX_BODY_T and diameter MIN_D..MAX_D."""
    lo = max(MIN_BODY_T / spec.thickness_mm, (MIN_D / spec.size_mm) ** 2)
    hi = min(MAX_BODY_T / spec.thickness_mm, (MAX_D / spec.size_mm) ** 2)
    return lo, hi


def coin_checks(spec, s):
    D, T, rim_h, rel_h, _ = _dims(spec, s)
    out = [f"body thickness {T:.2f} mm (min {MIN_BODY_T} mm)",
           f"diameter {D:.1f} mm",
           f"rim stands {rim_h:.2f} mm proud, relief {rel_h:.2f} mm: the rim protects the relief"]
    if spec.stamp:
        l1, l2 = stamp_lines(spec)
        out.append(f"back stamped '{l1}' / '{l2}'")
    return out


register(
    "coin_lotus_10g", "coin", build_lotus_coin,
    {"size_mm": 24.0, "thickness_mm": 1.0, "petals": 8, "params": {"stamp_g": 10.0}},
    {"size_mm": (0.88, 1.0, 1.12), "thickness_mm": (0.85, 1.0, 1.15)},
    scale_bounds=coin_bounds, checks=coin_checks, title="Lotus Coin")
