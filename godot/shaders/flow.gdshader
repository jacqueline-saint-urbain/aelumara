// Moving water: the Aubeline, its cascade and Lac d'Aube. UV.y runs along the flow.
shader_type spatial;
render_mode blend_mix, cull_disabled, specular_schlick_ggx;

uniform vec3 water : source_color = vec3(0.24, 0.62, 0.78);
uniform vec3 froth : source_color = vec3(0.9, 0.97, 1.0);
uniform float speed = 0.6;
uniform float whiteness = 0.15;

void fragment() {
	float s = sin(UV.y * 9.0 - TIME * speed * 9.0 + sin(UV.x * 6.28) * 0.8) * 0.5 + 0.5;
	float edge = 1.0 - smoothstep(0.0, 0.18, min(UV.x, 1.0 - UV.x));
	float f = clamp(whiteness + s * 0.25 + edge * 0.35, 0.0, 1.0);
	ALBEDO = mix(water, froth, f);
	ALPHA = mix(0.78, 0.95, f);
	ROUGHNESS = 0.1;
}
