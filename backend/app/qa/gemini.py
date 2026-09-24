"""Gemini vision integration (canonical module used by backend + prototype).

Two roles, both optional and gated by GEMINI_API_KEY:

  1. read_diagram()  - OCR/understanding for image-embedded diagrams whose labels
     live inside the pixels (e.g. slide 18). Returns node labels + relative
     positions so the builder can reconstruct native objects. These labels are
     VISION-DERIVED (they do not exist as source atoms) and are always flagged
     for human confirmation next to the original image.

  2. review_slide()  - visual QA of a rebuilt slide against the locked Stevens
     rubric. Returns a JSON list of visible problems. Every claim it makes is
     later cross-checked against the coverage map, so a vision hallucination can
     never cause real content to be deleted.

Design guarantees:
  - No key / network error / bad JSON  -> degrades to a safe empty result, so
    generation is never blocked by the vision step.
  - temperature 0 + JSON response mime type for determinism.
  - The model is asked for STRUCTURE only; the zero-loss proof still lives in
    verify.py and is never delegated to the model.
"""
from __future__ import annotations

import base64
import json
import os

import requests

# --------------------------------------------------------------------------- #
# config + .env loading
# --------------------------------------------------------------------------- #
DEFAULT_MODEL = "gemini-3.1-flash-lite"
DEFAULT_ESCALATE_MODEL = "gemini-3.5-flash"    # stronger; used only for low-conf diagrams
DEFAULT_ESCALATE_CONF = 0.6

_ENDPOINT = ("https://generativelanguage.googleapis.com/v1beta/models/"
             "{model}:generateContent")

# backend/ dir = three parents up from this file (app/qa/gemini.py)
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_ENV_LOADED = False


def _load_env():
    """Minimal .env loader (no dependency). Reads backend/.env once and populates
    os.environ for any key not already set in the real environment."""
    global _ENV_LOADED
    if _ENV_LOADED:
        return
    _ENV_LOADED = True
    path = os.path.join(_BACKEND_DIR, ".env")
    if not os.path.exists(path):
        return
    try:
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, val = line.partition("=")
                key = key.strip()
                val = val.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = val
    except Exception:
        pass


def _key():
    from ..ai.providers import setting
    return setting('GEMINI_API_KEY')


def _model():
    from ..ai.providers import setting
    return setting('GEMINI_MODEL',DEFAULT_MODEL)


def _escalate_model():
    _load_env()
    return os.environ.get("GEMINI_ESCALATE_MODEL", DEFAULT_ESCALATE_MODEL)


def _escalate_conf():
    _load_env()
    try:
        return float(os.environ.get("GEMINI_ESCALATE_CONF", DEFAULT_ESCALATE_CONF))
    except Exception:
        return DEFAULT_ESCALATE_CONF


def available():
    from ..ai.providers import configured
    return configured('gemini')


def review_slide_result(png_path, context_text=''):
    """Explicit optional-check outcome. A provider failure is never clean."""
    if not available():
        return {'status': 'not_configured', 'findings': [], 'message': 'Optional AI check is not configured.'}
    if not os.path.isfile(png_path):
        return {'status': 'invalid_response', 'findings': [], 'message': 'A rendered slide is required.'}
    try:
        parts = [{'text': _REVIEW_RUBRIC + '\n' + context_text},
                 {'inline_data': {'mime_type': 'image/png', 'data': _b64(png_path)}}]
        response = requests.post(_ENDPOINT.format(model=_model()), headers={'x-goog-api-key':_key()},
            json={'contents': [{'parts': parts}], 'generationConfig': {
                'temperature': 0, 'response_mime_type': 'application/json'}}, timeout=90)
        response.raise_for_status()
        data = response.json()
        value = json.loads(data['candidates'][0]['content']['parts'][0]['text'])
        if not isinstance(value, list) or any(not isinstance(x, dict) or not isinstance(x.get('note'), str) for x in value):
            raise ValueError('Invalid finding schema')
        return {'status': 'completed', 'findings': value}
    except requests.Timeout:
        return {'status': 'timeout', 'findings': [], 'message': 'Optional AI check timed out.'}
    except requests.RequestException:
        return {'status': 'provider_error', 'findings': [], 'message': 'Optional AI provider request failed.'}
    except (ValueError, KeyError, IndexError, TypeError):
        return {'status': 'invalid_response', 'findings': [], 'message': 'Optional AI response could not be validated.'}


# --------------------------------------------------------------------------- #
# core call
# --------------------------------------------------------------------------- #
def _b64(path):
    with open(path, "rb") as fh:
        return base64.b64encode(fh.read()).decode("ascii")


def _generate(parts, model=None, timeout=90):
    """Low-level JSON call. Returns parsed JSON (dict/list) or None on any error."""
    key = _key()
    if not key:
        return None
    try:
        payload = {
            "contents": [{"parts": parts}],
            "generationConfig": {
                "temperature": 0,
                "response_mime_type": "application/json",
            },
        }
        url = _ENDPOINT.format(model=model or _model())
        resp = requests.post(url, headers={'x-goog-api-key':key}, json=payload, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
        text = data["candidates"][0]["content"]["parts"][0]["text"]
        return json.loads(text)
    except Exception:
        return None


# --------------------------------------------------------------------------- #
# role 1: diagram OCR -> reconstruction hints
# --------------------------------------------------------------------------- #
_DIAGRAM_PROMPT = (
    "You are reconstructing a diagram from an image into editable PowerPoint "
    "objects. Look ONLY at what is visible. Do not invent labels. "
    "Classify the diagram and return STRICT JSON with this schema:\n"
    '{"kind":"hub|matrix|cycle|pyramid|flow|generic",'
    '"confidence":0.0-1.0,'
    '"center":"<text of the central/anchor node or empty>",'
    '"nodes":[{"label":"<verbatim visible text>","x":0.0-1.0,"y":0.0-1.0,'
    '"emphasis":true|false}],'
    '"edges":[[from_node_index,to_node_index]]}.\n'
    "x,y are the node center as a fraction of the diagram box (0,0=top-left). "
    "emphasis=true only if the text is colored/bold/highlighted. "
    "If you cannot read it reliably, return confidence below 0.5."
)


def _parse_diagram(out):
    """Normalize + clamp a raw diagram JSON. Returns dict or None."""
    if not isinstance(out, dict) or "nodes" not in out:
        return None
    nodes = []
    for n in out.get("nodes", []):
        try:
            nodes.append({
                "label": str(n.get("label", "")).strip(),
                "x": max(0.0, min(1.0, float(n.get("x", 0.5)))),
                "y": max(0.0, min(1.0, float(n.get("y", 0.5)))),
                "emphasis": bool(n.get("emphasis", False)),
            })
        except Exception:
            continue
    nodes = [n for n in nodes if n["label"]]
    if not nodes:
        return None
    edges = []
    for e in out.get("edges", []):
        try:
            edges.append([int(e[0]), int(e[1])])
        except Exception:
            continue
    return {
        "kind": str(out.get("kind", "generic")),
        "confidence": float(out.get("confidence", 0.0) or 0.0),
        "center": str(out.get("center", "")).strip(),
        "nodes": nodes,
        "edges": edges,
    }


def read_diagram(png_path, context_text=""):
    """Read an image-embedded diagram. Returns a dict:
        {"kind","confidence","center","nodes":[...],"edges":[...],"model","escalated"}
    or None if disabled / unreadable. Caller must treat labels as VISION-DERIVED.

    Auto-escalation: reads with the primary (cheap) model first; if that is
    missing or LOW-confidence, retries the SAME diagram once with the stronger
    escalation model and keeps whichever is more confident. If the escalation
    model is unavailable (e.g. no billing -> 429), it silently keeps the primary
    result, so nothing crashes."""
    if not _key() or not os.path.exists(png_path):
        return None
    ctx = (f"Context (the slide title / nearby source text): {context_text}\n"
           if context_text else "")
    parts = [
        {"text": _DIAGRAM_PROMPT + "\n" + ctx},
        {"inline_data": {"mime_type": "image/png", "data": _b64(png_path)}},
    ]

    primary = _model()
    out = _parse_diagram(_generate(parts, model=primary))
    if out is not None:
        out["model"] = primary
        out["escalated"] = False

    strong = _escalate_model()
    need_escalation = (out is None or out["confidence"] < _escalate_conf())
    if need_escalation and strong and strong != primary:
        alt = _parse_diagram(_generate(parts, model=strong))
        if alt is not None and (out is None or alt["confidence"] >= out["confidence"]):
            alt["model"] = strong
            alt["escalated"] = True
            out = alt
    return out


# --------------------------------------------------------------------------- #
# role 2: visual QA of a rebuilt slide
# --------------------------------------------------------------------------- #
_REVIEW_RUBRIC = (
    "You are a Stevens Institute brand QA reviewer. Inspect this rebuilt slide "
    "image and report only REAL, VISIBLE problems as STRICT JSON: a list of "
    '{"type":"overlap|overflow|offpalette|contrast|misalign|missing|other",'
    '"severity":"low|med|high","note":"short specific description",'
    '"where":"short location e.g. \'top-right box\'"}.\n'
    "BRAND PALETTE (do NOT flag these as off-palette):\n"
    "- Approved colors are Stevens Red (#A32537), Stevens Blue / dark navy "
    "(#00427F), charcoal body text (#363D45), white, black, and light neutral "
    "grays.\n"
    "- Stevens Blue is EXPECTED for shape fills, bullet markers, table header "
    "backgrounds, and diagram ovals. Do not flag blue fills/bullets/headers.\n"
    "- 'offpalette' applies ONLY to text color and ONLY when text is some color "
    "OTHER than black, white, or Stevens Red (e.g. green, orange, purple text).\n"
    "OTHER LOCKED RULES:\n"
    "- A red-filled background MUST have white text (flag as contrast if not).\n"
    "- No text may overflow or leave its box; labels must fit inside their "
    "diagram; no shapes may overlap; font is Arial.\n"
    "Return [] if the slide is clean. Judge only what is visible; do not guess "
    "about content that might be missing unless a box/label is visibly cut off."
)


def review_slide(png_path, context_text=""):
    """Return list of issue dicts. Empty list if disabled or on any error."""
    if not _key() or not os.path.exists(png_path):
        return []
    ctx = (f"For reference, the intended text on this slide is: {context_text}\n"
           if context_text else "")
    parts = [
        {"text": _REVIEW_RUBRIC + "\n" + ctx},
        {"inline_data": {"mime_type": "image/png", "data": _b64(png_path)}},
    ]
    out = _generate(parts)
    return out if isinstance(out, list) else []


# --------------------------------------------------------------------------- #
# role 3: figure triage (Flash) - decorative vs diagram, and rebuildable?
# --------------------------------------------------------------------------- #
_CLASSIFY_PROMPT = (
    "You are triaging a FIGURE cropped from a slide, to decide how to reproduce "
    "it on a rebranded slide. Look ONLY at what is visible. Return STRICT JSON:\n"
    '{"kind":"decorative|diagram","rebuildable":true|false,'
    '"confidence":0.0-1.0,"note":"<=8 words"}.\n'
    "\nDEFINITIONS:\n"
    "- kind='decorative': a photo, clip-art, icon, stock illustration, logo, or "
    "ornamental image that carries NO structured information. It should simply be "
    "copied and placed as-is.\n"
    "- kind='diagram': a figure that conveys STRUCTURE or relationships "
    "(hierarchy, cycle, flow, matrix, hub-and-spoke, labeled parts, chart).\n"
    "\nrebuildable = true ONLY IF the diagram is made of plain boxes/ovals joined "
    "by arrows or lines with short text labels (flowchart, hub-and-spoke, cycle, "
    "org/tree, 2x2 matrix) AND its full meaning is captured by boxes+labels+"
    "arrows alone.\n"
    "rebuildable = false when meaning depends on geometry, proportion, artwork, "
    "or embedded pictures -- e.g. pyramids/funnels (band sizes matter), gauges, "
    "Venn diagrams, timelines drawn as art, bar/line/pie charts, figures whose "
    "LINE LENGTHS or shapes ARE the content, or anything containing photos/icons "
    "as part of the figure. When unsure, choose rebuildable=false.\n"
    "\nEXAMPLES:\n"
    "- Central oval with 4 arrows to outer text labels -> diagram, rebuildable=true.\n"
    "- A 5-band pyramid with tier names -> diagram, rebuildable=false.\n"
    "- Two boxes holding red line segments labeled X, A, B, C (a comparison "
    "figure) -> diagram, rebuildable=false (the line lengths are the content).\n"
    "- People clip-art huddling -> decorative.\n"
)


def classify_figure(png_path, context_text=""):
    """Triage one figure crop. Returns dict
        {"kind","rebuildable","confidence","note","model"}
    or None if disabled / unreadable. Uses the cheap primary (Flash) model; the
    caller biases ties toward place/crop, so a low-confidence read never triggers
    a risky rebuild."""
    if not _key() or not os.path.exists(png_path):
        return None
    ctx = (f"Context (slide title / nearby text): {context_text}\n"
           if context_text else "")
    parts = [
        {"text": _CLASSIFY_PROMPT + "\n" + ctx},
        {"inline_data": {"mime_type": "image/png", "data": _b64(png_path)}},
    ]
    out = _generate(parts, model=_model())
    if not isinstance(out, dict):
        return None
    kind = str(out.get("kind", "diagram")).lower()
    kind = "decorative" if kind.startswith("dec") else "diagram"
    try:
        conf = float(out.get("confidence", 0.0) or 0.0)
    except Exception:
        conf = 0.0
    return {
        "kind": kind,
        "rebuildable": bool(out.get("rebuildable", False)) and kind == "diagram",
        "confidence": max(0.0, min(1.0, conf)),
        "note": str(out.get("note", ""))[:80],
        "model": _model(),
    }


# --------------------------------------------------------------------------- #
# role 4: verify a rebuilt figure against the original (Flash)
# --------------------------------------------------------------------------- #
_VERIFY_PROMPT = (
    "Two images: IMAGE 1 is the ORIGINAL figure; IMAGE 2 is a REBUILT version. "
    "Judge whether the rebuilt version faithfully preserves the original's "
    "meaning: same labels/text, same structure and relationships (arrows/order/"
    "grouping), nothing important missing, added, distorted, overlapping, or cut "
    "off. Ignore pure styling changes (colors, fonts, box outlines) -- those are "
    "intentional rebranding. Return STRICT JSON: "
    '{"faithful":true|false,"confidence":0.0-1.0,"issues":["short",...]}.'
)


def verify_rebuild(original_png, rebuilt_png):
    """Compare a rebuilt figure/slide against the original. Returns dict
        {"faithful","confidence","issues"} or None if disabled/unreadable.
    On None (disabled), the caller should keep the rebuild only if it also
    passed classification -- i.e. treat 'no verifier' as 'do not block'."""
    if not _key() or not os.path.exists(original_png) or not os.path.exists(rebuilt_png):
        return None
    parts = [
        {"text": _VERIFY_PROMPT},
        {"text": "IMAGE 1 (original):"},
        {"inline_data": {"mime_type": "image/png", "data": _b64(original_png)}},
        {"text": "IMAGE 2 (rebuilt):"},
        {"inline_data": {"mime_type": "image/png", "data": _b64(rebuilt_png)}},
    ]
    out = _generate(parts, model=_model())
    if not isinstance(out, dict):
        return None
    try:
        conf = float(out.get("confidence", 0.0) or 0.0)
    except Exception:
        conf = 0.0
    issues = out.get("issues", [])
    return {
        "faithful": bool(out.get("faithful", False)),
        "confidence": max(0.0, min(1.0, conf)),
        "issues": [str(x)[:120] for x in issues] if isinstance(issues, list) else [],
    }
