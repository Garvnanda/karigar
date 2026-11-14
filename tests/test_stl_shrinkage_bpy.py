"""Phase 5: casting.stl is scaled up by the configured shrinkage; the scene object is not."""
import struct

import bpy
import pytest

from karigar.packs.jewellery import render


def _stl_extent(path):
    data = path.read_bytes()
    n = struct.unpack_from("<I", data, 80)[0]
    xs, ys, zs = [], [], []
    for i in range(n):
        off = 84 + i * 50 + 12
        for v in range(3):
            x, y, z = struct.unpack_from("<3f", data, off + v * 12)
            xs.append(x), ys.append(y), zs.append(z)
    return max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs)


def test_export_stl_scales_by_shrinkage(tmp_path):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.mesh.primitive_cube_add(size=10.0)
    cube = bpy.context.active_object
    plain = render.export_stl(cube, tmp_path / "plain.stl", shrinkage_pct=0.0)
    cast = render.export_stl(cube, tmp_path / "cast.stl", shrinkage_pct=1.0)
    assert _stl_extent(plain) == pytest.approx((10.0, 10.0, 10.0), rel=1e-5)
    assert _stl_extent(cast) == pytest.approx((10.1, 10.1, 10.1), rel=1e-5)
    assert tuple(cube.scale) == pytest.approx((1, 1, 1))     # the design itself is untouched
