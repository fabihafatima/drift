"""Flags text boxes in Drift-intro.pptx whose wrapped text is taller than the box."""

from pathlib import Path

from PIL import ImageFont
from pptx import Presentation
from pptx.util import Emu

HERE = Path(__file__).resolve().parent
FONTS = {
    ("Helvetica Neue", False): ("/System/Library/Fonts/HelveticaNeue.ttc", 0),
    ("Helvetica Neue", True): ("/System/Library/Fonts/HelveticaNeue.ttc", 1),
    ("Menlo", False): ("/System/Library/Fonts/Menlo.ttc", 0),
    ("Menlo", True): ("/System/Library/Fonts/Menlo.ttc", 1),
}
PX = 100  # pixels per inch for measuring


def font(name, bold, pt):
    path, idx = FONTS[(name or "Helvetica Neue", bool(bold))]
    return ImageFont.truetype(path, int(pt * PX / 72), index=idx)


def para_lines(p, width_px):
    words = []
    for r in p.runs:
        f = font(r.font.name, r.font.bold, r.font.size.pt)
        for i, part in enumerate(r.text.split(" ")):
            words.append((("" if i == 0 else " ") + part, f))
    lines, cur = 1, 0.0
    for w, f in words:
        wpx = f.getlength(w)
        if cur and cur + wpx > width_px:
            lines += 1
            cur = f.getlength(w.lstrip())
        else:
            cur += wpx
    return lines


prs = Presentation(HERE / "Drift-intro.pptx")
for n, s in enumerate(prs.slides, 1):
    for shp in s.shapes:
        if not shp.has_text_frame or not shp.text_frame.text.strip():
            continue
        tf = shp.text_frame
        w = Emu(shp.width - tf.margin_left - tf.margin_right).inches * PX
        h = 0.0
        for p in tf.paragraphs:
            if not p.runs:
                continue
            pt = max(r.font.size.pt for r in p.runs)
            h += para_lines(p, w) * pt * 1.2 * (p.line_spacing or 1.0) / 72
        box_h = Emu(shp.height).inches
        bottom = Emu(shp.top).inches + h
        if h > box_h + 0.05 or bottom > 7.3:
            print(f"slide {n}: need {h:.2f}in, box {box_h:.2f}in, bottom {bottom:.2f}in :: {tf.text[:60]!r}")
print("done")
