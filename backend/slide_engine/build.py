"""Stage 4 - deterministic native builder (demo).

Takes SlidePlans (already coverage-verified) and emits native PowerPoint for the
cited problem slides, demonstrating the fixes:
  - text preserved with emphasis (bold + Stevens Red) and citations (italic),
  - native TABLE reconstruction (slide 21),
  - two-COLUMN reconstruction (slide 27),
  - OBJECT hub-and-spoke diagram (slide 2),
  - safe RASTER fallback for image/curve diagrams (slides 4, 18).
All text comes verbatim from atoms by id -- the builder never authors words.
"""
from __future__ import annotations

import io
import math
import os
import sys

from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.oxml.ns import qn
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE, MSO_CONNECTOR

_HERE = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_HERE)
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)
from app import brand as B                                      # noqa: E402
from slide_fixer.engine import _bare, _clear_bullets, _insert_bullet_group  # noqa: E402
from slide_engine import autofix                                   # noqa: E402

import fitz                                                     # noqa: E402

TEMPLATE = os.path.join(_BACKEND, "assets", "ppt_template.pptx")
EMU = 914400

# Presets that are safe to rebuild as a rounded rectangle box. Anything else
# (trapezoid, chevron, triangle, arrows, ovals, callouts, ...) is preserved as
# an exact crop so its meaning/shape is never distorted.
_RECT_GEOMS = {
    "rect", "roundRect", "round1Rect", "round2SameRect", "round2DiagRect",
    "snip1Rect", "snip2SameRect", "snip2DiagRect", "snipRoundRect",
    "plaque", "flowChartProcess", "flowChartAlternateProcess",
    "flowChartPredefinedProcess", "actionButtonBlank",
}


def C(h):
    return RGBColor.from_string(h)


def clean(t):
    return (t or "").replace("\x0b", " ").replace("\n", " ").strip()


def clear_slides(prs):
    lst = prs.slides._sldIdLst
    for s in list(lst):
        try:
            prs.part.drop_rel(s.get(qn("r:id")))
        except Exception:
            pass
        lst.remove(s)


def layout(prs, name):
    for l in prs.slide_layouts:
        if l.name == name:
            return l
    return prs.slide_layouts[0]


def run(p, text, size, bold=False, color=B.BLACK, italic=False):
    r = p.add_run(); r.text = text
    r.font.name = B.FONT; r.font.size = Pt(size)
    r.font.bold = bold; r.font.italic = italic
    r.font.color.rgb = C(color)
    return r


def set_bullet(p, level):
    level = max(0, min(level, 2))
    pPr = p._p.get_or_add_pPr(); _clear_bullets(pPr)
    pPr.set("marL", str(274638 * (level + 1))); pPr.set("indent", "-274638")
    ch, fn, col = B.BULLETS[level]
    bc = _bare("a:buClr"); s = _bare("a:srgbClr"); s.set("val", col); bc.append(s)
    bf = _bare("a:buFont"); bf.set("typeface", fn)
    bch = _bare("a:buChar"); bch.set("char", ch)
    _insert_bullet_group(pPr, [bc, bf, bch])


def no_bullet(p):
    pPr = p._p.get_or_add_pPr(); _clear_bullets(pPr)
    _insert_bullet_group(pPr, [_bare("a:buNone")])


def title_only(prs, title):
    slide = prs.slides.add_slide(layout(prs, B.L_TITLE_ONLY))
    if slide.shapes.title is not None:
        slide.shapes.title.text = clean(title)
        for p in slide.shapes.title.text_frame.paragraphs:
            no_bullet(p)
            for r in p.runs:
                r.font.name = B.FONT; r.font.bold = True
                r.font.size = Pt(B.TITLE_PT); r.font.color.rgb = C(B.BLACK)
    return slide


def textbox(slide, l, t, w, h):
    tb = slide.shapes.add_textbox(Inches(l), Inches(t), Inches(w), Inches(h))
    tf = tb.text_frame; tf.word_wrap = True
    return tb, tf


def emph_color(atom, emphasis):
    # locked rule: body text is charcoal ink / white / Stevens Red.
    # Emphasis -> Stevens Red; otherwise the theme body ink (#363D45).
    return B.RED if emphasis else B.INK


def _runtext(a):
    """Run text with vertical tab/newline flattened but spaces PRESERVED (so
    adjacent runs like '4' + 'th' keep reading as '4th', and 'to ' + 'engage'
    stays 'to engage')."""
    return (a.text or "").replace("\x0b", " ").replace("\n", " ")


def _is_dark(hexs):
    return _lum(hexs) < 0.32 if hexs else True


def _para_groups(deck, blocks):
    """Group consecutive blocks that came from the SAME source paragraph.

    The IR emits one atom per formatting run, so a single sentence with a bold
    or colored word becomes several atoms. Rendering one bullet per atom is the
    root cause of the 'fragmented / one word per line' output. Regrouping by
    (shape_id, paragraph) restores the original line as ONE bullet with mixed
    runs."""
    groups, cur, key = [], [], None
    for b in blocks:
        a = deck.atoms.get(b.atom_id)
        if not a:
            continue
        k = (a.shape_id, a.para)
        if cur and k != key:
            groups.append(cur); cur = []
        key = k
        cur.append((b, a))
    if cur:
        groups.append(cur)
    return groups


def _base_color(atoms):
    """Dominant run color of a paragraph (so we can tell which words are the
    genuine highlights that differ from the surrounding body color)."""
    from collections import Counter
    c = Counter((a.color or "").upper() for a in atoms)
    return c.most_common(1)[0][0] if c else ""


def _trim_ends(runs):
    if runs:
        runs[0].text = runs[0].text.lstrip()
        runs[-1].text = runs[-1].text.rstrip()


def _grp_pt(grp, fallback, lo=12, hi=30):
    """Average ORIGINAL point size of a paragraph group, clamped. Lets us respect
    the source's relative hierarchy (e.g. a quote that was smaller than its
    attribution stays smaller) instead of forcing one uniform size."""
    sizes = [a.size for _, a in grp if getattr(a, "size", None)]
    if not sizes:
        return fallback
    return int(max(lo, min(hi, round(sum(sizes) / len(sizes)))))


def render_paragraphs(tf, deck, blocks, base=B.BODY_PT, first=True, big=False):
    """Canonical text renderer used by every content path.

    Text is placed by ROLE, not flattened into identical bullets:
      - quote/citation : italic, no bullet, keeps its original size,
      - source         : attribution, no bullet, smaller, em-dash prefixed,
      - note           : annotation, no bullet, italic, 'Note' lead kept,
      - subhead        : black + bold, no bullet,
      - paragraph      : prose, no bullet,
      - body           : bulleted list item.
    Bold is preserved AS bold; Stevens Red only for a run whose color differs
    from the paragraph's dominant color (a genuine highlight).
    """
    for grp in _para_groups(deck, blocks):
        b0 = grp[0][0]
        atoms = [a for _, a in grp]
        p = tf.paragraphs[0] if first else tf.add_paragraph()
        first = False
        role = b0.role

        if role in ("quote", "citation"):
            no_bullet(p)
            sz = _grp_pt(grp, 18)
            rs = [run(p, _runtext(a), sz, italic=True, color=B.INK)
                  for _, a in grp]
            _trim_ends(rs)
            continue
        if role == "source":
            no_bullet(p)
            sz = _grp_pt(grp, 14)
            txt = clean(" ".join(_runtext(a) for _, a in grp))
            if txt and txt[0] not in "\u2014\u2013-":
                txt = "\u2014 " + txt          # em-dash lead-in for attributions
            run(p, txt, sz, color=B.INK)
            continue
        if role == "note":
            no_bullet(p)
            sz = _grp_pt(grp, 14)
            rs = [run(p, _runtext(a), sz, italic=True, color=B.INK)
                  for _, a in grp]
            _trim_ends(rs)
            continue
        if role == "subhead":
            no_bullet(p)
            rs = [run(p, _runtext(a), B.SUBHEAD_PT - 4, bold=True, color=B.INK)
                  for _, a in grp]
            _trim_ends(rs)
            continue

        lvl = b0.level
        basec = _base_color(atoms)
        sz = base if big else max(B.BODY_MIN_PT, base - 2 * lvl)
        # Stevens Red is for SPARSE inline highlights only. A run counts as a
        # highlight when its color differs from the paragraph's dominant color
        # AND it is a minority of the line -- i.e. a few emphasized words inside
        # otherwise-normal text. A whole line/list in one source color is body
        # copy (charcoal ink), NOT red. This is what stops the "everything red"
        # failure the references never show.
        chars = sum(len(_runtext(a)) for _, a in grp) or 1
        hi_chars = sum(len(_runtext(a)) for _, a in grp
                       if (a.color or "").upper()
                       and (a.color or "").upper() != basec
                       and not _is_dark((a.color or "").upper()))
        allow_red = 0 < hi_chars <= 0.5 * chars
        rs = []
        for _, a in grp:
            ac = (a.color or "").upper()
            emph = allow_red and bool(ac) and ac != basec and not _is_dark(ac)
            rs.append(run(p, _runtext(a), sz, bold=a.bold,
                          color=B.RED if emph else B.INK))
        _trim_ends(rs)
        if role == "paragraph":
            no_bullet(p)                       # prose: not every line is a bullet
        else:
            set_bullet(p, lvl)


def _blocks_paras(deck, blocks):
    return len(_para_groups(deck, blocks))


def _blocks_chars(deck, blocks):
    return sum(len(deck.atoms[b.atom_id].text or "")
               for b in blocks if b.atom_id in deck.atoms)


def add_block(tf, atom, block, first, base=B.BODY_PT):
    """Single-atom fallback (kept for callers that pass one block at a time).
    Bold stays bold/black; only a real color highlight would be red, which a
    single atom can't determine, so it renders black."""
    p = tf.paragraphs[0] if first else tf.add_paragraph()
    osz = int(atom.size) if getattr(atom, "size", None) else None
    if block.role in ("quote", "citation"):
        no_bullet(p)
        run(p, clean(atom.text), osz or 18, italic=True, color=B.INK)
    elif block.role == "source":
        no_bullet(p)
        txt = clean(atom.text)
        if txt and txt[0] not in "\u2014\u2013-":
            txt = "\u2014 " + txt
        run(p, txt, osz or 14, color=B.INK)
    elif block.role == "note":
        no_bullet(p)
        run(p, clean(atom.text), osz or 14, italic=True, color=B.INK)
    elif block.role == "subhead":
        no_bullet(p)
        run(p, clean(atom.text), B.SUBHEAD_PT - 4, bold=True, color=B.INK)
    elif block.role == "paragraph":
        no_bullet(p)
        run(p, clean(atom.text), max(B.BODY_MIN_PT, base - 2 * block.level),
            bold=block.emphasis, color=B.INK)
    else:
        run(p, clean(atom.text), max(B.BODY_MIN_PT, base - 2 * block.level),
            bold=block.emphasis, color=B.INK)
        set_bullet(p, block.level)
    return p


# --------------------------------------------------------------------------- #
def build_body(slide, deck, plan, sw, sh):
    imgs = plan.images
    blocks = plan.blocks

    # Sparse slide with no visual (e.g. "Today's objectives"): decorate with a
    # Stevens-Red-outlined box and larger text so it doesn't read as empty.
    sparse = (blocks and not imgs
              and all(b.role == "body" for b in blocks)
              and _blocks_paras(deck, blocks) <= 5
              and _blocks_chars(deck, blocks) <= 240)
    if sparse:
        bw, bh = sw - 3.0, sh - 3.6
        box = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE,
                                     Inches(1.5), Inches(2.3), Inches(bw), Inches(bh))
        box.shadow.inherit = False
        box.fill.solid(); box.fill.fore_color.rgb = C(B.WHITE)
        box.line.color.rgb = C(B.RED); box.line.width = Pt(1)
        tf = box.text_frame; tf.word_wrap = True
        try:
            tf.vertical_anchor = MSO_ANCHOR.MIDDLE
        except Exception:
            pass
        render_paragraphs(tf, deck, blocks, base=B.SUBHEAD_PT - 4, big=True)
        return

    if imgs:
        _, tf = textbox(slide, 0.8, 1.9, sw * 0.52 - 0.8, sh - 2.6)
    else:
        _, tf = textbox(slide, 0.9, 1.9, sw - 1.8, sh - 2.6)
    render_paragraphs(tf, deck, blocks)

    # Images placed at their ORIGINAL (scaled) positions -- so a slide with
    # several pictures (e.g. a pyramid + a photo) keeps its real layout instead
    # of stacking every image on top of each other at one fixed spot.
    ir_slide = deck.slides[plan.index]
    geo = {aid: shp for shp in ir_slide.shapes for aid in shp.atom_ids}
    for im in imgs:
        a = deck.atoms.get(im.atom_id)
        shp = geo.get(im.atom_id)
        if not a or not a.image_blob:
            continue
        if shp and shp.width and shp.height:
            x = shp.left / deck.width * sw
            y = shp.top / deck.height * sh
            w = shp.width / deck.width * sw
            h = shp.height / deck.height * sh
        else:  # no geometry -> fall back to the right rail
            x, y, w, h = sw * 0.56, 2.0, sw * 0.40, sh * 0.4
        # keep inside the slide, under the title
        x = max(0.2, min(x, sw - 0.5)); y = max(1.7, min(y, sh - 0.5))
        w = max(0.3, min(w, sw - x - 0.2)); h = max(0.3, min(h, sh - y - 0.2))
        try:
            slide.shapes.add_picture(io.BytesIO(a.image_blob),
                                     Inches(x), Inches(y), Inches(w), Inches(h))
        except Exception:
            pass


def _atoms_lines(deck, ids):
    lines, cur, cur_p = [], [], None
    for i in ids:
        a = deck.atoms.get(i)
        if not a or a.kind != "text":
            continue
        if cur_p is not None and a.para != cur_p and cur:
            lines.append(" ".join(cur)); cur = []
        cur_p = a.para
        cur.append(clean(a.text))
    if cur:
        lines.append(" ".join(cur))
    return [ln for ln in lines if ln.strip()]


def build_grid(slide, deck, plan, sw, sh):
    """Render an LLM-planned R x C layout: aligned columns of black text, boxed
    cells with a 1pt Stevens Red outline, headers bold, optional red row-arrows.
    Images are kept at their original positions (icons stay where they belong)."""
    g = plan.grid
    ax, ay, aw, ah = 0.8, 1.85, sw - 1.6, sh - 2.5
    rows, cols = max(1, g.rows), max(1, g.cols)
    cw, chh = aw / cols, ah / rows

    ir_slide = deck.slides[plan.index]
    geo = {aid: shp for shp in ir_slide.shapes for aid in shp.atom_ids}

    for iid in g.image_ids:
        a = deck.atoms.get(iid); shp = geo.get(iid)
        if not a or not a.image_blob or not shp:
            continue
        x = shp.left / deck.width * sw
        y = max(ay, shp.top / deck.height * sh)
        w = shp.width / deck.width * sw
        h = shp.height / deck.height * sh
        try:
            slide.shapes.add_picture(io.BytesIO(a.image_blob), Inches(x), Inches(y),
                                     Inches(max(0.3, w)), Inches(max(0.3, h)))
        except Exception:
            pass

    boxed_by_row = {}
    for c in g.cells:
        x = ax + min(c.col, cols - 1) * cw
        y = ay + min(c.row, rows - 1) * chh
        lines = _atoms_lines(deck, c.atom_ids)
        if not lines:
            continue
        if c.box:
            box = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE,
                                         Inches(x + 0.05), Inches(y + 0.05),
                                         Inches(cw - 0.1), Inches(chh - 0.1))
            box.shadow.inherit = False
            box.fill.solid(); box.fill.fore_color.rgb = C(B.WHITE)
            box.line.color.rgb = C(B.RED); box.line.width = Pt(1)
            tf = box.text_frame
            boxed_by_row.setdefault(c.row, []).append(
                (x + cw / 2, y + chh / 2, cw, chh))
        else:
            tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(cw), Inches(chh))
            tf = tb.text_frame
        tf.word_wrap = True
        try:
            tf.vertical_anchor = MSO_ANCHOR.MIDDLE
        except Exception:
            pass
        # A boxed cell is a "card" (e.g. My Strengths / My Aspirations): its
        # header is a Stevens Red section header, left-aligned on top. A plain
        # (unboxed) header is a column head -> black bold, per the references.
        card = bool(c.box)
        for li, ln in enumerate(lines):
            p = tf.paragraphs[0] if li == 0 else tf.add_paragraph()
            no_bullet(p)
            if c.header and li == 0:
                p.alignment = PP_ALIGN.LEFT if card else PP_ALIGN.CENTER
                run(p, ln, 22 if card else 16, bold=True,
                    color=B.RED if card else B.BLACK)
            else:
                p.alignment = PP_ALIGN.LEFT if card else PP_ALIGN.CENTER
                run(p, ln, 16 if card else 13, color=B.BLACK)

    if g.connect == "row-arrows":
        for _r, boxes in boxed_by_row.items():
            boxes.sort(key=lambda b: b[0])
            for i in range(len(boxes) - 1):
                cx1, cy1, w1, _ = boxes[i]
                cx2, cy2, w2, _ = boxes[i + 1]
                x1 = cx1 + w1 / 2 - 0.05
                x2 = cx2 - w2 / 2 + 0.05
                conn = slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT,
                                                  Inches(x1), Inches(cy1),
                                                  Inches(x2), Inches(cy2))
                conn.line.color.rgb = C(B.RED); conn.line.width = Pt(2)


def build_table(slide, deck, plan, sw, sh):
    ts = plan.table
    gt = slide.shapes.add_table(ts.rows, ts.cols, Inches(0.6), Inches(1.8),
                                Inches(sw - 1.2), Inches(sh - 2.4)).table
    for c in ts.cells:
        a = deck.atoms[c.atom_id]
        cell = gt.cell(c.row, c.col)
        cell.text = clean(a.text)
        para = cell.text_frame.paragraphs[0]
        for r in para.runs:
            r.font.name = B.FONT
            r.font.size = Pt(14 if not c.header else 15)
            if c.header:
                r.font.bold = True
                r.font.color.rgb = C(B.WHITE)
            else:
                # table body is charcoal ink; first column bold. (Red is reserved
                # for headers/outlines, never whole table cells.)
                r.font.color.rgb = C(B.INK)
                r.font.bold = c.col == 0
        if c.header:
            cell.fill.solid(); cell.fill.fore_color.rgb = C(B.BLUE)
        else:
            cell.fill.solid(); cell.fill.fore_color.rgb = C(B.WHITE)


def build_columns(slide, deck, plan, sw, sh):
    widths = (sw - 2.0) / 2
    # leftover body blocks (not assigned to any column) get a full-width band
    # BELOW the columns so nothing is ever silently dropped (e.g. a disclaimer).
    leftover = list(plan.blocks or [])
    col_h = (sh - 2.6) if not leftover else (sh - 2.6) * 0.70
    for ci, col in enumerate(plan.columns):
        x = 0.8 + ci * (widths + 0.4)
        _, tf = textbox(slide, x, 1.9, widths, col_h)
        first = True
        for hid in col.header_ids:
            p = tf.paragraphs[0] if first else tf.add_paragraph(); first = False
            no_bullet(p)
            run(p, clean(deck.atoms[hid].text), B.SUBHEAD_PT - 4, bold=True, color=B.BLACK)
        render_paragraphs(tf, deck, col.blocks, first=first)
    if leftover:
        _, tf = textbox(slide, 0.8, 1.9 + col_h + 0.15, sw - 1.6,
                        (sh - 2.6) - col_h - 0.15)
        render_paragraphs(tf, deck, leftover)


def _edge_point(lx, ly, tx, ty, bw, bh, gap=0.12):
    """Point just OUTSIDE the boundary of a box centered at (lx,ly) size (bw,bh),
    toward the target (tx,ty). Lets connectors stop short of the label (leaving a
    small gap) instead of cutting through the text."""
    dx, dy = tx - lx, ty - ly
    if dx == 0 and dy == 0:
        return lx, ly
    sx = (bw / 2) / abs(dx) if dx else float("inf")
    sy = (bh / 2) / abs(dy) if dy else float("inf")
    s = min(sx, sy)
    bxp, byp = lx + dx * s, ly + dy * s
    L = math.hypot(dx, dy)
    return bxp + dx / L * gap, byp + dy / L * gap


def _node_text(deck, n):
    if getattr(n, "vision_derived", False) and getattr(n, "label", ""):
        return clean(n.label)
    return " ".join(clean(deck.atoms[a].text) for a in n.atom_ids)


def _node_emph(deck, n):
    if getattr(n, "vision_derived", False):
        return False
    return any(deck.atoms[a].color and deck.atoms[a].color.upper() not in ("000000",)
               for a in n.atom_ids)


def build_hub(slide, deck, plan, sw, sh):
    import math
    dg = plan.diagram
    cx, cy = sw / 2, sh / 2 + 0.35
    ew, eh = 3.6, 1.7
    LBL_W, LBL_H = 2.8, 0.7

    # classify nodes: center / inside(direction labels) / outer
    center_i, inside, outer = None, [], []
    for i, n in enumerate(dg.nodes):
        t = _node_text(deck, n).lower()
        if "fundamental" in t or "skill" in t:
            center_i = i
        elif "outward" in t or "inward" in t:
            inside.append(i)
        else:
            outer.append(i)

    # 1) propose outer label centers by angle, 2) relax so none overlap each
    # other or the center oval, 3) THEN draw spokes + labels to resolved centers
    centers, angs = [], []
    for k, i in enumerate(outer):
        n = dg.nodes[i]
        if n.x != 0.5 or n.y != 0.5:
            ang = math.atan2(n.y - 0.5, n.x - 0.5)
        else:
            ang = 2 * math.pi * k / max(1, len(outer))
        angs.append(ang)
        centers.append([cx + 4.1 * math.cos(ang), cy + 2.7 * math.sin(ang)])
    bounds = (0.4 + LBL_W / 2, 0.5 + LBL_H / 2, sw - 0.4 - LBL_W / 2, sh - 0.7 - LBL_H / 2)
    autofix.relax_positions(centers, LBL_W, LBL_H, bounds,
                            obstacles=[(cx, cy, ew, eh)], pad=0.18)
    for k, i in enumerate(outer):
        n = dg.nodes[i]
        lx, ly = centers[k]
        ang = math.atan2(ly - cy, lx - cx)
        ex, ey = cx + (ew / 2) * math.cos(ang), cy + (eh / 2) * math.sin(ang)
        bx, by = _edge_point(lx, ly, cx, cy, LBL_W, LBL_H)   # stop at box edge
        conn = slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT,
                                          Inches(ex), Inches(ey), Inches(bx), Inches(by))
        conn.line.color.rgb = C(B.RED); conn.line.width = Pt(1.5)
        _, tf = textbox(slide, lx - LBL_W / 2, ly - LBL_H / 2, LBL_W, LBL_H)
        p = tf.paragraphs[0]; p.alignment = PP_ALIGN.CENTER; no_bullet(p)
        emph = _node_emph(deck, n)
        run(p, _node_text(deck, n), 13, bold=emph, color=B.RED if emph else B.BLACK)

    # center ellipse (blue fill => all text on it is WHITE for readability)
    ell = slide.shapes.add_shape(MSO_SHAPE.OVAL, Inches(cx - ew / 2), Inches(cy - eh / 2),
                                 Inches(ew), Inches(eh))
    ell.fill.solid(); ell.fill.fore_color.rgb = C(B.BLUE); ell.line.fill.background()
    ell.shadow.inherit = False
    etf = ell.text_frame; etf.word_wrap = True; etf.vertical_anchor = MSO_ANCHOR.MIDDLE
    inside_texts = [_node_text(deck, dg.nodes[i]) for i in inside]
    top_lbl = next((t for t in inside_texts if "outward" in t.lower()), None)
    bot_lbl = next((t for t in inside_texts if "inward" in t.lower()), None)
    ctext = (" / ".join(clean(deck.atoms[a].text) for a in dg.nodes[center_i].atom_ids)
             if center_i is not None else "Core")

    first = True
    if top_lbl:
        ep = etf.paragraphs[0]; ep.alignment = PP_ALIGN.CENTER; no_bullet(ep)
        run(ep, top_lbl, 12, color=B.WHITE); first = False
    p2 = etf.paragraphs[0] if first else etf.add_paragraph()
    p2.alignment = PP_ALIGN.CENTER; no_bullet(p2)
    run(p2, ctext, 16, bold=True, color=B.WHITE)
    if bot_lbl:
        p3 = etf.add_paragraph(); p3.alignment = PP_ALIGN.CENTER; no_bullet(p3)
        run(p3, bot_lbl, 12, color=B.WHITE)


def build_vision_diagram(slide, deck, plan, sw, sh):
    """Render a diagram reconstructed from image OCR (Gemini). Nodes carry
    vision-derived labels with relative positions; we place them as native
    objects, draw red spokes/edges, and add a small confirm-me caption so the
    labels are never mistaken for verified source content."""
    dg = plan.diagram
    # drawing area under the title, leaving room for the caption at the bottom
    ax, ay = 0.9, 2.0
    aw, ah = sw - 1.8, sh - 3.1
    LBL_W, LBL_H = 2.4, 0.7

    def place(nx, ny):
        cx = ax + max(0.0, min(1.0, nx)) * aw
        cy = ay + max(0.0, min(1.0, ny)) * ah
        cx = max(ax + LBL_W / 2, min(ax + aw - LBL_W / 2, cx))
        cy = max(ay + LBL_H / 2, min(ay + ah - LBL_H / 2, cy))
        return [cx, cy]

    has_center = bool(dg.center_label)
    ccx, ccy = ax + aw / 2, ay + ah / 2
    ew, eh = 3.4, 1.5

    # build-time collision relaxation so node boxes never overlap each other or
    # the center oval (connectors are drawn AFTER, to the resolved centers)
    centers = [place(n.x, n.y) for n in dg.nodes]
    bounds = (ax + LBL_W / 2, ay + LBL_H / 2, ax + aw - LBL_W / 2, ay + ah - LBL_H / 2)
    obstacles = [(ccx, ccy, ew, eh)] if has_center else []
    autofix.relax_positions(centers, LBL_W, LBL_H, bounds, obstacles=obstacles, pad=0.18)

    # edges first (behind nodes), stopping at each box edge (never through text)
    for e in dg.edges:
        if 0 <= e.frm < len(centers) and 0 <= e.to < len(centers):
            x1, y1 = centers[e.frm]; x2, y2 = centers[e.to]
            p1 = _edge_point(x1, y1, x2, y2, LBL_W, LBL_H)
            p2 = _edge_point(x2, y2, x1, y1, LBL_W, LBL_H)
            conn = slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT,
                                              Inches(p1[0]), Inches(p1[1]),
                                              Inches(p2[0]), Inches(p2[1]))
            conn.line.color.rgb = C(B.RED); conn.line.width = Pt(1.5)
    # if no explicit edges but there is a center, spoke every node to it (hub)
    if not dg.edges and has_center:
        for (x, y) in centers:
            bx, by = _edge_point(x, y, ccx, ccy, LBL_W, LBL_H)
            ang = math.atan2(y - ccy, x - ccx)
            ox, oy = ccx + (ew / 2) * math.cos(ang), ccy + (eh / 2) * math.sin(ang)
            conn = slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT,
                                              Inches(ox), Inches(oy), Inches(bx), Inches(by))
            conn.line.color.rgb = C(B.RED); conn.line.width = Pt(1.5)

    # center node (blue ellipse, white text) if present
    if has_center:
        ell = slide.shapes.add_shape(MSO_SHAPE.OVAL, Inches(ccx - ew / 2),
                                     Inches(ccy - eh / 2), Inches(ew), Inches(eh))
        ell.fill.solid(); ell.fill.fore_color.rgb = C(B.BLUE); ell.line.fill.background()
        ell.shadow.inherit = False
        etf = ell.text_frame; etf.word_wrap = True; etf.vertical_anchor = MSO_ANCHOR.MIDDLE
        ep = etf.paragraphs[0]; ep.alignment = PP_ALIGN.CENTER; no_bullet(ep)
        run(ep, clean(dg.center_label), 16, bold=True, color=B.WHITE)

    # nodes: white box, 1pt red border, black text (red if emphasis)
    for n, (cx, cy) in zip(dg.nodes, centers):
        box = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE,
                                     Inches(cx - LBL_W / 2), Inches(cy - LBL_H / 2),
                                     Inches(LBL_W), Inches(LBL_H))
        box.fill.solid(); box.fill.fore_color.rgb = C(B.WHITE)
        box.line.color.rgb = C(B.RED); box.line.width = Pt(1)
        box.shadow.inherit = False
        tf = box.text_frame; tf.word_wrap = True; tf.vertical_anchor = MSO_ANCHOR.MIDDLE
        p = tf.paragraphs[0]; p.alignment = PP_ALIGN.CENTER; no_bullet(p)
        run(p, _node_text(deck, n), 12, color=B.BLACK)

    # confirm-me caption (labels came from vision OCR)
    _, cap = textbox(slide, 0.9, sh - 0.95, sw - 1.8, 0.5)
    cp = cap.paragraphs[0]; no_bullet(cp)
    run(cp, "Reconstructed from image - confirm labels against the original.",
        11, italic=True, color=B.BLACK)


def _place_crop(slide, orig_pdf, idx, bbox, area):
    """Crop the diagram region from the original render and fit it into `area`
    (l,t,w,h in inches), centered, preserving aspect so it never bleeds out."""
    ax, ay, aw, ah = area
    doc = fitz.open(orig_pdf)
    page = doc.load_page(idx)
    if bbox:
        l, t, w, h = bbox
        clip = fitz.Rect(l / 12700, t / 12700, (l + w) / 12700, (t + h) / 12700)
    else:
        clip = None
    pix = page.get_pixmap(matrix=fitz.Matrix(2.5, 2.5), clip=clip)
    png = os.path.join(os.path.dirname(orig_pdf), f"_crop-{idx+1}.png")
    pix.save(png)
    from PIL import Image
    iw, ih = Image.open(png).size
    aspect = iw / ih if ih else 1.0
    if aw / aspect <= ah:
        w, h = aw, aw / aspect
    else:
        w, h = ah * aspect, ah
    x = ax + (aw - w) / 2
    y = ay + (ah - h) / 2
    slide.shapes.add_picture(png, Inches(x), Inches(y), width=Inches(w), height=Inches(h))


def build_raster(slide, deck, plan, sw, sh, orig_pdf, idx):
    """Preserve a diagram as an exact crop (full-width safe fallback)."""
    try:
        _place_crop(slide, orig_pdf, idx, plan.diagram.bbox,
                    (1.0, 1.9, sw - 2.0, sh - 2.8))
    except Exception as e:
        raise ValueError('Diagram preservation requires a valid source render') from e


def build_diagram(slide, deck, plan, sw, sh, orig_pdf, idx):
    """Fidelity-first diagram slide: keep the ORIGINAL diagram exactly (as a
    crop), and render any real body bullets natively on the opposite side."""
    dg = plan.diagram
    region = getattr(dg, "region", "full")
    has_body = bool(plan.blocks)

    try:
        if has_body and region in ("left", "right"):
            colw = sw * 0.46
            if region == "right":
                _, tf = textbox(slide, 0.8, 1.9, sw * 0.50 - 0.9, sh - 2.6)
                area = (sw * 0.52, 1.9, colw, sh - 2.7)
            else:
                _, tf = textbox(slide, sw * 0.52, 1.9, sw * 0.46 - 0.1, sh - 2.6)
                area = (0.6, 1.9, colw, sh - 2.7)
            render_paragraphs(tf, deck, plan.blocks)
            _place_crop(slide, orig_pdf, idx, dg.bbox, area)
        elif has_body:
            # body first, diagram below (uncommon full-width case)
            _, tf = textbox(slide, 0.9, 1.9, sw - 1.8, (sh - 2.6) * 0.42)
            render_paragraphs(tf, deck, plan.blocks)
            _place_crop(slide, orig_pdf, idx, dg.bbox,
                        (1.0, 1.9 + (sh - 2.6) * 0.46, sw - 2.0, (sh - 2.6) * 0.5))
        else:
            _place_crop(slide, orig_pdf, idx, dg.bbox, (1.0, 1.9, sw - 2.0, sh - 2.8))
    except Exception as e:
        _, tf = textbox(slide, 1, 2, sw - 2, 1)
        run(tf.paragraphs[0], f"[diagram preserved - render fallback unavailable: {e}]", 14)


def _lum(hexs):
    try:
        r, g, b = int(hexs[0:2], 16), int(hexs[2:4], 16), int(hexs[4:6], 16)
        return (0.299 * r + 0.587 * g + 0.114 * b) / 255
    except Exception:
        return 1.0


def _brand_fill(hexs):
    """Map an arbitrary source fill to the Stevens palette -> (fill, text)."""
    if not hexs:
        return None, B.BLACK
    return (B.BLUE, B.WHITE) if _lum(hexs) < 0.55 else (B.LIGHT_BLUE, B.BLACK)


def _shape_text(deck, sh):
    return " ".join(clean(deck.atoms[i].text) for i in sh.atom_ids
                    if i in deck.atoms and deck.atoms[i].kind == "text").strip()


def _shape_lines(deck, sh):
    """Text grouped by original paragraph -> preserves line breaks in boxes."""
    lines, cur, cur_p = [], [], None
    for i in sh.atom_ids:
        a = deck.atoms.get(i)
        if not a or a.kind != "text":
            continue
        if cur_p is not None and a.para != cur_p and cur:
            lines.append(" ".join(cur)); cur = []
        cur_p = a.para
        cur.append(clean(a.text))
    if cur:
        lines.append(" ".join(cur))
    return [ln for ln in lines if ln.strip()]


def _shape_emph(deck, sh):
    return any(deck.atoms[i].bold or (deck.atoms[i].color and
               deck.atoms[i].color.upper() not in ("000000",))
               for i in sh.atom_ids if i in deck.atoms)


def build_diagram_native(slide, deck, plan, sw, sh):
    """Rebuild a diagram IN PLACE as native, Stevens-branded objects.

    Preserves the exact relative geometry of the original shapes (uniform scale,
    so nothing overlaps that didn't before), converts text boxes/auto-shapes to
    Stevens styling, redraws connectors in Stevens Red, and keeps real pictures.
    This is faithful (same structure/meaning) AND branded -- not a screenshot.
    """
    dg = plan.diagram
    ir_slide = deck.slides[plan.index]
    by_id = {s.shape_id: s for s in ir_slide.shapes}
    shapes = [by_id[i] for i in dg.shape_ids if i in by_id]
    if not shapes or not dg.bbox:
        raise ValueError("no native shapes to rebuild")

    # Non-rectangular or rotated shapes (pyramids, funnels, chevrons, arrows,
    # cycles) cannot be faithfully rebuilt as rounded rectangles -- rebuilding
    # them changes the meaning. Bail out so the caller preserves an exact crop.
    if any((s.geom and s.geom not in _RECT_GEOMS) or abs(s.rotation) > 3.0
           for s in shapes if s.is_autoshape):
        raise ValueError("non-rectangular/rotated shapes -> preserve as crop")

    # target drawing area (leave the opposite side for native bullets if split)
    has_body = bool(plan.blocks)
    region = getattr(dg, "region", "full")
    if has_body and region in ("left", "right"):
        colw = sw * 0.46
        if region == "right":
            _, tf = textbox(slide, 0.8, 1.9, sw * 0.50 - 0.9, sh - 2.6)
            ax, ay, aw, ah = sw * 0.52, 1.9, colw, sh - 2.7
        else:
            _, tf = textbox(slide, sw * 0.52, 1.9, sw * 0.46 - 0.1, sh - 2.6)
            ax, ay, aw, ah = 0.6, 1.9, colw, sh - 2.7
        render_paragraphs(tf, deck, plan.blocks)
    else:
        ax, ay, aw, ah = 1.0, 1.9, sw - 2.0, sh - 2.6
        if has_body:
            _, tf = textbox(slide, 0.9, 1.9, sw - 1.8, (sh - 2.6) * 0.34)
            render_paragraphs(tf, deck, plan.blocks)
            ay, ah = 1.9 + (sh - 2.6) * 0.38, (sh - 2.6) * 0.60

    bl, bt, bw, bh = dg.bbox               # source EMU
    bw_in, bh_in = bw / EMU, bh / EMU
    scale = min(aw / bw_in, ah / bh_in) if bw_in and bh_in else 1.0
    off_x = ax + (aw - bw_in * scale) / 2
    off_y = ay + (ah - bh_in * scale) / 2

    def mrect(s):
        x = off_x + (s.left - bl) / EMU * scale
        y = off_y + (s.top - bt) / EMU * scale
        w = max(0.1, s.width / EMU * scale)
        h = max(0.1, s.height / EMU * scale)
        return x, y, w, h

    for s in sorted(shapes, key=lambda z: z.z):
        x, y, w, h = mrect(s)
        if s.kind == "picture":
            blob = next((deck.atoms[i].image_blob for i in s.atom_ids
                         if i in deck.atoms and deck.atoms[i].kind == "image"
                         and deck.atoms[i].image_blob), None)
            if blob:
                try:
                    slide.shapes.add_picture(io.BytesIO(blob), Inches(x), Inches(y),
                                             Inches(w), Inches(h))
                except Exception:
                    pass
            continue
        if s.kind == "connector":
            # only draw short, clean links between adjacent boxes; skip long
            # elbow/diagonal connectors that would render as odd straight lines.
            if w > aw * 0.34 and h > ah * 0.34:
                continue
            horiz = w >= h
            if horiz:
                cy = y + h / 2
                x1, y1, x2, y2 = x, cy, x + w, cy
            else:
                cx = x + w / 2
                x1, y1, x2, y2 = cx, y, cx, y + h
            conn = slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT,
                                              Inches(x1), Inches(y1),
                                              Inches(x2), Inches(y2))
            conn.line.color.rgb = C(B.RED); conn.line.width = Pt(2)
            continue

        text = _shape_text(deck, s)
        if not text or all(ch in "-\u2013\u2014\u2022\u00b7.,:;|_ " for ch in text):
            continue
        # Locked rule: diagram boxes get a 1pt Stevens Red outline; text stays
        # black (white only on a dark fill). Red is reserved for the outline,
        # never the label text.
        is_box = s.is_autoshape or bool(s.fill_rgb)
        txt_color = B.BLACK
        if is_box:
            box = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE,
                                         Inches(x), Inches(y), Inches(w), Inches(h))
            box.shadow.inherit = False
            box.fill.solid(); box.fill.fore_color.rgb = C(B.WHITE)
            box.line.color.rgb = C(B.RED); box.line.width = Pt(1)
            tf2 = box.text_frame
        else:
            tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
            tf2 = tb.text_frame
        tf2.word_wrap = True
        try:
            tf2.vertical_anchor = MSO_ANCHOR.MIDDLE
        except Exception:
            pass
        sizes = [deck.atoms[i].size for i in s.atom_ids
                 if i in deck.atoms and deck.atoms[i].size]
        base = (sum(sizes) / len(sizes)) if sizes else 14
        fsz = max(8, min(22, base * scale))
        emph = _shape_emph(deck, s)
        lines = _shape_lines(deck, s) or [text]
        for li, ln in enumerate(lines):
            p = tf2.paragraphs[0] if li == 0 else tf2.add_paragraph()
            p.alignment = PP_ALIGN.CENTER; no_bullet(p)
            run(p, ln, fsz, bold=emph, color=B.BLACK)


def build_demo(deck, plans, indices, out_path, orig_pdf):
    prs = Presentation(TEMPLATE)
    sw = prs.slide_width / EMU
    sh = prs.slide_height / EMU
    sw_emu, sh_emu = int(prs.slide_width), int(prs.slide_height)
    clear_slides(prs)
    pmap = {p.index: p for p in plans}
    fixlog = []
    for idx in indices:
        plan = pmap[idx]
        title_text = " ".join(clean(deck.atoms[i].text) for i in plan.title_ids) or "(untitled)"
        slide = title_only(prs, title_text)
        if plan.table:
            build_table(slide, deck, plan, sw, sh)
        elif plan.diagram and plan.diagram.kind == "hub" and not plan.diagram.raster_fallback \
                and not plan.diagram.vision_derived:
            build_hub(slide, deck, plan, sw, sh)
        elif plan.diagram and plan.diagram.vision_derived and not plan.diagram.raster_fallback:
            build_vision_diagram(slide, deck, plan, sw, sh)
        elif plan.diagram and plan.diagram.raster_fallback:
            build_raster(slide, deck, plan, sw, sh, orig_pdf, idx)
        elif plan.columns:
            build_columns(slide, deck, plan, sw, sh)
        else:
            build_body(slide, deck, plan, sw, sh)

        # deterministic auto-fix loop: correct + re-verify each built slide
        applied, remaining = autofix.autofix_slide(slide, sw_emu, sh_emu)
        fixlog.append({"index": idx, "applied": applied, "remaining": remaining})
    prs.save(out_path)
    return {"out_path": out_path, "fixlog": fixlog}
