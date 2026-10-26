class_name Models
extends RefCounted
## Loads a model file (glb, gltf or obj) once and flattens it into a single mesh with levels of detail,
## so it can be drawn many times with a MultiMesh. Also gives the model's bounding box, to scale it to a
## height in metres.

static var _cache := {}


static func get_mesh(path: String) -> Dictionary:
	if _cache.has(path):
		return _cache[path]
	var surfaces := []   # [arrays, material]
	var res = load(path)
	if res is Mesh:
		_collect(res, Transform3D(), surfaces)
	elif res is PackedScene:
		var root: Node = res.instantiate()
		for mi in root.find_children("*", "MeshInstance3D", true, false):
			var t := Transform3D()
			var p: Node = mi
			while p != root and p != null:
				t = (p as Node3D).transform * t
				p = p.get_parent()
			_collect(mi.mesh, t, surfaces, mi)
		root.free()
	if surfaces.is_empty():
		push_warning("Models: nothing to draw in " + path)
		var box := BoxMesh.new()
		_cache[path] = {"mesh": box, "aabb": box.get_aabb()}
		return _cache[path]
	var imp := ImporterMesh.new()
	# Surfaces without a texture are merged into one, their colour moved into the vertices: one draw call.
	var plain := []
	for s in surfaces:
		var mat := _fix(s[1], path)
		var std := mat as StandardMaterial3D
		if std and std.albedo_texture == null:
			plain.append([s[0], std.albedo_color])
		else:
			imp.add_surface(Mesh.PRIMITIVE_TRIANGLES, s[0], [], {}, mat)
	if not plain.is_empty():
		imp.add_surface(Mesh.PRIMITIVE_TRIANGLES, _merge(plain), [], {}, _vertex_colour_material())
	imp.generate_lods(25.0, 60.0, [])
	var mesh := imp.get_mesh()
	_cache[path] = {"mesh": mesh, "aabb": mesh.get_aabb()}
	return _cache[path]


static var _vc_material: StandardMaterial3D


static func _vertex_colour_material() -> StandardMaterial3D:
	if _vc_material == null:
		_vc_material = StandardMaterial3D.new()
		_vc_material.vertex_color_use_as_albedo = true
		_vc_material.vertex_color_is_srgb = true
		_vc_material.roughness = 0.9
		_vc_material.metallic_specular = 0.3
	return _vc_material


static func _merge(parts: Array) -> Array:
	var v := PackedVector3Array()
	var n := PackedVector3Array()
	var c := PackedColorArray()
	var idx := PackedInt32Array()
	for part in parts:
		var a: Array = part[0]
		var base := v.size()
		var pv: PackedVector3Array = a[Mesh.ARRAY_VERTEX]
		v.append_array(pv)
		if a[Mesh.ARRAY_NORMAL] != null:
			n.append_array(a[Mesh.ARRAY_NORMAL])
		else:
			for i in pv.size():
				n.append(Vector3.UP)
		var col: Color = part[1]
		for i in pv.size():
			c.append(col)
		if a[Mesh.ARRAY_INDEX] != null:
			for i in a[Mesh.ARRAY_INDEX]:
				idx.append(base + i)
		else:
			for i in pv.size():
				idx.append(base + i)
	var out := []
	out.resize(Mesh.ARRAY_MAX)
	out[Mesh.ARRAY_VERTEX] = v
	out[Mesh.ARRAY_NORMAL] = n
	out[Mesh.ARRAY_COLOR] = c
	out[Mesh.ARRAY_INDEX] = idx
	return out


static func _collect(mesh: Mesh, t: Transform3D, out: Array, mi: MeshInstance3D = null) -> void:
	var nb := t.basis.inverse().transposed()
	for s in mesh.get_surface_count():
		var arrays: Array = mesh.surface_get_arrays(s)
		var v: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
		for i in v.size():
			v[i] = t * v[i]
		arrays[Mesh.ARRAY_VERTEX] = v
		if arrays[Mesh.ARRAY_NORMAL] != null:
			var n: PackedVector3Array = arrays[Mesh.ARRAY_NORMAL]
			for i in n.size():
				n[i] = (nb * n[i]).normalized()
			arrays[Mesh.ARRAY_NORMAL] = n
		for k in [Mesh.ARRAY_TANGENT, Mesh.ARRAY_BONES, Mesh.ARRAY_WEIGHTS]:
			arrays[k] = null
		var mat: Material = mi.get_active_material(s) if mi else mesh.surface_get_material(s)
		out.append([arrays, mat])


## The packs export some materials as metallic (Kenney Nature Kit) or with linear colours read as sRGB
## (Quaternius OBJ), which turns them dark or sky-coloured. Make every material matte and fix the colours.
static func _fix(material: Material, path: String) -> Material:
	var mat := material as StandardMaterial3D
	if mat == null:
		return material
	mat = mat.duplicate()
	mat.metallic = 0.0
	mat.metallic_specular = 0.3
	mat.roughness = 0.9
	if path.ends_with(".obj"):
		mat.albedo_color = mat.albedo_color.linear_to_srgb()
	var c := mat.albedo_color
	if path.contains("kenney-nature") and c.s > 0.3 and c.h > 0.4 and c.h < 0.56:
		# Kenney Nature Kit foliage is teal; bring it to the tropical greens of the other packs.
		mat.albedo_color = Color.from_hsv(0.27 + (c.h - 0.4) * 0.3, minf(c.s * 1.1, 1.0), c.v * 0.85)
	if path.contains("kenney-pirate/palm") or path.contains("kenney-pirate/grass"):
		mat.albedo_color = Color(0.82, 1.0, 0.6)   # the Pirate Kit's mint greens, warmed toward the jungle's
	if mat.albedo_texture:
		mat.texture_filter = BaseMaterial3D.TEXTURE_FILTER_NEAREST
	return mat
