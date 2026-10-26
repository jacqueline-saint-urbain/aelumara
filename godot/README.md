# Aelúmara in Godot

The 3D world of [aelumara.pages.dev](https://aelumara.pages.dev/) in Godot 4.7: the relief and textures of the two islands, the sea, the river Aubeline, the cascade and Lac d'Aube on top of Mont Séréval. The plan is in the owner's vault; this folder follows it step by step (relief first, then the CC0 low-poly flora, then the sim's villagers and objects).

## Run it

- **Desktop**: open `project.godot` in Godot 4.7.2 and press ▶.
- **Android tablet**: install the Godot editor from the Play Store ([docs](https://docs.godotengine.org/en/stable/tutorials/editor/using_the_android_editor.html)), import this `godot/` folder (or the zip published next to the web build), then press ▶. One finger turns the camera, two fingers zoom and move it.

## Files

| path | what |
|---|---|
| `tools/terrain.py` | generates the relief: height grids, texture weights, river, lake, sea depth. Deterministic (fixed seeds). |
| `tools/test_terrain.py` | checks every sim position stands on dry, gentle ground, the river runs downhill, the islands don't touch |
| `terrain/` | generated: `home.*`, `far.*` (grid `.bin` float32 + mesh `.glb`), `water.glb`, `sea_depth.png`, `meta.json` |
| `textures/` | 512 px CC0 ground textures from ambientCG, see `CREDITS.md` |
| `shaders/` | `terrain` (5-layer blend, triplanar rock), `sea` (depth colour, foam, waves), `flow` (river, cascade, lake) |
| `scripts/world.gd` | builds the scene from `terrain/` |
| `scripts/heightfield.gd` | `height_at(x, z)` so anything can stand on the relief |
| `scripts/camera_rig.gd` | touch camera (mouse works too) |

Units are metres, Y is up, −Z is north, sea level is 0: the same frame as `sim.py` and `index.html`. Trio Island is at the origin, Horizon Island is centred on `[0, -150]`.

## Change the relief

```
pip install numpy pillow
python3 godot/tools/terrain.py          # rewrites godot/terrain/
python3 -m pytest -q godot/tools/test_terrain.py
```

Then reopen the project so Godot reimports the files.

## Screenshots without a window

```
godot --path godot -- --cam=x,z,distance,yaw,pitch
```

puts the camera on a point of the map, which helps with `--write-movie` captures.
