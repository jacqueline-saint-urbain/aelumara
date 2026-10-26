extends CanvasLayer
## Three buttons to jump between the islands, and a short help line.

const VIEWS := {
	"Both islands": [Vector3(0, 0, -60), 230.0],
	"Trio Island": [Vector3(0, 0, 0), 45.0],
	"Horizon Island": [Vector3(0, 0, -150), 200.0],
}


func _ready() -> void:
	var bar := HBoxContainer.new()
	bar.anchor_left = 0.0
	bar.anchor_right = 1.0
	bar.anchor_top = 1.0
	bar.anchor_bottom = 1.0
	bar.offset_top = -100.0
	bar.offset_bottom = -24.0
	bar.alignment = BoxContainer.ALIGNMENT_CENTER
	bar.add_theme_constant_override("separation", 16)
	add_child(bar)
	for label in VIEWS:
		var b := Button.new()
		b.text = label
		b.custom_minimum_size = Vector2(190, 64)
		b.add_theme_font_size_override("font_size", 24)
		b.pressed.connect(_go.bind(label))
		bar.add_child(b)
	var help := Label.new()
	help.text = "1 finger: turn   ·   2 fingers: zoom and move"
	help.add_theme_font_size_override("font_size", 22)
	help.set_anchors_and_offsets_preset(Control.PRESET_TOP_WIDE, Control.PRESET_MODE_MINSIZE, 20)
	help.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	add_child(help)


func _go(label: String) -> void:
	var v: Array = VIEWS[label]
	get_node("../CameraRig").focus(v[0], v[1])
