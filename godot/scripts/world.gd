extends Node3D
## Builds the two islands from godot/terrain (written by tools/terrain.py): ground, sea, river, cascade, lake.

const TEX := ["sand", "grass", "jungle_floor", "rock", "mud"]

var heights := Heightfield.new()
var meta: Dictionary


func _ready() -> void:
	meta = JSON.parse_string(FileAccess.get_file_as_string("res://terrain/meta.json"))
	_ground()
	_sea()
	_fresh_water()
	_camera_from_args()


func _ground() -> void:
	var mat := ShaderMaterial.new()
	mat.shader = load("res://shaders/terrain.gdshader")
	var uniforms := ["tex_sand", "tex_grass", "tex_jungle", "tex_rock", "tex_mud"]
	for i in TEX.size():
		mat.set_shader_parameter(uniforms[i], load("res://textures/%s.jpg" % TEX[i]))
	for island in ["home", "far"]:
		var scene: Node3D = load("res://terrain/%s.glb" % island).instantiate()
		scene.name = "Ground_" + island
		add_child(scene)
		for m in scene.find_children("*", "MeshInstance3D", true, false):
			m.material_override = mat


func _sea() -> void:
	var sea := MeshInstance3D.new()
	sea.name = "Sea"
	var plane := PlaneMesh.new()
	plane.size = Vector2(2400, 2400)
	plane.subdivide_width = 120
	plane.subdivide_depth = 120
	sea.mesh = plane
	var mat := ShaderMaterial.new()
	mat.shader = load("res://shaders/sea.gdshader")
	mat.set_shader_parameter("depth_map", load("res://terrain/sea_depth.png"))
	var b: Dictionary = meta["sea_depth"]
	mat.set_shader_parameter("bounds", Vector4(b["x0"], b["z0"], b["x1"], b["z1"]))
	sea.material_override = mat
	sea.position = Vector3(0, 0, -100)
	add_child(sea)


func _fresh_water() -> void:
	var water: Node3D = load("res://terrain/water.glb").instantiate()
	add_child(water)
	for m in water.find_children("*", "MeshInstance3D", true, false):
		var mat := ShaderMaterial.new()
		mat.shader = load("res://shaders/flow.gdshader")
		if m.name.begins_with("cascade"):
			mat.set_shader_parameter("speed", 2.2)
			mat.set_shader_parameter("whiteness", 0.55)
		m.material_override = mat
	var lake := MeshInstance3D.new()
	lake.name = "LacDAube"
	var disc := CylinderMesh.new()
	disc.top_radius = meta["lake"]["radius"]
	disc.bottom_radius = meta["lake"]["radius"]
	disc.height = 0.05
	disc.radial_segments = 32
	lake.mesh = disc
	var lm := ShaderMaterial.new()
	lm.shader = load("res://shaders/flow.gdshader")
	lm.set_shader_parameter("speed", 0.05)
	lm.set_shader_parameter("whiteness", 0.05)
	lake.material_override = lm
	var c: Array = meta["lake"]["center"]
	lake.position = Vector3(c[0], meta["lake"]["level"], c[1])
	add_child(lake)


## For screenshots: godot --path . -- --cam=x,z,distance,yaw,pitch
func _camera_from_args() -> void:
	for arg in OS.get_cmdline_user_args():
		if arg.begins_with("--cam="):
			var v := arg.substr(6).split_floats(",")
			var rig := $CameraRig
			rig.yaw = v[3]
			rig.pitch = v[4]
			rig.focus(Vector3(v[0], heights.height_at(v[0], v[1]), v[1]), v[2])
