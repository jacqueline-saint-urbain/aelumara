// Island ground: five CC0 textures blended by the weights that terrain.py writes per vertex.
// COLOR = (sand, grass, jungle floor, rock), UV2.x = mud and pebbles (river bed, lake shore).
shader_type spatial;
render_mode cull_back, diffuse_lambert, specular_disabled;

uniform sampler2D tex_sand : source_color, filter_linear_mipmap, repeat_enable;
uniform sampler2D tex_grass : source_color, filter_linear_mipmap, repeat_enable;
uniform sampler2D tex_jungle : source_color, filter_linear_mipmap, repeat_enable;
uniform sampler2D tex_rock : source_color, filter_linear_mipmap, repeat_enable;
uniform sampler2D tex_mud : source_color, filter_linear_mipmap, repeat_enable;
uniform vec3 grass_tint : source_color = vec3(0.92, 1.0, 0.82);

varying vec3 wpos;
varying vec3 wnrm;

void vertex() {
	wpos = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
	wnrm = normalize((MODEL_MATRIX * vec4(NORMAL, 0.0)).xyz);
}

// Two scales of the same texture hide the repetition.
vec3 layered(sampler2D t, vec2 p, float s) {
	return mix(texture(t, p * s).rgb, texture(t, p * s * 0.23 + 0.37).rgb, 0.45);
}

// Rock is projected on three axes so cliffs do not stretch it.
vec3 triplanar(sampler2D t, float s) {
	vec3 b = pow(abs(wnrm), vec3(4.0));
	b /= (b.x + b.y + b.z);
	return texture(t, wpos.zy * s).rgb * b.x + texture(t, wpos.xz * s).rgb * b.y + texture(t, wpos.xy * s).rgb * b.z;
}

void fragment() {
	vec4 w = COLOR;
	vec2 p = wpos.xz;
	vec3 sand = layered(tex_sand, p, 0.16);
	vec3 grass = layered(tex_grass, p, 0.12) * grass_tint;
	vec3 jungle = layered(tex_jungle, p, 0.15);
	vec3 rock = triplanar(tex_rock, 0.09);
	vec3 c = sand * w.r + grass * w.g + jungle * w.b + rock * w.a;
	c = mix(c, layered(tex_mud, p, 0.2), clamp(UV2.x, 0.0, 1.0));
	float wet = 1.0 - smoothstep(0.0, 0.7, wpos.y);   // wet sand and rock at the waterline
	c *= mix(1.0, 0.7, wet);
	ALBEDO = c;
	ROUGHNESS = 0.95;
}
