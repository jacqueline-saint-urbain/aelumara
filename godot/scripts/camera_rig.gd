extends Node3D
## Touch camera: one finger turns around, two fingers pinch to zoom and drag to move.
## With a mouse: drag to turn, wheel to zoom.

@export var distance := 230.0
@export var min_distance := 6.0
@export var max_distance := 500.0
@export var yaw := 0.0
@export var pitch := -0.75

var _touches := {}
var _last_pinch := 0.0
var _last_center := Vector2.ZERO

@onready var _cam: Camera3D = $Camera3D


func _ready() -> void:
	_apply()


func focus(target: Vector3, dist: float) -> void:
	position = target
	distance = dist
	_apply()


func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventScreenTouch:
		if event.pressed:
			_touches[event.index] = event.position
		else:
			_touches.erase(event.index)
		_start_two_fingers()
	elif event is InputEventScreenDrag:
		_touches[event.index] = event.position
		if _touches.size() == 1:
			yaw -= event.relative.x * 0.005
			pitch = clampf(pitch - event.relative.y * 0.004, -1.5, -0.05)
		elif _touches.size() >= 2:
			_two_fingers()
		_apply()
	elif event is InputEventMouseButton and event.pressed:
		if event.button_index == MOUSE_BUTTON_WHEEL_UP:
			distance = maxf(min_distance, distance * 0.9)
		elif event.button_index == MOUSE_BUTTON_WHEEL_DOWN:
			distance = minf(max_distance, distance * 1.1)
		_apply()


func _start_two_fingers() -> void:
	if _touches.size() == 2:
		var p: Array = _touches.values()
		_last_pinch = p[0].distance_to(p[1])
		_last_center = (p[0] + p[1]) / 2.0
	else:
		_last_pinch = 0.0


func _two_fingers() -> void:
	var p: Array = _touches.values()
	var d: float = p[0].distance_to(p[1])
	var c: Vector2 = (p[0] + p[1]) / 2.0
	if _last_pinch > 0.0 and d > 1.0:
		distance = clampf(distance * _last_pinch / d, min_distance, max_distance)
		var delta := c - _last_center
		var right := Vector3(cos(yaw), 0.0, -sin(yaw))
		var forward := Vector3(-sin(yaw), 0.0, -cos(yaw))
		position += (-right * delta.x + forward * delta.y) * distance * 0.002
	_last_pinch = d
	_last_center = c


func _apply() -> void:
	rotation = Vector3(pitch, yaw, 0.0)
	_cam.position = Vector3(0.0, 0.0, distance)
