"""Topology hygiene for castable meshes (bpy/bmesh). Units: millimetres.

A casting unit needs one closed solid: every edge shared by exactly two faces
(watertight, manifold), faces wound consistently and outward (positive signed
volume), no loose geometry, a single connected piece of gold and no faces
passing through each other. Wall thickness and other manufacturability checks
are not topology and live elsewhere (DFM).
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass

import bpy  # noqa: F401  (must precede bmesh)
import bmesh
from mathutils.bvhtree import BVHTree
from mathutils.geometry import intersect_ray_tri


@dataclass
class MeshReport:
    verts: int
    faces: int
    boundary_edges: int        # edges with one face: holes, not watertight
    non_manifold_edges: int    # edges without exactly two faces
    non_manifold_verts: int    # e.g. two solids touching at one vertex
    loose_verts: int
    loose_edges: int
    inconsistent_edges: int    # neighbouring faces wound in opposite directions
    components: int            # connected face islands
    signed_volume: float       # mm^3; > 0 means normals point outward
    self_intersections: int    # non-adjacent triangle pairs crossing > SELF_X_TOL_MM (-1 = not checked)

    def problems(self) -> list[str]:
        out = []
        for k in ("boundary_edges", "non_manifold_edges", "non_manifold_verts", "loose_verts",
                  "loose_edges", "inconsistent_edges"):
            if getattr(self, k):
                out.append(f"{k}={getattr(self, k)}")
        if self.components != 1:
            out.append(f"components={self.components} (expected 1)")
        if not self.signed_volume > 0:
            out.append(f"signed_volume={self.signed_volume:.3f} (normals point inward)")
        if self.self_intersections > 0:
            out.append(f"self_intersections={self.self_intersections}")
        return out

    @property
    def ok(self) -> bool:
        return not self.problems()

    def as_dict(self) -> dict:
        return asdict(self)


def _components(bm: bmesh.types.BMesh) -> int:
    seen: set[int] = set()
    n = 0
    for f in bm.faces:
        if f.index in seen:
            continue
        n += 1
        stack = [f]
        seen.add(f.index)
        while stack:
            cur = stack.pop()
            for e in cur.edges:
                for g in e.link_faces:
                    if g.index not in seen:
                        seen.add(g.index)
                        stack.append(g)
    return n


# Crossings shorter than this are float32 rounding of boolean-output vertices
# (measured 0.2-0.9e-6 mm on 10 mm rings), far below casting resolution
# (~0.025 mm). Real crossings found during Phase 2 were 0.2-0.45 mm.
SELF_X_TOL_MM = 1e-3


def _crossing_length(A, B) -> float:
    """Length of the segment where triangles A and B cross (0 if they only touch)."""
    pts = []
    for P, Q in ((A, B), (B, A)):
        for i in range(3):
            p0, p1 = P[i], P[(i + 1) % 3]
            d = p1 - p0
            if d.length == 0:
                continue
            h = intersect_ray_tri(Q[0], Q[1], Q[2], d, p0, True)
            if h is not None and (h - p0).length <= d.length:
                pts.append(h)
            h = intersect_ray_tri(Q[0], Q[1], Q[2], -d, p1, True)
            if h is not None and (h - p1).length <= d.length:
                pts.append(h)
    return max(((a - b).length for a in pts for b in pts), default=0.0)


def _self_intersections(bm: bmesh.types.BMesh) -> int:
    tris = bm.calc_loop_triangles()
    verts = [v.co.copy() for v in bm.verts]
    polys = [[l.vert.index for l in t] for t in tris]
    tree = BVHTree.FromPolygons(verts, polys, all_triangles=True)
    bad = 0
    for i, j in tree.overlap(tree):
        if i >= j:
            continue  # each pair once, and never a triangle with itself
        if set(polys[i]) & set(polys[j]):
            continue  # neighbours share a vertex or edge; touching there is expected
        A = [verts[k] for k in polys[i]]
        B = [verts[k] for k in polys[j]]
        if _crossing_length(A, B) > SELF_X_TOL_MM:
            bad += 1
    return bad


def check(ob: bpy.types.Object, self_intersection: bool = True) -> MeshReport:
    """Topology report for `ob` in world space."""
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    bm.transform(ob.matrix_world)
    bm.verts.index_update()
    bm.faces.index_update()
    inconsistent = 0
    for e in bm.edges:
        loops = list(e.link_loops)
        # Consistent winding: the two faces walk their shared edge in opposite directions.
        if len(loops) == 2 and loops[0].vert is loops[1].vert:
            inconsistent += 1
    rep = MeshReport(
        verts=len(bm.verts),
        faces=len(bm.faces),
        boundary_edges=sum(1 for e in bm.edges if e.is_boundary),
        non_manifold_edges=sum(1 for e in bm.edges if not e.is_manifold),
        non_manifold_verts=sum(1 for v in bm.verts if not v.is_manifold),
        loose_verts=sum(1 for v in bm.verts if not v.link_faces),
        loose_edges=sum(1 for e in bm.edges if not e.link_faces),
        inconsistent_edges=inconsistent,
        components=_components(bm),
        signed_volume=bm.calc_volume(signed=True),
        self_intersections=_self_intersections(bm) if self_intersection else -1,
    )
    bm.free()
    return rep


def _dist_to_origin_2d(ax: float, az: float, bx: float, bz: float) -> float:
    dx, dz = bx - ax, bz - az
    L2 = dx * dx + dz * dz
    t = 0.0 if L2 == 0 else max(0.0, min(1.0, -(ax * dx + az * dz) / L2))
    return math.hypot(ax + t * dx, az + t * dz)


def ring_inner_diameter(ob: bpy.types.Object) -> float:
    """Finger-hole diameter measured on the mesh, for a ring standing upright with
    its axis on world Y through the origin: twice the smallest distance from the
    axis to the surface. Distance to the Y axis is the (x, z) norm, a convex
    function, so over any face that does not straddle the axis its minimum lies
    on an edge; taking the minimum over edges gives the inscribed circle that a
    ring mandrel would measure, not just the nearest vertex."""
    me = ob.data
    mw = ob.matrix_world
    co = [mw @ v.co for v in me.vertices]
    best = math.inf
    for e in me.edges:
        a, b = co[e.vertices[0]], co[e.vertices[1]]
        best = min(best, _dist_to_origin_2d(a.x, a.z, b.x, b.z))
    return 2 * best
