# Aelúmara ground for Godot

A small Godot 4 project with the **ground only** of the two islands (grass, sand, wet sand, foam, mountain, hills, cascade, river, jungle floor). There are no plants, rocks or buildings in it. The owner asked for this on 2026-10-26 to try building the world with her finger in Godot on an Android tablet.

## Open it on an Android tablet

1. Install the **Godot Engine** editor from the Google Play Store. See the [Android editor docs](https://docs.godotengine.org/en/stable/tutorials/editor/using_the_android_editor.html).
2. Download [`aelumara-ground.zip`](https://github.com/jacqueline-saint-urbain/aelumara/raw/main/godot/aelumara-ground.zip).
3. In Godot's project manager, tap **Import**, pick the zip, and choose an empty folder. Then open the project.
4. Press ▶ (Run). One finger turns the camera, two fingers zoom and move it, and the buttons jump between the islands.

## Files

| file | what |
|---|---|
| `aelumara_ground.glb` | both islands' ground; Trio Island at the origin, Horizon Island at `[0, -150]` |
| `main.tscn` | sea, sun, sky, fog, the ground, the camera and the buttons |
| `camera_rig.gd` | touch camera (mouse works too) |
| `ui.gd` | island buttons and help line |

Units are metres, Y is up, and −Z is north, the same as in `index.html`.

## How the glb was made

`index.html` builds the islands with `homeIsland(true)` and `farIsland(region, true)`, which skip the plants. The two groups were exported with three.js `GLTFExporter`, with flat normals and patch layers lifted by a few centimetres instead of a polygon offset. If the islands change in `index.html`, export again the same way.
