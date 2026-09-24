"""Deterministic geometry QA: catch overlap / off-slide / text-overflow before
export. Runs without rendering, so it works even when LibreOffice is absent.

This directly serves the locked rule: no text out of the box, no overlap.
"""
from __future__ import annotations

from pptx.util import Emu
from pptx.enum.text import MSO_AUTO_SIZE

# Rough per-character width factor (as a fraction of font size) for Arial, and
# line-height factor. Used only to *estimate* overflow so we can shrink/flag;
# real fit is enforced by PowerPoint autofit at open time as a backstop.
_CHAR_W = 0.52
_LINE_H = 1.22


def _box(sh):
    try:
        return (int(sh.left or 0), int(sh.top or 0),
                int(sh.width or 0), int(sh.height or 0))
    except Exception:
        return (0, 0, 0, 0)


def _intersect_area(a, b):
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    ix = max(0, min(ax + aw, bx + bw) - max(ax, bx))
    iy = max(0, min(ay + ah, by + bh) - max(ay, by))
    return ix * iy


def overlaps(a, b, tol_frac=0.12):
    """True if two boxes overlap by more than tol_frac of the smaller area."""
    area = _intersect_area(a, b)
    if area <= 0:
        return False
    sa = max(1, a[2] * a[3])
    sb = max(1, b[2] * b[3])
    return area / min(sa, sb) > tol_frac


def estimate_overflow(sh):
    """Estimate whether text overflows its box. Returns (overflow, fill_ratio)."""
    if not sh.has_text_frame:
        return (False, 0.0)
    tf = sh.text_frame
    left, top, width, height = _box(sh)
    if width <= 0 or height <= 0:
        return (False, 0.0)
    ml = int(getattr(tf, "margin_left", Emu(91440)) or 0)
    mr = int(getattr(tf, "margin_right", Emu(91440)) or 0)
    mt = int(getattr(tf, "margin_top", Emu(45720)) or 0)
    mb = int(getattr(tf, "margin_bottom", Emu(45720)) or 0)
    avail_w = max(1, width - ml - mr)
    avail_h = max(1, height - mt - mb)

    total_lines = 0.0
    max_size = 12.0
    for p in tf.paragraphs:
        size = None
        text = ""
        for r in p.runs:
            text += r.text or ""
            if r.font.size:
                size = max(size or 0, r.font.size.pt)
        size = size or 18.0
        max_size = max(max_size, size)
        if not text.strip():
            total_lines += 0.6
            continue
        char_w_emu = size * _CHAR_W * 12700  # pt -> EMU (1pt = 12700 EMU)
        chars_per_line = max(1, int(avail_w / char_w_emu))
        total_lines += max(1, -(-len(text) // chars_per_line))  # ceil

    needed_h = total_lines * max_size * _LINE_H * 12700
    ratio = needed_h / avail_h if avail_h else 0.0
    return (ratio > 1.02, ratio)


def check_slide(slide, slide_w, slide_h):
    """Return a list of geometry issue dicts for one slide."""
    issues = []
    shapes = [sh for sh in slide.shapes]

    # off-slide bleed
    for sh in shapes:
        x, y, w, h = _box(sh)
        if w == 0 and h == 0:
            continue
        if x < -9144 or y < -9144 or (x + w) > slide_w + 9144 or (y + h) > slide_h + 9144:
            issues.append({"type": "offslide", "shape_id": sh.shape_id})

    # overflow
    for sh in shapes:
        over, ratio = estimate_overflow(sh)
        if over:
            issues.append({"type": "overflow", "shape_id": sh.shape_id,
                           "ratio": round(ratio, 2)})

    # overlap (text-bearing shapes only, to avoid decorative bands)
    text_shapes = [sh for sh in shapes
                   if sh.has_text_frame and sh.text_frame.text.strip()]
    for i in range(len(text_shapes)):
        for j in range(i + 1, len(text_shapes)):
            if overlaps(_box(text_shapes[i]), _box(text_shapes[j])):
                issues.append({"type": "overlap",
                               "shape_id": text_shapes[i].shape_id,
                               "other_id": text_shapes[j].shape_id})
    return issues


def enforce_autofit(slide):
    """Backstop: make every text box wrap + shrink-to-fit so PowerPoint will not
    render overflowing text. Deterministic and safe."""
    for sh in slide.shapes:
        if not sh.has_text_frame:
            continue
        tf = sh.text_frame
        try:
            tf.word_wrap = True
            tf.auto_size = MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE
        except Exception:
            pass
