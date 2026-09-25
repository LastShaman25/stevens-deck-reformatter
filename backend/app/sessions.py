"""Owned, bounded processing workspaces with observable, retried cleanup."""
import json
import os
import shutil
import stat
import tempfile
import time
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from threading import Lock

TTL_SECONDS = 3600
ABSOLUTE_SECONDS = 4 * 3600
MAX_UPLOAD_BYTES = 60 * 1024 * 1024
_ROOT = os.environ.get('STEVENS_WORKSPACE_ROOT', os.path.join(tempfile.gettempdir(), 'stevens_slide_studio'))
os.makedirs(_ROOT, exist_ok=True)
_lock = Lock()
_sessions = {}
active_session = ContextVar('active_processing_session', default=None)


class Session:
    def __init__(self, sid, path):
        from .auth import current_user
        user = current_user.get() or {}
        self.owner_user_id, self.login_id = user.get('id'), user.get('token')
        self.id, self.dir = sid, path
        self.created = self.touched = time.time()
        self.expires = self.created + ABSOLUTE_SECONDS
        self.close_after = None
        self.execution_deadline = None
        self.lifecycle = 'active'
        self.source_path = os.path.join(path, 'source.pptx')
        self.source_pdf = os.path.join(path, 'source.pdf')
        self.output_path = os.path.join(path, 'stevens.pptx')
        self.previews_dir = os.path.join(path, 'previews')
        os.makedirs(self.previews_dir, exist_ok=True)
        self.original_name = 'presentation.pptx'
        self.analysis = self.build_report = self.lint_report = self.generation = None
        self.revisions, self.ai_results, self.history = {}, {}, {}
        self.ai_check = set()
        self.job_lock = Lock()
        self.active_jobs = self.revision_version = self.calls = self.tokens = 0
        self.generated = self.benchmarked = False
        self.workflow = 'preserve'
        self.creation = None
        self.progress = {'stage': 'created'}
        self.persist_lifecycle()

    def persist_lifecycle(self):
        if Path(self.dir).is_dir():
            Path(self.dir, 'lifecycle.json').write_text(json.dumps({'expires': self.expires,
                'touched': self.touched, 'lifecycle': self.lifecycle, 'pid':os.getpid()}), encoding='utf-8')

    def ensure_active(self):
        if self.lifecycle != 'active' or time.time() >= self.expires or (self.execution_deadline and time.time() >= self.execution_deadline):
            raise ValueError('Job closed or expired.')

    def touch(self):
        self.touched = time.time()
        self.persist_lifecycle()

    def preview_path(self, index, variant):
        return os.path.join(self.previews_dir, f'{variant}-{index}.png')


def _purge(sess):
    root, path = Path(_ROOT).resolve(), Path(sess.dir).resolve()
    if path.parent != root or path == root or Path(sess.dir).is_symlink():
        raise ValueError('Unsafe workspace path.')
    sess.lifecycle = 'purging'
    try:
        if path.exists():
            remove_tree(path)
        if path.exists():
            raise OSError('Workspace remains')
    except OSError:
        sess.lifecycle = 'purge_failed'
        sess.persist_lifecycle()
        return False
    sess.lifecycle = 'purged'
    _sessions.pop(sess.id, None)
    return True


def remove_tree(path):
    """Retry read-only Windows artifacts without traversing outside this workspace."""
    root = Path(path).resolve()
    def retry(function, filename, exc):
        target = Path(filename).resolve()
        if not isinstance(exc, PermissionError) or not (target==root or target.is_relative_to(root)):
            raise exc
        os.chmod(filename, stat.S_IREAD | stat.S_IWRITE)
        function(filename)
    shutil.rmtree(path, onexc=retry)


def _sweep_locked():
    now = time.time()
    for sess in list(_sessions.values()):
        if now >= sess.expires or (not sess.active_jobs and now-sess.touched > TTL_SECONDS) or (sess.close_after and now >= sess.close_after):
            sess.lifecycle = 'closing'
        if sess.lifecycle != 'active' and not sess.active_jobs:
            _purge(sess)


def create():
    from .auth import current_user
    with _lock:
        _sweep_locked()
        owner = (current_user.get() or {}).get('id')
        if owner and sum(s.owner_user_id == owner for s in _sessions.values()) >= 3:
            raise ValueError('Finish or cancel an existing job first (maximum three).')
        sid = uuid.uuid4().hex
        path = os.path.join(_ROOT, sid)
        os.makedirs(path)
        sess = Session(sid, path)
        _sessions[sid] = sess
        return sess


def get(sid):
    with _lock:
        _sweep_locked()
        sess = _sessions.get(sid)
        return sess if sess and sess.lifecycle == 'active' else None


def delete(sid):
    with _lock:
        sess = _sessions.get(sid)
        if not sess:
            return True
        sess.lifecycle = 'closing'
        sess.persist_lifecycle()
        return _purge(sess) if not sess.active_jobs else False


def cancel_owner(uid, login_id=None):
    for sess in list(_sessions.values()):
        if sess.owner_user_id == uid and (login_id is None or sess.login_id == login_id):
            delete(sess.id)


def sweep():
    with _lock:
        _sweep_locked()


@contextmanager
def job(sess):
    with _lock:
        sess.ensure_active()
        if sess.id not in _sessions or not sess.job_lock.acquire(blocking=False):
            raise ValueError('Session is busy or expired.')
        sess.active_jobs += 1
        try:
            sess.touch()
        except OSError:
            sess.active_jobs -= 1
            sess.job_lock.release()
            raise
        sess.execution_deadline = time.time()+2700
    token = active_session.set(sess)
    try:
        yield sess
    finally:
        active_session.reset(token)
        with _lock:
            sess.active_jobs -= 1
            sess.job_lock.release()
            sess.execution_deadline = None
            if sess.lifecycle != 'active' and not sess.active_jobs:
                _purge(sess)


@contextmanager
def read_job(sess):
    with _lock:
        sess.ensure_active()
        if sess.id not in _sessions:
            raise ValueError('Session expired.')
        sess.active_jobs += 1
    try:
        yield sess
    finally:
        with _lock:
            sess.active_jobs -= 1
            if sess.lifecycle != 'active' and not sess.active_jobs:
                _purge(sess)


def cleanup_orphans(startup=False):
    with _lock:
        active = {s.dir for s in _sessions.values()}
        root = Path(_ROOT).resolve()
        for path in root.iterdir():
            if path.is_dir() and not path.is_symlink() and str(path) not in active and path.resolve().parent == root:
                try:
                    meta = json.loads((path/'lifecycle.json').read_text())
                except (OSError, ValueError):
                    meta = {}
                if meta.get('pid') and _process_alive(meta['pid']) and meta['pid'] != os.getpid():
                    continue  # Another live verifier/server owns the lease; never delete its inputs.
                expired = time.time() >= meta.get('expires', path.stat().st_mtime+TTL_SECONDS)
                if startup or expired or meta.get('lifecycle', 'active') != 'active':
                    try:
                        remove_tree(path)
                    except OSError:
                        # Remains discoverable for retry; never report purged.
                        pass


def _process_alive(pid):
    if os.name == 'nt':
        import ctypes
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.OpenProcess.restype = ctypes.c_void_p
        handle = kernel.OpenProcess(0x1000, False, int(pid))
        if not handle: return False
        try:
            code = ctypes.c_ulong()
            return bool(kernel.GetExitCodeProcess(ctypes.c_void_p(handle), ctypes.byref(code))) and code.value == 259
        finally:
            kernel.CloseHandle(ctypes.c_void_p(handle))
    try:
        os.kill(int(pid), 0)
        return True
    except OSError:
        return False
