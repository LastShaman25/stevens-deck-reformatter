"""OIDC identity, revocable opaque sessions, and account-only SQLite storage."""
import hashlib
import os
import secrets
import sqlite3
import time
import uuid
from threading import Lock
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from urllib.parse import urlsplit

from authlib.integrations.starlette_client import OAuth
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse, JSONResponse
from pydantic import BaseModel, Field
from typing import Literal
from .ai.providers import setting

current_user = ContextVar('current_user', default=None)
router = APIRouter()
COOKIE = 'stevens_login'
_attempts = {}
_attempt_lock = Lock()


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def trusted_origin(origin):
    configured = setting('STEVENS_PUBLIC_URL', 'http://localhost:8000').rstrip('/')
    if not origin or origin == configured: return True
    # Development-only aliases; never reflect arbitrary Host/Origin values.
    return configured in ('http://localhost:8000','http://127.0.0.1:8000') and origin in (
        'http://localhost:8000','http://127.0.0.1:8000','http://localhost:5173','http://127.0.0.1:5173')


@contextmanager
def database():
    base = Path(os.environ.get('LOCALAPPDATA', Path.home() / '.local/share')) / 'StevensSlideStudio'
    path = Path(setting('STEVENS_AUTH_DB', str(base / 'accounts.sqlite3')))
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path, timeout=20)
    con.row_factory = sqlite3.Row
    con.execute('PRAGMA foreign_keys=ON')
    # Schema version 1: account metadata only, never presentation content.
    con.executescript('''
    CREATE TABLE IF NOT EXISTS users (id TEXT PRIMARY KEY, email TEXT UNIQUE NOT NULL,
      issuer TEXT, subject TEXT, role TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1,
      UNIQUE(issuer,subject));
    CREATE TABLE IF NOT EXISTS logins (token TEXT PRIMARY KEY, user_id TEXT REFERENCES users(id) ON DELETE CASCADE,
      csrf TEXT NOT NULL, expires REAL NOT NULL);
    CREATE TABLE IF NOT EXISTS invites (token TEXT PRIMARY KEY, email TEXT NOT NULL,
      role TEXT NOT NULL, expires REAL NOT NULL);
    CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS codes (token TEXT PRIMARY KEY, user_id TEXT REFERENCES users(id) ON DELETE CASCADE);
    CREATE TABLE IF NOT EXISTS activity_events (id TEXT PRIMARY KEY, owner_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      job_id TEXT, stamp REAL NOT NULL, event TEXT NOT NULL);
    CREATE INDEX IF NOT EXISTS activity_stamp ON activity_events(stamp);
    PRAGMA user_version=1;
    ''')
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def cookie_secret():
    with database() as con:
        con.execute('INSERT OR IGNORE INTO settings VALUES (?,?)', ('cookie_secret', secrets.token_urlsafe(48)))
        return con.execute('SELECT value FROM settings WHERE key=?', ('cookie_secret',)).fetchone()[0]


def public_user(row):
    return {k: row[k] for k in ('id', 'email', 'role', 'active')}


def authenticate(request):
    token = request.cookies.get(COOKIE)
    if not token:
        return None
    with database() as con:
        con.execute('DELETE FROM logins WHERE expires < ?', (time.time(),))
        row = con.execute('SELECT u.*, l.csrf, l.token FROM users u JOIN logins l ON l.user_id=u.id '
                          'WHERE l.token=? AND u.active=1', (digest(token),)).fetchone()
        return dict(row) if row else None


def issue_login(user_id):
    token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    with database() as con:
        con.execute('INSERT INTO logins VALUES (?,?,?,?)', (digest(token), user_id, csrf, time.time()+8*3600))
    return token, csrf


def provision_identity(claims, invitation=''):
    issuer = setting('STEVENS_OIDC_ISSUER').rstrip('/')
    if claims.get('iss', '').rstrip('/') != issuer or not claims.get('sub'):
        raise HTTPException(403, 'Identity issuer does not match.')
    # Identity providers must emit a verified email claim; no email-only linking.
    if claims.get('email_verified') is not True:
        raise HTTPException(403, 'A verified email claim is required from the identity provider.')
    email = str(claims.get('email', '')).strip().lower()
    if not email or '@' not in email:
        raise HTTPException(403, 'Identity has no verified email.')
    with database() as con:
        con.execute('BEGIN IMMEDIATE')
        row = con.execute('SELECT * FROM users WHERE issuer=? AND subject=?', (issuer, claims['sub'])).fetchone()
        if row:
            if not row['active']:
                raise HTTPException(403, 'Account is inactive.')
            return public_user(row)
        invite = con.execute('SELECT * FROM invites WHERE token=? AND email=? AND expires>?',
                             (digest(invitation), email, time.time())).fetchone() if invitation else None
        bootstrap = setting('STEVENS_INITIAL_ADMIN_EMAIL').strip().lower()
        first = con.execute('SELECT count(*) FROM users').fetchone()[0] == 0
        if not invite and not (first and bootstrap and email == bootstrap):
            raise HTTPException(403, 'An invitation is required.')
        role = 'admin' if first and email == bootstrap else invite['role']
        uid = uuid.uuid4().hex
        try:
            con.execute('INSERT INTO users VALUES (?,?,?,?,?,1)', (uid, email, issuer, claims['sub'], role))
        except sqlite3.IntegrityError:
            raise HTTPException(403, 'This email is already bound to another identity.')
        if invite:
            con.execute('DELETE FROM invites WHERE token=?', (digest(invitation),))
        return {'id': uid, 'email': email, 'role': role, 'active': 1}


def oidc_client():
    issuer = setting('STEVENS_OIDC_ISSUER').rstrip('/')
    origin = setting('STEVENS_PUBLIC_URL', 'http://localhost:8000').rstrip('/')
    if not issuer.startswith('https://') or not setting('STEVENS_OIDC_CLIENT_ID'):
        raise HTTPException(503, 'Configure OIDC issuer, client ID, client secret, and initial admin email in backend/.env.')
    oauth = OAuth()
    client = oauth.register('identity', client_id=setting('STEVENS_OIDC_CLIENT_ID'),
        client_secret=setting('STEVENS_OIDC_CLIENT_SECRET'),
        server_metadata_url=issuer+'/.well-known/openid-configuration',
        client_kwargs={'scope': 'openid email profile', 'code_challenge_method': 'S256'})
    return client, origin


@router.get('/api/auth/status')
def auth_status(request: Request):
    bootstrap_codes()
    user = authenticate(request)
    return {'user': public_user(user) if user else None, 'csrf': user['csrf'] if user else None,
            'mode': setting('STEVENS_AUTH_MODE', 'invitation'),
            'configured': setting('STEVENS_AUTH_MODE', 'invitation') == 'invitation' or bool(setting('STEVENS_OIDC_ISSUER') and setting('STEVENS_OIDC_CLIENT_ID'))}


def bootstrap_codes():
    if setting('STEVENS_AUTH_MODE', 'invitation') != 'invitation':
        return
    with database() as con:
        con.execute('BEGIN IMMEDIATE')
        if not con.execute("SELECT 1 FROM settings WHERE key='codes_bootstrapped'").fetchone():
            uid = uuid.uuid4().hex
            con.execute('INSERT INTO users VALUES (?,?,?,?,?,1)', (uid, 'Administrator', 'invitation', uid, 'admin'))
            con.execute('INSERT INTO codes VALUES (?,?)', (digest(setting('STEVENS_ADMIN_CODE', 'admin')), uid))
            con.execute("INSERT INTO settings VALUES ('codes_bootstrapped','1')")


class CodeLogin(BaseModel):
    code: str = Field(min_length=1, max_length=200)


@router.post('/api/auth/code')
def code_login(request: Request, body: CodeLogin):
    if setting('STEVENS_AUTH_MODE', 'invitation') != 'invitation':
        raise HTTPException(404, 'Invitation-code sign-in is disabled.')
    origin = request.headers.get('origin')
    if not trusted_origin(origin):
        raise HTTPException(403, 'Untrusted request origin.')
    peer = request.client.host if request.client else 'unknown'
    now = time.time()
    with _attempt_lock:
        for key in list(_attempts):
            _attempts[key] = [t for t in _attempts[key] if t > now-60]
            if not _attempts[key]:
                del _attempts[key]
        attempts = _attempts.setdefault(peer, [])
        if len(attempts) >= 8:
            raise HTTPException(429, 'Too many sign-in attempts. Try again in one minute.')
        attempts.append(now)
    bootstrap_codes()
    with database() as con:
        row = con.execute('SELECT u.* FROM users u JOIN codes c ON c.user_id=u.id WHERE c.token=? AND u.active=1',
                          (digest(body.code.strip()),)).fetchone()
        if not row:
            raise HTTPException(401, 'Invalid or revoked invitation code.')
        user = public_user(row)
    token, csrf = issue_login(user['id'])
    response = JSONResponse({'user': user, 'csrf': csrf, 'mode': 'invitation', 'configured': True})
    response.set_cookie(COOKIE, token, httponly=True,
                        secure=setting('STEVENS_PUBLIC_URL', 'http://localhost:8000').startswith('https://'),
                        samesite='lax', max_age=8*3600)
    return response


class CodeCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    role: Literal['member', 'developer', 'admin'] = 'member'


@router.post('/api/admin/codes')
def create_code(request: Request, body: CodeCreate):
    admin(request)
    code, uid = secrets.token_urlsafe(18), uuid.uuid4().hex
    with database() as con:
        try:
            con.execute('INSERT INTO users VALUES (?,?,?,?,?,1)', (uid, body.name.strip(), 'invitation', uid, body.role))
        except sqlite3.IntegrityError:
            raise HTTPException(409, 'Use a distinct name for this account.')
        con.execute('INSERT INTO codes VALUES (?,?)', (digest(code), uid))
    return {'code': code, 'user': {'id': uid, 'email': body.name.strip(), 'role': body.role, 'active': 1}}


@router.post('/api/admin/users/{uid}/rotate-code')
def rotate_code(uid: str, request: Request):
    admin(request)
    from . import sessions
    code = secrets.token_urlsafe(18)
    with database() as con:
        if not con.execute('SELECT 1 FROM users WHERE id=?', (uid,)).fetchone():
            raise HTTPException(404, 'Account not found.')
        con.execute('DELETE FROM codes WHERE user_id=?', (uid,))
        con.execute('DELETE FROM logins WHERE user_id=?', (uid,))
        con.execute('INSERT INTO codes VALUES (?,?)', (digest(code), uid))
    sessions.cancel_owner(uid)
    if uid == request.state.user['id']:
        token, csrf = issue_login(uid)
        response = JSONResponse({'code':code, 'csrf':csrf})
        response.set_cookie(COOKIE, token, httponly=True,
            secure=setting('STEVENS_PUBLIC_URL','http://localhost:8000').startswith('https://'),
            samesite='lax', max_age=8*3600)
        return response
    return {'code': code}


@router.get('/auth/login')
async def login(request: Request, invite: str = ''):
    client, origin = oidc_client()
    request.session.clear()
    request.session['invite'] = invite[:200]
    return await client.authorize_redirect(request, origin+'/auth/callback')


@router.get('/auth/callback')
async def callback(request: Request):
    client, origin = oidc_client()
    try:
        token = await client.authorize_access_token(request)
        user = provision_identity(token['userinfo'], request.session.get('invite', ''))
        login_token, _ = issue_login(user['id'])
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(400, 'Sign-in validation failed. Start sign-in again.')
    finally:
        request.session.clear()
    response = RedirectResponse(origin+'/', status_code=303)
    response.set_cookie(COOKIE, login_token, httponly=True, secure=origin.startswith('https://'),
                        samesite='lax', max_age=8*3600)
    return response


@router.post('/api/auth/logout')
def logout(request: Request):
    from . import sessions
    user = request.state.user
    with database() as con:
        con.execute('DELETE FROM logins WHERE token=?', (user['token'],))
    sessions.cancel_owner(user['id'], login_id=user['token'])
    response = JSONResponse({'ok': True})
    response.delete_cookie(COOKIE)
    return response


def admin(request):
    if request.state.user['role'] != 'admin':
        raise HTTPException(403, 'Administrator access required.')


class Invite(BaseModel):
    email: str = Field(min_length=3, max_length=254, pattern=r'^[^\s@]+@[^\s@]+\.[^\s@]+$')
    role: Literal['member', 'developer', 'admin'] = 'member'


class AccountUpdate(BaseModel):
    role: Literal['member', 'developer', 'admin']
    active: bool


@router.get('/api/admin/users')
def users(request: Request):
    admin(request)
    with database() as con:
        return {'users': [public_user(row) for row in con.execute('SELECT * FROM users ORDER BY email')]}


@router.post('/api/admin/invitations')
def invite_user(request: Request, body: Invite):
    admin(request)
    token = secrets.token_urlsafe(32)
    with database() as con:
        con.execute('DELETE FROM invites WHERE expires<? OR email=?', (time.time(), body.email.lower()))
        con.execute('INSERT INTO invites VALUES (?,?,?,?)', (digest(token), body.email.lower(), body.role, time.time()+48*3600))
    return {'url': setting('STEVENS_PUBLIC_URL', 'http://localhost:8000').rstrip('/')+'/auth/login?invite='+token,
            'expires_in_hours': 48}


@router.patch('/api/admin/users/{uid}')
def update_user(uid: str, body: AccountUpdate, request: Request):
    admin(request)
    from . import sessions
    with database() as con:
        con.execute('BEGIN IMMEDIATE')
        row = con.execute('SELECT * FROM users WHERE id=?', (uid,)).fetchone()
        if not row:
            raise HTTPException(404, 'Account not found.')
        if row['role'] == 'admin' and row['active'] and (not body.active or body.role != 'admin'):
            if con.execute("SELECT count(*) FROM users WHERE active=1 AND role='admin'").fetchone()[0] <= 1:
                raise HTTPException(409, 'The last active administrator must remain active.')
        con.execute('UPDATE users SET role=?, active=? WHERE id=?', (body.role, int(body.active), uid))
        con.execute('DELETE FROM logins WHERE user_id=?', (uid,))
    if not body.active:
        sessions.cancel_owner(uid)
    return {'ok': True}


@router.delete('/api/admin/users/{uid}')
def remove_user(uid: str, request: Request):
    admin(request)
    from . import sessions
    with database() as con:
        con.execute('BEGIN IMMEDIATE')
        row = con.execute('SELECT * FROM users WHERE id=?', (uid,)).fetchone()
        if not row: return {'deleted':True}
        if row['active'] and row['role']=='admin' and con.execute("SELECT count(*) FROM users WHERE active=1 AND role='admin'").fetchone()[0] <= 1:
            raise HTTPException(409, 'The last active administrator cannot be removed.')
        con.execute('UPDATE users SET active=0 WHERE id=?',(uid,))
        con.execute('DELETE FROM logins WHERE user_id=?',(uid,))
    sessions.cancel_owner(uid)
    if any(s.owner_user_id==uid for s in sessions._sessions.values()):
        raise HTTPException(409,'Account disabled. Wait for processing-file deletion, then retry account removal.')
    with database() as con:
        con.execute('DELETE FROM invites WHERE email=?',(row['email'],))
        con.execute('DELETE FROM users WHERE id=?',(uid,))
    return {'deleted':True}


@router.get('/api/admin/processing-status')
def processing_status(request: Request):
    admin(request)
    from . import sessions
    return {'active_jobs':sum(s.lifecycle=='active' for s in sessions._sessions.values()),
            'deletion_pending':sum(s.lifecycle in ('closing','purging') for s in sessions._sessions.values()),
            'deletion_failed':sum(s.lifecycle=='purge_failed' for s in sessions._sessions.values())}


async def guard(request: Request, call_next):
    from . import sessions
    path = request.url.path
    if not path.startswith('/api/') or path in ('/api/auth/status', '/api/auth/code', '/api/health'):
        response = await call_next(request)
        response.headers['Cache-Control'] = 'no-store'
        return response
    user = authenticate(request)
    if not user:
        return JSONResponse({'detail': 'Sign in to continue.'}, status_code=401)
    if request.method not in ('GET', 'HEAD', 'OPTIONS'):
        if not secrets.compare_digest(request.headers.get('X-CSRF-Token', ''), user['csrf']):
            return JSONResponse({'detail': 'Invalid request token. Reload the page.'}, status_code=403)
        origin = request.headers.get('origin')
        allowed = setting('STEVENS_PUBLIC_URL', 'http://localhost:8000').rstrip('/')
        if not trusted_origin(origin):
            return JSONResponse({'detail': 'Untrusted request origin.'}, status_code=403)
    request.state.user = user
    token = current_user.set(user)
    try:
        parts = path.split('/')
        if len(parts) > 3 and parts[2] in ('sessions', 'jobs'):
            cleanup = request.method == 'DELETE' or parts[-1] in ('cancel','finalize','lifecycle')
            sess = sessions._sessions.get(parts[3]) if cleanup else sessions.get(parts[3])
            if cleanup and not sess and parts[-1] != 'lifecycle':
                return JSONResponse({'deleted':True, 'status':'purged'})
            if not sess or sess.owner_user_id != user['id']:
                return JSONResponse({'detail': 'Job not found or expired.'}, status_code=404)
        response = await call_next(request)
        response.headers['Cache-Control'] = 'no-store'
        return response
    finally:
        current_user.reset(token)
