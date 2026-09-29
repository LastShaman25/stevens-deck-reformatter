"""Grounded full-deck builder for the Studio app.

Wires the slide engine's analysis pipeline into the product:
  IR extract -> deterministic grounded plan -> (optional) Gemini vision augment
  for image-embedded diagrams -> bijective coverage proof -> native rebuild of
  EVERY slide (title/thankyou/content/table/columns/diagram/body) onto the
  Stevens template -> deterministic auto-fix loop per slide.

Content integrity: the plan references source atoms by id only, so nothing is
invented or dropped; verify.coverage() proves it. Vision-derived diagram labels
are the only text not from the source, and they are flagged for confirmation.
"""
from __future__ import annotations

import os
import sys

from pptx import Presentation
from pptx.util import Pt
from pptx.dml.color import RGBColor

_APP = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_APP)
_ROOT = os.path.dirname(_BACKEND)
for p in (_BACKEND, _ROOT):
    if p not in sys.path:
        sys.path.insert(0, p)

from . import brand
from .qa import gemini
from .qa import claude
from slide_engine import ir, planner, verify, build, autofix, llm_planner, learning   # noqa: E402


def _plan_deck(deck, use_llm=True, source=""):
    """Plan every slide. When Claude is available and use_llm, use the LLM
    planner (understands layout intent) and fall back to the deterministic plan
    for any slide whose LLM plan fails the coverage guardrail or errors out.

    Every slide's decision (deterministic vs Claude, and which was used) is
    logged to the learning loop so the deterministic engine can be tuned toward
    Claude and eventually replace it."""
    det = planner.plan_deterministic(deck)
    if not (use_llm and claude.available()):
        for slide, dplan in zip(deck.slides, det):
            try:
                learning.record_slide(source, slide.index,
                                      learning.signature(deck, slide),
                                      learning.plan_summary(dplan), None,
                                      "deterministic")
            except Exception:
                pass
        return det, [False] * len(det)
    out, used = [], []
    for slide, dplan in zip(deck.slides, det):
        lp = None
        try:
            lp = llm_planner.plan_slide_llm(deck, slide)
        except Exception:
            lp = None
        chosen = lp if lp is not None else dplan
        out.append(chosen)
        used.append(lp is not None)
        try:
            learning.record_slide(
                source, slide.index, learning.signature(deck, slide),
                learning.plan_summary(dplan),
                learning.plan_summary(lp) if lp is not None else None,
                "llm" if lp is not None else "deterministic")
        except Exception:
            pass
    return out, used

TEMPLATE_PATH = os.path.join(_BACKEND, "assets", "ppt_template.pptx")
EMU = brand.EMU_PER_INCH


def _C(hex6):
    return RGBColor.from_string(hex6)


def _clean(t):
    return (t or "").replace("\x0b", " ").replace("\n", " ").strip()


def _title_text(deck, plan):
    return " ".join(_clean(deck.atoms[i].text) for i in plan.title_ids
                    if i in deck.atoms).strip()


def _body_atoms(deck, plan):
    return [deck.atoms[b.atom_id] for b in plan.blocks if b.atom_id in deck.atoms]


# --------------------------------------------------------------------------- #
# title / thank-you slides (template-native layouts)
# --------------------------------------------------------------------------- #
def _set_ph_text(ph, text, size, bold=False, color=brand.BLACK):
    ph.text_frame.clear()
    r = ph.text_frame.paragraphs[0].add_run()
    r.text = _clean(text)
    r.font.name = brand.FONT
    r.font.size = Pt(size)
    r.font.bold = bold
    try:
        r.font.color.rgb = _C(color)
    except Exception:
        pass


def build_title_slide(prs, deck, plan):
    # The template title cover is a RED panel -> all text on it must be WHITE.
    slide = prs.slides.add_slide(build.layout(prs, brand.L_TITLE))
    body = _body_atoms(deck, plan)
    title = _title_text(deck, plan) or (_clean(body[0].text) if body else "Presentation")
    subtitle = " ".join(_clean(deck.atoms[i].text) for i in plan.subtitle_ids
                        if i in deck.atoms).strip()
    if not subtitle:
        subtitle = _clean(body[0].text) if body else ""
    if slide.shapes.title is not None:
        _set_ph_text(slide.shapes.title, title, brand.TITLE_SECTION_PT,
                     bold=True, color=brand.WHITE)
    for ph in slide.placeholders:
        if ph.placeholder_format.idx == 1 and subtitle:
            _set_ph_text(ph, subtitle, brand.SUBTITLE_PT, color=brand.WHITE)
    return slide


def build_thankyou_slide(prs, deck, plan):
    slide = prs.slides.add_slide(build.layout(prs, brand.L_THANKYOU))
    title = _title_text(deck, plan) or "Thank you!"
    if slide.shapes.title is not None:
        _set_ph_text(slide.shapes.title, title, brand.TITLE_SECTION_PT,
                     bold=True, color=brand.WHITE)
    return slide


# --------------------------------------------------------------------------- #
# per-slide dispatch (mirrors slide_engine.build.build_demo, for ALL slides)
# --------------------------------------------------------------------------- #
def _build_content(prs, deck, plan, sw, sh, orig_pdf):
    # No title in the source -> leave the title area blank rather than printing
    # a literal "(untitled)".
    title_text = _title_text(deck, plan) or ""
    slide = build.title_only(prs, title_text)
    dg = plan.diagram
    if plan.grid:
        build.build_grid(slide, deck, plan, sw, sh)
    elif plan.table:
        build.build_table(slide, deck, plan, sw, sh)
    elif dg and getattr(dg, "prefer_crop", False):
        # prefer_crop wins over every rebuild path: this is set for spatial-label
        # diagrams AND for any rebuild the verifier judged unfaithful -> preserve
        # the exact original as a crop so nothing is rearranged/hallucinated.
        build.build_diagram(slide, deck, plan, sw, sh, orig_pdf, plan.index)
    elif dg and dg.vision_derived and not dg.raster_fallback:
        # editable object reconstruction (Pro-read labels), gated by the verifier
        build.build_vision_diagram(slide, deck, plan, sw, sh)
    elif dg:
        # faithful, Stevens-branded native rebuild (keeps exact structure); fall
        # back to an exact crop only if the shapes can't be reconstructed.
        try:
            build.build_diagram_native(slide, deck, plan, sw, sh)
        except Exception:
            build.build_diagram(slide, deck, plan, sw, sh, orig_pdf, plan.index)
    elif plan.columns:
        build.build_columns(slide, deck, plan, sw, sh)
    else:
        build.build_body(slide, deck, plan, sw, sh)
    return slide


def _layout_label(plan):
    if plan.kind == "title":
        return "Title slide"
    if plan.kind == "thankyou":
        return "Closing slide"
    if plan.grid:
        return "Structured layout"
    if plan.table:
        return "Native table"
    if plan.diagram:
        return f"Diagram ({plan.diagram.kind})"
    if plan.columns:
        return "Two-column layout"
    return "Content slide"


def _rationale(deck, plan):
    if plan.kind == "title":
        return "Opening slide -> Stevens title layout; deck title and subtitle placed in the branded cover."
    if plan.kind == "thankyou":
        return "Closing slide -> Stevens Thank You layout."
    if plan.table:
        return "Detected a tabular block -> rebuilt as a native Stevens table (red header row, black body text)."
    if plan.diagram:
        dg = plan.diagram
        if dg.vision_derived:
            return f"Image-embedded {dg.kind} diagram -> reconstructed as editable Stevens objects (labels read by Gemini vision)."
        if dg.raster_fallback:
            return f"Complex {dg.kind} visual -> preserved as a clean image, fitted under the title so nothing bleeds off-page."
        return f"{dg.kind.title()} diagram -> rebuilt with native shapes and Stevens Red connectors."
    if plan.columns:
        return "Balanced content -> two-column layout to reduce density and white space."
    n = len(plan.blocks)
    if n >= brand.SPLIT_BULLET_CAP:
        return "Dense content -> square/arrow/dash hierarchy with sizes tuned to fit on one clean slide."
    return "Standard content -> Stevens title (black) with square/arrow/dash bullets; emphasis words in Stevens Red."


def _issues(plan):
    out = []
    if plan.diagram and plan.diagram.vision_derived:
        out.append("diagram reconstructed")
    if plan.diagram and plan.diagram.raster_fallback:
        out.append("diagram preserved as image")
    if plan.table:
        out.append("table rebuilt")
    if len(plan.blocks) >= brand.SPLIT_BULLET_CAP:
        out.append("dense")
    return out


def analyze(src_path):
    """Per-slide plan for the Review UI, from the SAME engine that builds the
    deck (so titles / kinds / rationale match the output 1:1 by index)."""
    deck = ir.extract(src_path)
    plans = planner.plan_deterministic(deck)
    slides = []
    for plan in plans:
        body = _body_atoms(deck, plan)
        title = _title_text(deck, plan) or (_clean(body[0].text) if body else "(untitled)")
        n_img = len(plan.images) + (len(plan.diagram.source_image_ids)
                                    if plan.diagram else 0)
        slides.append({
            "index": plan.index,
            "title": title[:120],
            "kind": plan.kind,
            "layout": _layout_label(plan),
            "rationale": _rationale(deck, plan),
            "issues": _issues(plan),
            "n_body": len(plan.blocks),
            "n_images": n_img,
            "needs_review": bool(
                (plan.diagram and plan.diagram.vision_derived) or plan.table),
        })
    return {"slide_count": len(plans), "slides": slides}


def hints_from_revision(rev):
    """Map reviewer tags to deterministic build hints.

    - Fix diagram        -> force a vision reconstruction attempt for the slide
    - Overlap/Layout/Dense -> run extra auto-fix (reflow) passes
    The free-text instruction is stored for the record but not applied blindly.
    """
    tags = set((rev or {}).get("tags") or [])
    return {
        "force_vision": "diagram" in tags,
        "reflow": bool(tags & {"overlap", "layout", "dense"}),
    }


def _fix_slide(slide, plan, sw_emu, sh_emu, iters):
    """Native diagrams have intentional geometry -> only clamp+palette (never
    spread/relax, which would wreck the layout). Everything else: full autofix."""
    if plan.grid or (plan.diagram and not plan.diagram.vision_derived):
        applied = (autofix.enforce_palette(slide)
                   + autofix.clamp_in_page(slide, sw_emu, sh_emu))
        return applied, []
    return autofix.autofix_slide(slide, sw_emu, sh_emu, max_iter=iters)


def _build_plan_slide(prs, deck, plan, sw, sh, orig_pdf):
    if plan.kind == "title":
        return build_title_slide(prs, deck, plan)
    if plan.kind == "thankyou":
        return build_thankyou_slide(prs, deck, plan)
    return _build_content(prs, deck, plan, sw, sh, orig_pdf)


def build_one(src_path, index, out_pptx, template_path=TEMPLATE_PATH,
              orig_pdf=None, revision=None, use_vision=True):
    """Rebuild a SINGLE source slide (for the interactive "Apply changes"
    button) honoring the reviewer's tags. Returns a small report dict."""
    hints = hints_from_revision(revision)
    deck = ir.extract(src_path)
    plans = planner.plan_deterministic(deck)
    plan = next((p for p in plans if p.index == index), None)
    if plan is None:
        raise ValueError(f"slide {index} not found")

    reconstructed = False
    if (use_vision and hints["force_vision"] and gemini.available()
            and orig_pdf and os.path.exists(orig_pdf)):
        reconstructed = bool(planner.augment_with_vision(deck, [plan], orig_pdf))

    prs = Presentation(template_path)
    sw, sh = prs.slide_width / EMU, prs.slide_height / EMU
    sw_emu, sh_emu = int(prs.slide_width), int(prs.slide_height)
    build.clear_slides(prs)
    slide = _build_plan_slide(prs, deck, plan, sw, sh, orig_pdf)
    iters = 6 if hints["reflow"] else 3
    applied, remaining = _fix_slide(slide, plan, sw_emu, sh_emu, iters)
    prs.save(out_pptx)

    # Is this slide's main figure a PRESERVED image (exact crop)? If so, tags
    # can't repaint what's baked into that image -- surface that clearly.
    dg = plan.diagram
    preserved_diagram = bool(
        dg and not getattr(dg, "vision_derived", False)
        and (getattr(dg, "prefer_crop", False)
             or getattr(dg, "raster_fallback", False)
             or getattr(dg, "kind", "") == "preserve"))
    changed = bool(applied or reconstructed)

    if reconstructed:
        summary = "Rebuilt the diagram as native Stevens shapes."
    elif applied:
        summary = "Applied: " + "; ".join(applied) + "."
    elif preserved_diagram:
        summary = ("No change: this slide's diagram is a preserved image, so tags "
                   "can't repaint what's inside it. Use \"Fix diagram\" to attempt "
                   "a native rebuild, or edit it in PowerPoint after download.")
    else:
        summary = "No layout changes were needed on this slide."

    return {
        "index": index,
        "kind": plan.kind,
        "applied": applied,
        "reconstructed": reconstructed,
        "preserved_diagram": preserved_diagram,
        "changed": changed,
        "summary": summary,
        "hard_issues": sum(1 for i in remaining
                           if i.get("type") in ("overlap", "offslide")),
    }


def _crop_pdf_region(pdf, page_i, bbox_emu, out_png, dpi=150):
    """Crop a region (EMU) out of a rendered PDF page to a PNG. Returns True on
    success. Used to hand a figure to the Flash classifier / verifier."""
    import fitz
    try:
        doc = fitz.open(pdf)
        if page_i >= doc.page_count:
            doc.close(); return False
        l, t, w, h = bbox_emu
        z = dpi / 72.0
        clip = fitz.Rect(l / EMU * 72, t / EMU * 72,
                         (l + w) / EMU * 72, (t + h) / EMU * 72)
        doc.load_page(page_i).get_pixmap(matrix=fitz.Matrix(z, z),
                                         clip=clip).save(out_png)
        doc.close()
        return os.path.exists(out_png)
    except Exception:
        return False


# Confidence needed before we trust Flash enough to REBUILD (ties break to crop).
_REBUILD_CONF = 0.55


def _triage_figures(deck, plans, orig_pdf):
    """Flash figure triage (the place / crop / rebuild router).

    For every planned diagram we crop the ORIGINAL figure and ask Flash: is this
    decorative or a diagram, and is it cleanly rebuildable? Anything that is not
    a confidently rebuildable box/arrow diagram is forced to an EXACT crop
    (prefer_crop=True) -- this is what stops figures like the Asch line-length
    chart from being mangled into boxes. Decorative/placed images are untouched
    (build_body already positions them faithfully). Returns triage records."""
    import tempfile
    recs = []
    tmpdir = tempfile.mkdtemp(prefix="fig_")
    for plan in plans:
        dg = plan.diagram
        if not dg or dg.vision_derived or not dg.bbox:
            continue
        # spatial-label crops are already preserved; record and move on
        if getattr(dg, "prefer_crop", False):
            recs.append({"index": plan.index, "decision": "crop",
                         "reason": "spatial-label", "kind": "diagram"})
            continue
        png = os.path.join(tmpdir, f"s{plan.index}.png")
        if not _crop_pdf_region(orig_pdf, plan.index, dg.bbox, png):
            continue
        ctx = _title_text(deck, plan) or ""
        c = gemini.classify_figure(png, ctx)
        if c is None:                      # verifier/classifier disabled -> don't block
            recs.append({"index": plan.index, "decision": "rebuild",
                         "reason": "no-classifier"})
            continue
        rebuild = (c["kind"] == "diagram" and c["rebuildable"]
                   and c["confidence"] >= _REBUILD_CONF)
        if not rebuild:
            dg.prefer_crop = True          # place/crop the exact original
        recs.append({"index": plan.index,
                     "decision": "rebuild" if rebuild else "crop",
                     "kind": c["kind"], "rebuildable": c["rebuildable"],
                     "confidence": round(c["confidence"], 2),
                     "note": c.get("note", "")})
    return recs


def _verify_rebuilds(deck, plans, out_path, orig_pdf, triage):
    """Render the freshly built deck and, for each diagram we REBUILT as objects,
    compare it against the original figure with Flash. Any rebuild judged NOT
    faithful is downgraded to an exact crop. Returns (changed, records)."""
    rebuilt = [t["index"] for t in triage if t.get("decision") == "rebuild"]
    rebuilt = [i for i in rebuilt
               if any(p.index == i and p.diagram
                      and not getattr(p.diagram, "prefer_crop", False)
                      for p in plans)]
    if not rebuilt:
        return False, []
    import tempfile
    from . import rendering
    tmp = tempfile.mkdtemp(prefix="verify_")
    new_pdf = os.path.join(tmp, "out.pdf")
    try:
        rendering.render_to_pdf(out_path, new_pdf)
    except Exception:
        return False, []
    changed, recs = False, []
    for plan in plans:
        if plan.index not in rebuilt:
            continue
        dg = plan.diagram
        orig_png = os.path.join(tmp, f"orig_{plan.index}.png")
        new_png = os.path.join(tmp, f"new_{plan.index}.png")
        if not (_crop_pdf_region(orig_pdf, plan.index, dg.bbox, orig_png)
                and _crop_pdf_region(new_pdf, plan.index, dg.bbox, new_png)):
            continue
        v = gemini.verify_rebuild(orig_png, new_png)
        if v is None:
            continue
        rec = {"index": plan.index, "faithful": v["faithful"],
               "confidence": round(v["confidence"], 2), "issues": v["issues"]}
        if not v["faithful"]:
            dg.prefer_crop = True          # revert this one to an exact crop
            changed = True
            rec["action"] = "downgraded-to-crop"
        recs.append(rec)
    return changed, recs


def _legacy_build_deck(src_path, out_path, template_path=TEMPLATE_PATH,
               orig_pdf=None, use_vision=True, revisions=None, use_llm=True):
    """Build the full Stevens deck from a source .pptx. Returns a report dict.
    `revisions` maps a source slide index -> {tags, instruction} and is honored
    via deterministic hints (extra reflow passes, forced diagram reconstruction).
    When `use_llm` and Claude is configured, the LLM planner arranges each slide
    (coverage-verified); slides where it fails fall back to deterministic rules.
    """
    revisions = {int(k): v for k, v in (revisions or {}).items()}
    deck = ir.extract(src_path)
    plans, llm_used = _plan_deck(deck, use_llm=use_llm, source=src_path)

    vision_used = bool(use_vision and gemini.available()
                       and orig_pdf and os.path.exists(orig_pdf))
    upgraded = []
    if vision_used:
        # Fidelity-first: only REBUILD a diagram into editable objects when the
        # reviewer explicitly tagged that slide "Fix diagram". Otherwise the
        # original diagram is preserved exactly (no meaning drift).
        fix_idx = {i for i, r in revisions.items()
                   if "diagram" in set((r or {}).get("tags") or [])}
        targets = [p for p in plans if p.index in fix_idx and p.diagram]
        if targets:
            upgraded = planner.augment_with_vision(deck, targets, orig_pdf)

    # Figure triage (place / crop / rebuild router). Forces an exact crop for any
    # figure that is decorative or not a confidently rebuildable box/arrow
    # diagram -- the core cure for "graphics mixed with text get hallucinated".
    triage = []
    if vision_used:
        triage = _triage_figures(deck, plans, orig_pdf)
        # "If rebuild -> Pro": for figures Flash judged cleanly rebuildable, read
        # them with the stronger model and reconstruct as editable objects. The
        # verify pass below downgrades any that don't come out faithful.
        rb = {t["index"] for t in triage if t.get("decision") == "rebuild"}
        rb_targets = [p for p in plans if p.index in rb and p.diagram
                      and not getattr(p.diagram, "prefer_crop", False)]
        if rb_targets:
            planner.augment_with_vision(deck, rb_targets, orig_pdf)

    cov = verify.coverage(deck, plans)

    sw = sh = sw_emu = sh_emu = None

    def _assemble():
        nonlocal sw, sh, sw_emu, sh_emu
        prs = Presentation(template_path)
        sw, sh = prs.slide_width / EMU, prs.slide_height / EMU
        sw_emu, sh_emu = int(prs.slide_width), int(prs.slide_height)
        build.clear_slides(prs)
        fixlog, slide_reports = [], []
        for plan in plans:
            slide = _build_plan_slide(prs, deck, plan, sw, sh, orig_pdf)
            hints = hints_from_revision(revisions.get(plan.index))
            iters = 6 if hints["reflow"] else 3
            applied, remaining = _fix_slide(slide, plan, sw_emu, sh_emu, iters)
            fixlog.append({"index": plan.index, "applied": applied,
                           "remaining": remaining})
            hard = sum(1 for i in remaining if i.get("type") in ("overlap", "offslide"))
            soft = sum(1 for i in remaining if i.get("type") == "overflow")
            dg = plan.diagram
            slide_reports.append({
                "index": plan.index,
                "kind": plan.kind,
                "has_table": bool(plan.table),
                "has_columns": bool(plan.columns),
                "hard_issues": hard,
                "soft_issues": soft,
                "diagram": (None if not dg else {
                    "kind": dg.kind,
                    "mode": ("vision-object" if dg.vision_derived else
                             "crop" if getattr(dg, "prefer_crop", False) else
                             "raster" if dg.raster_fallback else "object"),
                    "escalated": bool(getattr(dg, "escalated", False)),
                    "model": getattr(dg, "model", ""),
                }),
                "vision_derived": bool(dg and dg.vision_derived),
                "auto_fixes": applied,
                "geometry_clean": not remaining,
            })
        prs.save(out_path)
        return fixlog, slide_reports

    fixlog, slide_reports = _assemble()

    # Verify rebuilt diagrams against the originals; downgrade any unfaithful
    # rebuild to an exact crop and re-assemble once.
    verify_recs = []
    if vision_used and triage:
        changed, verify_recs = _verify_rebuilds(deck, plans, out_path, orig_pdf, triage)
        if changed:
            fixlog, slide_reports = _assemble()

    return {
        "source": src_path,
        "output": out_path,
        "slide_count": len(plans),
        "coverage": {
            "source": cov.source, "placed": cov.placed,
            "lost": len(cov.lost), "invented": len(cov.invented),
            "duplicated": len(cov.duplicated), "ok": cov.ok,
        },
        "vision_used": vision_used,
        "llm_used": bool(claude.available() and use_llm),
        "llm_slides": sum(1 for u in llm_used if u),
        "diagrams_reconstructed": [i + 1 for i in upgraded],
        "figure_triage": triage,
        "figure_verify": verify_recs,
        "slides": slide_reports,
        "fixlog": fixlog,
    }


def build_deck(src_path, out_path, template_path=TEMPLATE_PATH,
               orig_pdf=None, use_vision=False, revisions=None, use_llm=False,source_decisions=None,require_closing=False):
    """Build an explicitly inventoried native candidate; release requires QA."""
    from slide_engine.preserve import build as preserve_build
    from slide_engine.repair import repair
    report = preserve_build(src_path, out_path, template_path, revisions,source_decisions)
    report=repair(src_path, out_path, report)
    if require_closing:
        from slide_engine.bookends import ensure
        report=ensure(out_path,report)
    return report
