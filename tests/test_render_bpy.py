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
