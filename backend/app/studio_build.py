"""Studio builder: reconstruct a source deck onto the Stevens template applying
the locked V1 rules, and analyze a deck into a per-slide plan with rationale.

Locked rules enforced here:
- Arial; title 40 / subtitle 32 / subhead 28 / body 16-20 (11 floor when dense).
- Bullets L0 square, L1 arrow (Stevens Blue markers), L2 dash.
- Standard text color is ONLY black/white/red; red used for emphasis + box borders.
- First slide = title layout; last slide = Thank You layout.
- Callout boxes get a 1pt Stevens Red border; white fill, black text.
- Dense slides split into "... - Part - 1 / - 2"; structure preserved.
- No overflow: word-wrap + shrink-to-fit backstop on every text box.
"""
from __future__ import annotations

from slide_engine.package import save_deck

import io
import os
import sys

from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.oxml.ns import qn
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE

# make the bundled slide_fixer importable
_HERE = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_HERE)
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from slide_fixer.content import extract, classify_kind          # noqa: E402
from slide_fixer.engine import _bare, _clear_bullets, _insert_bullet_group  # noqa: E402

from . import brand
from .qa import geometry

TEMPLATE_PATH = os.path.join(_BACKEND, "assets", "ppt_template.pptx")


def C(hex6):
    return RGBColor.from_string(hex6)


# --------------------------------------------------------------------------- #
# low-level slide helpers
# --------------------------------------------------------------------------- #
def clear_slides(prs):
    lst = prs.slides._sldIdLst
    for sldId in list(lst):
        try:
            prs.part.drop_rel(sldId.get(qn("r:id")))
        except Exception:
            pass
        lst.remove(sldId)


def get_layout(prs, name):
    for lay in prs.slide_layouts:
        if lay.name == name:
            return lay
    return prs.slide_layouts[0]


def run(p, text, size, bold=False, color=brand.BLACK, italic=False):
    r = p.add_run()
    r.text = text
    r.font.name = brand.FONT
    r.font.size = Pt(size)
    r.font.bold = bold
    r.font.italic = italic
    r.font.color.rgb = C(color)
    return r


def set_bullet(p, level):
    level = max(0, min(level, 2))
    pPr = p._p.get_or_add_pPr()
    _clear_bullets(pPr)
    pPr.set("marL", str(274638 * (level + 1)))
    pPr.set("indent", "-274638")
    char, font, color = brand.BULLETS[level]
    buClr = _bare("a:buClr"); srgb = _bare("a:srgbClr"); srgb.set("val", color); buClr.append(srgb)
    buFont = _bare("a:buFont"); buFont.set("typeface", font)
    buChar = _bare("a:buChar"); buChar.set("char", char)
    _insert_bullet_group(pPr, [buClr, buFont, buChar])


def no_bullet(p):
    pPr = p._p.get_or_add_pPr()
    _clear_bullets(pPr)
    _insert_bullet_group(pPr, [_bare("a:buNone")])


def space_before(p, pts):
    pPr = p._p.get_or_add_pPr()
    for e in pPr.findall(qn("a:spcBef")):
        pPr.remove(e)
    spc = _bare("a:spcBef"); v = _bare("a:spcPts"); v.set("val", str(int(pts * 100)))
    spc.append(v); pPr.insert(0, spc)


def textbox(slide, l, t, w, h, anchor=None):
    tb = slide.shapes.add_textbox(Inches(l), Inches(t), Inches(w), Inches(h))
    tf = tb.text_frame
    tf.word_wrap = True
    tf.margin_left = Inches(0.1); tf.margin_right = Inches(0.1)
    tf.margin_top = Inches(0.05); tf.margin_bottom = Inches(0.05)
    if anchor is not None:
        tf.vertical_anchor = anchor
    return tb, tf


def red_box(slide, l, t, w, h):
    sp = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(l), Inches(t), Inches(w), Inches(h))
    sp.shadow.inherit = False
    sp.fill.solid(); sp.fill.fore_color.rgb = C(brand.WHITE)
    sp.line.color.rgb = C(brand.BOX_BORDER); sp.line.width = Pt(brand.BOX_BORDER_PT)
    tf = sp.text_frame; tf.word_wrap = True
    tf.margin_left = Inches(0.3); tf.margin_right = Inches(0.3)
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    return sp, tf


def _fit(iw, ih, bw, bh):
    if iw <= 0 or ih <= 0:
        return bw, bh
    s = min(bw / iw, bh / ih)
    return int(iw * s), int(ih * s)


def place_images(slide, images, region):
    if not images:
        return
    left, top, width, height = region
    n = len(images)
    gap = brand.in_to_emu(0.15)
    cell_h = (height - gap * (n - 1)) // n if n else height
    y = top
    for img in images:
        w, h = _fit(img["width"], img["height"], width, cell_h)
        x = left + (width - w) // 2
        yy = y + (cell_h - h) // 2
        try:
            slide.shapes.add_picture(io.BytesIO(img["blob"]), x, yy, width=w, height=h)
        except Exception:
            pass
        y += cell_h + gap


# --------------------------------------------------------------------------- #
# body construction
# --------------------------------------------------------------------------- #
def _has_children(body, i):
    return i + 1 < len(body) and body[i + 1][0] > body[i][0]


def _body_font(n_items, dense):
    if dense or n_items > 7:
        return max(brand.BODY_MIN_PT + 3, brand.BODY_PT - 4)  # ~16
    if n_items > 5:
        return brand.BODY_PT - 2                              # 18
    return brand.BODY_PT                                       # 20


def fill_bullets(tf, body, dense=False):
    base = _body_font(len(body), dense)
    for i, (lvl, text) in enumerate(body):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        subhead = lvl == 0 and _has_children(body, i)
        size = brand.SUBHEAD_PT - 6 if subhead else max(brand.BODY_MIN_PT, base - 2 * lvl)
        run(p, text, size, bold=subhead, color=brand.BLACK)
        set_bullet(p, lvl)
        if lvl == 0 and i != 0:
            space_before(p, 10)


def split_body(body):
    """Split into two chunks, preferring a top-level boundary near the middle."""
    n = len(body)
    if n < 2:
        return [body]
    mid = (n + 1) // 2
    # find nearest level-0 boundary to mid
    best = mid
    for d in range(0, n):
        for cand in (mid - d, mid + d):
            if 1 <= cand < n and body[cand][0] == 0:
                best = cand
                break
        else:
            continue
        break
    return [body[:best], body[best:]]


# --------------------------------------------------------------------------- #
# slide builders
# --------------------------------------------------------------------------- #
def build_title(prs, model):
    slide = prs.slides.add_slide(get_layout(prs, brand.L_TITLE))
    title = model["title"] or (model["body"][0][1] if model["body"] else "Presentation")
    rest = model["body"] if not model["title"] else model["body"]
    # title placeholder (inherit template color; brand-correct by design)
    if slide.shapes.title is not None:
        tp = slide.shapes.title.text_frame
        tp.clear()
        p = tp.paragraphs[0]
        r = p.add_run(); r.text = title
        r.font.name = brand.FONT; r.font.bold = True; r.font.size = Pt(brand.TITLE_SECTION_PT)
    subtitle = rest[0][1] if rest else ""
    for ph in slide.placeholders:
        idx = ph.placeholder_format.idx
        if idx == 1 and subtitle:
            ph.text_frame.clear()
            r = ph.text_frame.paragraphs[0].add_run(); r.text = subtitle
            r.font.name = brand.FONT; r.font.size = Pt(brand.SUBTITLE_PT)
        elif idx == 11 and len(rest) > 1:
            ph.text_frame.clear()
            r = ph.text_frame.paragraphs[0].add_run(); r.text = rest[1][1]
            r.font.name = brand.FONT; r.font.size = Pt(18)
    return slide


def build_thankyou(prs, model):
    slide = prs.slides.add_slide(get_layout(prs, brand.L_THANKYOU))
    if slide.shapes.title is not None:
        slide.shapes.title.text_frame.clear()
        r = slide.shapes.title.text_frame.paragraphs[0].add_run()
        r.text = model["title"] or "Thank you!"
        r.font.name = brand.FONT; r.font.bold = True; r.font.size = Pt(brand.TITLE_SECTION_PT)
    return slide


def build_section(prs, model):
    slide = prs.slides.add_slide(get_layout(prs, brand.L_SECTION))
    if slide.shapes.title is not None and model["title"]:
        slide.shapes.title.text = model["title"]
        for p in slide.shapes.title.text_frame.paragraphs:
            for r in p.runs:
                r.font.name = brand.FONT; r.font.bold = True
                r.font.size = Pt(brand.TITLE_SECTION_PT); r.font.color.rgb = C(brand.BLACK)
    return slide


def _set_title_only(slide, title):
    if slide.shapes.title is not None:
        slide.shapes.title.text = title or ""
        for p in slide.shapes.title.text_frame.paragraphs:
            no_bullet(p)
            for r in p.runs:
                r.font.name = brand.FONT; r.font.bold = True
                r.font.size = Pt(brand.TITLE_PT); r.font.color.rgb = C(brand.BLACK)


def build_content(prs, model, body, dense, sw_in, sh_in, part=None):
    slide = prs.slides.add_slide(get_layout(prs, brand.L_TITLE_ONLY))
    title = model["title"] or ""
    if part:
        title = f"{title} - Part - {part}" if title else f"Part - {part}"
    _set_title_only(slide, title)

    images = model["images"]
    sparse = (len(body) <= 2 and sum(len(t.split()) for _, t in body) <= 24 and not images)

    if sparse and body:
        # decorate: large centered text in a red-bordered box
        _, tf = red_box(slide, 1.5, 2.7, sw_in - 3.0, 2.2)
        for i, (_, text) in enumerate(body):
            p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            p.alignment = PP_ALIGN.CENTER
            no_bullet(p)
            run(p, text, 26 if len(body) == 1 else 22, color=brand.BLACK)
        geometry.enforce_autofit(slide)
        return slide

    if images:
        _, tf = textbox(slide, 0.8, 1.9, sw_in * 0.52 - 0.8, sh_in - 2.6)
        fill_bullets(tf, body, dense)
        region = (brand.in_to_emu(sw_in * 0.56), brand.in_to_emu(2.0),
                  brand.in_to_emu(sw_in * 0.40), brand.in_to_emu(sh_in - 2.8))
        place_images(slide, images, region)
    else:
        _, tf = textbox(slide, 0.9, 1.9, sw_in - 1.8, sh_in - 2.6)
        fill_bullets(tf, body, dense)

    geometry.enforce_autofit(slide)
    return slide


# --------------------------------------------------------------------------- #
# analyze + build entry points
# --------------------------------------------------------------------------- #
def _dense(model):
    n = len(model["body"])
    words = sum(len(t.split()) for _, t in model["body"])
    return n > brand.SPLIT_BULLET_CAP or words > brand.SPLIT_WORD_CAP


def _plan_for(model, kind):
    layout = {
        "title": brand.L_TITLE, "thankyou": brand.L_THANKYOU,
        "section": brand.L_SECTION,
    }.get(kind, brand.L_TITLE_ONLY)

    issues = []
    n = len(model["body"])
    words = sum(len(t.split()) for _, t in model["body"])
    if kind == "content":
        if _dense(model):
            issues.append("dense")
        if n <= 2 and words <= 24 and not model["images"]:
            issues.append("sparse")
    if model["images"]:
        issues.append("diagram")
    if model["n_tables"]:
        issues.append("table")

    # rationale (surfaces the logical + creative thinking)
    if kind == "title":
        rationale = "Opening slide -> Stevens title layout; deck title and subtitle placed in the branded cover."
    elif kind == "thankyou":
        rationale = "Closing slide -> Stevens Thank You layout to end on-brand."
    elif kind == "section":
        rationale = "Title-only content -> Section Header layout to act as a divider."
    elif "sparse" in issues:
        rationale = "Very little text -> enlarged and framed in a Stevens Red callout box so the slide does not look empty."
    elif "diagram" in issues:
        rationale = "Has a diagram/visual -> Title Only + two columns: bullets left, the visual placed right (kept intact so it never breaks)."
    elif "dense" in issues:
        rationale = f"{n} points is dense -> split into Part 1 / Part 2 so no slide is overloaded and text never overflows."
    else:
        rationale = "Standard content -> Title Only with a clean square/arrow bullet hierarchy, black text, Stevens template."
    return layout, issues, rationale


def analyze(src_path):
    prs = Presentation(src_path)
    total = len(prs.slides)
    slides = []
    for idx, slide in enumerate(prs.slides):
        model = extract(slide, idx)
        kind = classify_kind(model, idx, total)
        layout, issues, rationale = _plan_for(model, kind)
        slides.append({
            "index": idx,
            "title": model["title"] or "(untitled)",
            "kind": kind,
            "layout": layout,
            "rationale": rationale,
            "issues": issues,
            "n_body": len(model["body"]),
            "n_images": len(model["images"]),
            "needs_review": bool(model["images"] or model["n_tables"]),
        })
    return {"slide_count": total, "slides": slides}


def build(src_path, out_path, revisions=None, template_path=TEMPLATE_PATH):
    """revisions: {src_index(int): {"tags":[...], "instruction":str}}."""
    revisions = revisions or {}
    src = Presentation(src_path)
    tpl = Presentation(template_path)
    sw_in = tpl.slide_width / brand.EMU_PER_INCH
    sh_in = tpl.slide_height / brand.EMU_PER_INCH
    sw, sh = int(tpl.slide_width), int(tpl.slide_height)
    clear_slides(tpl)

    total = len(src.slides)
    report = {"source": src_path, "output": out_path, "slides": []}

    for idx, slide in enumerate(src.slides):
        model = extract(slide, idx)
        kind = classify_kind(model, idx, total)
        rev = revisions.get(idx) or revisions.get(str(idx)) or {}
        tags = set(rev.get("tags") or [])
        instruction = (rev.get("instruction") or "").strip()

        built = []
        if kind == "title":
            built = [build_title(tpl, model)]
        elif kind == "thankyou":
            built = [build_thankyou(tpl, model)]
        elif kind == "section":
            built = [build_section(tpl, model)]
        else:
            dense = _dense(model) or "dense" in tags
            force_split = "split" in tags or dense
            chunks = split_body(model["body"]) if (force_split and len(model["body"]) >= 4) else [model["body"]]
            for ci, chunk in enumerate(chunks):
                part = (ci + 1) if len(chunks) > 1 else None
                m2 = dict(model)
                m2["images"] = model["images"] if ci == 0 else []
                built.append(build_content(tpl, m2, chunk, dense, sw_in, sh_in, part))

        # attach reviewer instruction to speaker notes (human-visible, non-destructive)
        if instruction:
            for b in built:
                try:
                    b.notes_slide.notes_text_frame.text = f"Reviewer request: {instruction}"
                except Exception:
                    pass

        # geometry QA per built slide
        for b in built:
            issues = geometry.check_slide(b, sw, sh)
            report["slides"].append({
                "src_index": idx,
                "kind": kind,
                "geometry_issues": issues,
            })

    save_deck(tpl,out_path)
    return report
