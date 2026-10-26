#!/usr/bin/env python3
"""Flora and rocks for the Godot version of Aelumara (step 2 of the Godot plan).

Places the CC0 low-poly models of godot/models/ on the relief from terrain.py,
zone by zone, as the owner asked on 2026-10-26:

- beaches (Trio Island and the far island): palm trees, low dense bushes, flowers
- jungle: dense and diverse (several trees, palms, large plants, bushes, flowers)
- Mont Séréval: more uniform (one tree family dominates) but still varied, thinning toward the top
- plains: grass and flowers, sparse trees
- rocks nearly everywhere, gathered along the bed of the Aubeline and around Lac d'Aube

Writes godot/terrain/flora.json (layers and models) and flora.bin (float32 records
x, y, z, rotation, size in metres; Godot scales each model so that its height, or half its
width for flat and wide plants, matches that size).

Trees come in two kinds (owner's request, 2026-10-26): resource trees, spread at least
RESOURCE_SPACING metres apart, which the islanders can use and which are always drawn, and decor
trees, which Godot hides around the camera when it is zoomed in so the residents stay visible.
Inside each tree model the resource trees come first ("resource" = how many); their list is also
written to godot/terrain/resource_trees.json for the simulation.
Deterministic: fixed seeds.

Usage: python3 godot/tools/flora.py   (after terrain.py)
"""
import json
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import terrain  # noqa: E402
from terrain import smoothstep  # noqa: E402

ROOT = os.path.join(terrain.HERE, "..", "..")
OUT = terrain.OUT

KN, KP, KT = "kenney-nature/", "kenney-pirate/", "kenney-town/"
KK, QN, QP = "kaykit-forest/", "quaternius-nature/", "quaternius-platformer/"


def kk(*names):
    return [KK + n + "_Color1.gltf" for n in names]


def qn(*names):
    return [QN + n + ".obj" for n in names]


def kn(*names):
    return [KN + n + ".glb" for n in names]


# Model families: (models, height range in metres). Weights are equal inside a family unless repeated.
PALMS = (kn("tree_palm", "tree_palmBend", "tree_palmTall", "tree_palmDetailedTall")
         + [KP + n + ".glb" for n in ("palm-bend", "palm-detailed-bend", "palm-detailed-straight", "palm-straight")]
         + qn("PalmTree_1", "PalmTree_2", "PalmTree_3", "PalmTree_4"), (6.5, 11.0))
JUNGLE_TREES = (kk("Tree_1_C", "Tree_2_D", "Tree_2_E", "Tree_3_C", "Tree_4_C")
                + qn("CommonTree_5")
                + kn("tree_detailed", "tree_oak"), (9.0, 16.0))
MOUNTAIN_MAIN = (kk("Tree_2_A", "Tree_2_B", "Tree_2_C", "Tree_2_D", "Tree_2_E"), (5.0, 10.0))
MOUNTAIN_OTHER = (kk("Tree_4_A", "Tree_4_B") + kn("tree_tall", "tree_simple"), (5.0, 9.0))
PLAINS_TREES = (kn("tree_plateau", "tree_plateau") + kk("Tree_1_A", "Tree_1_B", "Tree_3_A", "Tree_3_B")
                + qn("CommonTree_3", "CommonTree_4"), (6.0, 10.0))
LOW_BUSHES = (kk("Bush_1_C", "Bush_1_D", "Bush_2_B", "Bush_2_C", "Bush_4_C")
              + kn("plant_bush", "plant_bushDetailed", "plant_bushLarge", "plant_bushTriangle")
              + qn("Bush_1", "Bush_2"), (0.6, 1.3))
BIG_BUSHES = (kk("Bush_1_E", "Bush_1_F", "Bush_2_E", "Bush_2_F", "Bush_4_E") + qn("BushBerries_1", "BushBerries_2"),
              (1.0, 2.0))
JUNGLE_PLANTS = (qn("Plant_1", "Plant_2", "Plant_3", "Plant_4", "Plant_5", "Plant_5")
                 + [QP + "Plant_Large.gltf", QP + "Plant_Small.gltf"]
                 + kn("plant_flatTall", "plant_flatShort") + kk("Bush_3_A", "Bush_3_B", "Bush_3_C"), (0.9, 2.4))
FLOWERS = (kn(*[f"flower_{c}{v}" for c in ("red", "yellow", "purple") for v in "ABC"]) + qn("Flowers", "Flowers"),
           (0.3, 0.6))
GRASS = (kn("grass_large", "grass_leafsLarge") + [KP + "grass-plant.glb", KP + "grass.glb"] + qn("Grass_Short"),
         (0.35, 0.8))
ROCKS_SMALL = (kn("rock_smallA", "rock_smallB", "rock_smallD", "rock_smallE", "rock_smallG", "rock_smallH",
                  "rock_smallFlatA", "rock_largeA", "rock_largeC", "rock_largeE")
               + qn("Rock_1", "Rock_2", "Rock_3", "Rock_5", "Rock_6"), (0.25, 0.9))
ROCKS_BIG = (kk("Rock_1_D", "Rock_1_G", "Rock_1_J", "Rock_1_K", "Rock_2_C", "Rock_2_D", "Rock_2_E", "Rock_2_G",
                "Rock_3_G", "Rock_3_K", "Rock_3_M", "Rock_3_Q") + kn("rock_tallA", "rock_tallB", "rock_tallG"),
             (1.2, 4.0))
WATER_ROCKS = (qn(*[f"Rock_Moss_{i}" for i in range(1, 8)]) + kk("Rock_3_A", "Rock_3_E", "Rock_1_D", "Rock_2_C")
               + kn("rock_largeB", "rock_largeD", "rock_largeF", "rock_tallG", "rock_tallH"), (0.4, 1.8))
BEACH_ROCKS = ([KP + n + ".glb" for n in ("rocks-sand-a", "rocks-sand-b", "rocks-sand-c")], (0.9, 2.2))
FOREST_FLOOR = (qn("WoodLog_Moss", "TreeStump_Moss") + kn("mushroom_redGroup", "log", "stump_old"), (0.3, 0.8))
LILIES = (qn("Lilypad"), (0.05, 0.12))

# Layers: name, family, fade distance in metres (0 = always drawn), cast shadows.
LAYERS = [
    ("palms", PALMS, 0, True), ("jungle_trees", JUNGLE_TREES, 0, True), ("mountain_main", MOUNTAIN_MAIN, 0, True),
    ("mountain_other", MOUNTAIN_OTHER, 0, True), ("plains_trees", PLAINS_TREES, 0, True),
    ("big_bushes", BIG_BUSHES, 220, False), ("low_bushes", LOW_BUSHES, 140, False),
    ("jungle_plants", JUNGLE_PLANTS, 120, False), ("rocks_big", ROCKS_BIG, 0, True),
    ("water_rocks", WATER_ROCKS, 160, False), ("beach_rocks", BEACH_ROCKS, 260, True),
    ("rocks_small", ROCKS_SMALL, 90, False), ("forest_floor", FOREST_FLOOR, 60, False),
    ("flowers", FLOWERS, 60, False), ("grass", GRASS, 45, False), ("lilies", LILIES, 160, False),
]


TREE_LAYERS = ("palms", "jungle_trees", "mountain_main", "mountain_other", "plains_trees")
RESOURCE_SPACING = 11.0   # metres between two resource trees


def jittered(rng, x0, x1, z0, z1, spacing):
    """One candidate per cell of a grid with the given spacing, at a random spot in the cell."""
    gx, gz = np.meshgrid(np.arange(x0, x1, spacing), np.arange(z0, z1, spacing))
    gx = gx.ravel() + rng.random(gx.size) * spacing
    gz = gz.ravel() + rng.random(gz.size) * spacing
    return gx, gz


class Placer:
    def __init__(self):
        self.out = {name: [] for name, *_ in LAYERS}
        self.family = {name: fam for name, fam, *_ in LAYERS}

    def add(self, layer, rng, x, z, y, height_scale=1.0, sink=0.08):
        models, (h0, h1) = self.family[layer]
        for xi, zi, yi in zip(x, z, y):
            m = int(rng.integers(len(models)))
            h = (h0 + (h1 - h0) * rng.random()) * height_scale
            self.out[layer].append((m, float(xi), float(yi) - sink * h, float(zi), float(rng.random() * math.tau), h))


def keep_clear(x, z, points, radius):
    """Mask of candidates farther than radius from every point."""
    ok = np.ones(x.shape, bool)
    for px, pz in points:
        ok &= np.hypot(x - px, z - pz) > radius
    return ok


def sim_points():
    state = json.load(open(os.path.join(ROOT, "state.json")))
    world = json.load(open(os.path.join(ROOT, "world.json")))
    pts = [n["pos"] for n in state["nodes"]] + [p["pos"] for p in state["projects"]]
    pts += [e["pos"] for e in world["entities"]]
    return pts


def home(placer, g):
    """Trio Island: a tropical beach all around, the village in the middle stays open."""
    xs, zs, y = g["x"], g["z"], g["y"]
    zn = g["zones"]
    s_at = lambda px, pz: terrain._sample(zn["s"], xs, zs, px, pz)
    y_at = lambda px, pz: terrain._sample(y, xs, zs, px, pz)
    pts = sim_points()
    rng = np.random.default_rng(101)

    def take(spacing, keep, clear_r, layer, **kw):
        px, pz = jittered(rng, xs[0], xs[-1], zs[0], zs[-1], spacing)
        s, r, h = s_at(px, pz), np.hypot(px, pz), y_at(px, pz)
        m = keep(s, r, h, rng.random(px.size)) & (h > 0.35) & keep_clear(px, pz, pts, clear_r)
        placer.add(layer, rng, px[m], pz[m], h[m], **kw)

    # Palms on the top of the beach, a loose ring that leaves the raft's beach (north) more open.
    take(3.2, lambda s, r, h, u: (s > -1.5) & (s < 3.0) & (u < 0.55), 3.0, "palms")
    # Low dense bushes in a band along the inner edge of the beach.
    take(1.3, lambda s, r, h, u: (s > -4.5) & (s < 0.5) & (u < 0.75), 2.2, "low_bushes", height_scale=0.85)
    take(4.0, lambda s, r, h, u: (s > -6) & (s < -1) & (u < 0.35), 3.0, "big_bushes")
    # Flowers and grass on the grass, fewer in the village square.
    take(1.6, lambda s, r, h, u: (s < -0.5) & (u < np.where(r < 11, 0.08, 0.35)), 1.0, "flowers")
    take(1.4, lambda s, r, h, u: (s < 1.5) & (u < np.where(r < 11, 0.06, 0.3)), 1.0, "grass")
    # Rocks: the north-east knoll, a few on the beach.
    px, pz = jittered(rng, 6, 22, -22, -6, 1.6)
    k = np.exp(-(((px - 14) ** 2 + (pz + 14) ** 2) / (2 * 3.2 ** 2)))
    m = (rng.random(px.size) < k * 0.9) & keep_clear(px, pz, pts, 1.5) & (y_at(px, pz) > 0.35)
    placer.add("rocks_small", rng, px[m], pz[m], y_at(px[m], pz[m]), height_scale=1.4)
    take(6.0, lambda s, r, h, u: (s > 0) & (s < 5) & (u < 0.25), 2.0, "rocks_small")
    take(14.0, lambda s, r, h, u: (s > 1) & (s < 5) & (u < 0.5), 3.0, "beach_rocks")


def far(placer, g):
    xs, zs, y = g["x"], g["z"], g["y"]
    zn = g["zones"]
    cx, cz = g["offset"]
    sample = lambda f, px, pz: terrain._sample(f, xs, zs, px, pz)
    rng = np.random.default_rng(202)
    lake_level = g["water"]["lake_level"]

    def fields(spacing):
        px, pz = jittered(rng, xs[0], xs[-1], zs[0], zs[-1], spacing)
        f = {k: sample(v, px, pz) for k, v in zn.items()}
        f["y"] = sample(y, px, pz)
        f["u"] = rng.random(px.size)
        lxp, lzp = px - cx, pz - cz
        f["noise"] = terrain.fbm(lxp / 25, lzp / 25, 77, 3)   # clumps: some patches denser than others
        land = f["y"] > 0.4
        mount = (f["rm"] < 80) & (f["y"] > 5)
        f["mount"] = mount
        f["jungle_z"] = (f["jungle"] > 0.45) & ~mount & (f["inside"] > 4) & land
        f["plains"] = ~f["jungle_z"] & ~mount & (f["inside"] > 4) & land
        f["beach"] = land & (f["inside"] <= 4)
        river_bank = f["river_d"] - f["river_half"]
        f["bank"] = river_bank
        f["dry"] = land & (river_bank > 1.5) & (f["cascade_d"] > 2.5) & (f["rm"] > terrain.CRATER_R + 1.5)
        return px, pz, f

    def put(layer, spacing, prob, **kw):
        px, pz, f = fields(spacing)
        m = f["u"] < np.clip(prob(f), 0, 1)
        placer.add(layer, rng, px[m], pz[m], f["y"][m], **kw)

    gentle = lambda f, lim=0.75: f["slope"] < lim
    # Beaches: palms on the upper beach, low dense bushes behind them, flowers, sand rocks.
    put("palms", 4.0, lambda f: f["beach"] * f["dry"] * (f["inside"] > -7) * gentle(f) * 0.5)
    put("low_bushes", 1.5, lambda f: f["dry"] * (f["inside"] > -2) * (f["inside"] < 8) * ~f["mount"] * gentle(f) * 0.7)
    put("flowers", 2.0, lambda f: f["dry"] * (f["inside"] > -1) * (f["inside"] < 9) * ~f["mount"] * 0.25)
    put("beach_rocks", 16.0, lambda f: f["beach"] * (f["y"] > 0.5) * 0.35)
    # Jungle: dense and diverse.
    put("jungle_trees", 4.2, lambda f: f["jungle_z"] * f["dry"] * gentle(f, 0.9) * (0.55 + 0.4 * f["noise"]))
    put("palms", 9.0, lambda f: f["jungle_z"] * f["dry"] * 0.45)
    put("big_bushes", 3.5, lambda f: f["jungle_z"] * f["dry"] * 0.45)
    put("jungle_plants", 1.9, lambda f: f["jungle_z"] * f["dry"] * (0.35 + 0.4 * f["noise"]))
    put("flowers", 2.6, lambda f: f["jungle_z"] * f["dry"] * 0.2)
    put("forest_floor", 6.0, lambda f: f["jungle_z"] * f["dry"] * 0.3)
    # Mont Séréval: one tree family dominates, thinning toward the top, bare by the lake.
    up = lambda f: 1 - smoothstep(26, 36, f["y"])
    put("mountain_main", 3.8, lambda f: f["mount"] * f["dry"] * gentle(f, 0.9) * up(f) * 0.75)
    put("mountain_other", 7.5, lambda f: f["mount"] * f["dry"] * gentle(f, 0.85) * up(f) * 0.45)
    put("grass", 2.2, lambda f: f["mount"] * f["dry"] * gentle(f, 0.8) * 0.3)
    put("low_bushes", 3.5, lambda f: f["mount"] * f["dry"] * gentle(f, 0.85) * up(f) * 0.3)
    put("flowers", 4.0, lambda f: f["mount"] * f["dry"] * (f["y"] > 18) * 0.2)
    # Plains: grass and flowers, sparse trees (about one per 400 m²), rare bushes.
    put("plains_trees", 20.0, lambda f: f["plains"] * f["dry"] * 0.9)
    put("grass", 1.6, lambda f: f["plains"] * f["dry"] * (0.35 + 0.3 * f["noise"]))
    put("flowers", 2.0, lambda f: f["plains"] * f["dry"] * 0.3)
    put("big_bushes", 12.0, lambda f: f["plains"] * f["dry"] * 0.4)
    # Rocks nearly everywhere, more on steep ground and toward the summit...
    put("rocks_small", 7.0, lambda f: (f["y"] > 0.3) * (0.18 + 0.5 * smoothstep(0.6, 1.2, f["slope"])))
    put("rocks_big", 12.0, lambda f: (f["y"] > 0.3) * f["dry"] * (0.2 + 0.6 * smoothstep(0.7, 1.3, f["slope"])
                                                                   + 0.5 * smoothstep(25, 38, f["y"])))
    # ...gathered along the bed of the Aubeline and the cascade...
    put("water_rocks", 1.4, lambda f: (np.abs(f["bank"]) < 2.2) * (f["y"] > -0.2) * 0.35)
    put("water_rocks", 1.6, lambda f: (f["cascade_d"] < 3.0) * (f["rm"] > terrain.CRATER_R) * 0.5,
        height_scale=1.3)
    # ...and around Lac d'Aube.
    rim = lambda f: np.exp(-(((f["rm"] - terrain.CRATER_R - 1.5) / 2.5) ** 2))
    put("water_rocks", 1.2, lambda f: rim(f) * 0.8, height_scale=1.2)
    put("rocks_big", 5.0, lambda f: rim(f) * 0.45, height_scale=0.8)
    # Lilies on the lake, close to its shore.
    mx, mz = terrain.MOUNT[0] + cx, terrain.MOUNT[1] + cz
    lake_r = terrain.CRATER_R * math.sqrt(2.5 / 3.9)
    a = rng.random(18) * math.tau
    r = lake_r * (0.55 + 0.35 * rng.random(18))
    placer.add("lilies", rng, mx + r * np.cos(a), mz + r * np.sin(a), np.full(18, lake_level + 0.03), sink=0)


def pick_resource_trees(placer):
    """Marks a spread-out subset of the trees as resource trees: visited in a fixed random order, a tree
    becomes a resource tree when no resource tree stands within RESOURCE_SPACING of it."""
    trees = [(name, i) for name in TREE_LAYERS for i in range(len(placer.out[name]))]
    rng = np.random.default_rng(303)
    cell = RESOURCE_SPACING
    grid, chosen = {}, set()
    for k in rng.permutation(len(trees)):
        name, i = trees[k]
        _, x, _, z, _, _ = placer.out[name][i]
        cx, cz = int(x // cell), int(z // cell)
        near = (grid.get((cx + a, cz + b), ()) for a in (-1, 0, 1) for b in (-1, 0, 1))
        if any(math.hypot(x - px, z - pz) < RESOURCE_SPACING for pts in near for px, pz in pts):
            continue
        grid.setdefault((cx, cz), []).append((x, z))
        chosen.add((name, i))
    return chosen


def main():
    placer = Placer()
    home(placer, terrain.home_island())
    far(placer, terrain.far_island())
    chosen = pick_resource_trees(placer)
    layers, recs, resource = [], [], []
    for name, (models, _), fade, shadow in LAYERS:
        items = placer.out[name]
        entry = {"name": name, "fade": fade, "shadow": shadow, "models": []}
        for mi, path in enumerate(models):
            res = [it for i, it in enumerate(items) if it[0] == mi and (name, i) in chosen]
            rest = [it for i, it in enumerate(items) if it[0] == mi and (name, i) not in chosen]
            if not res and not rest:
                continue
            model = {"path": "res://models/" + path, "offset": len(recs), "count": len(res) + len(rest)}
            if name in TREE_LAYERS:
                model["resource"] = len(res)
            entry["models"].append(model)
            for _, x, y, z, _, h in res:
                island = "home" if math.hypot(x, z) < 46 else "far"   # Trio Island's grid is -46..46
                resource.append({"kind": name, "model": os.path.splitext(os.path.basename(path))[0],
                                 "island": island, "pos": [round(x, 2), round(z, 2)], "y": round(y, 2),
                                 "height": round(h, 1)})
            recs.extend(it[1:] for it in res + rest)
        layers.append(entry)
    resource.sort(key=lambda r: (r["island"] != "home", r["pos"][1], r["pos"][0]))
    for n, r in enumerate(resource):
        r["id"] = f"tree-{n + 1:03d}"
    with open(os.path.join(OUT, "resource_trees.json"), "w") as f:
        json.dump({"about": "Resource trees of the Godot world (godot/tools/flora.py): always drawn, at least "
                            f"{RESOURCE_SPACING:g} m apart. pos = [x, z] in sim coordinates, y = ground height.",
                   "count": len(resource), "trees": [{"id": r.pop("id"), **r} for r in resource]}, f, indent=1)
    np.array(recs, np.float32).tofile(os.path.join(OUT, "flora.bin"))
    with open(os.path.join(OUT, "flora.json"), "w") as f:
        json.dump({"record": ["x", "y", "z", "rotation", "height"], "count": len(recs), "layers": layers}, f, indent=1)
    print("flora:", len(recs), {n: len(v) for n, v in placer.out.items()}, "resource trees:", len(resource))


if __name__ == "__main__":
    main()
