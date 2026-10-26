extends Node
## Talks with the web page around the Godot canvas (aelumara.pages.dev): the page keeps the chat, the book,
## the stats and the info panel; Godot draws the world. Messages are JSON strings sent with postMessage.
##
## Page -> Godot: {"type": "view", "name": "overview" | "top" | "horizon" | "far"}
##                {"type": "follow", "index": n}  (-1 stops following)
##                {"type": "zoom", "f": 0.75}
##                {"type": "data", "state": {...}, "world": {...}}
## Godot -> page: {"type": "ready"}
##                {"type": "pick", "title": "...", "body": ["...", ...]}  (no title: close the panel)
##                {"type": "followables", "names": [...]}
##                {"type": "follow", "name": "..."}  (empty: not following)

signal command(msg: Dictionary)

var embedded := false
var _callback: JavaScriptObject


func _ready() -> void:
	if not OS.has_feature("web"):
		return
	var win := JavaScriptBridge.get_interface("window")
	embedded = JavaScriptBridge.eval("window.parent !== window", true)
	_callback = JavaScriptBridge.create_callback(_on_message)
	win.addEventListener("message", _callback)
	send({"type": "ready"})


func send(msg: Dictionary) -> void:
	if embedded:
		JavaScriptBridge.get_interface("window").parent.postMessage(JSON.stringify(msg), "*")


func _on_message(args: Array) -> void:
	var data = args[0].data
	if typeof(data) != TYPE_STRING:
		return
	var msg = JSON.parse_string(data)
	if msg is Dictionary and msg.has("type"):
		command.emit(msg)
