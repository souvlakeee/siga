#!/usr/bin/env python3
"""Build Siga.ttf: 20 full-cell sbix glyphs whose colors encode bar position.

Each glyph is split into STRIPES vertical stripes. Stripe slot s = cell*STRIPES + k
is painted with key color (0xFF, KEY_G, KEY_B0 + 2*s). The shader recovers s from
B/R and verifies the key with G/R, which survives blending against the background.

Why sbix, P3 and the OS/2 heights:
- Ghostty 1.3 draws COLR glyphs in the text color; only sbix bitmaps keep their color.
- On macOS Ghostty rasterizes color glyphs in Display P3 and hands shaders P3 values
  (alpha-blending = native), so the PNGs carry a P3 profile to skip any conversion.
- Ghostty scales fallback faces to match the primary font's x-height; without
  JetBrains Mono's x/cap heights the glyph shrinks to ~75% of the cell.
"""
import io
import sys
from pathlib import Path

from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import newTable
from fontTools.ttLib.tables.sbixGlyph import Glyph as SbixGlyph
from fontTools.ttLib.tables.sbixStrike import Strike
from PIL import Image

FAMILY = "Siga"
PS_NAME = "Siga-Regular"
FIRST_CP = 0x10FB00
CELLS = 20
STRIPES = 4
KEY_G = 0x11
KEY_B0 = 0x30
STRIKES = (16, 20, 24, 28, 32, 36, 40, 48, 56, 64, 80, 96, 128)
P3_PROFILE = Path("/System/Library/ColorSync/Profiles/Display P3.icc")

# JetBrains Mono metrics, so the glyph box equals the terminal cell.
UPM = 1000
ADVANCE = 600
ASCENT = 1020
DESCENT = -300
CAP_HEIGHT = 730
X_HEIGHT = 550


def rect():
    pen = TTGlyphPen(None)
    pen.moveTo((0, DESCENT))
    pen.lineTo((0, ASCENT))
    pen.lineTo((ADVANCE, ASCENT))
    pen.lineTo((ADVANCE, DESCENT))
    pen.closePath()
    return pen.glyph()


def cell_png(cell, ppem, icc):
    w = round(ADVANCE * ppem / UPM)
    h = round((ASCENT - DESCENT) * ppem / UPM)
    im = Image.new("RGBA", (w, h))
    for x in range(w):
        slot = cell * STRIPES + x * STRIPES // w
        color = (0xFF, KEY_G, KEY_B0 + 2 * slot, 0xFF)
        for y in range(h):
            im.putpixel((x, y), color)
    buf = io.BytesIO()
    im.save(buf, "PNG", icc_profile=icc)
    return buf.getvalue()


def build(out: Path):
    bars = [f"bar{i:02d}" for i in range(CELLS)]
    order = [".notdef", *bars]
    icc = P3_PROFILE.read_bytes()

    fb = FontBuilder(UPM, isTTF=True)
    fb.setupGlyphOrder(order)
    fb.setupCharacterMap({FIRST_CP + i: name for i, name in enumerate(bars)})
    fb.setupGlyf({".notdef": TTGlyphPen(None).glyph(), **{n: rect() for n in bars}})
    fb.setupHorizontalMetrics({n: (ADVANCE, 0) for n in order})
    fb.setupHorizontalHeader(ascent=ASCENT, descent=DESCENT)
    fb.setupNameTable({
        "familyName": FAMILY,
        "styleName": "Regular",
        "uniqueFontIdentifier": f"{PS_NAME};1.0",
        "fullName": f"{FAMILY} Regular",
        "version": "Version 1.000",
        "psName": PS_NAME,
    })
    fb.setupOS2(
        version=4,
        sTypoAscender=ASCENT, sTypoDescender=DESCENT, sTypoLineGap=0,
        usWinAscent=ASCENT, usWinDescent=-DESCENT,
        sCapHeight=CAP_HEIGHT, sxHeight=X_HEIGHT,
        fsSelection=0x40 | 0x80,
    )
    fb.setupPost(isFixedPitch=1)

    sbix = newTable("sbix")
    sbix.version = 1
    sbix.flags = 1
    for ppem in STRIKES:
        strike = Strike(ppem=ppem, resolution=72)
        strike.glyphs[".notdef"] = SbixGlyph(glyphName=".notdef", graphicType=None)
        for i, name in enumerate(bars):
            strike.glyphs[name] = SbixGlyph(
                glyphName=name, graphicType="png ",
                originOffsetX=0, originOffsetY=round(DESCENT * ppem / UPM),
                imageData=cell_png(i, ppem, icc),
            )
        sbix.strikes[ppem] = strike
    fb.font["sbix"] = sbix
    fb.save(str(out))


if __name__ == "__main__":
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[1] / "src" / "siga" / "data" / "Siga.ttf"
    build(out)
    print(out)
