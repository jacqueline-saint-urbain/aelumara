extends Node3D
## Draws the flora and rocks placed by tools/flora.py: one MultiMesh per model and per map chunk, so the
## chunks out of view are skipped and grass and flowers fade out with distance.

const NEAR_CHUNK := 64.0   # for layers that fade (grass, flowers, small rocks)
const FAR_CHUNK := 128.0   # for layers always drawn (trees, big rocks)


func _ready() -> void:
	var info: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://terrain/flora.json"))
	var rec := FileAccess.get_file_as_bytes("res://terrain/flora.bin").to_float32_array()
	for layer in info["layers"]:
		var fade: float = layer["fade"]
		var size := NEAR_CHUNK if fade > 0.0 and fade < 150.0 else FAR_CHUNK
		var group := Node3D.new()
		group.name = layer["name"]
		add_child(group)
		for model in layer["models"]:
			_add_model(group, model, rec, size, fade, layer["shadow"])


func _add_model(group: Node3D, model: Dictionary, rec: PackedFloat32Array, size: float, fade: float, shadow: bool) -> void:
	var m := Models.get_mesh(model["path"])
	var aabb: AABB = m["aabb"]
	var chunks := {}
	for i in range(int(model["offset"]), int(model["offset"]) + int(model["count"])):
		var k := Vector2i(floori(rec[i * 5] / size), floori(rec[i * 5 + 2] / size))
		if not chunks.has(k):
			chunks[k] = []
		chunks[k].append(i)
	for k in chunks:
		var centre := Vector3((k.x + 0.5) * size, 0.0, (k.y + 0.5) * size)
		var mm := MultiMesh.new()
		mm.transform_format = MultiMesh.TRANSFORM_3D
		mm.mesh = m["mesh"]
		mm.instance_count = chunks[k].size()
		for j in chunks[k].size():
			var i: int = chunks[k][j]
			var s := rec[i * 5 + 4] / maxf(maxf(aabb.size.y, 0.5 * maxf(aabb.size.x, aabb.size.z)), 0.01)
			var b := Basis(Vector3.UP, rec[i * 5 + 3]).scaled(Vector3.ONE * s)
			var pos := Vector3(rec[i * 5], rec[i * 5 + 1] - aabb.position.y * s, rec[i * 5 + 2]) - centre
			mm.set_instance_transform(j, Transform3D(b, pos))
		var mmi := MultiMeshInstance3D.new()
		mmi.multimesh = mm
		mmi.position = centre
		mmi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_ON if shadow else GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		if fade > 0.0:
			mmi.visibility_range_end = fade + size * 0.7
			mmi.visibility_range_end_margin = 12.0
			mmi.visibility_range_fade_mode = GeometryInstance3D.VISIBILITY_RANGE_FADE_DISABLED
		group.add_child(mmi)
