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
| `scripts/camera_rig.gd` | touch camera (mouse works too), views and following |
| `tools/flora.py` | places the CC0 flora and rocks zone by zone → `terrain/flora.json` + `flora.bin`; picks the resource trees (at least 11 m apart) → `terrain/resource_trees.json` |
| `models/` | the CC0 models used (Kenney, KayKit, Quaternius), see `models/CREDITS.md` |
| `scripts/flora.gd`, `scripts/models.gd` | draw the flora with chunked MultiMeshes and generated levels of detail; zoomed in, decor trees around the camera's target make room, resource trees stay |
| `scripts/sim_layer.gd`, `scripts/props.gd` | residents, resource nodes, projects, `world.json` pieces and avatars, from `state.json` and `world.json` |
| `scripts/bridge.gd` | messages with the web page around the canvas (views, follow, zoom, tapped object) |
| `export_presets.cfg`, `tools/build_site.sh` | web export (Compatibility renderer, no threads) and site assembly |

Units are metres, Y is up, −Z is north, sea level is 0: the same frame as `sim.py` and `index.html`. Trio Island is at the origin, Horizon Island is centred on `[0, -150]`.

## On the website

The workflow `.github/workflows/site.yml` exports the project with Godot 4.7.2 on every push that touches `godot/` or `index.html`, and publishes the page on the `site` branch: `index.html` at the root and the build in `godot/` (its wasm cut in parts under 25 MiB, joined again by the page). The page loads Godot in a frame when `godot/build.json` is there, keeps its own panels (stats, book, chat, info card), and talks to Godot with `postMessage`. `?three=1` keeps the old three.js renderer for now.

## Change the relief

```
pip install numpy pillow
python3 godot/tools/terrain.py          # rewrites godot/terrain/
python3 godot/tools/flora.py            # places the flora on it
python3 -m pytest -q godot/tools/test_terrain.py
```

Then reopen the project so Godot reimports the files.

## Screenshots without a window

```
godot --path godot -- --cam=x,z,distance,yaw,pitch [--stats]
```

puts the camera on a point of the map, which helps with `--write-movie` captures; `--stats` prints the triangles and draw calls of the frame.
