extends Node3D
## The living part of the island: residents, resource nodes, projects, the pieces of world.json and the
## avatars of Claude, Spark and the owner. Reads state.json and world.json (from GitHub, or handed over by
## the web page) and stands everything on the relief.

signal updated(info: Dictionary)

const RAW := "https://raw.githubusercontent.com/jacqueline-saint-urbain/aelumara/main/"
const POLL := 60.0
const TASKS := {"sleep": "sleeping 😴", "go_home": "going home", "eat": "eating", "forage": "foraging berries",
	"deliver": "delivering a haul", "gather_wood": "chopping wood 🪵", "gather_fiber": "gathering fiber 🌾",
	"gather_food": "picking berries 🫐", "rest": "resting", "idle": "idling",
	"stone": "leaving a shell on the stone 🐚", "fire": "at the evening fire 🔥"}
const RESOURCE := {"wood": "Tree (wood)", "food": "Berry bush", "fiber": "Reeds (fiber)"}
const CHARACTERS := ["female-a", "male-b", "female-c", "male-d", "female-e", "male-f", "female-b", "male-a",
	"female-d", "male-c", "female-f", "male-e"]

var heights: Heightfield
var state: Dictionary
var world: Dictionary
var pickables: Array = []    # {pos: Vector3, radius: float, title: String, body: Array}
var followables: Array = []  # {name: String, node: Node3D}
var _residents := {}         # npc id -> Node3D, kept between updates so they can walk
var _static_root: Node3D
var _http: HTTPRequest
var _queue: Array = []
var _handed_over_at := -1000.0
var _floaters: Array = []


func _ready() -> void:
	_http = HTTPRequest.new()
	add_child(_http)
	_http.request_completed.connect(_on_loaded)
	var t := Timer.new()
	t.wait_time = POLL
	t.autostart = true
	t.timeout.connect(refresh)
	add_child(t)
	refresh()


## Data handed over by the web page (it reads the same files for its panels): no second download.
func set_data(new_state: Dictionary, new_world: Dictionary) -> void:
	_handed_over_at = Time.get_ticks_msec() / 1000.0
	state = new_state
	world = new_world
	_rebuild()


func refresh() -> void:
	if Time.get_ticks_msec() / 1000.0 - _handed_over_at < POLL * 1.5:
		return
	_queue = ["state.json", "world.json"]
	_next()


func _next() -> void:
	if _queue.is_empty():
		_rebuild()
		return
	_http.request(RAW + _queue[0] + "?t=%d" % Time.get_unix_time_from_system())


func _on_loaded(result: int, code: int, _headers: PackedStringArray, body: PackedByteArray) -> void:
	var name: String = _queue.pop_front()
	if result == HTTPRequest.RESULT_SUCCESS and code == 200:
		var data = JSON.parse_string(body.get_string_from_utf8())
		if data is Dictionary:
			if name == "state.json":
				state = data
			else:
				world = data
	_next()


func _process(delta: float) -> void:
	var t := Time.get_ticks_msec() / 1000.0
	for i in _floaters.size():
		var f: Node3D = _floaters[i]
		f.position.y = f.get_meta("base_y") + sin(t * 1.5 + i) * 0.15
		f.get_child(0).rotation.y = t * 0.6
	for id in _residents:
		var r: Node3D = _residents[id]
		var target: Vector3 = r.get_meta("target")
		var to := target - r.position
		to.y = 0.0
		var anim: AnimationPlayer = r.get_meta("anim")
		if to.length() > 0.05:
			var step := minf(to.length(), 1.4 * delta)
			r.position += to.normalized() * step
			r.position.y = heights.height_at(r.position.x, r.position.z)
			r.rotation.y = atan2(to.x, to.z)
			_play(anim, "walk")
		else:
			_play(anim, r.get_meta("rest_anim"))
		for p in pickables:
			if p.get("node") == r:
				p["pos"] = r.position + Vector3(0, 0.9, 0)


func _ground(p: Array) -> Vector3:
	return Vector3(p[0], heights.height_at(p[0], p[1]), p[1])


func _on_land(p) -> bool:
	return p is Array and p.size() == 2 and heights.height_at(p[0], p[1]) > 0.2


func _rebuild() -> void:
	if _static_root:
		_static_root.queue_free()
	_static_root = Node3D.new()
	add_child(_static_root)
	pickables.clear()
	followables.clear()
	_floaters.clear()
	for e in world.get("entities", []):
		if not (e is Dictionary) or not _on_land(e.get("pos")):
			continue
		var o := Props.make(str(e.get("type", "")), Color.from_string(str(e.get("color", "#bbbbbb")), Color.WHITE))
		o.rotation.y = float(e.get("rot", 0.0))
		o.scale = Vector3.ONE * clampf(float(e.get("scale", 1.0)), 0.3, 3.0)
		o.position = _ground(e["pos"])
		_static_root.add_child(o)
		var meta := [str(e.get("type", ""))]
		if e.has("by"):
			meta.append("by " + str(e["by"]))
		if e.has("added"):
			meta.append(str(e["added"]))
		_pick(o.position, 1.2 * o.scale.x, str(e.get("label", e.get("type", ""))), [str(e.get("note", "")), " · ".join(meta)])
		if e.get("type") == "sign" and e.has("label"):
			_label(o, str(e["label"]), 2.4, 0.45)
	for n in state.get("nodes", []):
		if not _on_land(n.get("pos")):
			continue
		var o := Props.make(str(n.get("type", "")), Color.WHITE)
		o.position = _ground(n["pos"])
		o.rotation.y = fmod(float(n["pos"][0]) * 1.7 + float(n["pos"][1]) * 0.9, TAU)
		_static_root.add_child(o)
		var res: String = n.get("resource", "") if n.get("resource") != null else ""
		var body := []
		if res != "":
			body.append("Stock: %d %s" % [int(n.get("stock", 0)), {"wood": "wood", "food": "berries", "fiber": "fiber"}.get(res, res)])
		_pick(o.position, 1.5, str(n.get("label", RESOURCE.get(res, n.get("type", "")))), body)
	for p in state.get("projects", []):
		var pr := 100 if p.get("status") == "done" else _progress(p)
		var o := Props.shelter(pr) if p.get("type") == "shelter" else Props.raft(pr)
		o.position = _ground(p["pos"])
		_static_root.add_child(o)
		var needs := []
		for r in p.get("needs", {}):
			needs.append("%s: %d/%d" % [{"wood": "Wood", "fiber": "Fiber"}.get(r, r), int(p.get("have", {}).get(r, 0)), int(p["needs"][r])])
		_pick(o.position, 2.5, "The %s — %d%%" % [p.get("name", ""), pr], needs)
		_label(o, "%s %s %d %%" % ["🛖" if p.get("type") == "shelter" else "🛶", p.get("name", ""), pr], 2.6, 0.5)
	var seen := {}
	for i in state.get("npcs", []).size():
		var npc: Dictionary = state["npcs"][i]
		if not _on_land(npc.get("pos")):
			continue
		var id := str(npc.get("id", npc.get("name", i)))
		seen[id] = true
		var r: Node3D = _residents.get(id)
		if r == null:
			r = _resident(i, npc)
			_residents[id] = r
			add_child(r)
			r.position = _ground(npc["pos"])
		r.set_meta("target", _ground(npc["pos"]))
		r.set_meta("rest_anim", "sit" if npc.get("task") in ["rest", "fire", "eat"] else ("crouch" if npc.get("task") == "sleep" else "idle"))
		var tag: Label3D = r.get_meta("say")
		tag.text = ("💬 " + str(npc.get("say", "")).left(60)) if npc.get("say") else ""
		var needs: Dictionary = npc.get("needs", {})
		var company = needs.get("company")
		var body := [TASKS.get(npc.get("task"), str(npc.get("task", ""))),
			"Hunger %d · Energy %d · Company %s" % [int(needs.get("hunger", 0)), roundi(float(needs.get("energy", 0))), "–" if company == null else str(roundi(float(company)))],
			"Delivered %d resources" % int(npc.get("delivered", 0))]
		var pk := _pick(r.position + Vector3(0, 0.9, 0), 0.9, str(npc.get("name", "")), body)
		pk["node"] = r
		followables.append({"name": str(npc.get("name", "")), "node": r})
	for id in _residents.keys():
		if not seen.has(id):
			_residents[id].queue_free()
			_residents.erase(id)
	var avatars: Dictionary = world.get("avatars", {})
	for name in avatars:
		var a = avatars[name]
		if not (a is Dictionary) or not _on_land(a.get("pos")):
			continue
		var g := _avatar(str(a.get("shape", "orb")), Color.from_string(str(a.get("color", "#ffffff")), Color.WHITE))
		g.position = _ground(a["pos"]) + Vector3(0, 1.2, 0)
		g.set_meta("base_y", g.position.y)
		_static_root.add_child(g)
		_label(g, name, 1.0, 0.45)
		if str(a.get("say", "")) != "":
			_label(g, "💬 " + str(a["say"]).left(80), 1.6, 0.42, true)
		_pick(g.position, 0.8, name, [str(a.get("say", ""))])
		_floaters.append(g)
		followables.append({"name": name, "node": g})
	var st := state
	updated.emit({"day": st.get("day"), "time": st.get("time"), "residents": st.get("npcs", []).size()})


func _progress(p: Dictionary) -> int:
	var total := 0.0
	var have := 0.0
	for r in p.get("needs", {}):
		total += float(p["needs"][r])
		have += minf(float(p.get("have", {}).get(r, 0)), float(p["needs"][r]))
	return roundi(100.0 * have / maxf(total, 1.0))


func _pick(pos: Vector3, radius: float, title: String, body: Array) -> Dictionary:
	var p := {"pos": pos + Vector3(0, radius * 0.6, 0), "radius": radius, "title": title, "body": body.filter(func(l): return str(l) != "")}
	pickables.append(p)
	return p


## The nearest object under a screen point, or an empty dictionary.
func pick(cam: Camera3D, screen: Vector2) -> Dictionary:
	var o := cam.project_ray_origin(screen)
	var d := cam.project_ray_normal(screen)
	var best := {}
	var best_t := INF
	for p in pickables:
		var to: Vector3 = p["pos"] - o
		var t := to.dot(d)
		if t < 0.0:
			continue
		if (o + d * t).distance_to(p["pos"]) < float(p["radius"]) + 0.004 * t and t < best_t:
			best_t = t
			best = p
	return best


func _resident(i: int, npc: Dictionary) -> Node3D:
	var who: String = CHARACTERS[i % CHARACTERS.size()]
	var root := Node3D.new()
	var body: Node3D = load("res://models/kenney-characters/character-%s.glb" % who).instantiate()
	body.scale = Vector3.ONE * 1.6 / 0.75   # the Mini Characters are 0.75 m tall
	root.add_child(body)
	var anim: AnimationPlayer = body.find_children("*", "AnimationPlayer", true, false)[0]
	for a in ["idle", "walk", "sit", "crouch"]:
		if anim.has_animation(a):
			anim.get_animation(a).loop_mode = Animation.LOOP_LINEAR
	root.set_meta("anim", anim)
	var ring := CylinderMesh.new()   # a ring of the resident's colour on the ground, as in the dashboard
	ring.top_radius = 0.5
	ring.bottom_radius = 0.5
	ring.height = 0.04
	var m := StandardMaterial3D.new()
	m.albedo_color = Color.from_string(str(npc.get("color", "#ffffff")), Color.WHITE)
	m.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	ring.material = m
	var mi := MeshInstance3D.new()
	mi.mesh = ring
	mi.position.y = 0.03
	root.add_child(mi)
	_label(root, str(npc.get("name", "")), 2.2, 0.42)
	root.set_meta("say", _label(root, "", 2.75, 0.4, true))
	return root


func _avatar(shape: String, color: Color) -> Node3D:
	var root := Node3D.new()
	var mesh: PrimitiveMesh
	match shape:
		"crystal":
			mesh = PrismMesh.new()
			mesh.size = Vector3(0.9, 1.2, 0.9)
		"star":
			mesh = SphereMesh.new()
			mesh.radial_segments = 6
			mesh.rings = 3
			mesh.radius = 0.6
			mesh.height = 1.2
		_:
			mesh = SphereMesh.new()
			mesh.radius = 0.55
			mesh.height = 1.1
	var mat := StandardMaterial3D.new()
	mat.albedo_color = color
	mat.emission_enabled = true
	mat.emission = color
	mat.emission_energy_multiplier = 0.6
	mesh.material = mat
	var mi := MeshInstance3D.new()
	mi.mesh = mesh
	root.add_child(mi)
	return root


func _label(parent: Node3D, text: String, y: float, size: float, speech := false) -> Label3D:
	var l := Label3D.new()
	l.text = text
	l.billboard = BaseMaterial3D.BILLBOARD_ENABLED
	l.no_depth_test = true
	l.fixed_size = false
	l.pixel_size = size / 48.0
	l.font_size = 48
	l.outline_size = 14
	l.modulate = Color("1b1b1b") if speech else Color.WHITE
	l.outline_modulate = Color(1, 1, 1, 0.92) if speech else Color(0.08, 0.09, 0.12, 0.85)
	l.position.y = y
	l.render_priority = 10
	l.width = 900
	l.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	parent.add_child(l)
	return l


func _play(anim: AnimationPlayer, name: String) -> void:
	if anim and anim.current_animation != name and anim.has_animation(name):
		anim.play(name, 0.3)
