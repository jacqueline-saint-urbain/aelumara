#!/usr/bin/env python3
"""Terrain generator for the Godot version of Aelumara (step 1 of the Godot plan).

Builds the relief of both islands from the same outlines as index.html and
writes everything the Godot project needs into godot/terrain/:

- home.bin, far.bin   float32 height grids (row-major, z rows then x columns)
- meta.json           grid origins and steps, place names, lake and river data
- home.glb, far.glb   terrain meshes; COLOR_0 = weights (sand, grass, jungle floor, rock),
                      TEXCOORD_1.x = mud/pebbles (river bed, lake shore)
- water.glb           river Aubeline and the cascade from lake d'Aube (ribbons, UV.y along the flow)
- sea_depth.png       sea depth around the islands (R = depth / 8 m), for the sea shader

Deterministic: same input, same output. Sea level is y = 0. World axes as in
index.html: x east, z south, the far island centred at [0, -150].

Usage: python3 godot/tools/terrain.py
"""
import json
import math
import os
import struct

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "terrain")
FAR_CENTER = (0.0, -150.0)  # same as FAR_ISLAND in sim.py

NAMES = {"mountain": "Mont Séréval", "lake": "Lac d'Aube", "river": "Aubeline"}  # named by spark, 2026-10-26


# ---------------------------------------------------------------- noise ---
def _hash(ix, iz, seed):
    """Integer hash to [0, 1], vectorised over numpy int arrays."""
    m = np.uint64(0xFFFFFFFF)
    h = (ix.astype(np.uint64) * np.uint64(374761393) + iz.astype(np.uint64) * np.uint64(668265263)
         + np.uint64(seed * 2654435761 % 2 ** 32)) & m
    h = ((h ^ (h >> np.uint64(13))) * np.uint64(1274126177)) & m
    return ((h ^ (h >> np.uint64(16))) & np.uint64(0xFFFF)).astype(float) / 65535.0


def value_noise(x, z, seed):
    """Smooth value noise in [0, 1] on numpy arrays."""
    x, z = np.asarray(x, float), np.asarray(z, float)
    ix, iz = np.floor(x).astype(np.int64), np.floor(z).astype(np.int64)
    fx, fz = x - ix, z - iz
    ux, uz = fx * fx * (3 - 2 * fx), fz * fz * (3 - 2 * fz)
    h = _hash
    a, b = h(ix, iz, seed), h(ix + 1, iz, seed)
    c, d = h(ix, iz + 1, seed), h(ix + 1, iz + 1, seed)
    return (a + (b - a) * ux) * (1 - uz) + (c + (d - c) * ux) * uz


def fbm(x, z, seed, octaves=4):
    total, amp, norm = 0.0, 1.0, 0.0
    for o in range(octaves):
        total = total + amp * value_noise(x * 2 ** o, z * 2 ** o, seed + o * 17)
        norm += amp
        amp *= 0.5
    return total / norm


def smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3 - 2 * t)


# ------------------------------------------------------ far island shape ---
# Port of LONG in index.html (owner's shape 3 with her retouch), in island-local coordinates.
O = (-8.547, -6.970)


def _E(t):
    return 105 + 14 * np.sin(3 * t) + 9 * np.sin(7 * t + 1) + 25 * np.sin(t + 0.3)


def edge(a):
    d = np.arctan2(np.sin(a + 2.8), np.cos(a + 2.8))
    bulge = 90 * np.exp(-((d / 0.22) ** 2))
    t = np.arctan2(1.9 * np.sin(a), 0.75 * np.cos(a))
    e = _E(t)
    return np.hypot(np.cos(t) * e * 1.9, np.sin(t) * e * 0.75) + bulge


def beach(a):
    return 8 + 22 * np.maximum(0, np.sin(a)) ** 1.5


MOUNT = (-145.0, -32.0)     # Mont Séréval, local
MOUNT_R, MOUNT_H = 78.0, 46.0
CRATER_R, CRATER_FLOOR = 12.0, 41.0   # lake level (Lac d'Aube) is computed from the rim, see far_island()
HILLS = [(-95, -55, 22, 14), (-205, 12, 18, 11)]
KNOTS = [(-122, -14), (-100, -4), (-78, -18), (-52, -12), (-30, 6), (-8, 2), (14, 16), (28, 36), (40, 56),
         (46, 78), (50, 100), (52, 112), (54, 124)]


def jungle_mask(lx, lz, in_grass):
    blob = lambda cx, cz, rx, rz: ((lx - cx) / rx) ** 2 + ((lz - cz) / rz) ** 2 < 1
    band = (lz < -8 + 12 * np.sin(lx / 37)) & (lx < 110)
    near_mount = np.hypot(lx - MOUNT[0], lz - MOUNT[1]) < 95
    return in_grass & (band | near_mount | blob(-42, 12, 72, 30) | blob(132, -14, 42, 22))


def catmull(points, n):
    p = [points[0]] + list(points) + [points[-1]]
    out = []
    for i in range(1, len(p) - 2):
        p0, p1, p2, p3 = map(np.array, p[i - 1:i + 3])
        for t in np.linspace(0, 1, 24, endpoint=False):
            out.append(0.5 * (2 * p1 + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t
                              + (-p0 + 3 * p1 - 3 * p2 + p3) * t ** 3))
    out.append(np.array(points[-1], float))
    out = np.array(out)
    seg = np.hypot(*np.diff(out, axis=0).T)
    s = np.concatenate([[0], np.cumsum(seg)])
    u = np.linspace(0, s[-1], n)
    return np.stack([np.interp(u, s, out[:, 0]), np.interp(u, s, out[:, 1])], axis=1)


def dist_to_polyline(px, pz, line):
    """Distance from points to a polyline, and the index of the nearest segment."""
    best = np.full(px.shape, np.inf)
    idx = np.zeros(px.shape, dtype=int)
    for i in range(len(line) - 1):
        ax, az = line[i]
        bx, bz = line[i + 1]
        vx, vz = bx - ax, bz - az
        ll = vx * vx + vz * vz or 1e-9
        t = np.clip(((px - ax) * vx + (pz - az) * vz) / ll, 0, 1)
        d = np.hypot(px - (ax + t * vx), pz - (az + t * vz))
        m = d < best
        best[m] = d[m]
        idx[m] = i
    return best, idx


# --------------------------------------------------------------- islands ---
def home_island():
    step = 1.0
    xs = np.arange(-46, 46 + step, step)
    zs = np.arange(-46, 46 + step, step)
    x, z = np.meshgrid(xs, zs)
    r, a = np.hypot(x, z), np.arctan2(z, x)
    g = 20 + 0.6 * (np.sin(a * 7 + 8) * 0.6 + np.sin(a * 13 + 18.4) * 0.4)   # grass edge, as in index.html
    s = r - g
    dome = 0.9 + 1.8 * (1 - np.clip(r / 20, 0, 1) ** 2.2)
    knoll = 2.6 * np.exp(-(((x - 14) ** 2 + (z + 14) ** 2) / (2 * 3.2 ** 2)))   # rocky lookout, north-east
    bumps = 0.35 * (fbm(x / 9, z / 9, 3) - 0.5)
    inland = dome + knoll + bumps
    dunes = 0.28 * np.sin(a * 9 + 1.3) * smoothstep(0.5, 2, s) * (1 - smoothstep(4, 6, s))
    coast = np.interp(s, [0, 6, 6.5, 10, 16, 26], [0.9, 0.15, 0.0, -2.0, -4.0, -7.0]) + dunes
    y = np.where(s < 0, inland, coast)
    y = np.where((s >= -1.5) & (s < 0), inland + (coast - inland) * 0, y)
    sand = smoothstep(-1.5, 0.5, s)
    rock = np.clip(knoll / 2.6 * 1.6 - 0.6, 0, 1) * (1 - sand)
    w = np.stack([sand, (1 - sand) * (1 - rock), np.zeros_like(y), rock], axis=-1)
    return dict(name="home", x=xs, z=zs, y=y, w=w, mud=np.zeros_like(y))


def far_island():
    step = 2.0
    cx, cz = FAR_CENTER
    lxs = np.arange(-262, 262 + step, step)
    lzs = np.arange(-120, 116 + step, step)
    lx, lz = np.meshgrid(lxs, lzs)
    a = np.arctan2(lz - O[1], lx - O[0])
    d = np.hypot(lx - O[0], lz - O[1])
    e, b = edge(a), beach(a)
    gedge = e - b
    inside = gedge - d            # metres inside the grass edge (negative on the beach and in the sea)
    in_grass = inside > 1.5

    # Interior: rolling plains, jungle hills, two hills, Mont Séréval with the crater of Lac d'Aube.
    t = smoothstep(0, 14, inside)
    plains = 1.3 + t * (0.6 + 1.6 * fbm(lx / 70, lz / 70, 11))
    jm = jungle_mask(lx, lz, in_grass).astype(float)
    jm = _blur(jm, 4)
    ridges = 1 - np.abs(2 * fbm(lx / 45, lz / 45, 23) - 1)
    jungle_hills = jm * t * (2.5 + 6.5 * ridges ** 2)
    hills = sum(h * np.exp(-(((lx - hx) ** 2 + (lz - hz) ** 2) / (2 * (r * 0.55) ** 2))) for hx, hz, r, h in HILLS)
    rm = np.hypot(lx - MOUNT[0], lz - MOUNT[1])
    am = np.arctan2(lz - MOUNT[1], lx - MOUNT[0])
    ridge_n = fbm(np.cos(am) * 3 + 50, np.sin(am) * 3 + 50, 31)
    rough = 0.9 + 0.2 * ridge_n * np.clip(rm / 30, 0, 1)   # ridges on the flanks, a smooth summit
    reach = MOUNT_R * (0.8 + 0.4 * fbm(np.cos(am) * 1.5 + 7, np.sin(am) * 1.5 + 7, 37))   # spurs and gullies
    gullies = 1 + 0.25 * (fbm(lx / 22, lz / 22, 41) - 0.5) * np.clip(rm / 20, 0, 1)
    mountain = MOUNT_H * (1 - smoothstep(0, reach, rm)) * rough * gullies
    rim = MOUNT_H * (1 - smoothstep(0, MOUNT_R, CRATER_R)) * rough
    crater = CRATER_FLOOR + (rim - CRATER_FLOOR) * (rm / CRATER_R) ** 2
    mountain = np.where(rm < CRATER_R, crater, mountain)
    # The lake overflows through a notch in the rim, toward the spring of the Aubeline.
    src = np.array(KNOTS[0], float)
    out_a = math.atan2(src[1] - MOUNT[1], src[0] - MOUNT[0])
    da = np.arctan2(np.sin(am - out_a), np.cos(am - out_a))
    notch = 3.2 * np.exp(-((da / 0.12) ** 2)) * np.exp(-(((rm - CRATER_R) / 3.5) ** 2))
    mountain = mountain - notch
    y_in = plains + jungle_hills + np.maximum(hills, 0) * t

    # Coast: beach from the grass edge to the outline, then the sea floor.
    sc = d - e
    beach_y = np.interp(np.clip(-sc / np.maximum(b, 1), 0, 1), [0, 1], [0.5, 1.3])
    sea_y = np.interp(sc, [0, 4.5, 10, 30, 80], [0.5, 0.0, -2.5, -5.0, -7.0])
    y = np.where(inside > 0, y_in, np.where(sc < 0, beach_y, sea_y))
    # Blend the grass edge into the beach over 3 m so there is no step.
    blend = smoothstep(-1.5, 1.5, inside)
    y = np.where((inside > -1.5) & (inside < 1.5), beach_y * (1 - blend) + y_in * blend, y)

    # The mountain rises over everything, down into the sea on its north and west sides (sea cliffs).
    y = np.maximum(y, 1.0 + mountain - 9.0 * smoothstep(MOUNT_R * 0.55, MOUNT_R, rm))

    # Cascade: from the notch down to the spring, a channel 0.8 m deep.
    cas = np.array([[MOUNT[0] + math.cos(out_a) * r, MOUNT[1] + math.sin(out_a) * r]
                    for r in np.linspace(CRATER_R - 1, math.hypot(*(src - MOUNT)), 24)])
    cd, _ = dist_to_polyline(lx, lz, cas)
    y = y - 0.8 * (1 - smoothstep(1.0, 3.0, cd)) * (rm > CRATER_R - 1)

    # Lac d'Aube: its level sits just under the lowest point of the rim (the notch); the bowl is dug under it.
    ring = (rm > CRATER_R - 1) & (rm < CRATER_R + 1)
    lake_level = float(y[ring].min()) - 0.4
    bowl = lake_level - 2.5 + 3.9 * (rm / CRATER_R) ** 2
    y = np.where(rm < CRATER_R, np.minimum(y, bowl), y)

    # River Aubeline: water level falls monotonically from the spring to the sea; the bed is carved under it.
    river = catmull(KNOTS, 220)
    ry = _sample(y, lxs, lzs, river[:, 0], river[:, 1])
    level = np.zeros(len(river))
    level[0] = ry[0] - 0.5
    for i in range(1, len(river)):
        level[i] = max(0.0, min(level[i - 1], ry[i] - 0.5))
    width = 3 + 7 * np.arange(len(river)) / len(river)
    depth = 0.6 + 1.2 * np.arange(len(river)) / len(river)
    rd, ri = dist_to_polyline(lx, lz, river)
    half = width[ri] / 2
    bed = level[ri] - depth[ri]
    bank = 3 + half * 0.6
    f = smoothstep(half, half + bank, rd)
    carved = bed * (1 - f) + y * f
    y = np.where(rd < half + bank, np.minimum(y, carved), y)

    # Weights: sand, grass, jungle floor, rock; mud/pebbles in the river bed and on the lake shore.
    gz, gx = np.gradient(y, step)
    slope = np.hypot(gx, gz)
    sand = np.maximum(smoothstep(-2.0, 1.0, -inside) * (1 - smoothstep(2.0, 4.0, y)), (y < 0.3).astype(float))
    rock = np.clip(smoothstep(0.9, 1.3, slope) + smoothstep(34, 42, y) * (rm < MOUNT_R), 0, 1)
    rock = np.where(rm < CRATER_R - 2, 0.25, rock)
    upland = smoothstep(14, 26, y) * (rm < MOUNT_R)   # Mont Séréval: meadow and forest floor rather than jungle litter
    jungle = jm * (1 - sand) * (1 - rock) * (1 - 0.7 * upland)
    grass = np.clip(1 - sand - rock - jungle, 0, 1)
    tot = sand + grass + jungle + rock + 1e-6
    w = np.stack([sand, grass, jungle, rock], axis=-1) / tot[..., None]
    mud = np.maximum(1 - smoothstep(half + 0.5, half + 2.5, rd), (1 - smoothstep(2, 4, np.abs(rm - 10))) * (rm < 15))
    mud = np.maximum(mud, (1 - smoothstep(1.0, 2.5, cd)) * (rm > CRATER_R - 1) * (rm < math.hypot(*(src - MOUNT))))

    water = dict(lake_level=lake_level, river=river, level=level, width=width, cascade=cas,
                 cascade_y=_sample(y, lxs, lzs, cas[:, 0], cas[:, 1]) + 0.3)
    return dict(name="far", x=lxs + cx, z=lzs + cz, y=y, w=w, mud=mud, water=water, offset=(cx, cz))


def _blur(m, radius):
    k = np.exp(-np.linspace(-2, 2, 2 * radius + 1) ** 2)
    k /= k.sum()
    m = np.apply_along_axis(lambda r: np.convolve(r, k, mode="same"), 1, m)
    return np.apply_along_axis(lambda c: np.convolve(c, k, mode="same"), 0, m)


def _sample(y, xs, zs, px, pz):
    """Bilinear height sample on a grid (xs, zs are the grid axes)."""
    step = xs[1] - xs[0]
    fx = np.clip((np.asarray(px) - xs[0]) / step, 0, len(xs) - 1.001)
    fz = np.clip((np.asarray(pz) - zs[0]) / step, 0, len(zs) - 1.001)
    ix, iz = np.floor(fx).astype(int), np.floor(fz).astype(int)
    tx, tz = fx - ix, fz - iz
    a, b = y[iz, ix], y[iz, ix + 1]
    c, d = y[iz + 1, ix], y[iz + 1, ix + 1]
    return (a * (1 - tx) + b * tx) * (1 - tz) + (c * (1 - tx) + d * tx) * tz


# ------------------------------------------------------------ public API ---
_GRIDS = None


def height_at(x, z):
    """World height at (x, z) in metres, sea level 0. Used by tests and by spark's checks."""
    global _GRIDS
    if _GRIDS is None:
        _GRIDS = [home_island(), far_island()]
    for g in _GRIDS:
        if g["x"][0] <= x <= g["x"][-1] and g["z"][0] <= z <= g["z"][-1]:
            return float(_sample(g["y"], g["x"], g["z"], x, z))
    return -7.0


# ---------------------------------------------------------------- output ---
def grid_mesh(g):
    xs, zs, y = g["x"], g["z"], g["y"]
    nz, nx = y.shape
    X, Z = np.meshgrid(xs, zs)
    pos = np.stack([X, y, Z], axis=-1).reshape(-1, 3).astype(np.float32)
    gz, gx = np.gradient(y, xs[1] - xs[0])
    n = np.stack([-gx, np.ones_like(y), -gz], axis=-1)
    n /= np.linalg.norm(n, axis=-1, keepdims=True)
    uv = np.stack([X / 8.0, Z / 8.0], axis=-1).reshape(-1, 2).astype(np.float32)
    uv2 = np.stack([g["mud"], np.zeros_like(y)], axis=-1).reshape(-1, 2).astype(np.float32)
    col = g["w"].reshape(-1, 4).astype(np.float32)
    # Skip quads that are entirely deep under the sea.
    i = np.arange(nz - 1)[:, None] * nx + np.arange(nx - 1)[None, :]
    quad_min = np.minimum.reduce([y[:-1, :-1], y[:-1, 1:], y[1:, :-1], y[1:, 1:]])
    i = i[quad_min > -5.5]
    tris = np.stack([i, i + nx, i + 1, i + 1, i + nx, i + nx + 1], axis=-1).reshape(-1).astype(np.uint32)
    return dict(POSITION=pos, NORMAL=n.reshape(-1, 3).astype(np.float32), TEXCOORD_0=uv, TEXCOORD_1=uv2,
                COLOR_0=col, indices=tris)


def ribbon_mesh(line, ys, widths, uv_scale=6.0):
    pos, uv, idx = [], [], []
    run = 0.0
    for i, (p, yy, w) in enumerate(zip(line, ys, widths)):
        q0, q1 = line[max(0, i - 1)], line[min(len(line) - 1, i + 1)]
        t = np.array(q1) - np.array(q0)
        t /= np.linalg.norm(t) or 1
        nrm = np.array([-t[1], t[0]]) * w / 2
        if i:
            run += float(np.linalg.norm(np.array(p) - np.array(line[i - 1])))
        for side, sgn in ((0, -1), (1, 1)):
            pos.append([p[0] + sgn * nrm[0], yy, p[1] + sgn * nrm[1]])
            uv.append([side, run / uv_scale])
        if i:
            k = (i - 1) * 2
            idx += [k, k + 2, k + 1, k + 1, k + 2, k + 3]
    pos = np.array(pos, np.float32)
    return dict(POSITION=pos, NORMAL=np.tile(np.array([[0, 1, 0]], np.float32), (len(pos), 1)),
                TEXCOORD_0=np.array(uv, np.float32), indices=np.array(idx, np.uint32))


def write_glb(path, meshes):
    """Minimal glTF 2.0 binary writer: one node per named mesh, no materials (set in Godot)."""
    bin_ = bytearray()
    views, accs, gl_meshes, nodes = [], [], [], []

    def add(arr, target):
        nonlocal bin_
        while len(bin_) % 4:
            bin_ += b"\0"
        data = arr.tobytes()
        views.append({"buffer": 0, "byteOffset": len(bin_), "byteLength": len(data), "target": target})
        bin_ += data
        comp = 5125 if arr.dtype == np.uint32 else 5126
        typ = {1: "SCALAR", 2: "VEC2", 3: "VEC3", 4: "VEC4"}[1 if arr.ndim == 1 else arr.shape[1]]
        acc = {"bufferView": len(views) - 1, "componentType": comp, "count": int(arr.shape[0]), "type": typ}
        if typ == "VEC3" and comp == 5126:
            acc["min"] = arr.min(axis=0).tolist()
            acc["max"] = arr.max(axis=0).tolist()
        accs.append(acc)
        return len(accs) - 1

    for name, m in meshes:
        attrs = {k: add(v, 34962) for k, v in m.items() if k != "indices"}
        ind = add(m["indices"], 34963)
        gl_meshes.append({"name": name, "primitives": [{"attributes": attrs, "indices": ind}]})
        nodes.append({"name": name, "mesh": len(gl_meshes) - 1})
    gltf = {"asset": {"version": "2.0", "generator": "aelumara terrain.py"}, "scene": 0,
            "scenes": [{"nodes": list(range(len(nodes)))}], "nodes": nodes, "meshes": gl_meshes,
            "accessors": accs, "bufferViews": views, "buffers": [{"byteLength": len(bin_)}]}
    js = json.dumps(gltf, separators=(",", ":")).encode()
    js += b" " * (-len(js) % 4)
    while len(bin_) % 4:
        bin_ += b"\0"
    with open(path, "wb") as f:
        f.write(struct.pack("<III", 0x46546C67, 2, 12 + 8 + len(js) + 8 + len(bin_)))
        f.write(struct.pack("<II", len(js), 0x4E4F534A) + js)
        f.write(struct.pack("<II", len(bin_), 0x004E4942) + bytes(bin_))


def main():
    os.makedirs(OUT, exist_ok=True)
    home, far = home_island(), far_island()
    meta = {"sea_level": 0.0, "names": NAMES, "islands": {}}
    for g in (home, far):
        g["y"].astype(np.float32).tofile(os.path.join(OUT, g["name"] + ".bin"))
        meta["islands"][g["name"]] = {"x0": float(g["x"][0]), "z0": float(g["z"][0]),
                                      "step": float(g["x"][1] - g["x"][0]), "nx": len(g["x"]), "nz": len(g["z"])}
        write_glb(os.path.join(OUT, g["name"] + ".glb"), [(g["name"] + "_terrain", grid_mesh(g))])

    cx, cz = FAR_CENTER
    wtr = far["water"]
    river = wtr["river"] + [cx, cz]
    ys = wtr["level"] + 0.02
    keep = np.arange(len(river))
    lv = wtr["level"]
    mouth = int(np.argmax(lv <= 0.0)) if (lv <= 0.0).any() else len(lv) - 1
    keep = keep[: mouth + 4]
    cascade = wtr["cascade"] + [cx, cz]
    write_glb(os.path.join(OUT, "water.glb"), [
        ("river", ribbon_mesh(river[keep].tolist(), np.maximum(ys[keep], 0.02).tolist(), wtr["width"][keep].tolist())),
        ("cascade", ribbon_mesh(cascade.tolist(), wtr["cascade_y"].tolist(), [2.4] * len(cascade), uv_scale=3.0)),
    ])
    meta["lake"] = {"name": NAMES["lake"], "center": [MOUNT[0] + cx, MOUNT[1] + cz],
                    "level": round(wtr["lake_level"], 2), "radius": round(CRATER_R * math.sqrt(2.5 / 3.9), 2)}
    meta["mountain"] = {"name": NAMES["mountain"], "center": [MOUNT[0] + cx, MOUNT[1] + cz]}
    meta["river"] = {"name": NAMES["river"], "points": river[keep][::10].round(1).tolist()}

    # Sea depth texture: 2 m per pixel over the area of both islands.
    x0, x1, z0, z1 = -280.0, 280.0, -290.0, 56.0
    px = np.arange(x0, x1, 2.0) + 1
    pz = np.arange(z0, z1, 2.0) + 1
    PX, PZ = np.meshgrid(px, pz)
    hgt = np.full(PX.shape, -7.0)
    for g in (home, far):
        m = (PX >= g["x"][0]) & (PX <= g["x"][-1]) & (PZ >= g["z"][0]) & (PZ <= g["z"][-1])
        hgt[m] = _sample(g["y"], g["x"], g["z"], PX[m], PZ[m])
    depth = np.clip(-hgt / 8.0, 0, 1)
    Image.fromarray((depth * 255).astype(np.uint8), "L").save(os.path.join(OUT, "sea_depth.png"))
    meta["sea_depth"] = {"x0": x0, "z0": z0, "x1": x1, "z1": z1}
    with open(os.path.join(OUT, "meta.json"), "w") as f:
        json.dump(meta, f, indent=1, ensure_ascii=False)
    print("terrain written:", {k: (v["nx"], v["nz"]) for k, v in meta["islands"].items()},
          "peak %.1f m" % far["y"].max(), "lake %.1f m" % wtr["lake_level"])


if __name__ == "__main__":
    main()
