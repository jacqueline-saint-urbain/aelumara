"""Checks the Godot relief against the simulation: nothing of the village may float, sink or end up in the sea.

Run from the repo root:  python3 -m pytest godot/tools/test_terrain.py -q
"""
import json
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import terrain  # noqa: E402

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")


def sim_positions():
    state = json.load(open(os.path.join(ROOT, "state.json")))
    world = json.load(open(os.path.join(ROOT, "world.json")))
    pts = [("node " + n["id"], n["pos"]) for n in state["nodes"]]
    pts += [("project " + p["id"], p["pos"]) for p in state["projects"]]
    pts += [("entity " + e["id"], e["pos"]) for e in world["entities"]]
    return pts


def slope_at(x, z, h=1.0):
    gx = (terrain.height_at(x + h, z) - terrain.height_at(x - h, z)) / (2 * h)
    gz = (terrain.height_at(x, z + h) - terrain.height_at(x, z - h)) / (2 * h)
    return math.hypot(gx, gz)


def test_every_sim_position_is_on_dry_gentle_ground():
    for name, (x, z) in sim_positions():
        assert terrain.height_at(x, z) > 0.6, f"{name} at {x},{z} is too close to the sea"
        assert slope_at(x, z) < 0.35, f"{name} at {x},{z} stands on a slope"


def test_the_village_sits_on_a_plateau():
    hs = [terrain.height_at(x, z) for x in range(-10, 11, 2) for z in range(-10, 11, 2) if math.hypot(x, z) <= 10]
    assert max(hs) - min(hs) < 0.6


def test_the_whole_home_disc_is_land():
    for a in np.linspace(0, 2 * math.pi, 36, endpoint=False):
        assert terrain.height_at(19.5 * math.cos(a), 19.5 * math.sin(a)) > 0.5


def test_the_lake_and_the_river_run_downhill_to_the_sea():
    far = terrain.far_island()
    w = far["water"]
    level = w["level"]
    assert all(b <= a + 1e-9 for a, b in zip(level, level[1:])), "the Aubeline must never flow uphill"
    assert level[-1] == 0.0, "the Aubeline must reach the sea"
    assert w["lake_level"] > level[0], "Lac d'Aube must be above the spring"


def test_the_islands_do_not_touch():
    # Along the line between the two islands there is open sea.
    assert min(terrain.height_at(0, z) for z in range(-40, -24)) < -0.5
