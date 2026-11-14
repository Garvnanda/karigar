"""Mesh-based manufacturability checks (Phase 4, spec §6). Units: millimetres.

The checks run on the built gold mesh, never on the spec: wall thickness is MEASURED by
ray-casting. At area-weighted random points on the surface a ray is shot inward along the
face normal (mathutils BVHTree); the distance to where it leaves the solid is the local
thickness (a plate gives its thickness, a round wire or claw its diameter, a ring shank
sampled on its finger-hole face its radial thickness). Each sample is then given to a part:

- `ring_shank`  rings: points on the finger-hole surface (radial shank thickness),
- `prong`       claw settings: points within reach of the main stone,
- `setting`     other stone settings (bezel, cup, grain beads),
- `wall`        everything else (the family's own minimum: chain wire, ornament wall, ...).

Each rule reports pass / warn / fail with the measured minimum and where it is ("ring shank at
6 o'clock 1.42 mm < 1.5 mm"). One more rule is not a thickness: a claw setting holding a large
stone in soft (22K+) gold is flagged. Rule values come from data/dfm_rules.json (the per-process
config a shop edits); fail below the minimum, warn within `warn_margin_pct` above it.

A minimum is a robust low quantile of the part's samples, not the single thinnest ray: a ray
grazing a boolean crease or the rim of a smooth bead can come out short without the metal
being thin there. A real thin part is thin over its whole area, so it still shows up.
"""
from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path

RULES_FILE = Path(__file__).resolve().parents[3] / "data" / "dfm_rules.json"
_CACHE: dict = {}

PASS, WARN, FAIL = "pass", "warn", "fail"
RULE_TITLES = {
    "ring_shank": "ring shank",
    "prong": "claw (prong)",
    "setting": "stone setting",
    "wall": "wall",
    "soft_gold_claws": "claw setting in soft gold",
    "build": "build",
}


def rules(path: Path | None = None) -> dict:
    """data/dfm_rules.json (re-read when the file changes)."""
    p = Path(path or RULES_FILE)
    mtime = p.stat().st_mtime
    hit = _CACHE.get(p)
    if hit is None or hit[0] != mtime:
        _CACHE[p] = (mtime, json.loads(p.read_text(encoding="utf-8")))
    return _CACHE[p][1]


@dataclass
class RuleResult:
    rule: str                   # ring_shank / prong / setting / wall / soft_gold_claws / build
    status: str                 # pass / warn / fail
    measured_mm: float | None
    min_mm: float | None
    location: str
    text: str
    samples: int = 0

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class MeshDFM:
    results: list[RuleResult] = field(default_factory=list)

    @property
    def failed(self) -> list[RuleResult]:
        return [r for r in self.results if r.status == FAIL]

    @property
    def warned(self) -> list[RuleResult]:
        return [r for r in self.results if r.status == WARN]

    @property
    def ok(self) -> bool:
        return not self.failed

    def passed_texts(self) -> list[str]:
        return [r.text for r in self.results if r.status == PASS]

    def warning_texts(self) -> list[str]:
        return [("FAIL: " if r.status == FAIL else "") + r.text for r in self.results
                if r.status in (WARN, FAIL)]

    def as_list(self) -> list[dict]:
        return [r.as_dict() for r in self.results]


def grade(measured: float, minimum: float, margin_pct: float, tol_pct: float = 0.0) -> str:
    """fail below the minimum, warn within margin_pct above it, else pass. `tol_pct` is the
    measuring tolerance: a faceted round wire of diameter d measures d x cos(pi / sides) flat to
    flat (12 sides: 3.4% under), so a reading within tol_pct under the minimum warns."""
    if measured < minimum * (1 - tol_pct / 100) - 1e-9:
        return FAIL
    if measured < minimum - 1e-9 or measured < minimum * (1 + margin_pct / 100) - 1e-9:
        return WARN
    return PASS


# ------------------------------------------------------------------ measuring
def _world_tris(ob):
    """(vertices Nx3, triangles Mx3, areas M, unit normals Mx3) of `ob` in world space."""
    import numpy as np

    me = ob.data
    me.calc_loop_triangles()
    nv, nt = len(me.vertices), len(me.loop_triangles)
    co = np.empty(nv * 3, dtype=np.float64)
    me.vertices.foreach_get("co", co)
    co = co.reshape(nv, 3)
    mw = np.array(ob.matrix_world, dtype=np.float64)
    co = co @ mw[:3, :3].T + mw[:3, 3]
    tri = np.empty(nt * 3, dtype=np.int64)
    me.loop_triangles.foreach_get("vertices", tri)
    tri = tri.reshape(nt, 3)
    a, b, c = co[tri[:, 0]], co[tri[:, 1]], co[tri[:, 2]]
    cr = np.cross(b - a, c - a)
    L = np.linalg.norm(cr, axis=1)
    keep = L > 1e-12
    return co, tri[keep], L[keep] / 2, cr[keep] / L[keep][:, None]


def thickness_samples(ob, n: int = 1500, seed: int = 7, near_lowest: float = 0.0) -> list[tuple]:
    """[(point, inward thickness mm, outward normal)] at `n` area-weighted surface points.
    Deterministic for a given mesh and seed. Points whose ray escapes (open mesh) are dropped.
    `near_lowest` > 0 samples only triangles within that distance of the lowest vertex."""
    import numpy as np
    from mathutils import Vector
    from mathutils.bvhtree import BVHTree

    co, tri, areas, normals = _world_tris(ob)
    if not len(tri):
        return []
    tree = BVHTree.FromPolygons(co.tolist(), tri.tolist(), all_triangles=True)
    if near_lowest > 0:
        low = co[np.argmin(co[:, 2])]
        cen = co[tri].mean(axis=1)
        win = np.linalg.norm(cen - low, axis=1) < near_lowest
        tri, areas, normals = tri[win], areas[win], normals[win]
    rng = np.random.default_rng(seed)
    picks = rng.choice(len(tri), size=n, p=areas / areas.sum())
    u, v = rng.random(n), rng.random(n)
    flip = u + v > 1
    u[flip], v[flip] = 1 - u[flip], 1 - v[flip]
    a, b, c = co[tri[picks, 0]], co[tri[picks, 1]], co[tri[picks, 2]]
    pts = a + (b - a) * u[:, None] + (c - a) * v[:, None]
    nrm = normals[picks]
    eps = 1e-4
    out = []
    for p, nn in zip(pts.tolist(), nrm.tolist()):
        P, N = Vector(p), Vector(nn)
        hit, _, _, dist = tree.ray_cast(P - N * eps, -N)
        if hit is None:
            continue
        out.append((P, dist + eps, N))
    return out


def close_thin_edges(smp: list[tuple], radius: float) -> list[float]:
    """Each sample's thickness raised to the thickest sample within `radius` mm (a
    morphological closing on the surface). A tapering rim or a seat-cut sliver next to full
    metal is fed by that metal and reads as its neighbour; a part thin over a stretch longer
    than `radius` (a thin wire, claw, shank or plate) stays thin."""
    from mathutils.kdtree import KDTree

    if radius <= 0 or not smp:
        return [t for _, t, _ in smp]
    kd = KDTree(len(smp))
    for i, (p, _, _) in enumerate(smp):
        kd.insert(p, i)
    kd.balance()
    return [max(smp[j][1] for _, j, _ in kd.find_range(p, radius)) for p, _, _ in smp]


def low_quantile(values: list[float], q: float) -> float:
    """k-th smallest value, k = max(1, ceil(q * n)): the robust minimum of a part."""
    s = sorted(values)
    k = max(1, math.ceil(q * len(s)))
    return s[min(k, len(s)) - 1]


def clock(p) -> int:
    """Clock position of a point on an upright ring (axis Y, 12 o'clock = +Z, 3 = +X)."""
    a = math.degrees(math.atan2(p.x, p.z)) % 360
    h = round(a / 30) % 12
    return 12 if h == 0 else h


def where(p, bbox) -> str:
    """Coarse position in the piece's own frame (worn view: +Z up, viewer at -Y)."""
    (x0, z0), (x1, z1) = bbox
    fx = (p.x - x0) / (x1 - x0) if x1 > x0 else 0.5
    fz = (p.z - z0) / (z1 - z0) if z1 > z0 else 0.5
    v = "top" if fz > 2 / 3 else "bottom" if fz < 1 / 3 else "middle"
    h = "right" if fx > 2 / 3 else "left" if fx < 1 / 3 else "centre"
    return f"{v} {h} (x {p.x:.1f}, z {p.z:.1f} mm)"


def _gem_balls(gems) -> list[tuple]:
    """(centre, radius) of each stone from its world bounding box."""
    from mathutils import Vector
    out = []
    for g in gems:
        cs = [g.matrix_world @ Vector(c) for c in g.bound_box]
        lo = Vector((min(c.x for c in cs), min(c.y for c in cs), min(c.z for c in cs)))
        hi = Vector((max(c.x for c in cs), max(c.y for c in cs), max(c.z for c in cs)))
        out.append(((lo + hi) / 2, max(hi.x - lo.x, hi.y - lo.y, hi.z - lo.z) / 2))
    return out


def _claw_setting(spec, cfg) -> bool:
    if spec.gem == "none" or spec.gem_d_mm <= 0:
        return False
    if spec.family:
        return spec.family in cfg.get("claw_families", [])
    return spec.piece_type == "ring" and spec.motif != "floral"


def wall_min(spec, cfg) -> tuple[float, str]:
    """(minimum, what) for the `wall` rule of this design."""
    key = cfg.get("family_wall", {}).get(spec.family or "", "wall")
    return float(cfg["min_mm"][key]), key


def sample_piece(spec, gold, cfg: dict, n: int | None = None) -> list[tuple]:
    """Thickness samples of the casting model. A chain is measured on a few links at its
    lowest point (every link is the same wire), not spread thin over the whole length."""
    if n is None:
        area = sum(p.area for p in gold.data.polygons)
        n = int(min(cfg["samples_max"], max(cfg["samples_min"], area * cfg["samples_per_mm2"])))
    seed = int(cfg.get("seed", 7))
    if spec.piece_type != "chain":
        return thickness_samples(gold, n, seed)
    return thickness_samples(gold, n, seed, near_lowest=float(cfg["chain_window_mm"]))


def check_built(spec, b, cfg: dict | None = None, n: int | None = None) -> MeshDFM:
    """Run every mesh rule on a built design (`geometry.Built`): the gold is measured, the
    stones only locate the setting. An earring pair is checked on the one casting model."""
    cfg = cfg or rules()
    mins, margin = cfg["min_mm"], float(cfg["warn_margin_pct"])
    q = float(cfg["robust_quantile"])
    smp = sample_piece(spec, b.gold, cfg, n)
    balls = _gem_balls(b.gems)
    # The setter works the metal round a stone (seat floor, notched claw tips): a point on a
    # seat, or one whose ray leaves the metal into a seat, is not measured (its neighbours are).
    inside = lambda q: any((q - c).length < rad * 0.98 for c, rad in balls)
    smp = [s for s in smp if not inside(s[0]) and not inside(s[0] - s[2] * s[1])]
    closed = close_thin_edges(smp, float(cfg["fill_radius_mm"]))
    xs = [p.x for p, _, _ in smp] or [0.0]
    zs = [p.z for p, _, _ in smp] or [0.0]
    bbox = ((min(xs), min(zs)), (max(xs), max(zs)))
    main = max(balls, key=lambda gb: gb[1]) if balls else None
    claws = _claw_setting(spec, cfg)
    reach = float(cfg["setting_reach_mm"])
    ring = spec.piece_type == "ring"
    r_in = spec.inner_d_mm / 2 if ring else 0.0

    parts: dict[str, list] = {"ring_shank": [], "prong": [], "setting": [], "wall": []}
    for (p, _, nrm), t in zip(smp, closed):
        if ring:
            r = math.hypot(p.x, p.z)
            if r < r_in + 0.15 and (p.x * nrm.x + p.z * nrm.z) < -0.7 * max(r, 1e-9):
                parts["ring_shank"].append((p, t))
                continue
        near = [c for c, rad in balls if (p - c).length < rad + reach]
        if near:
            is_main = main is not None and any(c is main[0] for c in near)
            parts["prong" if (claws and is_main) else "setting"].append((p, t))
            continue
        parts["wall"].append((p, t))

    wmin, wkey = wall_min(spec, cfg)
    limits = {"ring_shank": (float(mins["ring_shank"]), "ring_shank"),
              "prong": (float(mins["prong_d"]), "prong_d"),
              "setting": (min(float(mins["setting"]), wmin), "setting"),
              "wall": (wmin, wkey)}
    out = MeshDFM()
    for rule, pts in parts.items():
        if not pts:
            continue
        lo_t = low_quantile([t for _, t in pts], q)
        p_at = min((pt for pt in pts if pt[1] <= lo_t), key=lambda pt: -pt[1])[0]
        minimum, key = limits[rule]
        status = grade(lo_t, minimum, margin, float(cfg.get("measure_tolerance_pct", 0)))
        if rule == "ring_shank":
            loc = f"{clock(p_at)} o'clock"
        else:
            loc = where(p_at, bbox)
        name = RULE_TITLES[rule] + ("" if rule != "wall" or key == "wall" else f" ({key.replace('_', ' ')})")
        sym = "<" if lo_t < minimum else "≥"
        text = f"{name} at {loc}: {lo_t:.2f} mm {sym} {minimum:g} mm"
        if status == WARN:
            text += (" (within the measuring tolerance of the minimum)" if lo_t < minimum
                     else f" (within {margin:g}% of the minimum)")
        out.results.append(RuleResult(rule, status, round(lo_t, 3), minimum, loc, text, len(pts)))

    sg = cfg["soft_gold_claws"]
    if claws and spec.karat >= int(sg["min_karat"]) and spec.gem_d_mm > float(sg["max_stone_d_mm"]):
        pr = next((r for r in out.results if r.rule == "prong"), None)
        meas = f", claws measured {pr.measured_mm:.2f} mm" if pr else ""
        out.results.append(RuleResult(
            "soft_gold_claws", sg.get("status", WARN), spec.gem_d_mm, float(sg["max_stone_d_mm"]),
            "centre stone",
            f"claw setting holds a {spec.gem_d_mm:g} mm stone in {spec.karat}K{meas}: soft gold claws "
            f"can bend and lose a stone over {sg['max_stone_d_mm']:g} mm; use a bezel, 18K claws or "
            f"claws of at least {float(sg['claw_d_mm']):g} mm"))
    return out


def failure_text(rep: MeshDFM) -> str:
    """One line naming each failing rule (the thin part and where)."""
    return "; ".join(r.text for r in rep.failed)


# ------------------------------------------------------------------ build + check (cached)
CACHE_MAX = 256
_REPORTS: dict = {}


def clear_cache() -> None:
    _REPORTS.clear()


def build_failure(e: Exception, scale: float | None = None) -> MeshDFM:
    at = f" at scale {scale:.3f}" if scale is not None else ""
    return MeshDFM([RuleResult("build", FAIL, None, None, "whole piece",
                               f"build failed{at}: {type(e).__name__}: {e}")])


def check_spec(spec, scale: float, cfg: dict | None = None) -> MeshDFM:
    """Build the design at `scale` and run the mesh rules (cached by spec hash and rules). A
    build that raises is reported as a failed `build` rule, not an exception."""
    from . import geometry

    cfg = cfg or rules()
    key = (geometry.spec_hash(spec, scale), json.dumps(cfg, sort_keys=True))
    if key in _REPORTS:
        return _REPORTS[key]
    geometry.clear_scene()
    try:
        rep = check_built(spec, geometry.build(spec, scale), cfg)
    except Exception as e:                        # a failed build is a failed check
        rep = build_failure(e, scale)
    finally:
        geometry.clear_scene()
    if len(_REPORTS) >= CACHE_MAX:
        _REPORTS.pop(next(iter(_REPORTS)))
    _REPORTS[key] = rep
    return rep


RELAX_AXES = ("width_mm", "size_mm")       # spread, not metal thickness: the generic relax


def relax(spec, rep: MeshDFM, cfg: dict | None = None) -> tuple:
    """The one retry after a failed check: (relaxed spec, what changed) or (None, "").

    A family with a `relax` hook relaxes its own optional features (fewer stones, ...).
    Otherwise the design is made less spread out: width / motif size x `relax_factor` and,
    where the builder has them, fewer petals and beads. Re-solved to the SAME gold target, the
    smaller design comes out at a larger scale, so every thin part (claws, shank, walls) gets
    thicker. The spec's thickness is never reduced."""
    from .schema import DesignSpec

    cfg = cfg or rules()
    if spec.family:
        from . import families
        hook = getattr(families.get(spec.family), "relax", None)
        if hook is not None:
            out = hook(spec, rep.failed)
            if out is not None and out[0] != spec:
                return out
    f = float(cfg["relax_factor"])
    upd, said = {}, []
    for k in RELAX_AXES:
        upd[k] = getattr(spec, k) * f
    if not spec.family and spec.piece_type == "ring" and spec.motif == "floral" or             not spec.family and spec.piece_type == "pendant" and spec.shape == "lotus":
        upd["petals"] = spec.petals - 1
    if not spec.family and spec.piece_type == "bangle" and spec.motif == "beaded":
        upd["bead_count"] = round(spec.bead_count * f)
    good = {}
    for k, v in upd.items():                # keep each change the schema accepts
        try:
            DesignSpec.model_validate({**spec.model_dump(), **good, k: v})
            good[k] = v
        except Exception:
            continue
    if not good:
        return None, ""
    for k, v in good.items():
        said.append(f"{k.replace('_mm', '').replace('_', ' ')} {getattr(spec, k):g} -> "
                    + (f"{v:.2f}" if isinstance(v, float) else f"{v}"))
    return spec.model_copy(update=good), "less spread-out design (" + ", ".join(said) + ")"
