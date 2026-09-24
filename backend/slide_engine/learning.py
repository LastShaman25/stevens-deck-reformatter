"""Learning loop: capture every layout decision so the deterministic engine can
be tuned to match Claude, and Claude can eventually be switched off.

For each slide we log a compact FEATURE SIGNATURE of the source, the plan the
DETERMINISTIC engine produced, the plan CLAUDE produced (when on), which one was
USED, and per-decision AGREEMENT flags. Human revisions (tags/instructions) are
logged as CORRECTIONS. `learn.py` then reports a "Claude-removal readiness"
score (deterministic vs Claude agreement) and mines candidate rules.

Design: never throws into the build path (all writes are best-effort), append-
only JSONL, gated by env STEVENS_LEARN (default on).
"""
from __future__ import annotations

import json
import os
import time
from collections import Counter

_HERE = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_HERE)
LOG_DIR = os.path.join(_BACKEND, "learning")
LOG_PATH = os.path.join(LOG_DIR, "decisions.jsonl")


def enabled():
    return os.environ.get("STEVENS_LEARN", "0") not in ("0", "false", "False", "")


# --------------------------------------------------------------------------- #
# feature signature of a SOURCE slide (what the engine has to react to)
# --------------------------------------------------------------------------- #
def signature(deck, slide):
    try:
        ats = list(deck.slide_atoms(slide.index))
        txt = [a for a in ats if a.kind == "text" and (a.text or "").strip()]
        imgs = [a for a in ats if a.kind == "image"]
        # source paragraphs (shape, para)
        paras = {}
        for a in txt:
            paras.setdefault((a.shape_id, a.para), []).append(a)
        para_wordcounts = [sum(len((x.text or "").split()) for x in g)
                           for g in paras.values()]
        short_labels = sum(1 for w in para_wordcounts if 0 < w <= 3)
        sizes = [a.size for a in txt if a.size]
        kinds = Counter(sh.kind for sh in slide.shapes)
        autoshape_fill = sum(1 for sh in slide.shapes
                             if getattr(sh, "is_autoshape", False) and sh.fill_rgb)
        # horizontal column bands among text shapes
        W = deck.width or 1
        centers = sorted((sh.left + sh.width / 2) / W for sh in slide.shapes
                         if sh.kind == "text" and sh.width)
        cols = 1
        for a, b in zip(centers, centers[1:]):
            if b - a > 0.18:
                cols += 1
        return {
            "n_text_paras": len(paras),
            "n_text_atoms": len(txt),
            "n_images": len(imgs),
            "n_short_labels": short_labels,
            "col_bands": cols,
            "has_pictures": bool(imgs),
            "has_connectors": kinds.get("connector", 0) > 0,
            "has_table": kinds.get("table", 0) > 0,
            "n_autoshape_fill": autoshape_fill,
            "max_size": max(sizes) if sizes else None,
            "min_size": min(sizes) if sizes else None,
        }
    except Exception:
        return {}


# --------------------------------------------------------------------------- #
# summary of a PLAN (the decision the engine made)
# --------------------------------------------------------------------------- #
def _diagram_mode(dg):
    if not dg:
        return None
    if getattr(dg, "vision_derived", False):
        return "vision-object"
    if getattr(dg, "prefer_crop", False):
        return "crop"
    if getattr(dg, "raster_fallback", False):
        return "raster"
    return "object"


def plan_summary(plan):
    try:
        roles = Counter(b.role for b in plan.blocks)
        grid = getattr(plan, "grid", None)
        return {
            "kind": plan.kind,
            "has_table": bool(plan.table),
            "has_columns": bool(plan.columns),
            "n_columns": len(plan.columns or []),
            "has_grid": bool(grid),
            "grid_cards": sum(1 for c in (grid.cells if grid else []) if c.box),
            "has_diagram": bool(plan.diagram),
            "diagram_mode": _diagram_mode(plan.diagram),
            "n_blocks": len(plan.blocks),
            "n_title": len(plan.title_ids),
            "n_subtitle": len(getattr(plan, "subtitle_ids", []) or []),
            "roles": dict(roles),
        }
    except Exception:
        return {}


# the decisions we care about matching when deciding to drop Claude
_KEYS = ("kind", "has_table", "has_columns", "has_grid", "has_diagram",
         "diagram_mode", "grid_cards", "n_subtitle")


def agreement(det, llm):
    out = {}
    for k in _KEYS:
        dv, lv = det.get(k), llm.get(k)
        # collapse counts to booleans for grid_cards / n_subtitle
        if k in ("grid_cards", "n_subtitle"):
            dv, lv = bool(dv), bool(lv)
        out[k] = (dv == lv)
    # role distribution agreement (same set of role types used)
    out["roles"] = set((det.get("roles") or {})) == set((llm.get("roles") or {}))
    out["_overall"] = all(out.values())
    return out


# --------------------------------------------------------------------------- #
# writers
# --------------------------------------------------------------------------- #
def _append(rec):
    if not enabled():
        return
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        with open(LOG_PATH, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        pass


def record_slide(source, index, sig, det_summary, llm_summary, used):
    """used: 'llm' or 'deterministic'. llm_summary may be None (Claude off/failed)."""
    rec = {
        "t": "slide",
        "ts": round(time.time(), 1),
        "source": os.path.basename(source or ""),
        "index": index,
        "sig": sig,
        "deterministic": det_summary,
        "llm": llm_summary,
        "used": used,
    }
    if llm_summary:
        rec["agree"] = agreement(det_summary, llm_summary)
    _append(rec)


def record_revision(source, index, tags, instruction):
    """A human correction -> the strongest learning signal."""
    _append({
        "t": "revision",
        "ts": round(time.time(), 1),
        "source": os.path.basename(source or ""),
        "index": index,
        "tags": list(tags or []),
        "instruction": (instruction or "")[:300],
    })
