"""Stage 1 - Complete Intermediate Representation (IR).

Parses a .pptx into a full model that keeps EVERYTHING: every shape's geometry,
z-order and type, every text run with its formatting, table cells, images, groups
and connectors. Each piece of *content* (text run, table cell, image) gets a
stable integer id -- this is what makes the no-loss guarantee possible: the
planner may only ever reference these ids, never author text.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import List, Optional

from pptx import Presentation
from pptx.oxml.ns import qn
from pptx.util import Emu

try:
    from pptx.enum.shapes import MSO_SHAPE_TYPE
    from pptx.enum.dml import MSO_FILL
except Exception:      # pragma: no cover
    MSO_SHAPE_TYPE = MSO_FILL = None

EMU = 914400


def _shape_fill(sh):
    try:
        f = sh.fill
        if MSO_FILL is not None and f.type == MSO_FILL.SOLID:
            return str(f.fore_color.rgb)
    except Exception:
        pass
    return None


def _shape_line(sh):
    try:
        ln = sh.line
        if ln.color is not None and ln.color.type is not None:
            return str(ln.color.rgb)
    except Exception:
        pass
    return None


def _is_autoshape(sh):
    try:
        return sh.shape_type == MSO_SHAPE_TYPE.AUTO_SHAPE
    except Exception:
        return False


def _geom(sh):
    """prstGeom preset name (e.g. 'rect', 'roundRect', 'trapezoid', 'chevron').
    Used to decide whether a shape can be faithfully rebuilt as a box or must be
    preserved as a crop (non-rectangular presets distort when boxed)."""
    try:
        spPr = sh._element.find(qn("p:spPr"))
        if spPr is not None:
            pg = spPr.find(qn("a:prstGeom"))
            if pg is not None:
                return pg.get("prst")
    except Exception:
        pass
    return None


def _rot(sh):
    try:
        return float(sh.rotation or 0.0)
    except Exception:
        return 0.0


def _identity(l, t, w, h):
    return (l, t, w, h)


def _group_xf(sh):
    """Transform mapping a group's child (local) coords -> the group's parent
    space, using the group xfrm off/ext/chOff/chExt. Returns identity on failure."""
    try:
        gpr = sh._element.find(qn("p:grpSpPr"))
        xfrm = gpr.find(qn("a:xfrm"))
        off, ext = xfrm.find(qn("a:off")), xfrm.find(qn("a:ext"))
        choff, chext = xfrm.find(qn("a:chOff")), xfrm.find(qn("a:chExt"))
        ox, oy = int(off.get("x")), int(off.get("y"))
        ex, ey = int(ext.get("cx")), int(ext.get("cy"))
        cox, coy = int(choff.get("x")), int(choff.get("y"))
        cex, cey = int(chext.get("cx")), int(chext.get("cy"))
        sx = ex / cex if cex else 1.0
        sy = ey / cey if cey else 1.0

        def f(l, t, w, h):
            return (ox + (l - cox) * sx, oy + (t - coy) * sy, w * sx, h * sy)
        return f
    except Exception:
        return _identity


@dataclass
class Atom:
    """An immutable unit of content. The AI/planner references these by id only."""
    id: int
    slide: int
    shape_id: str
    kind: str                       # 'text' | 'cell' | 'image'
    text: str = ""
    bold: bool = False
    italic: bool = False
    underline: bool = False
    color: Optional[str] = None     # 'RRGGBB' if explicit RGB, else None
    size: Optional[float] = None    # pt
    level: int = 0
    para: int = 0                   # paragraph index within the shape
    row: int = -1
    col: int = -1
    image_sha: Optional[str] = None
    image_ext: Optional[str] = None
    image_blob: Optional[bytes] = None


@dataclass
class Shape:
    shape_id: str
    slide: int
    kind: str                       # 'text' | 'picture' | 'table' | 'connector' | 'shape' | 'group'
    name: str
    z: int
    left: int = 0
    top: int = 0
    width: int = 0
    height: int = 0
    is_placeholder: bool = False
    ph_type: Optional[str] = None
    parent: Optional[str] = None
    atom_ids: List[int] = field(default_factory=list)
    fill_rgb: Optional[str] = None   # solid fill 'RRGGBB' if any
    line_rgb: Optional[str] = None   # border color 'RRGGBB' if any
    is_autoshape: bool = False       # true box/shape (vs a plain text box)
    geom: Optional[str] = None       # prstGeom preset (e.g. 'rect','trapezoid')
    rotation: float = 0.0            # degrees


@dataclass
class Slide:
    index: int
    width: int
    height: int
    shapes: List[Shape] = field(default_factory=list)


@dataclass
class Deck:
    width: int
    height: int
    slides: List[Slide]
    atoms: dict                     # id -> Atom

    def slide_atoms(self, idx):
        return [a for a in self.atoms.values() if a.slide == idx]


def _int(v):
    try:
        return int(v)
    except Exception:
        return 0


def _hex(run):
    try:
        rgb = run.font.color.rgb
        return str(rgb)
    except Exception:
        return None


def _size(run):
    try:
        return run.font.size.pt if run.font.size is not None else None
    except Exception:
        return None


def _flag(v):
    return bool(v) if v is not None else False


class _Counter:
    def __init__(self):
        self.n = 0

    def next(self):
        self.n += 1
        return self.n


def _shape_kind(sh):
    tag = sh._element.tag
    if tag == qn("p:grpSp"):
        return "group"
    if tag == qn("p:cxnSp"):
        return "connector"
    if tag == qn("p:pic"):
        return "picture"
    try:
        if sh.has_table:
            return "table"
    except Exception:
        pass
    return "text"


def _extract_shape(sh, slide_idx, parent, zc, ac, atoms, shapes, xf=None):
    xf = xf or _identity
    kind = _shape_kind(sh)
    sid = f"s{slide_idx}_{zc.next()}"
    ph_type = None
    is_ph = False
    try:
        if sh.is_placeholder:
            is_ph = True
            ph_type = str(sh.placeholder_format.type)
    except Exception:
        pass

    al, at, aw, ah = xf(_int(sh.left), _int(sh.top),
                        _int(sh.width), _int(sh.height))
    shape = Shape(
        shape_id=sid, slide=slide_idx, kind=kind, name=(sh.name or ""),
        z=zc.n, left=int(al), top=int(at), width=int(aw), height=int(ah),
        is_placeholder=is_ph, ph_type=ph_type, parent=parent,
    )
    shapes.append(shape)

    if kind == "group":
        gf = _group_xf(sh)
        composed = (lambda l, t, w, h: xf(*gf(l, t, w, h)))
        for child in sh.shapes:
            _extract_shape(child, slide_idx, sid, zc, ac, atoms, shapes, composed)
        return

    if kind == "picture":
        try:
            img = sh.image
            sha = hashlib.sha1(img.blob).hexdigest()[:12]
            a = Atom(id=ac.next(), slide=slide_idx, shape_id=sid, kind="image",
                     image_sha=sha, image_ext=img.ext, image_blob=img.blob)
            atoms[a.id] = a
            shape.atom_ids.append(a.id)
        except Exception:
            pass
        return

    if kind == "table":
        try:
            tbl = sh.table
            for r, row in enumerate(tbl.rows):
                for c, cell in enumerate(row.cells):
                    txt = (cell.text or "").strip()
                    if not txt:
                        continue
                    # capture first-run formatting as representative
                    b = i = u = False
                    col = None
                    sz = None
                    for p in cell.text_frame.paragraphs:
                        for run in p.runs:
                            if run.text.strip():
                                b = _flag(run.font.bold); i = _flag(run.font.italic)
                                u = _flag(run.font.underline)
                                col = _hex(run); sz = _size(run)
                                break
                        if col is not None or b or i:
                            break
                    a = Atom(id=ac.next(), slide=slide_idx, shape_id=sid, kind="cell",
                             text=txt, bold=b, italic=i, underline=u, color=col,
                             size=sz, row=r, col=c)
                    atoms[a.id] = a
                    shape.atom_ids.append(a.id)
        except Exception:
            pass
        return

    # capture fill/border/box-ness for text & auto shapes (for branded rebuild)
    if kind == "text":
        shape.fill_rgb = _shape_fill(sh)
        shape.line_rgb = _shape_line(sh)
        shape.is_autoshape = _is_autoshape(sh)
        shape.geom = _geom(sh)
        shape.rotation = _rot(sh)

    # text-bearing shape (textbox / autoshape / connector with label)
    if sh.has_text_frame:
        for pi, p in enumerate(sh.text_frame.paragraphs):
            lvl = p.level or 0
            for run in p.runs:
                t = run.text or ""
                if not t.strip():
                    continue
                a = Atom(id=ac.next(), slide=slide_idx, shape_id=sid, kind="text",
                         text=t, bold=_flag(run.font.bold), italic=_flag(run.font.italic),
                         underline=_flag(run.font.underline), color=_hex(run),
                         size=_size(run), level=lvl, para=pi)
                atoms[a.id] = a
                shape.atom_ids.append(a.id)


def extract(path) -> Deck:
    prs = Presentation(path)
    W, H = int(prs.slide_width), int(prs.slide_height)
    atoms: dict = {}
    ac = _Counter()
    slides: List[Slide] = []
    for idx, slide in enumerate(prs.slides):
        zc = _Counter()
        shapes: List[Shape] = []
        for sh in slide.shapes:
            _extract_shape(sh, idx, None, zc, ac, atoms, shapes)
        slides.append(Slide(index=idx, width=W, height=H, shapes=shapes))
    return Deck(width=W, height=H, slides=slides, atoms=atoms)
