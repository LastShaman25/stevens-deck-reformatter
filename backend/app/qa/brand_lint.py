"""Brand-lint verifier.

Re-opens a GENERATED .pptx and audits every slide against the locked Stevens
rules (brand.py) + the template theme: font family, text colors, red-bg->white
text, title presence, and geometry (overlap / off-slide / overflow via the
deterministic geometry checker). Produces a per-slide pass/warn/fail report that
drives the Quality panel and is the sign-off gate before download.

Runs fully offline (no rendering, no API).
"""
from __future__ import annotations

from pptx import Presentation
from pptx.util import Emu

from .. import brand as B
from . import geometry

# Text may be charcoal ink / black / white / Stevens Red. (None = inherit theme,
# which resolves to the on-brand dk1/accent colors, so it is allowed.)
_ALLOWED_TEXT = {c.upper() for c in B.ALLOWED_TEXT}
_RED = B.RED.upper()


def _rgb(color):
    """Return 'RRGGBB' for an explicit RGB color, else None (theme/inherited)."""
    try:
        if color is None or color.type is None:
            return None
        return str(color.rgb).upper()
    except Exception:
        return None


def _fill_rgb(shape):
    try:
        f = shape.fill
        if f.type is not None and f.fore_color and f.fore_color.type is not None:
            return str(f.fore_color.rgb).upper()
    except Exception:
        pass
    return None


def _runs(shape):
    if not shape.has_text_frame:
        return []
    return [r for p in shape.text_frame.paragraphs for r in p.runs]


def _audit_slide(slide, sw, slide_height, kind):
    from .style_audit import audit
    try:
        issues = audit(slide, sw, slide_height)
    except Exception as exc:
        issues = [{'sev': 'fail', 'type': 'checker_error', 'note': f'{type(exc).__name__}: {exc}'}]
    fails = sum(i['sev'] == 'fail' for i in issues)
    warns = sum(i['sev'] == 'warn' for i in issues)
    return {'status': 'fail' if fails else 'warn' if warns else 'pass',
            'fails': fails, 'warns': warns, 'issues': issues}


def lint(pptx_path, kinds=None):
    """Audit a generated deck. `kinds` optionally maps slide index -> kind
    (title/section/content/thankyou) so title checks apply only to content."""
    prs = Presentation(pptx_path)
    sw, sh = int(prs.slide_width), int(prs.slide_height)
    kinds = kinds or {}
    slides = []
    for i, slide in enumerate(prs.slides):
        res = _audit_slide(slide, sw, sh, kinds.get(i, "content"))
        res["index"] = i
        slides.append(res)

    total_fail = sum(s["fails"] for s in slides)
    total_warn = sum(s["warns"] for s in slides)
    passed = sum(1 for s in slides if s["status"] == "pass")
    return {
        "slides": slides,
        "n_slides": len(slides),
        "passed": passed,
        "warned": sum(1 for s in slides if s["status"] == "warn"),
        "failed": sum(1 for s in slides if s["status"] == "fail"),
        "total_fail": total_fail,
        "total_warn": total_warn,
        "clean": total_fail == 0,
    }
