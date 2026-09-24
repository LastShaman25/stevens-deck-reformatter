"""LLM planner (Claude) - constrained, coverage-verified slide planning.

Claude reads a compact IR of each slide (atoms with IDs, position %, formatting)
and returns a layout plan that references atoms BY ID ONLY. The plan is converted
to a SlidePlan and passed through verify.validate_plan(); any plan that invents,
drops, or duplicates content is rejected so the caller can fall back to the
deterministic planner. Claude therefore improves *arrangement* but can never
fabricate or lose content -- that guarantee stays in code.
"""
from __future__ import annotations

import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_HERE)
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from app.qa import claude                                            # noqa: E402

from .ir import Deck, Slide                                          # noqa: E402
from .planner import (Block, Column, GridCell, GridSpec, ImgPlace,   # noqa: E402
                      SlidePlan, referenced_ids)
from .verify import validate_plan                                    # noqa: E402


_SYSTEM = (
    "You are the layout planner for Stevens Slide Studio, which rebuilds a "
    "messy PowerPoint slide as a clean, on-brand Stevens slide. You are given "
    "the slide's content as a JSON list of ATOMS, each with a stable integer "
    "id, its text, position (x,y,w,h as 0..1 fractions of the slide), and "
    "formatting. Decide the best Stevens layout and return STRICT JSON.\n\n"
    "ABSOLUTE RULES:\n"
    "1. Reference every atom by its id. You MUST place EVERY atom id exactly "
    "once across the plan. Never invent an id. Never output text -- only ids.\n"
    "2. Understand INTENT. If small headers sit above a diagram's stages (e.g. "
    "phase names over funnel stages with columns beneath), model it as a GRID "
    "with aligned rows/cols -- do NOT flatten headers into bullets.\n"
    "3. Not every line is a bullet. Use bullets only for genuine list items; "
    "use short headers/labels for titles of sections or diagram parts.\n"
    "4. Choose each line's ROLE from its content, formatting, and position -- "
    "place by MEANING, do not force one uniform pattern:\n"
    "   - 'quote'     : a quotation (in quote marks or italic prose).\n"
    "   - 'source'    : an attribution/reference (author, journal, year). It "
    "belongs UNDER its quote and is smaller/secondary -- never a bullet.\n"
    "   - 'note'      : an annotation such as 'Note: ...' or 'NB ...'. It is "
    "secondary to the list it sits beside -- style it as a note, NOT a bullet.\n"
    "   - 'subhead'   : a short section/label header (often bold/underlined).\n"
    "   - 'paragraph' : a full prose sentence that is not a list item.\n"
    "   - 'bullet'    : a genuine list item.\n"
    "5. RESPECT ORIGINAL HIERARCHY. The atoms include size/x/y/bold/italic. "
    "Preserve the source's relative prominence -- e.g. if the quote is in a "
    "smaller font than the name, keep the quote smaller; a caption stays a "
    "caption. Group each label with the diagram part it belongs to (via GRID) "
    "rather than listing labels as loose text.\n"
    "6. PATTERNS FROM THE STEVENS REFERENCE DECKS (follow these):\n"
    "   - CARDS: when the slide has 2-4 parallel labeled sections each with a "
    "short heading + its own lines (e.g. 'My Strengths' / 'My Aspirations', or "
    "'Idealized Influence (Attitudes)/(Behavior)'), model them as a GRID of "
    "cells with header=true. Set box=true ONLY for standalone section cards "
    "(these render with a Stevens Red header in a red-outlined box); leave "
    "box=false for plain parallel bullet columns (black bold header).\n"
    "   - TABLES: a comparison of two+ things across attributes is a table, not "
    "prose. Keep it as columns/grid, not bullets.\n"
    "   - SOURCES stay small and go at the BOTTOM (role 'source').\n"
    "   - A title-slide subtitle should be the deck/course name; also keep the "
    "presenter and any copyright line if present.\n"
    "   - IGNORE repeated running-heads/footers (e.g. a course name printed on "
    "every slide) -- if such an atom appears, put it last as role 'note' or omit "
    "it from emphasis; never make it a bullet or title.\n"
    "   - DENSE slides: if content clearly exceeds one slide, it is fine to keep "
    "one logical group; the app will split overflow and suffix '(part 2)'.\n\n"
    "OUTPUT SCHEMA (JSON object):\n"
    "{\n"
    '  "kind": "content|title|section|thankyou",\n'
    '  "layout": "<=40 char label of the layout you chose",\n'
    '  "title": [ids],            // slide title (for title slide: the deck name)\n'
    '  "subtitle": [ids],         // title-slide subheading, or a lead line\n'
    '  "body": [{"id":int,"level":0..2,"role":"bullet|paragraph|subhead|quote|source|note","emphasis":bool}],\n'
    '  "columns": [{"header":[ids],"items":[{"id":int,"level":0}]}],\n'
    '  "grid": {"rows":R,"cols":C,"connect":"none|row-arrows",\n'
    '           "cells":[{"ids":[ints],"row":r,"col":c,"box":bool,"header":bool}],\n'
    '           "images":[ids]},  // pictures kept in place inside the diagram\n'
    '  "notes": "one sentence: why this layout"\n'
    "}\n"
    "Use ONLY the fields you need (e.g. a simple slide uses title+body; a funnel "
    "uses title+grid). Put picture/image atoms into grid.images (diagram) or, if "
    "purely decorative, into body is NOT allowed -- images go to grid.images. "
    "Return ONLY the JSON."
)


def _payload(deck: Deck, slide: Slide):
    geo = {}
    for sh in slide.shapes:
        for aid in sh.atom_ids:
            geo[aid] = (sh, sh.is_autoshape or bool(sh.fill_rgb))
    atoms = []
    for a in deck.slide_atoms(slide.index):
        sh, is_box = geo.get(a.id, (None, False))
        entry = {"id": a.id, "kind": a.kind, "text": (a.text or "")[:200]}
        if sh is not None and deck.width and deck.height:
            entry.update({
                "x": round(sh.left / deck.width, 3),
                "y": round(sh.top / deck.height, 3),
                "w": round(sh.width / deck.width, 3),
                "h": round(sh.height / deck.height, 3),
            })
        if a.kind == "text":
            if a.bold:
                entry["bold"] = True
            if a.italic:
                entry["italic"] = True
            if a.color:
                entry["color"] = a.color
            if a.size:
                entry["size"] = a.size
            if is_box:
                entry["in_box"] = True
        atoms.append(entry)
    atoms.sort(key=lambda e: (e.get("y", 0), e.get("x", 0)))
    return {"slide_index": slide.index, "atoms": atoms}


_ROLES = {"bullet", "paragraph", "subhead", "citation",
          "quote", "source", "note", "body"}


def _role(r):
    r = (r or "body").lower()
    if r == "bullet":
        return "body"
    return r if r in _ROLES else "body"


def _to_plan(index, data, valid_ids):
    used = set()

    def take(ids):
        out = []
        for i in ids or []:
            if isinstance(i, int) and i in valid_ids and i not in used:
                used.add(i)
                out.append(i)
        return out

    plan = SlidePlan(index=index, kind=str(data.get("kind", "content")),
                     layout=str(data.get("layout", ""))[:40] or "Content slide")
    plan.title_ids = take(data.get("title"))
    plan.subtitle_ids = take(data.get("subtitle"))

    for b in data.get("body") or []:
        i = b.get("id")
        if isinstance(i, int) and i in valid_ids and i not in used:
            used.add(i)
            plan.blocks.append(Block(atom_id=i, role=_role(b.get("role")),
                                     level=int(b.get("level", 0) or 0),
                                     emphasis=bool(b.get("emphasis"))))

    cols = data.get("columns")
    if cols:
        built = []
        for c in cols:
            hdr = take(c.get("header"))
            blocks = []
            for it in c.get("items") or []:
                i = it.get("id")
                if isinstance(i, int) and i in valid_ids and i not in used:
                    used.add(i)
                    blocks.append(Block(atom_id=i, level=int(it.get("level", 0) or 0)))
            if hdr or blocks:
                built.append(Column(header_ids=hdr, blocks=blocks))
        if built:
            plan.columns = built

    g = data.get("grid")
    if g and g.get("cells"):
        cells = []
        for c in g["cells"]:
            ids = take(c.get("ids"))
            if not ids:
                continue
            cells.append(GridCell(atom_ids=ids, row=int(c.get("row", 0) or 0),
                                  col=int(c.get("col", 0) or 0),
                                  box=bool(c.get("box")), header=bool(c.get("header"))))
        if cells:
            plan.grid = GridSpec(
                rows=int(g.get("rows", 1) or 1), cols=int(g.get("cols", 1) or 1),
                connect=str(g.get("connect", "none")),
                image_ids=take(g.get("images")), cells=cells)

    # sweep any atoms Claude forgot so coverage always holds (images kept by
    # geometry; stray text appended as body so nothing is ever dropped).
    for a in [x for x in valid_atoms_order(index, valid_ids)]:
        if a in used:
            continue
        used.add(a)
        if _atom_kind(index, a) == "image":
            if plan.grid:
                plan.grid.image_ids.append(a)
            else:
                plan.images.append(ImgPlace(atom_id=a, region="right"))
        else:
            plan.blocks.append(Block(atom_id=a, role="body"))
    return plan


# these two are filled by plan_slide_llm via closures over the deck
_DECK = None


def valid_atoms_order(index, valid_ids):
    return sorted(valid_ids)


def _atom_kind(index, aid):
    return _DECK.atoms[aid].kind if (_DECK and aid in _DECK.atoms) else "text"


def plan_slide_llm(deck: Deck, slide: Slide):
    """Return an LLM SlidePlan for one slide, or None to fall back."""
    global _DECK
    _DECK = deck
    if not claude.available():
        return None
    data = claude.generate_json(_SYSTEM, json.dumps(_payload(deck, slide)))
    if not isinstance(data, dict):
        return None
    valid_ids = {a.id for a in deck.slide_atoms(slide.index)}
    try:
        plan = _to_plan(slide.index, data, valid_ids)
    except Exception:
        return None
    if validate_plan(deck, plan):     # non-empty => errors => reject
        return None
    return plan
