"""Stage 2/3 - Understand + Plan.

Produces a SlidePlan that references content ONLY by atom id. Two implementations
share the exact same schema and validation:
  - plan_deterministic(): grounded rules over IR geometry/formatting (runs now).
  - plan_with_gemini():   AI judgment, constrained to return ids only (drop-in).

Because the plan can only reference ids, and verify.py proves every source atom
is placed exactly once with no invented ids, the AI can never fabricate or drop
content -- it can only (mis)arrange, which is caught and/or flagged.
"""
from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, field
from typing import List, Optional

from .ir import Deck, Slide, Shape, Atom


# Auto-shape presets that are effectively rectangles (safe to treat as plain
# boxes). Any other preset (trapezoid, chevron, arrow, oval, ...) is a real
# visual and marks the shape as diagram material.
_RECT_GEOMS = {
    "rect", "roundRect", "round1Rect", "round2SameRect", "round2DiagRect",
    "snip1Rect", "snip2SameRect", "snip2DiagRect", "snipRoundRect",
    "plaque", "flowChartProcess", "flowChartAlternateProcess",
    "flowChartPredefinedProcess", "actionButtonBlank",
}


# --------------------------------------------------------------------------- #
# plan schema
# --------------------------------------------------------------------------- #
@dataclass
class Block:
    atom_id: int
    role: str = "body"        # body | subhead | quote | source | note | paragraph
    level: int = 0
    emphasis: bool = False


@dataclass
class ImgPlace:
    atom_id: int
    region: str = "right"     # left | right | full


@dataclass
class Node:
    atom_ids: List[int] = field(default_factory=list)
    x: float = 0.5             # 0..1 center
    y: float = 0.5
    label: str = ""            # only for vision-derived nodes (no source atom)
    vision_derived: bool = False


@dataclass
class Edge:
    frm: int                   # node index
    to: int


@dataclass
class DiagramSpec:
    kind: str                  # preserve | hub | matrix | cycle | vision | generic
    nodes: List[Node] = field(default_factory=list)
    edges: List[Edge] = field(default_factory=list)
    raster_fallback: bool = False
    confidence: float = 0.0
    bbox: Optional[tuple] = None       # (l,t,w,h) EMU for raster crop
    source_image_ids: List[int] = field(default_factory=list)  # picture atoms consumed
    covered_ids: List[int] = field(default_factory=list)       # text atoms shown inside the crop
    shape_ids: List[str] = field(default_factory=list)         # region shapes (for native rebuild)
    region: str = "full"       # left | right | full  (where the visual lives)
    vision_derived: bool = False       # labels came from Gemini OCR, not source
    center_label: str = ""             # vision-read central/anchor text
    escalated: bool = False            # stronger (Pro) model was used for this read
    model: str = ""                    # which Gemini model produced the read
    prefer_crop: bool = False          # spatial-label diagram -> keep exact crop


@dataclass
class Cell:
    atom_id: int
    row: int
    col: int
    header: bool = False


@dataclass
class TableSpec:
    rows: int
    cols: int
    cells: List[Cell] = field(default_factory=list)


@dataclass
class Column:
    header_ids: List[int] = field(default_factory=list)
    blocks: List[Block] = field(default_factory=list)


@dataclass
class GridCell:
    atom_ids: List[int] = field(default_factory=list)
    row: int = 0
    col: int = 0
    box: bool = False          # draw a red-outline box around this cell
    header: bool = False       # bold header styling (phase/stage headers)


@dataclass
class GridSpec:
    """Generic R x C layout the LLM planner uses for funnels, timelines,
    matrices, phase/stage/act structures, etc. Rendered as aligned columns of
    black text; boxed cells get a 1pt Stevens Red outline."""
    rows: int = 1
    cols: int = 1
    cells: List[GridCell] = field(default_factory=list)
    connect: str = "none"      # none | row-arrows (red connectors across a row)
    image_ids: List[int] = field(default_factory=list)  # pictures kept by geometry


@dataclass
class SlidePlan:
    index: int
    kind: str = "content"
    layout: str = "Title Only"
    title_ids: List[int] = field(default_factory=list)
    blocks: List[Block] = field(default_factory=list)
    images: List[ImgPlace] = field(default_factory=list)
    diagram: Optional[DiagramSpec] = None
    table: Optional[TableSpec] = None
    columns: Optional[List[Column]] = None
    grid: Optional[GridSpec] = None
    subtitle_ids: List[int] = field(default_factory=list)
    flagged: List[int] = field(default_factory=list)
    split_hint: bool = False
    confidence: float = 1.0
    notes: str = ""


def referenced_ids(plan: SlidePlan) -> List[int]:
    """Every atom id the plan places (multiset -> list, so duplicates show up)."""
    ids: List[int] = []
    ids += list(plan.title_ids)
    ids += list(plan.subtitle_ids)
    ids += [b.atom_id for b in plan.blocks]
    ids += [im.atom_id for im in plan.images]
    if plan.grid:
        for c in plan.grid.cells:
            ids += list(c.atom_ids)
        ids += list(plan.grid.image_ids)
    if plan.diagram:
        for n in plan.diagram.nodes:
            ids += list(n.atom_ids)
        ids += list(plan.diagram.source_image_ids)
        ids += list(plan.diagram.covered_ids)
    if plan.table:
        ids += [c.atom_id for c in plan.table.cells]
    if plan.columns:
        for col in plan.columns:
            ids += list(col.header_ids)
            ids += [b.atom_id for b in col.blocks]
    return ids


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _by_shape(slide: Slide):
    return {sh.shape_id: sh for sh in slide.shapes}


def _shape_atoms(deck: Deck, sh: Shape):
    return [deck.atoms[i] for i in sh.atom_ids if i in deck.atoms]


def _avg_size(atoms):
    sizes = [a.size for a in atoms if a.size]
    return sum(sizes) / len(sizes) if sizes else 0.0


def _is_black(color):
    return color is None or color.upper() in ("000000",)


import re as _re

_DATE_RE = _re.compile(r"^\s*\d{1,2}[/\-.]\d{1,2}[/\-.]\d{2,4}\s*$")
_CITE_RE = _re.compile(r"\(\s*(19|20)\d{2}\s*\)|,\s*(19|20)\d{2}\b|et al\.?",
                       _re.IGNORECASE)
_QUOTE_CHARS = "\u201c\u201d\u2018\u2019\"'"


import string as _string


def _is_junk(text):
    """Slide numbers / bare dates / lone punctuation that add noise, not content."""
    t = (text or "").strip()
    if not t:
        return True
    if all(ch in _string.punctuation or ch.isspace() for ch in t):
        return True                      # stray "."/"-"/bullet-only fragments
    if _DATE_RE.match(t):
        return True
    if t.isdigit() and len(t) <= 3:      # stray page number
        return True
    if _PLACEHOLDER_TITLE.match(t):      # 'Title', 'Title2', 'Untitled', ...
        return True
    return False


_YEAR_RE = _re.compile(r"\b(19|20)\d{2}\b")
_PUBWORDS = _re.compile(
    r"\b(review|journal|press|proceedings|conference|magazine|report|"
    r"quarterly|edition|vol\.?|pp\.?|no\.?)\b", _re.I)
_NOTE_RE = _re.compile(r"^\s*(note|nb|n\.b\.)\b\s*[:.\-\u2013)]?\s*", _re.I)


def _is_note(t):
    """An annotation ('Note: ...', 'NB ...') -- secondary to the list it sits by,
    must NOT be styled as another bullet."""
    return bool(_NOTE_RE.match(t or ""))


def _is_source(t, words):
    """An attribution / reference line (author + journal + year). Rendered small,
    below its quote, never as a bullet."""
    if _CITE_RE.search(t):
        return True
    # a year plus attribution signals (comma / ampersand / publication word),
    # short, and NOT a full prose sentence (which would end in . ! ?)
    if (_YEAR_RE.search(t) and words <= 18
            and not t.rstrip().endswith((".", "!", "?"))
            and ("," in t or "&" in t or _PUBWORDS.search(t))):
        return True
    return False


def _is_quote(atom, t, words):
    """A quotation: wrapped in quote marks, or italic prose."""
    if t[:1] in _QUOTE_CHARS and words >= 4:
        return True
    if atom.italic and words >= 6:
        return True
    return False


def _text_role(atom):
    """Infer the semantic role of a text atom from its content + formatting so it
    is placed by MEANING, not flattened into an identical bullet. Order matters:
    note -> source(attribution) -> quote -> subhead -> body."""
    t = (atom.text or "").strip()
    words = len(t.split())
    if _is_note(t):
        return "note"
    if _is_source(t, words):
        return "source"
    if _is_quote(atom, t, words):
        return "quote"
    if atom.underline and words <= 6:
        return "subhead"
    return "body"


def _para_role(atoms):
    """Role for a whole SOURCE paragraph (list of run atoms) judged on the joined
    text + aggregate formatting -- so a quote/attribution split across several
    runs is still classified correctly."""
    t = " ".join((a.text or "") for a in atoms)
    t = _re.sub(r"\s+", " ", t).strip()
    words = len(t.split())
    italic = any(getattr(a, "italic", False) for a in atoms)
    underline = any(getattr(a, "underline", False) for a in atoms)
    if _is_note(t):
        return "note"
    if _is_source(t, words):
        return "source"
    if (t[:1] in _QUOTE_CHARS and words >= 4) or (italic and words >= 6):
        return "quote"
    if underline and words <= 6:
        return "subhead"
    return "body"


def _is_citation(atom):
    """Back-compat: any non-body text role (quote/source/note)."""
    return _text_role(atom) in ("quote", "source", "note")


def _center(sh: Shape, W, H):
    return ((sh.left + sh.width / 2) / W if W else 0.5,
            (sh.top + sh.height / 2) / H if H else 0.5)


def _find_title(deck: Deck, slide: Slide):
    shapes = slide.shapes
    # 1) real title placeholder
    for sh in shapes:
        if sh.is_placeholder and sh.ph_type and "TITLE" in sh.ph_type.upper():
            ats = _shape_atoms(deck, sh)
            txt = " ".join((a.text or "") for a in ats).strip()
            if ats and not _PLACEHOLDER_TITLE.match(txt):
                return sh, ats
    # 2) infer: top-most text shape with the largest average font
    cands = []
    for sh in shapes:
        if sh.kind != "text":
            continue
        ats = _shape_atoms(deck, sh)
        if not ats:
            continue
        if sh.top / (deck.height or 1) > 0.30:
            continue
        cands.append((_avg_size(ats), -sh.top, sh, ats))
    if cands:
        # Sort by (avg font size, higher on slide) only -- never fall through to
        # comparing the Shape objects (which aren't orderable) on a tie.
        cands.sort(key=lambda c: (c[0], c[1]), reverse=True)
        _, _, sh, ats = cands[0]
        # A title is SHORT. If the top text is a full sentence/paragraph, it is
        # body copy (a statement slide), not a title -- don't promote it, or it
        # renders as a cramped multi-line "title".
        text = " ".join((a.text or "") for a in ats).strip()
        if (len(text) <= 70 and len(text.split()) <= 11
                and not _PLACEHOLDER_TITLE.match(text)):
            return sh, ats
    return None, []


# --------------------------------------------------------------------------- #
# diagram / table / column detection
# --------------------------------------------------------------------------- #
def _detect_table(deck: Deck, slide: Slide):
    for sh in slide.shapes:
        if sh.kind == "table":
            ats = _shape_atoms(deck, sh)
            if not ats:
                continue
            rows = max(a.row for a in ats) + 1
            cols = max(a.col for a in ats) + 1
            cells = [Cell(atom_id=a.id, row=a.row, col=a.col,
                          header=(a.row == 0)) for a in ats]
            return TableSpec(rows=rows, cols=cols, cells=cells), sh
    return None, None


def _detect_columns(deck: Deck, slide: Slide, title_shape):
    """Two side-by-side text shapes -> two columns (e.g. Initiator/Responder)."""
    W = deck.width
    text_shapes = [sh for sh in slide.shapes
                   if sh.kind == "text" and sh is not title_shape
                   and _shape_atoms(deck, sh)]
    if any(sh.kind in ("picture", "table") for sh in slide.shapes):
        return None
    if not (2 <= len(text_shapes) <= 3):
        return None
    left = [sh for sh in text_shapes if _center(sh, W, deck.height)[0] < 0.5]
    right = [sh for sh in text_shapes if _center(sh, W, deck.height)[0] >= 0.5]
    if not (left and right):
        return None
    cols = []
    for group in (left, right):
        group.sort(key=lambda s: s.top)
        sh = group[0]
        ats = _shape_atoms(deck, sh)
        header_ids, blocks = [], []
        if ats and (ats[0].underline or ats[0].bold):
            header_ids = [ats[0].id]
            body = ats[1:]
        else:
            body = ats
        for a in body:
            blocks.append(Block(atom_id=a.id, role="body", level=a.level,
                                emphasis=a.bold or not _is_black(a.color)))
        cols.append(Column(header_ids=header_ids, blocks=blocks))
    return cols


def _detect_diagram(deck: Deck, slide: Slide, title_shape):
    """Fidelity-first diagram detection.

    We do NOT try to guess a diagram's semantic type and rebuild it from scratch
    (that is what turned a linear process into a meaningless hub). Instead we
    detect the *visual region* of the slide and preserve it as an exact crop of
    the original render, so the diagram always keeps its true structure/meaning.
    Object reconstruction happens later ONLY on explicit request, via
    augment_with_vision(). Text labels living inside the visual region are marked
    `covered_ids` (shown in the crop, not re-rendered as stray bullets); body
    text outside the region stays native.
    """
    W, H = deck.width, deck.height
    connectors = [sh for sh in slide.shapes if sh.kind == "connector"]
    pictures = [sh for sh in slide.shapes if sh.kind == "picture"]
    text_nodes = [sh for sh in slide.shapes
                  if sh.kind == "text" and sh is not title_shape
                  and _shape_atoms(deck, sh)]

    # A shape only counts as a genuine VISUAL (diagram material) if it is a
    # picture/connector/freeform, or an auto-shape with a fill or a
    # non-rectangular geometry. Plain (even empty) text boxes are layout, NOT a
    # diagram -- otherwise two side-by-side bullet columns get boxed as a fake
    # diagram.
    def _is_visual(sh):
        if sh.kind in ("picture", "connector", "freeform"):
            return True
        if getattr(sh, "is_autoshape", False):
            geom = getattr(sh, "geom", None)
            if sh.fill_rgb or (geom and geom not in _RECT_GEOMS):
                return True
        return False

    visuals = [sh for sh in slide.shapes
               if _is_visual(sh) and sh is not title_shape
               and sh.kind != "connector" and sh.width and sh.height]

    # Conservative diagram gate. Pictures ALONE never force diagram mode -- a
    # photo (decorative or even a whole diagram-image) is handled far more
    # safely by build_body, which places pictures at their ORIGINAL positions
    # and keeps the real text as proper bullets. This is the core cure for
    # "graphics mixed with text get mangled": we only reconstruct/crop when
    # there is a genuinely CONSTRUCTED visual --
    #   - labels joined by connectors (a wired diagram), or
    #   - a large non-rectangular / filled shape structure (funnel, pyramid,
    #     chevrons, callouts, ...).
    non_pic_visuals = [sh for sh in visuals if sh.kind != "picture"]
    big_visual = any(sh.width * sh.height > 0.05 * W * H for sh in non_pic_visuals)
    wired = bool(connectors) and len(text_nodes) >= 3      # labels joined by lines

    # Spatial-label diagram: MANY short text labels positioned around a graphic
    # (each labels a part of the visual), spread across >=2 horizontal columns.
    # Linearizing these into bullets is exactly the "graphics + text -> garbage"
    # failure. When we see this signature we PRESERVE the whole content area as
    # an exact crop so the meaning/positions are never rearranged. Guarded
    # tightly (>=6 SHORT labels in >=2 columns) so a normal bullet list beside a
    # photo (few, long text boxes) is never caught.
    has_visual = bool(pictures) or bool(non_pic_visuals)
    short_labels = [sh for sh in text_nodes if len(_shape_atoms(deck, sh)) <= 3]
    if has_visual and len(short_labels) >= 6:
        xs = sorted((sh.left + sh.width / 2) / (W or 1) for sh in short_labels)
        cols = 1
        for a, b in zip(xs, xs[1:]):
            if b - a > 0.18:
                cols += 1
        if cols >= 2:
            body = [sh for sh in slide.shapes if sh is not title_shape
                    and sh.width and sh.height
                    and sh.kind in ("picture", "connector", "freeform", "text")]
            vl = min(sh.left for sh in body)
            vt = min(sh.top for sh in body)
            vr = max(sh.left + sh.width for sh in body)
            vb = max(sh.top + sh.height for sh in body)
            covered = [a.id for sh in text_nodes for a in _shape_atoms(deck, sh)]
            src_imgs = [a.id for sh in pictures for a in _shape_atoms(deck, sh)
                        if a.kind == "image"]
            return DiagramSpec(kind="preserve", raster_fallback=True,
                               prefer_crop=True, confidence=0.6,
                               bbox=(vl, vt, vr - vl, vb - vt),
                               covered_ids=covered,
                               shape_ids=[sh.shape_id for sh in body],
                               source_image_ids=src_imgs, region="full")

    if not (big_visual or wired):
        return None

    # visual anchors define the region; fall back to wired labels if needed
    def _dedup(shapes):
        seen, out = set(), []
        for sh in shapes:
            if sh.shape_id not in seen:
                seen.add(sh.shape_id); out.append(sh)
        return out

    anchors = _dedup(list(pictures) + list(connectors) + list(visuals))
    if not anchors and wired:
        anchors = list(text_nodes)
    if not anchors:
        return None

    vl = min(sh.left for sh in anchors)
    vt = min(sh.top for sh in anchors)
    vr = max(sh.left + sh.width for sh in anchors)
    vb = max(sh.top + sh.height for sh in anchors)

    # pull in any text labels whose center sits within the visual region
    def in_region(sh, mx=0.05, my=0.05):
        cx, cy = sh.left + sh.width / 2, sh.top + sh.height / 2
        return (vl - mx * W <= cx <= vr + mx * W and
                vt - my * H <= cy <= vb + my * H)

    region_text = [sh for sh in text_nodes if in_region(sh)]
    covered_ids = []
    for sh in region_text:
        covered_ids += [a.id for a in _shape_atoms(deck, sh)]
        vl, vt = min(vl, sh.left), min(vt, sh.top)
        vr, vb = max(vr, sh.left + sh.width), max(vb, sh.top + sh.height)

    # Reclassify false diagrams (this is where mixed text+graphics used to get
    # mangled):
    #  - decorative photo(s) with NO labels sitting inside them -> not a diagram;
    #    build_body will place the pictures at their original spots and keep the
    #    real text as proper bullets (e.g. a numbered list beside a photo).
    only_pics = bool(pictures) and not connectors and not non_pic_visuals
    if only_pics and not covered_ids:
        return None
    #  - just filled/plain rectangles of text (no pictures, no connectors) ->
    #    styled text boxes, not a diagram; keep the words as bullets/columns.
    rects_only = (not pictures and not connectors and non_pic_visuals
                  and all((getattr(v, "geom", None) in _RECT_GEOMS)
                          for v in non_pic_visuals))
    if rects_only and not wired:
        return None

    bbox = (vl, vt, vr - vl, vb - vt)
    src_img_ids = [a.id for sh in pictures for a in _shape_atoms(deck, sh)
                   if a.kind == "image"]
    shape_ids = [sh.shape_id
                 for sh in _dedup(anchors + region_text)]

    # placement region: if real body text remains outside a not-too-wide visual,
    # keep the visual to one side and the bullets to the other.
    other_text = [sh for sh in text_nodes if sh not in region_text
                  and _shape_atoms(deck, sh)]
    width_frac = (vr - vl) / (W or 1)
    ccx = ((vl + vr) / 2) / (W or 1)
    if other_text and width_frac < 0.6:
        region = "right" if ccx >= 0.5 else "left"
    else:
        region = "full"

    return DiagramSpec(kind="preserve", raster_fallback=True, confidence=0.5,
                       bbox=bbox, covered_ids=covered_ids, shape_ids=shape_ids,
                       source_image_ids=src_img_ids, region=region)


# --------------------------------------------------------------------------- #
# deterministic grounded planner
# --------------------------------------------------------------------------- #
def _classify_kind(deck, slide, title_atoms, body_atoms, images):
    txt = " ".join(a.text for a in title_atoms + body_atoms).lower()
    if "thank" in txt and len(body_atoms) <= 2 and not images:
        return "thankyou", "1_Title Slide"
    if slide.index == 0:
        return "title", "Title Slide"
    return "content", "Title Only"


_PLACEHOLDER_TITLE = _re.compile(r"^(title|untitled|slide)\s*[0-9]*$", _re.I)


def _deck_chrome(deck: Deck):
    """Deck-level 'chrome' detector: repeated running-heads / footers (e.g. a
    course name printed small at the bottom of most slides). The hand-formatted
    references strip these -- the template supplies its own footer. We flag the
    atoms so they are counted (coverage holds) but never rendered as content."""
    from collections import defaultdict
    n_slides = len(deck.slides) or 1
    occ = defaultdict(list)
    for s in deck.slides:
        bysh = _by_shape(s)
        for a in deck.slide_atoms(s.index):
            if a.kind != "text":
                continue
            t = _re.sub(r"\s+", " ", (a.text or "").strip().lower())
            if not t or len(t.split()) > 10:
                continue
            occ[t].append((a, bysh.get(a.shape_id)))
    thresh = max(3, int(round(0.4 * n_slides)))
    chrome = set()
    for t, items in occ.items():
        if len({id(a) for a, _ in items}) < thresh:
            continue
        edgey = 0
        for a, sh in items:
            small = (a.size is None) or (a.size <= 16)
            edge = False
            if sh and deck.height:
                yc = (sh.top + sh.height / 2) / deck.height
                edge = yc > 0.85 or yc < 0.10
            if small or edge:
                edgey += 1
        if edgey >= thresh:
            chrome.update(a.id for a, _ in items)
    return chrome


def plan_deterministic(deck: Deck) -> List[SlidePlan]:
    chrome = _deck_chrome(deck)
    plans = []
    for slide in deck.slides:
        plan = _plan_one(deck, slide, chrome)
        plans.append(plan)
    return plans


def _plan_one(deck: Deck, slide: Slide, chrome=frozenset()) -> SlidePlan:
    W, H = deck.width, deck.height
    by_shape = _by_shape(slide)
    all_atoms = {a.id for a in deck.slide_atoms(slide.index)}
    assigned = set()

    title_shape, title_atoms = _find_title(deck, slide)
    title_ids = [a.id for a in title_atoms]
    assigned.update(title_ids)

    images = [a for a in deck.slide_atoms(slide.index) if a.kind == "image"]
    kind, layout = _classify_kind(deck, slide, title_atoms,
                                  [a for a in deck.slide_atoms(slide.index)
                                   if a.kind in ("text", "cell") and a.id not in assigned],
                                  images)

    plan = SlidePlan(index=slide.index, kind=kind, layout=layout,
                     title_ids=title_ids)

    # structure detection only on CONTENT slides -- title/closing slides just get
    # their title + subtitle (a full-bleed cover photo must not be mistaken for a
    # diagram, which would swallow the subtitle).
    table = diagram = None
    if kind == "content":
        table, table_shape = _detect_table(deck, slide)
        if table:
            plan.table = table
            assigned.update(c.atom_id for c in table.cells)

        diagram = _detect_diagram(deck, slide, title_shape)
        if diagram:
            plan.diagram = diagram
            if diagram.raster_fallback:
                plan.notes = ("diagram preserved / rebuilt natively from the "
                              "original shapes")
            for n in diagram.nodes:
                assigned.update(n.atom_ids)
            assigned.update(diagram.covered_ids)
            assigned.update(diagram.source_image_ids)

        if not table and not diagram:
            cols = _detect_columns(deck, slide, title_shape)
            if cols:
                plan.columns = cols
                for c in cols:
                    assigned.update(c.header_ids)
                    assigned.update(b.atom_id for b in c.blocks)

    # images
    for a in images:
        if a.id in assigned:
            continue
        sh = by_shape.get(a.shape_id)
        cx = _center(sh, W, H)[0] if sh else 0.5
        region = "left" if cx < 0.4 else "right" if cx > 0.6 else "full"
        plan.images.append(ImgPlace(atom_id=a.id, region=region))
        assigned.add(a.id)

    # body: everything text not yet claimed, ordered by geometry then reading order
    remaining = [a for a in deck.slide_atoms(slide.index)
                 if a.kind == "text" and a.id not in assigned]

    def sortkey(a):
        sh = by_shape.get(a.shape_id)
        return (sh.top if sh else 0, sh.left if sh else 0, a.id)

    # Group runs into their SOURCE paragraphs and assign ONE role per paragraph
    # from the full joined text. A quote or an attribution is usually split into
    # several runs (authors / journal / year); judging each run alone loses the
    # role, so we judge the whole line.
    paras = OrderedDict()
    for a in sorted(remaining, key=sortkey):
        # junk (page numbers, bare dates) or deck chrome (repeated footer /
        # running-head) -> flag, count for coverage, but never render
        paras.setdefault((a.shape_id, a.para), []).append(a)
    for atoms in paras.values():
        role = _para_role(atoms)
        for a in atoms:
            plan.blocks.append(Block(atom_id=a.id, role=role, level=a.level,
                                     emphasis=(a.bold or not _is_black(a.color))))
            assigned.add(a.id)

    # coverage guarantee: anything still unplaced is FLAGGED, never dropped
    for aid in all_atoms:
        if aid not in assigned:
            plan.flagged.append(aid)

    # context-aware split hint (does NOT drop content; builder may split)
    plan.split_hint = (len(plan.blocks) > 12 and not plan.diagram
                       and not plan.table and not plan.columns and not plan.images)
    if plan.diagram and plan.diagram.raster_fallback:
        plan.confidence = 0.5
    return plan


# --------------------------------------------------------------------------- #
# Gemini planner (drop-in; identical schema, ids only). Guarded by API key.
# --------------------------------------------------------------------------- #
GEMINI_SCHEMA_HINT = """
Return STRICT JSON: {"title_ids":[int], "blocks":[{"atom_id":int,"role":"body|subhead|citation","level":int,"emphasis":bool}],
"images":[{"atom_id":int,"region":"left|right|full"}], "diagram":null|{...}, "table":null|{...},
"columns":null|[{"header_ids":[int],"blocks":[...]}], "flagged":[int]}.
RULES: only use atom_id values from the provided list; reference EVERY atom exactly once; never write text.
"""


def augment_with_vision(deck: Deck, plans: List[SlidePlan], orig_pdf: str,
                        min_conf: float = 0.55, workdir: Optional[str] = None):
    """Upgrade raster-fallback diagrams into native object diagrams using Gemini
    OCR, ONLY when vision is available and confident.

    The read labels are VISION-DERIVED (not source atoms): they are attached to
    diagram nodes with `vision_derived=True`, and the consumed picture atom is
    moved into `source_image_ids` so coverage still counts it exactly once. Every
    upgraded slide is annotated for human confirmation.

    Returns the list of slide indices that were upgraded (empty if vision is off).
    """
    import os
    try:
        import sys
        _here = os.path.dirname(os.path.abspath(__file__))
        _backend = os.path.dirname(_here)
        if _backend not in sys.path:
            sys.path.insert(0, _backend)
        from app.qa import gemini
        import fitz
    except Exception:
        return []

    if not gemini.available() or not orig_pdf or not os.path.exists(orig_pdf):
        return []

    workdir = workdir or os.path.dirname(orig_pdf)
    upgraded = []
    try:
        doc = fitz.open(orig_pdf)
    except Exception:
        return []

    for plan in plans:
        dg = plan.diagram
        if not dg or not dg.raster_fallback:
            continue
        if plan.index >= doc.page_count:
            continue
        try:
            page = doc.load_page(plan.index)
            clip = None
            if dg.bbox:
                l, t, w, h = dg.bbox
                clip = fitz.Rect(l / 12700, t / 12700,
                                 (l + w) / 12700, (t + h) / 12700)
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), clip=clip)
            png = os.path.join(workdir, f"_visioncrop-{plan.index + 1}.png")
            pix.save(png)
        except Exception:
            continue

        title = " ".join(deck.atoms[i].text for i in plan.title_ids
                         if i in deck.atoms).replace("\x0b", " ").strip()
        read = gemini.read_diagram(png, context_text=title)
        if not read or read.get("confidence", 0) < min_conf:
            continue
        # Only reconstruct true node/relationship diagrams. Charts, curves, axis
        # graphs, and anything Gemini can only call "generic" stay as a safe
        # raster crop -- forcing boxes onto a curve just creates overlaps.
        rkind = (read.get("kind") or "generic").lower()
        if rkind not in ("hub", "cycle", "pyramid", "flow", "matrix"):
            continue
        # Drop any node whose label is really the center (avoids a node box
        # overlapping the center shape, e.g. slide 18 "Compromising").
        center = (read.get("center") or "").strip().lower()
        remap, nodes = {}, []
        for old_i, n in enumerate(read["nodes"]):
            if center and n["label"].strip().lower() == center:
                continue
            remap[old_i] = len(nodes)
            nodes.append(Node(x=n["x"], y=n["y"], label=n["label"], vision_derived=True))
        if len(nodes) < 2:
            continue
        edges = [Edge(frm=remap[e[0]], to=remap[e[1]]) for e in read.get("edges", [])
                 if e[0] in remap and e[1] in remap]

        # consume the picture atom(s): move from images -> source_image_ids
        moved = [im.atom_id for im in plan.images
                 if deck.atoms.get(im.atom_id) and deck.atoms[im.atom_id].kind == "image"]
        plan.images = [im for im in plan.images if im.atom_id not in moved]

        dg.kind = read.get("kind", "vision") or "vision"
        dg.nodes = nodes
        dg.edges = edges
        dg.center_label = read.get("center", "")
        dg.confidence = read.get("confidence", 0.0)
        dg.raster_fallback = False
        dg.vision_derived = True
        dg.source_image_ids = moved
        dg.escalated = bool(read.get("escalated"))
        dg.model = read.get("model", "")
        plan.notes = ("diagram reconstructed from image via Gemini vision - "
                      "labels are vision-derived, confirm against original")
        plan.confidence = min(plan.confidence, 0.8)
        upgraded.append(plan.index)

    return upgraded


def plan_with_gemini(deck: Deck):  # pragma: no cover - requires API key
    """Placeholder that shows the intended call. Returns None if unavailable so
    callers fall back to the deterministic planner. The critical point: whatever
    the model returns is passed through verify.validate_plan (ids-only + coverage),
    so a hallucinated/omitted id is rejected before it can affect output."""
    import os
    if not os.environ.get("GEMINI_API_KEY"):
        return None
    # A full implementation would, per slide, send the atom table (id,text,geometry,
    # formatting) + the rendered slide image + GEMINI_SCHEMA_HINT, parse JSON into
    # SlidePlan, then hand every plan to validate_plan(). Left as an integration
    # point for the prototype.
    return None
