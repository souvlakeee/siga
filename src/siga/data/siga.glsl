// siga: repaints Siga font glyphs (U+10FB00..U+10FB4F) as live segmented bars.
//
// Glyph pixels carry key color (1, (17 + 12*bar)/255, (48 + 2*slot)/255): slot 0..79
// across the 20-cell bar (4 slots per cell), and bar 0..3 says which of FAMILIES bars
// the glyph belongs to. Blending against the background scales all channels, so both
// are read by ratio to R, each bar's green at least half a GSTEP from its neighbours'.
//
// Each bar's value arrives in palette entry BASE+bar (OSC 4), written by `siga`, so a
// finished bar keeps its own entry and freezes while another bar moves. The cursor color
// would be less visible, but Ghostty only refreshes shader uniforms when the terminal is
// dirty, and OSC 12 does not mark it dirty; OSC 4 does. Each entry stays within
// #e0e0e0..#ffffff, near the default ramp it overwrites:
//   R = 0xE0 | (v >> 5)          v = progress in 0..1023
//   G = 0xE0 | (v & 31)
//   B = 0xF0 | state             state: 0 clear, 1 run, 2 busy, 3 done, 4 fail

const float CELLS = 20.0;
const float SEGS_PER_CELL = 2.0;
const float SEGS = CELLS * SEGS_PER_CELL;
const int FAMILIES = 4;
const int BASE = 252;              // palette entry of bar 0; bar j uses BASE+j
const float KEY_G = 17.0 / 255.0;
const float GSTEP = 12.0 / 255.0;  // green step between bars; match within less than half
const float KEY_B0 = 48.0 / 255.0;
const float THICKNESS = 0.55;  // segment height, fraction of the glyph height
const float GAP = 2.0;         // px between adjacent cell boxes
const float RADIUS = 2.0;      // px corner radius
const int SCAN = 48;           // max px searched for cell and glyph edges

const vec3 OFF = vec3(0.13, 0.15, 0.18);
const vec3 RUN_A = vec3(0.13, 0.83, 0.93);
const vec3 RUN_B = vec3(0.23, 0.51, 0.96);
const vec3 DONE = vec3(0.20, 0.80, 0.42);
const vec3 FAIL = vec3(0.96, 0.30, 0.30);

// A per-(bar,cell) id, so cells of different bars standing side by side never merge
// when the edges are scanned, or -1 off a bar. One texture fetch: the green/red ratio
// gives the bar (one of FAMILIES key greens), the blue/red ratio the cell within it.
float cellAt(vec2 p) {
    vec4 c = texture(iChannel0, p / iResolution.xy);
    if (c.r < 0.25) return -1.0;
    float gr = c.g / c.r;
    float bar = -1.0;
    for (int j = 0; j < FAMILIES; j++) {
        if (abs(gr - (KEY_G + float(j) * GSTEP)) < 0.008) { bar = float(j); break; }
    }
    if (bar < 0.0) return -1.0;
    float s = (c.b / c.r - KEY_B0) * 255.0 / 2.0;  // 0..79 across the 20 cells, 4 per cell
    if (s < -0.6 || s > CELLS * 4.0 - 0.4) return -1.0;
    return bar * CELLS + floor(floor(s + 0.5) / 4.0);
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
    float bar = floor(cell / CELLS);
    float lcell = cell - bar * CELLS;  // 0..19 within this bar

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
    if (cellW < 6.0 || glyphH < 8.0) {  // too small to be a bar cell: a text stroke keyed by chance
        fragColor = c;
        return;
    }

    // The two segments only set the fill resolution; the drawn box is the whole cell,
    // so the GAP falls at cell boundaries and the first and last cells are full boxes,
    // not halves (segments flush to the cell edges paired up across the joins).
    float segW = cellW / SEGS_PER_CELL;
    float x = l + 0.5;
    float k = min(floor(x / segW), SEGS_PER_CELL - 1.0);
    float sx = x - k * segW;
    float seg = lcell * SEGS_PER_CELL + k;
    float pos = (seg + clamp(sx / segW, 0.0, 1.0)) / SEGS;

    vec2 p = vec2(x - 0.5 * cellW, (dn + 0.5) - 0.5 * glyphH);
    float d = roundedBox(p, vec2(0.5 * cellW - 0.5 * GAP, 0.5 * THICKNESS * glyphH), RADIUS);
    float inside = clamp(0.5 - d, 0.0, 1.0);

    // Decode progress and state from this bar's palette entry (BASE+bar).
    ivec3 cc = ivec3(iPalette[BASE + int(bar)] * 255.0 + 0.5);
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
