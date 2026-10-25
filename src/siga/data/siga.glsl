// siga: repaints Siga font glyphs (U+10FB00..U+10FB13) as a live segmented bar.
//
// Glyph pixels carry key color (1, 17/255, (48 + 2*slot)/255), slot 0..79 across
// the 20-cell bar, 4 slots per cell. Blending against the background scales all
// channels, so the key is checked by ratio to R.
//
// The value arrives in palette entry 254 (OSC 4), written by `siga`. The cursor
// color would be less visible, but Ghostty only refreshes shader uniforms when
// the terminal is dirty, and OSC 12 does not mark it dirty; OSC 4 does.
// Encoded colors stay within #e0e0e0..#ffffff, near the default #e4e4e4:
//   R = 0xE0 | (v >> 5)          v = progress in 0..1023
//   G = 0xE0 | (v & 31)
//   B = 0xF0 | state             state: 0 clear, 1 run, 2 busy, 3 done, 4 fail

const float CELLS = 20.0;
const float SEGS_PER_CELL = 2.0;
const float SEGS = CELLS * SEGS_PER_CELL;
const float KEY_G = 17.0 / 255.0;
const float KEY_B0 = 48.0 / 255.0;
const float THICKNESS = 0.55;  // segment height, fraction of the glyph height
const float GAP = 2.0;         // px between the two segments inside a cell
const float RADIUS = 2.0;      // px corner radius
const int SCAN = 48;           // max px searched for cell and glyph edges

const vec3 OFF = vec3(0.13, 0.15, 0.18);
const vec3 RUN_A = vec3(0.13, 0.83, 0.93);
const vec3 RUN_B = vec3(0.23, 0.51, 0.96);
const vec3 DONE = vec3(0.20, 0.80, 0.42);
const vec3 FAIL = vec3(0.96, 0.30, 0.30);

// Slot under pixel p, or -1 when p is not a key pixel.
float slotAt(vec2 p) {
    vec4 c = texture(iChannel0, p / iResolution.xy);
    if (c.r < 0.25) return -1.0;
    if (abs(c.g / c.r - KEY_G) > 0.02) return -1.0;
    float s = (c.b / c.r - KEY_B0) * 255.0 / 2.0;
    if (s < -0.6 || s > CELLS * 4.0 - 0.4) return -1.0;
    return floor(s + 0.5);
}

float cellAt(vec2 p) {
    float s = slotAt(p);
    return s < 0.0 ? -1.0 : floor(s / 4.0);
}

float roundedBox(vec2 p, vec2 halfSize, float r) {
    vec2 q = abs(p) - halfSize + r;
    return length(max(q, 0.0)) + min(max(q.x, q.y), 0.0) - r;
}

void mainImage(out vec4 fragColor, in vec2 fragCoord) {
    vec4 c = texture(iChannel0, fragCoord / iResolution.xy);
    float cell = cellAt(fragCoord);
    if (cell < 0.0) {
        fragColor = c;
        return;
    }

    // Extent of this glyph: horizontally within the cell, vertically overall.
    float l = 0.0, r = 0.0, up = 0.0, dn = 0.0;
    for (int i = 1; i < SCAN; i++) {
        if (cellAt(fragCoord - vec2(float(i), 0.0)) != cell) break;
        l = float(i);
    }
    for (int i = 1; i < SCAN; i++) {
        if (cellAt(fragCoord + vec2(float(i), 0.0)) != cell) break;
        r = float(i);
    }
    for (int i = 1; i < SCAN; i++) {
        if (cellAt(fragCoord + vec2(0.0, float(i))) < 0.0) break;
        up = float(i);
    }
    for (int i = 1; i < SCAN; i++) {
        if (cellAt(fragCoord - vec2(0.0, float(i))) < 0.0) break;
        dn = float(i);
    }
    float cellW = l + r + 1.0;
    float glyphH = up + dn + 1.0;

    // Which segment of the cell, and the pixel's position inside it.
    float segW = (cellW - GAP * (SEGS_PER_CELL - 1.0)) / SEGS_PER_CELL;
    float x = l + 0.5;
    float k = min(floor(x / (segW + GAP)), SEGS_PER_CELL - 1.0);
    float sx = x - k * (segW + GAP);
    float seg = cell * SEGS_PER_CELL + k;
    float pos = (seg + clamp(sx / segW, 0.0, 1.0)) / SEGS;

    vec2 p = vec2(sx - 0.5 * segW, (dn + 0.5) - 0.5 * glyphH);
    float d = roundedBox(p, vec2(0.5 * segW, 0.5 * THICKNESS * glyphH), RADIUS);
    float inside = clamp(0.5 - d, 0.0, 1.0);

    // Decode progress and state from palette entry 254.
    ivec3 cc = ivec3(iPalette[254] * 255.0 + 0.5);
    int state = 0;
    float v = 0.0;
    if ((cc.r & 0xE0) == 0xE0 && (cc.g & 0xE0) == 0xE0 && (cc.b & 0xF8) == 0xF0) {
        state = cc.b & 7;
        v = float(((cc.r & 31) << 5) | (cc.g & 31)) / 1023.0;
    }

    // How much of this segment is lit: 0..1, partial for the leading one.
    float lit = clamp(v * SEGS - seg, 0.0, 1.0);
    // strict: an unlit segment (lit = 0) must not light its sx = 0 column
    float segFill = sx / segW < lit ? 1.0 : 0.0;
    vec3 col = OFF;

    if (state == 1) {
        vec3 base = mix(RUN_A, RUN_B, pos);
        // Fast highlight wave running through the lit segments.
        float wave = fract(iTime * 1.6 - seg / SEGS * 1.5);
        float shine = 0.45 * pow(wave, 10.0);
        // Leading segment pulses.
        float lead = (lit > 0.0 && lit < 1.0) || (seg == floor(v * SEGS) - 1.0 && lit == 1.0 && v < 1.0) ? 1.0 : 0.0;
        float pulse = lead * (0.35 + 0.35 * sin(iTime * 12.0));
        col = mix(OFF, base * (1.0 + shine + pulse), segFill);
    } else if (state == 2) {
        // Comet bouncing across the bar.
        float t = fract(iTime / 1.2);
        float head = (t < 0.5 ? t * 2.0 : 2.0 - t * 2.0) * (SEGS + 6.0) - 3.0;
        float dist = t < 0.5 ? head - seg : seg - head;
        float trail = dist >= 0.0 ? exp(-dist * 0.55) : 0.0;
        col = mix(OFF, mix(RUN_A, RUN_B, pos), clamp(trail, 0.0, 1.0));
    } else if (state == 3) {
        float wave = fract(iTime * 0.8 - seg / SEGS);
        col = DONE * (1.0 + 0.25 * pow(wave, 12.0));
    } else if (state == 4) {
        col = mix(vec3(0.29, 0.13, 0.14), FAIL, segFill);
    }

    fragColor = vec4(mix(iBackgroundColor, col, inside), 1.0);
}
