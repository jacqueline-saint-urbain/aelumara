class_name Props
extends RefCounted
## The objects of the simulation (state.json nodes and projects, world.json entities), built from the
## CC0 models. Each type maps to a model and a height in metres; types without a model get a simple shape.

const M := "res://models/"

# type: [model, height]
const MODELS := {
	"tree": ["kaykit-forest/Tree_1_B_Color1.gltf", 5.5],
	"pine": ["kaykit-forest/Tree_2_C_Color1.gltf", 6.0],   # no pines on the tropical islands: a broadleaf instead
	"palm": ["kenney-pirate/palm-detailed-straight.glb", 7.5],
	"bush": ["quaternius-nature/BushBerries_1.obj", 1.4],
	"reeds": ["quaternius-nature/Grass_2.obj", 1.7],
	"rock": ["kenney-nature/rock_largeD.glb", 1.0],
	"rocks": ["kenney-pirate/rocks-a.glb", 1.4],
	"hut": ["kenney-survival/tent-canvas.glb", 2.4],
	"lamp": ["kenney-town/lantern.glb", 2.6],
	"bench": ["kenney-town/stall-bench.glb", 0.6],
	"flower": ["kenney-nature/flower_redA.glb", 0.6],
	"sign": ["kenney-survival/signpost.glb", 1.8],
	"campfire": ["kenney-survival/campfire-pit.glb", 0.6],
	"jungleTree": ["kaykit-forest/Tree_4_C_Color1.gltf", 8.0],
	"banana": ["quaternius-nature/Plant_5.obj", 2.4],
	"fern": ["quaternius-nature/Plant_1.obj", 1.1],
	"tuft": ["kenney-nature/grass_large.glb", 0.7],
	"shrub": ["kaykit-forest/Bush_2_C_Color1.gltf", 0.9],
	"logpile": ["kenney-nature/log_stack.glb", 0.9],
}


static func make(type: String, color: Color) -> Node3D:
	var root := Node3D.new()
	root.name = type
	match type:
		"storehouse":
			_cabin(root, 5.0)
			for i in 3:
				var b := _model("kenney-survival/barrel.glb" if i % 2 else "kenney-survival/box.glb", 0.8)
				b.position = Vector3(-1.9, 0, -0.8 + i * 0.8)
				root.add_child(b)
		"house":
			_cabin(root, 6.0)
		"campfire":
			root.add_child(_model("kenney-survival/campfire-pit.glb", 0.6))
			root.add_child(_flame(color if color != Color.WHITE else Color("ff9f43")))
		"lamp":
			root.add_child(_model("kenney-town/lantern.glb", 2.6))
			var l := _light(color if color != Color.WHITE else Color("ffd166"), 9.0)
			l.position.y = 2.3
			root.add_child(l)
		"portal":
			var t := TorusMesh.new()
			t.inner_radius = 1.05
			t.outer_radius = 1.4
			root.add_child(_shape(t, color, 1.0, Vector3(0, 1.5, 0), Vector3(PI / 2, 0, 0)))
		"crystal":
			var p := PrismMesh.new()
			p.size = Vector3(1.0, 1.6, 1.0)
			root.add_child(_shape(p, color, 0.6, Vector3(0, 0.8, 0)))
		"statue":
			var base := BoxMesh.new()
			base.size = Vector3(1, 0.6, 1)
			root.add_child(_shape(base, Color("9e9e9e"), 0.0, Vector3(0, 0.3, 0)))
			var body := CapsuleMesh.new()
			body.radius = 0.35
			body.height = 1.7
			root.add_child(_shape(body, color, 0.0, Vector3(0, 1.45, 0)))
		"pond":
			var d := CylinderMesh.new()
			d.top_radius = 2.0
			d.bottom_radius = 2.0
			d.height = 0.06
			root.add_child(_shape(d, color, 0.0, Vector3(0, 0.04, 0)))
		"tower":
			var c := CylinderMesh.new()
			c.top_radius = 0.9
			c.bottom_radius = 1.1
			c.height = 5.0
			root.add_child(_shape(c, color, 0.0, Vector3(0, 2.5, 0)))
			var cone := CylinderMesh.new()
			cone.top_radius = 0.0
			cone.bottom_radius = 1.3
			cone.height = 1.6
			root.add_child(_shape(cone, Color("8d3b2f"), 0.0, Vector3(0, 5.8, 0)))
		"shell":
			var s := SphereMesh.new()
			s.radius = 0.14
			s.height = 0.18
			root.add_child(_shape(s, color, 0.0, Vector3(0, 0.08, 0)))
		_:
			if MODELS.has(type):
				root.add_child(_model(MODELS[type][0], MODELS[type][1]))
			else:
				var box := BoxMesh.new()
				root.add_child(_shape(box, color, 0.0, Vector3(0, 0.5, 0)))
	return root


## A raft on the north beach, log by log as the islanders bring wood, with a mast and sail when done.
static func raft(progress: int) -> Node3D:
	var root := Node3D.new()
	var logs := maxi(1, roundi(progress / 100.0 * 8))
	for i in logs:
		var l := _model("kenney-nature/log_large.glb", 0.45)
		l.scale.x = 4.0   # the model is 1 m long along x; a raft log is 4 m
		l.rotation.y = PI / 2
		l.position = Vector3((i - 3.5) * 0.48, l.position.y, 0)
		root.add_child(l)
	if progress >= 100:
		var mast := CylinderMesh.new()
		mast.top_radius = 0.07
		mast.bottom_radius = 0.09
		mast.height = 3.0
		root.add_child(_shape(mast, Color("6d4c41"), 0.0, Vector3(0, 1.8, 0)))
		var sail := PrismMesh.new()
		sail.size = Vector3(2.0, 2.2, 0.04)
		root.add_child(_shape(sail, Color("f1faee"), 0.0, Vector3(0.6, 2.2, 0)))
	else:
		var frame := BoxMesh.new()
		frame.size = Vector3(3.8, 0.04, 4.2)
		root.add_child(_shape(frame, Color(1.0, 0.82, 0.4, 0.35), 0.0, Vector3(0, 0.03, 0)))
	return root


## The shelter by the fire: posts first, then the roof from half way.
static func shelter(progress: int) -> Node3D:
	var root := Node3D.new()
	if progress >= 50:
		_cabin(root, 4.4)
	else:
		var posts := maxi(1, roundi(progress / 50.0 * 4))
		var spots := [Vector2(-1.1, -1.1), Vector2(1.1, -1.1), Vector2(1.1, 1.1), Vector2(-1.1, 1.1)]
		for i in posts:
			var p := CylinderMesh.new()
			p.top_radius = 0.1
			p.bottom_radius = 0.12
			p.height = 2.0
			root.add_child(_shape(p, Color("8d6e63"), 0.0, Vector3(spots[i].x, 1.0, spots[i].y)))
	return root


## A Survival Kit frame with its canvas; the kit's pieces share one grid, so both share one scale.
static func _cabin(root: Node3D, s: float) -> void:
	for piece in [["structure.glb", 0.0], ["structure-canvas.glb", 0.0]]:
		var e := Models.get_mesh(M + "kenney-survival/" + piece[0])
		var mi := MeshInstance3D.new()
		mi.mesh = e["mesh"]
		mi.scale = Vector3.ONE * s
		mi.position.y = (piece[1] - e["aabb"].position.y) * s
		root.add_child(mi)


static func _model(path: String, height: float) -> MeshInstance3D:
	var e := Models.get_mesh(M + path)
	var aabb: AABB = e["aabb"]
	var mi := MeshInstance3D.new()
	mi.mesh = e["mesh"]
	var s := height / maxf(aabb.size.y, 0.01)
	mi.scale = Vector3.ONE * s
	mi.position.y = -aabb.position.y * s
	return mi


static func _shape(mesh: PrimitiveMesh, color: Color, glow: float, pos: Vector3, rot := Vector3.ZERO) -> MeshInstance3D:
	var mat := StandardMaterial3D.new()
	mat.albedo_color = color
	mat.roughness = 0.8
	if color.a < 1.0:
		mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	if glow > 0.0:
		mat.emission_enabled = true
		mat.emission = color
		mat.emission_energy_multiplier = glow
	mesh.material = mat
	var mi := MeshInstance3D.new()
	mi.mesh = mesh
	mi.position = pos
	mi.rotation = rot
	return mi


static func _flame(color: Color) -> Node3D:
	var root := Node3D.new()
	var cone := CylinderMesh.new()
	cone.top_radius = 0.0
	cone.bottom_radius = 0.3
	cone.height = 0.8
	root.add_child(_shape(cone, color, 2.5, Vector3(0, 0.5, 0)))
	var l := _light(color, 8.0)
	l.position.y = 1.0
	root.add_child(l)
	return root


static func _light(color: Color, reach: float) -> OmniLight3D:
	var l := OmniLight3D.new()
	l.light_color = color
	l.omni_range = reach
	l.light_energy = 1.5
	l.shadow_enabled = false
	l.add_to_group("night_light")
	return l
