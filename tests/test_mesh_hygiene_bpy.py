"""The mesh hygiene checker must catch each defect it claims to, on known-bad meshes;
otherwise a green family test proves nothing."""
import math

import pytest


@pytest.fixture(scope="module")
def gm():
    from karigar.packs.jewellery import geometry, mesh_check
    return geometry, mesh_check


def _cube(geometry, name="cube", offset=(0, 0, 0), size=2.0):
    import bmesh
    from mathutils import Vector
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=size)
    bmesh.ops.translate(bm, vec=Vector(offset), verts=bm.verts)
    return bm


def _obj(geometry, bm, name, recalc=True):
    import bpy
    if recalc:
        return geometry._obj_from_bm(bm, name)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def test_clean_cube_passes(gm):
    geometry, mc = gm
    geometry.clear_scene()
    rep = mc.check(_obj(geometry, _cube(geometry), "c"))
    assert rep.ok, rep.problems()
    assert rep.signed_volume == pytest.approx(8.0, rel=1e-6)


def test_open_mesh_is_not_watertight(gm):
    geometry, mc = gm
    geometry.clear_scene()
    bm = _cube(geometry)
    bm.faces.ensure_lookup_table()
    bm.faces.remove(bm.faces[0])
    rep = mc.check(_obj(geometry, bm, "open"))
    assert rep.boundary_edges == 4 and rep.non_manifold_edges == 4
    assert not rep.ok


def test_two_pieces_are_flagged(gm):
    geometry, mc = gm
    geometry.clear_scene()
    bm = _cube(geometry)
    other = _cube(geometry, offset=(5, 0, 0))
    me = __import__("bpy").data.meshes.new("tmp")
    other.to_mesh(me)
    other.free()
    bm.from_mesh(me)
    rep = mc.check(_obj(geometry, bm, "two"))
    assert rep.components == 2
    assert any("components" in p for p in rep.problems())


def test_inverted_normals_are_flagged(gm):
    geometry, mc = gm
    geometry.clear_scene()
    import bmesh
    bm = _cube(geometry)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bmesh.ops.reverse_faces(bm, faces=bm.faces)
    rep = mc.check(_obj(geometry, bm, "inside_out", recalc=False))
    assert rep.signed_volume < 0
    assert not rep.ok


def test_one_flipped_face_is_inconsistent(gm):
    geometry, mc = gm
    geometry.clear_scene()
    import bmesh
    bm = _cube(geometry)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.faces.ensure_lookup_table()
    bmesh.ops.reverse_faces(bm, faces=[bm.faces[0]])
    rep = mc.check(_obj(geometry, bm, "flip1", recalc=False))
    assert rep.inconsistent_edges == 4
    assert not rep.ok


def test_overlapping_unmerged_solids_self_intersect(gm):
    """Two closed cubes passing through each other but never booleaned:
    each is watertight, but the faces cross."""
    geometry, mc = gm
    geometry.clear_scene()
    import bpy
    bm = _cube(geometry)
    other = _cube(geometry, offset=(1, 0.3, 0.2))
    me = bpy.data.meshes.new("tmp")
    other.to_mesh(me)
    other.free()
    bm.from_mesh(me)
    rep = mc.check(_obj(geometry, bm, "crossing"))
    assert rep.self_intersections > 0
    assert not rep.ok


def test_union_of_overlapping_solids_is_clean(gm):
    geometry, mc = gm
    geometry.clear_scene()
    a = _obj(geometry, _cube(geometry), "a")
    b = _obj(geometry, _cube(geometry, offset=(1, 0.3, 0.2)), "b")
    rep = mc.check(geometry.union([a, b], "ab"))
    assert rep.ok, rep.problems()


def test_inner_diameter_uses_facets_not_vertices(gm):
    """A 6-sided 'ring' whose vertices sit at r=10: the hole a mandrel feels is
    the inscribed circle, r = 10 cos(30 deg)."""
    geometry, mc = gm
    geometry.clear_scene()
    bm = geometry._revolve(geometry._profile(11.0, 1.0, 1.0, 2, 2, 8), 6)
    ob = geometry._obj_from_bm(bm, "hex")
    ob.data.transform(geometry.ROT_UPRIGHT)
    assert mc.ring_inner_diameter(ob) == pytest.approx(20 * math.cos(math.pi / 6), abs=1e-4)


def test_shallow_real_crossing_is_still_flagged(gm):
    """The float-noise tolerance (1 micron) must not hide a 0.01 mm interpenetration."""
    geometry, mc = gm
    geometry.clear_scene()
    import bpy
    bm = _cube(geometry)
    other = _cube(geometry, offset=(1.99, 0.3, 0.2))
    me = bpy.data.meshes.new("tmp")
    other.to_mesh(me)
    other.free()
    bm.from_mesh(me)
    rep = mc.check(_obj(geometry, bm, "kiss"))
    assert rep.self_intersections > 0
    assert mc.SELF_X_TOL_MM <= 0.001
