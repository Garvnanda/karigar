"""bpy material setup must work on the pinned Blender (bpy 5.0.1)."""
import pytest

from karigar.packs.jewellery import render


@pytest.mark.parametrize("kind", list(render.GEM_MAT))
def test_gem_material_builds_for_every_gem(kind):
    m = render.gem_material(kind)
    p = m.node_tree.nodes["Principled BSDF"]
    col, ior, _ = render.GEM_MAT[kind]
    assert p.inputs["Transmission Weight"].default_value == 1.0
    assert p.inputs["IOR"].default_value == pytest.approx(ior)
    assert tuple(p.inputs["Base Color"].default_value)[:3] == pytest.approx(col)


@pytest.mark.parametrize("metal,karat", list(render.METAL_RGB))
def test_metal_material_builds(metal, karat):
    p = render.metal_material(metal, karat).node_tree.nodes["Principled BSDF"]
    assert p.inputs["Metallic"].default_value == 1.0


def test_earring_pair_glb_copies_are_gold():
    """The mirrored second earring carries the same gold (and stone) materials as the first."""
    from karigar.packs.jewellery import geometry, render
    from karigar.packs.jewellery.families import FAMILIES
    from karigar.packs.jewellery.schema import DesignSpec
    f = FAMILIES["earring_jhumka"]
    spec = DesignSpec(**{**f.default_spec, "piece_type": "earring", "family": f.name, "name": "J"})
    geometry.clear_scene()
    b = geometry.build(spec, 1.0)
    render.stage(b.gold, b.gems, spec.metal, spec.karat, spec.gem)
    render.dress_pair([b.gold, *b.gems], b.mirror)
    assert b.mirror and b.mirror[0].data.materials[0] == b.gold.data.materials[0]
    geometry.clear_scene()
