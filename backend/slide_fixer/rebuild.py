"""Rebuild engine (Option B): reconstruct each source slide natively onto the
Stevens template's own layouts/placeholders, then apply the Stevens rulebook.

This yields output very close to native Stevens quality (unlike re-skin, which
keeps the source geometry). Text slides rebuild with high fidelity; image slides
are rebuilt with title + body in template placeholders and images fitted into
the remaining region (flagged for human review).
"""
import io
import os

from pptx import Presentation
from pptx.util import Pt, Emu
from pptx.dml.color import RGBColor
from pptx.oxml.ns import qn
from pptx.enum.text import MSO_AUTO_SIZE
from pptx.enum.shapes import PP_PLACEHOLDER as PPP

from .rules import DEFAULT_RULES
from .engine import _set_run, set_square_bullet, set_no_bullet
from .content import extract, classify_kind

TEMPLATE_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "assets", "stevens_template.pptx"))

# layout names in the Stevens template
L_TITLE = "Title Slide"
L_SECTION = "Section Header"
L_CONTENT = "Title and Content"
L_SUBHEAD = "Title, Subhead and Content"
L_TITLE_ONLY = "Title Only"
L_THANKYOU = "Thank You Slide"

_SKIP_PH = {PPP.SLIDE_NUMBER, PPP.DATE, PPP.FOOTER, PPP.HEADER}


# --------------------------------------------------------------------------- #
# template helpers
# --------------------------------------------------------------------------- #
def get_layout(prs, name):
    for lay in prs.slide_layouts:
        if lay.name == name:
            return lay
    return prs.slide_layouts[0]


def clear_slides(prs):
    """Remove all slides AND their parts so new slides don't collide names."""
    part = prs.part
    lst = prs.slides._sldIdLst
    for sldId in list(lst):
        rId = sldId.get(qn("r:id"))
        try:
            part.drop_rel(rId)
        except Exception:
            pass
        lst.remove(sldId)


def body_placeholder(slide):
    """Return the main content/body placeholder (not title/number/date)."""
    title = slide.shapes.title
    cands = []
    for ph in slide.placeholders:
        if title is not None and ph._element is title._element:
            continue
        t = ph.placeholder_format.type
        if t in _SKIP_PH:
            continue
        cands.append(ph)
    # prefer OBJECT/BODY content
    for ph in cands:
        if ph.placeholder_format.type in (PPP.OBJECT, PPP.BODY):
            return ph
    return cands[0] if cands else None


# --------------------------------------------------------------------------- #
# layout selection + dense split
# --------------------------------------------------------------------------- #
def pick_layout(kind, model):
    if kind == "title":
        return L_TITLE
    if kind == "thankyou":
        return L_TITLE            # thank-you rendered as a title-style slide
    if kind == "section":
        return L_SECTION
    if kind == "picture":
        return L_TITLE_ONLY
    return L_CONTENT


def split_chunks(model, cfg):
    """Split body into chunks when dense. Returns list of body-lists."""
    body = model["body"]
    words = sum(len(t.split()) for _, t in body)
    # Be conservative: only split clearly overloaded slides.
    dense = len(body) > cfg.split_bullet_cap * 2 or words > cfg.split_word_cap * 2
    if not dense or len(body) < 4:
        return [body]
    mid = (len(body) + 1) // 2
    return [body[:mid], body[mid:]]


# --------------------------------------------------------------------------- #
# fillers
# --------------------------------------------------------------------------- #
def _style_title(slide, text, size_pt, cfg):
    ph = slide.shapes.title
    if ph is None or not text:
        return
    ph.text = text
    for p in ph.text_frame.paragraphs:
        set_no_bullet(p)
        for r in p.runs:
            _set_run(r, cfg, size_pt, cfg.text_color)


def _fill_body(ph, items, cfg):
    if ph is None or not items:
        return
    tf = ph.text_frame
    tf.clear()
    for i, (lvl, text) in enumerate(items):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.level = lvl
        run = p.add_run()
        run.text = text
        _set_run(run, cfg, cfg.body_pt, cfg.text_color)
        if cfg.square_bullets:
            set_square_bullet(p, cfg)
    if cfg.shrink_to_fit:
        try:
            tf.word_wrap = True
            tf.auto_size = MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE
        except Exception:
            pass


def _fit_box(iw, ih, bw, bh):
    """Fit (iw,ih) inside (bw,bh) preserving aspect. Returns (w,h)."""
    if iw <= 0 or ih <= 0:
        return bw, bh
    scale = min(bw / iw, bh / ih)
    return int(iw * scale), int(ih * scale)


def _place_images(slide, images, region, cfg):
    """Stack images vertically inside region=(left,top,width,height) EMU."""
    if not images:
        return
    left, top, width, height = region
    n = len(images)
    gap = Emu(91440)  # 0.1"
    cell_h = (height - gap * (n - 1)) // n if n else height
    y = top
    for img in images:
        w, h = _fit_box(img["width"], img["height"], width, cell_h)
        x = left + (width - w) // 2
        yy = y + (cell_h - h) // 2
        try:
            slide.shapes.add_picture(io.BytesIO(img["blob"]), x, yy, width=w, height=h)
        except Exception:
            pass
        y += cell_h + gap


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def rebuild(src_path, out_path, cfg=DEFAULT_RULES, template_path=TEMPLATE_PATH):
    src = Presentation(src_path)
    tpl = Presentation(template_path)
    sw, sh = int(tpl.slide_width), int(tpl.slide_height)
    clear_slides(tpl)

    report = {"source": src_path, "output": out_path, "template": template_path, "slides": []}
    total = len(src.slides)

    for idx, slide in enumerate(src.slides):
        model = extract(slide, idx)
        kind = classify_kind(model, idx, total)
        chunks = split_chunks(model, cfg) if kind == "content" else [model["body"]]

        for ci, body_chunk in enumerate(chunks):
            layout_name = pick_layout(kind, model)
            new = tpl.slides.add_slide(get_layout(tpl, layout_name))

            title = model["title"] or ""
            if len(chunks) > 1 and title:
                title = f"{title} - Part - {ci + 1}"

            title_size = cfg.title_section_pt if kind in ("title", "section", "thankyou") \
                else cfg.title_content_pt
            _style_title(new, title, title_size, cfg)

            bph = body_placeholder(new)
            imgs = model["images"] if ci == 0 else []

            if kind == "content" and imgs:
                # body left ~54%, images right ~40%
                if bph is not None:
                    bph.left = Emu(int(sw * 0.05))
                    bph.width = Emu(int(sw * 0.52))
                _fill_body(bph, body_chunk, cfg)
                region = (int(sw * 0.60), int(sh * 0.22), int(sw * 0.36), int(sh * 0.68))
                _place_images(new, imgs, region, cfg)
            elif kind == "content":
                _fill_body(bph, body_chunk, cfg)
            elif kind == "picture":
                region = (int(sw * 0.08), int(sh * 0.24), int(sw * 0.84), int(sh * 0.66))
                _place_images(new, imgs, region, cfg)
            elif kind == "section":
                _fill_body(bph, body_chunk, cfg)
            # title / thankyou: title only

            report["slides"].append({
                "src_index": idx + 1, "kind": kind, "layout": layout_name,
                "part": (ci + 1) if len(chunks) > 1 else None,
                "bullets": len(body_chunk), "images": len(imgs),
                "needs_review": bool(imgs),
            })

    tpl.save(out_path)
    return report
