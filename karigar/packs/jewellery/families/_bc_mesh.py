"""Numpy mesh helpers shared by the bangle and chain families (no bpy at import time).

Everything here works on plain arrays: a mesh is (V, F) with V float (n, 3) and F int
(m, 4) quads. Building hundreds of chain links or a finely displaced bangle this way is
fast (no per-face Python, no booleans); `to_object` turns the arrays into one Blender
object at the end. Quads are wound so the signed volume is positive (normals outward).
"""
from __future__ import annotations

import math

import numpy as np


def grid_faces(m: int, k: int) -> np.ndarray:
    """Quads of an m x k grid closed in both directions (a torus-topology tube)."""
    i = np.arange(m)[:, None]
    j = np.arange(k)[None, :]
    a = i * k + j
    b = ((i + 1) % m) * k + j
    c = ((i + 1) % m) * k + (j + 1) % k
    d = i * k + (j + 1) % k
    return np.stack([a, b, c, d], -1).reshape(-1, 4)


def signed_volume(V: np.ndarray, F: np.ndarray) -> float:
    v0, v1, v2, v3 = (V[F[:, n]] for n in range(4))
    t1 = np.einsum("ij,ij->i", v0, np.cross(v1, v2))
    t2 = np.einsum("ij,ij->i", v0, np.cross(v2, v3))
    return float((t1.sum() + t2.sum()) / 6.0)


def orient(V: np.ndarray, F: np.ndarray):
    """Flip the winding if the closed mesh's normals point inward."""
    if signed_volume(V, F) < 0:
        F = F[:, ::-1].copy()
    return V, F


def superellipse(k: int, expo: float = 2.0):
    """(cos, sin)-like coordinates of k points on a unit superellipse (2 = circle)."""
    u = 2 * math.pi * np.arange(k) / k
    c, s = np.cos(u), np.sin(u)
    if expo != 2.0:
        c = np.sign(c) * np.abs(c) ** (2 / expo)
        s = np.sign(s) * np.abs(s) ** (2 / expo)
    return c, s


def sweep(C, N, B, rn, rb, k: int = 8, expo: float = 2.0):
    """Closed tube along the closed centreline C (m, 3). The cross-section at point i is
    the superellipse rn[i] * N[i] x rb[i] * B[i]. Returns (V, F) wound outward."""
    m = len(C)
    rn = np.broadcast_to(np.asarray(rn, float), (m,))
    rb = np.broadcast_to(np.asarray(rb, float), (m,))
    cu, su = superellipse(k, expo)
    V = (C[:, None, :] + rn[:, None, None] * cu[None, :, None] * N[:, None, :]
         + rb[:, None, None] * su[None, :, None] * B[:, None, :]).reshape(-1, 3)
    return orient(V, grid_faces(m, k))


def torus(R: float, r: float, m: int = 32, k: int = 10):
    """Torus in the XY plane centred at the origin (axis Z)."""
    t = 2 * math.pi * np.arange(m) / m
    C = np.stack([R * np.cos(t), R * np.sin(t), np.zeros(m)], 1)
    N = np.stack([np.cos(t), np.sin(t), np.zeros(m)], 1)
    B = np.tile([0.0, 0.0, 1.0], (m, 1))
    return sweep(C, N, B, r, r, k)


def transform(V: np.ndarray, M: np.ndarray) -> np.ndarray:
    return V @ M[:3, :3].T + M[:3, 3]


def rot(axis: str, a: float) -> np.ndarray:
    c, s = math.cos(a), math.sin(a)
    M = np.eye(4)
    i, j = {"x": (1, 2), "y": (2, 0), "z": (0, 1)}[axis]
    M[i, i], M[i, j], M[j, i], M[j, j] = c, -s, s, c
    return M


def trans(x: float, y: float, z: float) -> np.ndarray:
    M = np.eye(4)
    M[:3, 3] = (x, y, z)
    return M


class Soup:
    """Accumulates closed quad meshes (separate components) into one (V, F)."""

    def __init__(self):
        self.vs: list[np.ndarray] = []
        self.fs: list[np.ndarray] = []
        self.n = 0

    def add(self, V: np.ndarray, F: np.ndarray) -> None:
        self.vs.append(V)
        self.fs.append(F + self.n)
        self.n += len(V)

    def arrays(self):
        return np.concatenate(self.vs), np.concatenate(self.fs)


def to_object(V: np.ndarray, F: np.ndarray, name: str, smooth: bool = True):
    """One Blender mesh object from quad arrays (in the scene collection)."""
    import bpy
    me = bpy.data.meshes.new(name)
    nf, k = F.shape
    me.vertices.add(len(V))
    me.vertices.foreach_set("co", np.ascontiguousarray(V, dtype=np.float32).ravel())
    me.loops.add(nf * k)
    me.loops.foreach_set("vertex_index", np.ascontiguousarray(F, dtype=np.int32).ravel())
    me.polygons.add(nf)
    me.polygons.foreach_set("loop_start", np.arange(0, nf * k, k, dtype=np.int32))
    me.update(calc_edges=True)
    me.polygons.foreach_set("use_smooth", np.full(nf, smooth, dtype=bool))
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def join(objs, name: str):
    """Concatenate objects' meshes (world space) into one new object; no boolean, so
    separate solids stay separate components. The inputs are removed."""
    import bmesh
    import bpy
    bm = bmesh.new()
    for o in objs:
        tmp = o.data.copy()
        tmp.transform(o.matrix_world)
        bm.from_mesh(tmp)
        bpy.data.meshes.remove(tmp)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    for o in objs:
        bpy.data.objects.remove(o, do_unlink=True)
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    return ob
