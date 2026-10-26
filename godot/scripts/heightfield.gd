class_name Heightfield
extends RefCounted
## Heights written by tools/terrain.py: sample the ground anywhere, so things stand on the relief.

var _grids := []


func _init() -> void:
	var meta: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://terrain/meta.json"))
	for name in meta["islands"]:
		var g: Dictionary = meta["islands"][name]
		var bytes := FileAccess.get_file_as_bytes("res://terrain/%s.bin" % name)
		_grids.append({"x0": g["x0"], "z0": g["z0"], "step": g["step"], "nx": int(g["nx"]), "nz": int(g["nz"]),
			"h": bytes.to_float32_array()})


func height_at(x: float, z: float) -> float:
	for g in _grids:
		var fx: float = (x - g["x0"]) / g["step"]
		var fz: float = (z - g["z0"]) / g["step"]
		if fx < 0.0 or fz < 0.0 or fx > g["nx"] - 1.001 or fz > g["nz"] - 1.001:
			continue
		var ix := int(fx)
		var iz := int(fz)
		var tx := fx - ix
		var tz := fz - iz
		var h: PackedFloat32Array = g["h"]
		var nx: int = g["nx"]
		var a := lerpf(h[iz * nx + ix], h[iz * nx + ix + 1], tx)
		var b := lerpf(h[(iz + 1) * nx + ix], h[(iz + 1) * nx + ix + 1], tx)
		return lerpf(a, b, tz)
	return -7.0
