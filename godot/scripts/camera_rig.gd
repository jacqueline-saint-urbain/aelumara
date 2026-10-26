extends Node3D
## Touch camera: one finger turns around, two fingers pinch to zoom and drag to move.
## With a mouse: drag to turn, wheel to zoom.

@export var distance := 230.0
@export var min_distance := 6.0
@export var max_distance := 500.0
@export var yaw := 0.0
@export var pitch := -0.75

var follow: Node3D
var _tween: Tween
var _touches := {}
var _last_pinch := 0.0
var _last_center := Vector2.ZERO

@onready var _cam: Camera3D = $Camera3D


func _ready() -> void:
	_apply()


func focus(target: Vector3, dist: float) -> void:
	if _tween:
		_tween.kill()
	position = target
	distance = dist
	_apply()


## Glides to a view in about a second.
func fly_to(target: Vector3, dist: float, to_yaw: float, to_pitch: float) -> void:
	if _tween:
		_tween.kill()
	# Turn the short way round.
	to_yaw = yaw + wrapf(to_yaw - yaw, -PI, PI)
	_tween = create_tween().set_parallel().set_trans(Tween.TRANS_CUBIC).set_ease(Tween.EASE_OUT)
	_tween.tween_property(self, "position", target, 1.1)
	_tween.tween_property(self, "distance", dist, 1.1)
	_tween.tween_property(self, "yaw", to_yaw, 1.1)
	_tween.tween_property(self, "pitch", to_pitch, 1.1)


func zoom(f: float) -> void:
	distance = clampf(distance * f, min_distance, max_distance)


func _process(_delta: float) -> void:
	if follow and is_instance_valid(follow) and not (_tween and _tween.is_running()):
		position = position.lerp(follow.global_position + Vector3(0, 1, 0), 0.1)
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
			if _tween:
				_tween.kill()
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
		follow = null
		var right := Vector3(cos(yaw), 0.0, -sin(yaw))
		var forward := Vector3(-sin(yaw), 0.0, -cos(yaw))
		position += (-right * delta.x + forward * delta.y) * distance * 0.002
	_last_pinch = d
	_last_center = c


func _apply() -> void:
	rotation = Vector3(pitch, yaw, 0.0)
	_cam.position = Vector3(0.0, 0.0, distance)
