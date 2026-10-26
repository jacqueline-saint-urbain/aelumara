extends Node3D
## Draws the flora and rocks placed by tools/flora.py: one MultiMesh per model and per map chunk, so the
## chunks out of view are skipped and grass and flowers fade out with distance.
##
## Trees are resource trees (always drawn) or decor trees: when the camera is zoomed in, the decor trees
## around the point it looks at and between it and that point are hidden, so a resident walking in the
## jungle stays visible. A resource tree only makes room when the camera is inside its crown. Zoomed out,
## every tree is drawn.

const NEAR_CHUNK := 64.0   # for layers that fade (grass, flowers, small rocks)
const FAR_CHUNK := 128.0   # for layers always drawn (trees, big rocks)
const CLOSE := 70.0        # camera distance under which decor trees make room
const FAR := 80.0          # and over which they all come back
const LINE_CLEAR := 7.0    # metres kept clear on each side of the line from the camera to its target
const EYE_CLEAR := 6.0     # a resource tree this close to the camera (on the ground) would fill the screen
const HIDDEN := Basis(Vector3.ZERO, Vector3.ZERO, Vector3.ZERO)

var rig: Node3D            # the camera rig (set by world.gd); its position is the point looked at
# Trees that can make room: their MultiMesh, instance index, ground position, transform, and kind.
var _tree_mm: Array[MultiMesh] = []
var _tree_index := PackedInt32Array()
var _tree_xz := PackedVector2Array()
var _tree_xf: Array[Transform3D] = []
var _tree_hidden := PackedByteArray()
var _tree_resource := PackedByteArray()
var _clearing := false
var _wait := 0.0


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
	var is_tree := model.has("resource")
	var decor_from := int(model["offset"]) + int(model.get("resource", 0))
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
			if is_tree:
				_tree_mm.append(mm)
				_tree_index.append(j)
				_tree_xz.append(Vector2(rec[i * 5], rec[i * 5 + 2]))
				_tree_xf.append(Transform3D(b, pos))
				_tree_hidden.append(0)
				_tree_resource.append(1 if i < decor_from else 0)
		var mmi := MultiMeshInstance3D.new()
		mmi.multimesh = mm
		mmi.position = centre
		mmi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_ON if shadow else GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		if fade > 0.0:
			mmi.visibility_range_end = fade + size * 0.7
			mmi.visibility_range_end_margin = 12.0
			mmi.visibility_range_fade_mode = GeometryInstance3D.VISIBILITY_RANGE_FADE_DISABLED
		group.add_child(mmi)


func _process(delta: float) -> void:
	_wait -= delta
	if not rig or _wait > 0.0:
		return
	_wait = 0.15
	var d: float = rig.distance
	if not _clearing and d > CLOSE:
		return
	_clearing = d < FAR
	var target := Vector2(rig.global_position.x, rig.global_position.z)
	var eye_3d: Vector3 = rig.get_node("Camera3D").global_position
	var eye := Vector2(eye_3d.x, eye_3d.z)
	var radius := clampf(d * 0.6, 14.0, 35.0)
	for n in _tree_xz.size():
		var p := _tree_xz[n]
		var out := false
		if _clearing and _tree_resource[n] == 1:
			out = p.distance_to(eye) < EYE_CLEAR
		elif _clearing:
			out = (p.distance_to(target) < radius
					or p.distance_to(Geometry2D.get_closest_point_to_segment(p, eye, target)) < LINE_CLEAR)
		if out != (_tree_hidden[n] == 1):
			_tree_hidden[n] = 1 if out else 0
			var xf := _tree_xf[n]
			_tree_mm[n].set_instance_transform(_tree_index[n], Transform3D(HIDDEN, xf.origin) if out else xf)
