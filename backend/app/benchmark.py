from __future__ import annotations

import json
import os
import shutil
import time
import uuid
from pathlib import Path
from threading import Lock
_CAPTURE_LOCK = Lock()

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_STORE = os.path.join(_BACKEND, "learning", "benchmarks")
_LOG = os.path.join(_BACKEND, "learning", "benchmarks.jsonl")


def _safe(name: str) -> str:
    keep = "-_.() "
    base = "".join(c for c in name if c.isalnum() or c in keep).strip()
    return (base or "deck")[:80]


def _mine(report):
    """Distill the build report into a compact, reusable pattern signature:
    which layout each slide used, and the aggregate layout histogram."""
    slides = (report or {}).get("slides", [])
    per_slide = [{"index": s.get("index"),
                  "layout": s.get("layout"),
                  "kind": s.get("kind")} for s in slides]
    hist = {}
    for s in per_slide:
        hist[s["layout"]] = hist.get(s["layout"], 0) + 1
    return {"layout_histogram": hist, "slides": per_slide}


def capture(sess, note: str = "", data=None):
    """Snapshot an approved deck + mine its patterns. Returns a summary dict."""
    from .generations import verify_identity
    verify_identity(sess, sess.generation)
    if data is None:
        data = Path(sess.generation['candidate']).read_bytes()
    import hashlib
    if hashlib.sha256(data).hexdigest() != sess.generation['candidate_sha256']:
        raise ValueError('ARTIFACT_CHANGED')
    # The session mutation lock serializes requests for a generation.
    if sess.generation.get('benchmark_capture'):
        return sess.generation['benchmark_capture']
    os.makedirs(_STORE, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    base = _safe(os.path.splitext(sess.original_name)[0])
    dest = os.path.join(_STORE, f"{stamp}-{uuid.uuid4().hex}-{base}.pptx")
    Path(dest).write_bytes(data)

    report = getattr(sess, "build_report", None) or {}
    record = {
        "ts": stamp,
        "generation_id": sess.generation["generation_id"],
        "candidate_sha256": sess.generation["candidate_sha256"],
        "source_name": sess.original_name,
        "deck": os.path.basename(dest),
        "slide_count": report.get("slide_count"),
        "llm_used": report.get("llm_used", False),
        "coverage_ok": (report.get("coverage") or {}).get("ok", False),
        "note": (note or "").strip(),
        "patterns": _mine(report),
    }
    with _CAPTURE_LOCK, open(_LOG, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record) + "\n")

    result = {"ok": True, "deck": record["deck"],
            "slide_count": record["slide_count"],
            "total_benchmarks": _count()}
    sess.generation['benchmark_capture'] = result
    from .generations import save
    save(sess.generation)
    return result


def _count() -> int:
    if not os.path.exists(_LOG):
        return 0
    try:
        with open(_LOG, encoding="utf-8") as fh:
            return sum(1 for line in fh if line.strip())
    except Exception:
        return 0


def stats():
    return {"total_benchmarks": _count(), "store": _STORE}
