"""Stage 6 - deterministic auto-fix loop.

The QA layer (deterministic geometry + Gemini vision) DETECTS problems; this
module FIXES them with safe, deterministic corrections and re-verifies, looping
until the slide is clean or no further progress is possible.

Correctors (all safe, never remove content):
  - enforce_palette : text not black/white/red -> Stevens Red; text on a red or
                      blue fill -> white (contrast).
  - clamp_in_page   : any shape bleeding off the slide is moved/resized back in.
  - center_tables   : a table shifted off the title's left margin is re-centered.
  - enforce_autofit : word-wrap + shrink-to-fit so text never overflows.
  - spread_overlaps : independent text boxes that overlap are pushed apart.

relax_positions() is a general 2D collision relaxation used at BUILD time by the
diagram builders so reconstructed diagrams don't overlap in the first place.
"""
from __future__ import annotations

import math
import os
import sys

from pptx.util import Emu
from pptx.dml.color import RGBColor
from pptx.enum.dml import MSO_FILL

_HERE = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_HERE)
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)
from app import brand as B                       # noqa: E402
from app.qa import geometry                      # noqa: E402

EMU = 914400
# Allowed text colors: charcoal ink (body), black (diagram labels), white, red.
ALLOWED = {B.INK.upper(), B.BLACK.upper(), B.WHITE.upper(), B.RED.upper()}


# --------------------------------------------------------------------------- #
# build-time collision relaxation (inches)
# --------------------------------------------------------------------------- #
def _overlap_xy(ax, ay, bx, by, w, h, pad):
    """Return the overlap extent (ox, oy) of two equal boxes centered at a,b."""
    ox = (w + pad) - abs(ax - bx)
    oy = (h + pad) - abs(ay - by)
    return ox, oy


def relax_positions(centers, w, h, bounds, obstacles=None, pad=0.15, iters=300):
    """Nudge box centers so no two overlap, staying within bounds.

    centers  : list of [x, y] (inches, box CENTER)
    w, h     : box size (inches)
    bounds   : (xmin, ymin, xmax, ymax) allowed range for centers
    obstacles: list of (cx, cy, bw, bh) fixed boxes to also avoid (e.g. center oval)
    Returns the adjusted centers (same list, mutated)."""
    xmin, ymin, xmax, ymax = bounds
    obstacles = obstacles or []
    n = len(centers)
    for _ in range(iters):
        moved = False
        for i in range(n):
            for j in range(i + 1, n):
                ax, ay = centers[i]; bx, by = centers[j]
                ox, oy = _overlap_xy(ax, ay, bx, by, w, h, pad)
                if ox > 0 and oy > 0:
                    moved = True
                    if ox < oy:   # separate along the smaller axis
                        dx = ox / 2 * (1 if ax >= bx else -1)
                        centers[i][0] += dx; centers[j][0] -= dx
                    else:
                        dy = oy / 2 * (1 if ay >= by else -1)
                        centers[i][1] += dy; centers[j][1] -= dy
            # push out of fixed obstacles (e.g. the center oval)
            for (cx, cy, bw, bh) in obstacles:
                ox = (w + bw) / 2 + pad - abs(centers[i][0] - cx)
                oy = (h + bh) / 2 + pad - abs(centers[i][1] - cy)
                if ox > 0 and oy > 0:
                    moved = True
                    if oy <= ox:
                        centers[i][1] += oy * (1 if centers[i][1] >= cy else -1)
                    else:
                        centers[i][0] += ox * (1 if centers[i][0] >= cx else -1)
            # clamp inside bounds
            centers[i][0] = max(xmin, min(xmax, centers[i][0]))
            centers[i][1] = max(ymin, min(ymax, centers[i][1]))
        if not moved:
            break
    return centers


# --------------------------------------------------------------------------- #
# slide-level correctors (EMU)
# --------------------------------------------------------------------------- #
def _fill_hex(sh):
    try:
        if sh.fill.type == MSO_FILL.SOLID:
            return str(sh.fill.fore_color.rgb).upper()
    except Exception:
        pass
    return None


def enforce_palette(slide):
    fixes = 0
    for sh in slide.shapes:
        if not sh.has_text_frame:
            continue
        fh = _fill_hex(sh)
        on_strong = fh in (B.RED.upper(), B.BLUE.upper())
        for p in sh.text_frame.paragraphs:
            for r in p.runs:
                try:
                    cur = str(r.font.color.rgb).upper()
                except Exception:
                    cur = None
                if on_strong:
                    if cur != B.WHITE.upper():
                        r.font.color.rgb = RGBColor.from_string(B.WHITE); fixes += 1
                elif cur is not None and cur not in ALLOWED:
                    # off-brand body text snaps to charcoal ink, NOT red -- red is
                    # reserved for deliberate, sparse emphasis (never a blanket
                    # recolor, which is what produced "everything red").
                    r.font.color.rgb = RGBColor.from_string(B.INK); fixes += 1
    return fixes


def clamp_in_page(slide, sw, sh):
    fixes = 0
    for shape in slide.shapes:
        try:
            x, y, w, h = (int(shape.left or 0), int(shape.top or 0),
                          int(shape.width or 0), int(shape.height or 0))
        except Exception:
            continue
        if w == 0 and h == 0:
            continue
        nw, nh = min(w, sw), min(h, sh)
        nx = 0 if nw >= sw else min(max(x, 0), sw - nw)
        ny = 0 if nh >= sh else min(max(y, 0), sh - nh)
        if (nx, ny, nw, nh) != (x, y, w, h):
            try:
                shape.left, shape.top = Emu(nx), Emu(ny)
                shape.width, shape.height = Emu(nw), Emu(nh)
                fixes += 1
            except Exception:
                pass
    return fixes


def center_tables(slide, sw, title_left_emu=None):
    fixes = 0
    for shape in slide.shapes:
        if not getattr(shape, "has_table", False):
            continue
        try:
            w = int(shape.width or 0)
            target = (sw - w) // 2
            if abs(int(shape.left or 0) - target) > 0.15 * EMU:
                shape.left = Emu(max(0, target)); fixes += 1
        except Exception:
            pass
    return fixes


def _box(sh):
    return geometry._box(sh)


def spread_overlaps(slide, sw, sh, overlaps):
    """Push apart independent overlapping text boxes (skips tables/pictures)."""
    by_id = {s.shape_id: s for s in slide.shapes if hasattr(s, "shape_id")}
    changed = 0
    for iss in overlaps:
        a = by_id.get(iss.get("shape_id")); b = by_id.get(iss.get("other_id"))
        if a is None or b is None:
            continue
        if getattr(a, "has_table", False) or getattr(b, "has_table", False):
            continue
        ax, ay, aw, ah = _box(a); bx, by, bw, bh = _box(b)
        acx, acy = ax + aw / 2, ay + ah / 2
        bcx, bcy = bx + bw / 2, by + bh / 2
        ox = (aw + bw) / 2 - abs(acx - bcx)
        oy = (ah + bh) / 2 - abs(acy - bcy)
        if ox <= 0 or oy <= 0:
            continue
        try:
            if oy <= ox:
                d = int(oy / 2) + 9144
                a.top = Emu(max(0, min(sh - ah, int(a.top) + (d if acy >= bcy else -d))))
                b.top = Emu(max(0, min(sh - bh, int(b.top) + (-d if acy >= bcy else d))))
            else:
                d = int(ox / 2) + 9144
                a.left = Emu(max(0, min(sw - aw, int(a.left) + (d if acx >= bcx else -d))))
                b.left = Emu(max(0, min(sw - bw, int(b.left) + (-d if acx >= bcx else d))))
            changed += 1
        except Exception:
            pass
    return changed


def autofix_slide(slide, sw, sh, max_iter=3):
    """Apply safe corrections and loop geometry checks. sw, sh in EMU.
    Returns (applied: list[str], remaining: list[dict])."""
    applied = []
    n = enforce_palette(slide)
    if n:
        applied.append(f"recolored {n} off-brand text run(s) -> brand palette")
    n = clamp_in_page(slide, sw, sh)
    if n:
        applied.append(f"clamped {n} shape(s) back inside the page")
    n = center_tables(slide, sw)
    if n:
        applied.append("re-centered table")
    geometry.enforce_autofit(slide)

    for _ in range(max_iter):
        issues = geometry.check_slide(slide, sw, sh)
        overl = [i for i in issues if i["type"] == "overlap"]
        if not overl:
            break
        if not spread_overlaps(slide, sw, sh, overl):
            break
        applied.append(f"separated {len(overl)} overlapping text box(es)")

    remaining = geometry.check_slide(slide, sw, sh)
    return applied, remaining
