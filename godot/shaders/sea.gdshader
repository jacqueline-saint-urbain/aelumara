// Sea: colour from the depth map that terrain.py writes, foam on the shore, small waves.
shader_type spatial;
render_mode blend_mix, cull_disabled, depth_draw_always, specular_schlick_ggx;

uniform sampler2D depth_map : filter_linear, repeat_disable;
uniform vec4 bounds = vec4(-280.0, -290.0, 280.0, 56.0);   // x0, z0, x1, z1 of the depth map
uniform vec3 shallow : source_color = vec3(0.36, 0.83, 0.82);
uniform vec3 deep : source_color = vec3(0.07, 0.36, 0.58);

varying vec3 wpos;

void vertex() {
	wpos = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
	VERTEX.y += sin(wpos.x * 0.15 + TIME * 0.8) * 0.06 + sin(wpos.z * 0.21 + TIME * 0.6) * 0.05;
}

void fragment() {
	vec2 uv = (wpos.xz - bounds.xy) / (bounds.zw - bounds.xy);
	bool inside = all(greaterThan(uv, vec2(0.0))) && all(lessThan(uv, vec2(1.0)));
	float d = inside ? texture(depth_map, uv).r * 8.0 : 8.0;
	vec3 col = mix(shallow, deep, smoothstep(0.0, 5.0, d));
	float ripple = 0.5 + 0.5 * sin(TIME * 1.6 - d * 9.0 + sin(wpos.x * 0.3) * 1.5);
	float foam = (1.0 - smoothstep(0.08, 0.7, d)) * mix(0.55, 1.0, ripple);
	ALBEDO = mix(col, vec3(0.97), foam * 0.85);
	ALPHA = min(1.0, mix(0.45, 1.0, smoothstep(0.0, 3.5, d)) + foam * 0.3);
	ROUGHNESS = 0.12;
	SPECULAR = 0.55;
}
