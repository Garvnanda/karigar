"""Catalog-style studio renders (Cycles) and production exports (STL, GLB).

Lighting uses emissive softbox planes, which look the same at any scene
scale, plus a seamless sweep backdrop: the classic jewellery packshot.
"""
from __future__ import annotations

import math
import os
from pathlib import Path

import bpy
import bmesh
from mathutils import Vector

from .geometry import _obj_from_bm

METAL_RGB = {  # linear base colours (F0) for gold alloys
    ("yellow", 22): (1.0, 0.70, 0.29), ("yellow", 18): (1.0, 0.76, 0.38), ("yellow", 14): (0.98, 0.78, 0.45),
    ("rose", 22): (0.97, 0.62, 0.46), ("rose", 18): (0.96, 0.64, 0.52), ("rose", 14): (0.95, 0.66, 0.56),
    ("white", 22): (0.86, 0.85, 0.80), ("white", 18): (0.88, 0.88, 0.86), ("white", 14): (0.88, 0.88, 0.86),
}
GEM_MAT = {  # base colour, IOR, Abbe number (dispersion)
    "diamond": ((1.0, 1.0, 1.0), 2.42, 55.0),
    "ruby": ((0.85, 0.03, 0.08), 1.77, 0.0),
    "sapphire": ((0.06, 0.18, 0.85), 1.77, 0.0),
    "emerald": ((0.03, 0.62, 0.22), 1.58, 0.0),
}
QUALITY = {
    "draft":   {"res": 480,  "samples": 16,  "views": ["hero"]},
    "preview": {"res": 720,  "samples": 48,  "views": ["hero", "top"]},
    "final":   {"res": 1400, "samples": 160, "views": ["hero", "front", "top"]},
}
VIEWS = {"hero": (-35, 18), "front": (0, 6), "top": (-20, 62)}  # azimuth, elevation (deg)


def _principled(name):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    return m, m.node_tree.nodes["Principled BSDF"]


def metal_material(metal: str, karat: int):
    m, p = _principled(f"gold_{metal}_{karat}")
    p.inputs["Base Color"].default_value = (*METAL_RGB[(metal, karat)], 1)
    p.inputs["Metallic"].default_value = 1.0
    p.inputs["Roughness"].default_value = 0.13
    return m


def gem_material(kind: str):
    col, ior, abbe = GEM_MAT[kind]
    m, p = _principled(f"gem_{kind}")
    p.inputs["Base Color"].default_value = (*col, 1)
    p.inputs["Transmission Weight"].default_value = 1.0
    p.inputs["Roughness"].default_value = 0.0
    p.inputs["IOR"].default_value = ior
    # Dispersion socket was renamed/removed across Blender versions; the bpy 5.0.1
    # wheel exposes none, so dispersion is applied only where a socket exists.
    if abbe:
        if "Transmission Dispersion Abbe Number" in p.inputs:
            p.inputs["Transmission Dispersion Abbe Number"].default_value = abbe
        elif "Dispersion" in p.inputs:  # Blender 4.2+: amount = 20 / Abbe number
            p.inputs["Dispersion"].default_value = 20.0 / abbe
    return m


def _emitter(name, size, loc, target, strength):
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=size / 2)
    ob = _obj_from_bm(bm, name, smooth=False)
    ob.location = loc
    ob.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat("Z", "Y").to_euler()
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Strength"].default_value = strength
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(em.outputs[0], out.inputs[0])
    ob.data.materials.append(m)
    ob.visible_camera = False      # seen only in reflections, like a real softbox
    return ob


def _sweep(S):
    """Seamless L-shaped backdrop: floor curving up into a wall behind the piece."""
    W, F, R, H, n = 30 * S, 25 * S, 6 * S, 25 * S, 24
    pts = [(-F, 0.0), (0.0, 0.0)]
    pts += [(R * math.sin(a), R - R * math.cos(a)) for a in
            (math.pi / 2 * i / n for i in range(1, n + 1))]
    pts.append((R, H))
    bm = bmesh.new()
    rows = [[bm.verts.new((x, y + 4 * S, z)) for x in (-W, W)] for y, z in pts]
    for a, b in zip(rows, rows[1:]):
        bm.faces.new((a[0], a[1], b[1], b[0]))
    ob = _obj_from_bm(bm, "backdrop")
    m, p = _principled("backdrop")
    p.inputs["Base Color"].default_value = (0.9, 0.88, 0.85, 1)
    p.inputs["Roughness"].default_value = 0.85
    ob.data.materials.append(m)


def _bounds(objs):
    pts = [o.matrix_world @ Vector(c) for o in objs for c in o.bound_box]
    lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    return lo, hi


def stage(gold, gems, metal: str, karat: int, gem_kind: str, float_up: bool = False):
    """Materials, sit the piece on the floor, build studio. Returns (centre, size)."""
    gold.data.materials.clear()
    gold.data.materials.append(metal_material(metal, karat))
    if gems:
        gm = gem_material(gem_kind)
        for g in gems:
            g.data.materials.clear()
            g.data.materials.append(gm)
    objs = [gold, *gems]
    lo, hi = _bounds(objs)
    S = max(hi - lo)
    lift = -lo.z + (0.18 * S if float_up else 0.0)
    for o in objs:
        o.location.z += lift
    bpy.context.view_layer.update()
    lo, hi = _bounds(objs)
    c = (lo + hi) / 2
    _sweep(S)
    _emitter("key", 3.0 * S, (-3.2 * S, -3.0 * S, 3.6 * S), c, 7.0)
    _emitter("fill", 2.2 * S, (3.6 * S, -2.2 * S, 1.8 * S), c, 2.5)
    _emitter("top", 2.8 * S, (0.0, 0.0, 5.0 * S), c, 4.5)
    _emitter("rim", 2.0 * S, (1.5 * S, 3.5 * S, 3.0 * S), c, 6.0)
    _emitter("card_l", 1.5 * S, (-3.0 * S, 0.5 * S, 0.6 * S), c, 2.0)
    w = bpy.data.worlds.get("World") or bpy.data.worlds.new("World")
    bpy.context.scene.world = w
    w.use_nodes = True
    bg = w.node_tree.nodes.get("Background")
    bg.inputs["Color"].default_value = (0.9, 0.9, 0.92, 1)
    bg.inputs["Strength"].default_value = 0.35
    return c, S


def _camera(c, S, az, el, lens=100):
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
    bpy.context.scene.collection.objects.link(cam)
    cam.data.lens = lens
    cam.data.clip_start, cam.data.clip_end = 0.1, 1e5
    fov = 2 * math.atan(18 / lens)
    dist = (S * 1.55) / (2 * math.tan(fov / 2))
    a, e = math.radians(az), math.radians(el)
    cam.location = c + Vector((dist * math.sin(a) * math.cos(e) * -1, -dist * math.cos(a) * math.cos(e),
                               dist * math.sin(e)))
    cam.rotation_euler = (c - cam.location).to_track_quat("-Z", "Y").to_euler()
    bpy.context.scene.camera = cam
    return cam


def render_views(c, S, out_dir: Path, quality: str) -> dict[str, Path]:
    q = QUALITY[quality]
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    sc.cycles.device = "CPU"
    gpu = os.environ.get("KARIGAR_GPU")  # CUDA | OPTIX | HIP | METAL | ONEAPI
    if gpu:
        try:
            prefs = bpy.context.preferences.addons["cycles"].preferences
            prefs.compute_device_type = gpu
            prefs.get_devices()
            for d in prefs.devices:
                d.use = True
            sc.cycles.device = "GPU"
        except Exception as e:
            print(f"  (GPU {gpu} unavailable: {e}; rendering on CPU)")
    sc.cycles.samples = q["samples"]
    sc.cycles.max_bounces = 14
    sc.cycles.transmission_bounces = 12
    sc.cycles.glossy_bounces = 8
    sc.cycles.caustics_reflective = sc.cycles.caustics_refractive = False
    try:
        sc.cycles.use_denoising = True
        sc.cycles.denoiser = "OPENIMAGEDENOISE"
    except Exception:
        sc.cycles.use_denoising = False
    sc.render.resolution_x = sc.render.resolution_y = q["res"]
    sc.render.image_settings.file_format = "PNG"
    sc.view_settings.view_transform = "AgX"
    sc.view_settings.exposure = -1.0
    try:
        sc.view_settings.look = "AgX - Medium High Contrast"
    except TypeError:
        pass
    out_dir.mkdir(parents=True, exist_ok=True)
    files = {}
    for v in q["views"]:
        az, el = VIEWS[v]
        cam = _camera(c, S, az, el)
        p = out_dir / f"render_{v}.png"
        sc.render.filepath = str(p)
        bpy.ops.render.render(write_still=True)
        files[f"render_{v}"] = p
        bpy.data.objects.remove(cam, do_unlink=True)
    return files


def _select_only(objs):
    for o in bpy.context.scene.objects:
        o.select_set(False)
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]


def export_stl(gold, path: Path) -> Path:
    """Gold body only, in millimetres: what the wax printer / casting unit needs."""
    _select_only([gold])
    bpy.ops.wm.stl_export(filepath=str(path), export_selected_objects=True, ascii_format=False)
    return path


def export_glb(objs, path: Path) -> Path:
    """Real-world scale (metres) with materials, for the AR viewer."""
    saved = [(o, o.location.copy(), o.scale.copy()) for o in objs]
    for o in objs:
        o.location *= 0.001
        o.scale *= 0.001
    _select_only(objs)
    bpy.ops.export_scene.gltf(filepath=str(path), export_format="GLB", use_selection=True)
    for o, loc, sc in saved:
        o.location, o.scale = loc, sc
    return path
