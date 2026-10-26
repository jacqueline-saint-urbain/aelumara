extends Node3D
## Builds the two islands from godot/terrain (written by tools/terrain.py): ground, sea, river, cascade,
## lake, flora; then the living layer from the simulation, the day and night of Toronto, the camera views,
## and the link with the web page.

const TEX := ["sand", "grass", "jungle_floor", "rock", "mud"]
# name: [target, distance, yaw, pitch]
const VIEWS := {
	"overview": [Vector3(0, 1, 0), 42.0, 0.0, -0.62],
	"top": [Vector3(0, 0, 0), 60.0, 0.0, -1.45],
	"horizon": [Vector3(0, 6, -150), 175.0, 0.0, -0.1],
	"far": [Vector3(-10, 4, -150), 260.0, 0.35, -0.7],
}

var heights := Heightfield.new()
var meta: Dictionary
var sim: Node3D
var bridge: Node
var _follow_index := -1
var _press := {}
var _info_panel: PanelContainer
var _night := false

@onready var rig: Node3D = $CameraRig
@onready var cam: Camera3D = $CameraRig/Camera3D
@onready var sun: DirectionalLight3D = $Sun
@onready var env: Environment = $WorldEnvironment.environment


func _ready() -> void:
	meta = JSON.parse_string(FileAccess.get_file_as_string("res://terrain/meta.json"))
	_ground()
	_sea()
	_fresh_water()
	var flora := preload("res://scripts/flora.gd").new()
	flora.name = "Flora"
	add_child(flora)
	sim = preload("res://scripts/sim_layer.gd").new()
	sim.name = "Sim"
	sim.heights = heights
	sim.updated.connect(_on_sim_updated)
	add_child(sim)
	bridge = preload("res://scripts/bridge.gd").new()
	add_child(bridge)
	bridge.command.connect(_on_command)
	if not bridge.embedded:
		_build_native_ui()
	_apply_time()
	var t := Timer.new()
	t.wait_time = 60.0
	t.autostart = true
	t.timeout.connect(_apply_time)
	add_child(t)
	view("overview")
	_camera_from_args()


func view(name: String) -> void:
	if not VIEWS.has(name):
		return
	rig.follow = null
	_follow_index = -1
	bridge.send({"type": "follow", "name": ""})
	var v: Array = VIEWS[name]
	var vp := get_viewport().get_visible_rect().size
	var k := pow(vp.y / vp.x, 0.7) if vp.x < vp.y else 1.0   # portrait screens: step back a little
	rig.fly_to(v[0], v[1] * k, v[2], v[3])


func follow_next() -> void:
	_follow(_follow_index + 1)


func _follow(i: int) -> void:
	var list: Array = sim.followables
	if i < 0 or i >= list.size():
		_follow_index = -1
		rig.follow = null
		bridge.send({"type": "follow", "name": ""})
		return
	_follow_index = i
	var node: Node3D = list[i]["node"]
	rig.fly_to(node.global_position + Vector3(0, 1, 0), 11.0, rig.yaw, -0.45)
	rig.follow = node
	bridge.send({"type": "follow", "name": list[i]["name"]})


func _on_command(msg: Dictionary) -> void:
	match msg["type"]:
		"view":
			view(str(msg.get("name", "")))
		"follow":
			_follow(int(msg.get("index", -1)))
		"zoom":
			rig.zoom(float(msg.get("f", 1.0)))
		"data":
			if msg.get("state") is Dictionary and msg.get("world") is Dictionary:
				sim.set_data(msg["state"], msg["world"])


func _on_sim_updated(_info: Dictionary) -> void:
	var names := []
	for f in sim.followables:
		names.append(f["name"])
	bridge.send({"type": "followables", "names": names})
	if _follow_index >= 0 and _follow_index < sim.followables.size():
		rig.follow = sim.followables[_follow_index]["node"]
	_apply_time()


# A tap (a short touch that barely moved) opens the card of the object under the finger.
func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventScreenTouch:
		if event.pressed:
			_press[event.index] = [event.position, Time.get_ticks_msec()]
		elif _press.has(event.index):
			var p: Array = _press[event.index]
			_press.erase(event.index)
			if event.position.distance_to(p[0]) < 10.0 and Time.get_ticks_msec() - p[1] < 400 and _press.is_empty():
				_tap(event.position)


func _tap(at: Vector2) -> void:
	var hit: Dictionary = sim.pick(cam, at)
	if hit.is_empty():
		bridge.send({"type": "pick"})
		if _info_panel:
			_info_panel.hide()
		return
	bridge.send({"type": "pick", "title": hit["title"], "body": hit["body"]})
	if _info_panel:
		var l: Label = _info_panel.get_child(0)
		l.text = hit["title"] + "\n" + "\n".join(hit["body"])
		_info_panel.show()


# ---------------------------------------------------------------- day and night ---
## Hour in Toronto (Eastern time, with daylight saving from the second Sunday of March to the first
## Sunday of November), the island's clock.
static func toronto_hour(unix: float) -> float:
	var est := unix - 5 * 3600
	var d := Time.get_datetime_dict_from_unix_time(int(est))
	var y: int = d["year"]
	var dst_start := _nth_sunday(y, 3, 2) + 2 * 3600
	var dst_end := _nth_sunday(y, 11, 1) + 1 * 3600
	var local := est + (3600 if est >= dst_start and est < dst_end else 0)
	return fmod(local / 3600.0, 24.0)


static func _nth_sunday(year: int, month: int, n: int) -> int:
	var first := Time.get_unix_time_from_datetime_dict({"year": year, "month": month, "day": 1, "hour": 0})
	var wd: int = Time.get_datetime_dict_from_unix_time(first)["weekday"]   # 0 = Sunday
	return first + (((7 - wd) % 7) + 7 * (n - 1)) * 86400


func _apply_time() -> void:
	var h := toronto_hour(Time.get_unix_time_from_system())
	_night = h < 7.0 or h >= 19.0
	var sky := env.sky.sky_material as ProceduralSkyMaterial
	if _night:
		sky.sky_top_color = Color(0.03, 0.06, 0.16)
		sky.sky_horizon_color = Color(0.1, 0.14, 0.28)
		sky.ground_horizon_color = Color(0.1, 0.14, 0.28)
		sky.ground_bottom_color = Color(0.02, 0.04, 0.1)
		sun.light_energy = 0.22
		sun.light_color = Color(0.62, 0.71, 1.0)
		sun.rotation = Vector3(-0.7, -0.8, 0)
		env.ambient_light_energy = 0.35
		env.fog_light_color = Color(0.08, 0.11, 0.22)
	else:
		var golden := clampf(1.0 - minf(h - 7.0, 19.0 - h) / 2.0, 0.0, 1.0)   # warm light near sunrise and sunset
		sky.sky_top_color = Color(0.32, 0.6, 0.86)
		sky.sky_horizon_color = Color(0.7, 0.85, 0.93).lerp(Color(1.0, 0.75, 0.55), golden * 0.6)
		sky.ground_horizon_color = sky.sky_horizon_color
		sky.ground_bottom_color = Color(0.1, 0.3, 0.45)
		sun.light_energy = 1.25 - 0.4 * golden
		sun.light_color = Color.WHITE.lerp(Color(1.0, 0.8, 0.6), golden)
		sun.rotation = Vector3(-0.25 - 0.75 * sin(PI * (h - 7.0) / 12.0), 0.6, 0)
		env.ambient_light_energy = 0.8
		env.fog_light_color = sky.sky_horizon_color
	for l in get_tree().get_nodes_in_group("night_light"):
		l.visible = _night


# ---------------------------------------------------------------- without the web page ---
## In the Godot editor on a tablet or a computer there is no web page around: a few buttons and a card.
func _build_native_ui() -> void:
	var ui := CanvasLayer.new()
	add_child(ui)
	var bar := HBoxContainer.new()
	bar.anchor_left = 0.5
	bar.anchor_right = 0.5
	bar.anchor_top = 1.0
	bar.anchor_bottom = 1.0
	bar.offset_left = -230
	bar.offset_right = 230
	bar.offset_top = -74
	bar.offset_bottom = -16
	bar.alignment = BoxContainer.ALIGNMENT_CENTER
	ui.add_child(bar)
	for b in [["🏝️", func(): view("overview")], ["⬆️", func(): view("top")], ["🌅", func(): view("horizon")],
			["⛰️", func(): view("far")], ["🎯", follow_next], ["＋", func(): rig.zoom(0.75)], ["－", func(): rig.zoom(1.33)]]:
		var btn := Button.new()
		btn.text = b[0]
		btn.custom_minimum_size = Vector2(58, 58)
		btn.add_theme_font_size_override("font_size", 26)
		btn.pressed.connect(b[1])
		bar.add_child(btn)
	_info_panel = PanelContainer.new()
	_info_panel.offset_left = 16
	_info_panel.offset_top = 16
	_info_panel.custom_minimum_size = Vector2(320, 0)
	var l := Label.new()
	l.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	l.add_theme_font_size_override("font_size", 20)
	_info_panel.add_child(l)
	_info_panel.hide()
	ui.add_child(_info_panel)


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
		if arg == "--stats":
			_print_stats.call_deferred()
		if arg.begins_with("--cam="):
			var v := arg.substr(6).split_floats(",")
			var rig := $CameraRig
			rig.yaw = v[3]
			rig.pitch = v[4]
			rig.focus(Vector3(v[0], heights.height_at(v[0], v[1]), v[1]), v[2])


func _print_stats() -> void:
	for i in 5:
		await get_tree().process_frame
	var rs := RenderingServer
	print("stats: primitives %d, draw calls %d, objects %d, video memory %.1f MB" % [
		rs.get_rendering_info(rs.RENDERING_INFO_TOTAL_PRIMITIVES_IN_FRAME),
		rs.get_rendering_info(rs.RENDERING_INFO_TOTAL_DRAW_CALLS_IN_FRAME),
		rs.get_rendering_info(rs.RENDERING_INFO_TOTAL_OBJECTS_IN_FRAME),
		rs.get_rendering_info(rs.RENDERING_INFO_VIDEO_MEM_USED) / 1048576.0])
