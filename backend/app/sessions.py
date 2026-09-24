"""Ephemeral session store.

Each session is a temp directory holding the uploaded deck, the generated deck,
cached previews, and the cached analysis. Sessions are purged on delete and by a
TTL sweep, so nothing persists beyond use.
"""
from __future__ import annotations

import os
import shutil
import tempfile
import time
import uuid
from threading import Lock
from contextlib import contextmanager
from pathlib import Path

TTL_SECONDS = 60 * 60          # 1 hour
MAX_UPLOAD_BYTES = 60 * 1024 * 1024  # 60 MB

_ROOT = os.path.join(tempfile.gettempdir(), "stevens_slide_studio")
os.makedirs(_ROOT, exist_ok=True)

_lock = Lock()
_sessions = {}   # id -> Session


class Session:
    def __init__(self, sid, path):
        self.id = sid
        self.dir = path
        self.created = time.time()
        self.touched = self.created
        self.source_path = os.path.join(path, "source.pptx")
        self.source_pdf = os.path.join(path, "source.pdf")
        self.output_path = os.path.join(path, "stevens.pptx")
        self.previews_dir = os.path.join(path, "previews")
        os.makedirs(self.previews_dir, exist_ok=True)
        self.original_name = "presentation.pptx"
        self.analysis = None      # cached analyze() result
        self.build_report = None  # grounded.build_deck() report
        self.revisions = {}       # src_index -> {tags, instruction}
        self.ai_check = set()     # slide indices the reviewer opted into AI check
        self.ai_results = {}      # src_index -> list[issue dict] from last AI check
        self.lint_report = None   # brand_lint.lint() result for the built deck
        self.job_lock = Lock()
        self.active_jobs = 0
        self.revision_version = 0
        self.generation = None
        self.history = {}
        self.generated = False
        self.benchmarked = False  # reviewer approved this deck as a gold benchmark

    def touch(self):
        self.touched = time.time()

    def preview_path(self, index, variant):
        return os.path.join(self.previews_dir, f"{variant}-{index}.png")


def _sweep_locked():
    now = time.time()
    for sid, sess in list(_sessions.items()):
        if not sess.active_jobs and now - sess.touched > TTL_SECONDS:
            shutil.rmtree(sess.dir, ignore_errors=True)
            _sessions.pop(sid, None)


def create():
    with _lock:
        _sweep_locked()
        sid = uuid.uuid4().hex[:12]
        path = os.path.join(_ROOT, sid)
        os.makedirs(path, exist_ok=True)
        sess = Session(sid, path)
        _sessions[sid] = sess
        return sess


def get(sid):
    with _lock:
        sess = _sessions.get(sid)
        if sess and not sess.active_jobs and time.time() - sess.touched > TTL_SECONDS:
            shutil.rmtree(sess.dir, ignore_errors=True)
            _sessions.pop(sid, None)
            return None
        if sess:
            sess.touch()
        return sess


def delete(sid):
    with _lock:
        sess = _sessions.get(sid)
        if sess and sess.active_jobs:
            raise ValueError("Session has active work; try again when it completes.")
        sess = _sessions.pop(sid, None)
        if sess:
            shutil.rmtree(sess.dir, ignore_errors=True)
            return True
        return False


def sweep():
    with _lock:
        _sweep_locked()


@contextmanager
def job(sess):
    with _lock:
        if sess.id not in _sessions or not sess.job_lock.acquire(blocking=False):
            raise ValueError("Session is busy or expired.")
        sess.active_jobs += 1
    try:
        yield sess
    finally:
        with _lock:
            sess.active_jobs -= 1
            sess.touch()
            sess.job_lock.release()


def cleanup_orphans():
    with _lock:
        active = {s.dir for s in _sessions.values()}
        root = Path(_ROOT).resolve()
        for path in root.iterdir():
            if path.is_dir() and not path.is_symlink() and str(path) not in active:
                if path.resolve().parent == root and time.time() - path.stat().st_mtime > TTL_SECONDS:
                    shutil.rmtree(path, ignore_errors=True)


@contextmanager
def read_job(sess):
    """Pin immutable source/generation files without making parallel previews conflict."""
    with _lock:
        if sess.id not in _sessions:
            raise ValueError('Session expired.')
        sess.active_jobs += 1
    try:
        yield sess
    finally:
        with _lock:
            sess.active_jobs -= 1
            sess.touch()
