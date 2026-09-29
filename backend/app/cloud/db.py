"""Shared PostgreSQL transactions. No presentation data is stored in account tables."""
import os
import re
import sqlite3
from contextlib import contextmanager
from threading import Lock

_initialized = set()
_lock = Lock()
SCHEMA = '''
CREATE TABLE IF NOT EXISTS users (id TEXT PRIMARY KEY, email TEXT UNIQUE NOT NULL,
 issuer TEXT, subject TEXT, role TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1, UNIQUE(issuer,subject));
CREATE TABLE IF NOT EXISTS logins (token TEXT PRIMARY KEY, user_id TEXT REFERENCES users(id) ON DELETE CASCADE,
 csrf TEXT NOT NULL, expires DOUBLE PRECISION NOT NULL);
CREATE TABLE IF NOT EXISTS invites (token TEXT PRIMARY KEY, email TEXT NOT NULL, role TEXT NOT NULL, expires DOUBLE PRECISION NOT NULL);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS codes (token TEXT PRIMARY KEY, user_id TEXT REFERENCES users(id) ON DELETE CASCADE);
CREATE TABLE IF NOT EXISTS login_attempts (peer TEXT NOT NULL, stamp DOUBLE PRECISION NOT NULL);
CREATE INDEX IF NOT EXISTS login_attempts_peer ON login_attempts(peer,stamp);
CREATE TABLE IF NOT EXISTS processing_sessions (
 id TEXT PRIMARY KEY, owner_id TEXT NOT NULL REFERENCES users(id), login_id TEXT NOT NULL,
 state JSONB NOT NULL, snapshot TEXT, version INTEGER NOT NULL DEFAULT 0,
 lifecycle TEXT NOT NULL DEFAULT 'active', touched DOUBLE PRECISION NOT NULL,
 expires DOUBLE PRECISION NOT NULL, close_after DOUBLE PRECISION,
 lease TEXT, lease_until DOUBLE PRECISION NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS processing_tasks (
 id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES processing_sessions(id) ON DELETE CASCADE,
 owner_id TEXT NOT NULL, login_id TEXT NOT NULL, operation TEXT NOT NULL, body JSONB NOT NULL,
 baseline JSONB NOT NULL, snapshot TEXT, state TEXT NOT NULL DEFAULT 'queued',
 created DOUBLE PRECISION NOT NULL, updated DOUBLE PRECISION NOT NULL, lease TEXT,
 lease_until DOUBLE PRECISION NOT NULL DEFAULT 0, result JSONB, error TEXT,
 attempts INTEGER NOT NULL DEFAULT 0, runtime DOUBLE PRECISION NOT NULL DEFAULT 0,
 code_version TEXT NOT NULL, configuration JSONB NOT NULL);
CREATE UNIQUE INDEX IF NOT EXISTS processing_one_task ON processing_tasks(session_id)
 WHERE state IN ('queued','running');
CREATE TABLE IF NOT EXISTS processing_steps (
 task_id TEXT NOT NULL REFERENCES processing_tasks(id) ON DELETE CASCADE,
 ordinal INTEGER NOT NULL, signature TEXT NOT NULL, value JSONB NOT NULL,
 PRIMARY KEY(task_id,ordinal));
CREATE TABLE IF NOT EXISTS upload_tickets (
 id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, login_id TEXT NOT NULL, target TEXT NOT NULL,
 object_key TEXT NOT NULL, filename TEXT NOT NULL, size BIGINT NOT NULL, expires DOUBLE PRECISION NOT NULL,
 consumed BOOLEAN NOT NULL DEFAULT FALSE);
'''


def namespace():
    value = os.environ['STEVENS_STORAGE_NAMESPACE']
    if not re.fullmatch(r'[a-z][a-z0-9_]{2,40}', value):
        raise RuntimeError('STEVENS_STORAGE_NAMESPACE must be 3–41 lowercase letters/digits/underscores.')
    return value


@contextmanager
def connect():
    import psycopg
    from psycopg.rows import dict_row
    from psycopg import sql
    url, name = os.environ['DATABASE_URL'], namespace()
    con = psycopg.connect(url, connect_timeout=10, row_factory=dict_row)
    try:
        identity = (url, name)
        with _lock:
            if identity not in _initialized:
                con.execute('SELECT pg_advisory_xact_lock(hashtext(%s))',('schema:'+name,))
                con.execute(sql.SQL('CREATE SCHEMA IF NOT EXISTS {}').format(sql.Identifier(name)))
                con.execute(sql.SQL('SET search_path TO {}').format(sql.Identifier(name)))
                con.execute(SCHEMA)
                con.commit()
                _initialized.add(identity)
        con.execute(sql.SQL('SET search_path TO {}').format(sql.Identifier(name)))
        yield con
        con.commit()
    except BaseException:
        con.rollback()
        raise
    finally:
        con.close()


class Row(dict):
    def __getitem__(self, key):
        return list(self.values())[key] if isinstance(key, int) else super().__getitem__(key)


class Cursor:
    def __init__(self, cursor): self.cursor = cursor
    def fetchone(self):
        row = self.cursor.fetchone()
        return Row(row) if row is not None else None
    def fetchall(self): return [Row(row) for row in self.cursor.fetchall()]
    def __iter__(self): return iter(self.fetchall())


class Accounts:
    """Small compatibility adapter for the existing parameterized account queries."""
    def __init__(self, con): self.con = con
    def execute(self, query, values=()):
        import psycopg
        if query == 'BEGIN IMMEDIATE':
            # Serialize bootstrap/invitation/admin invariants across instances.
            return Cursor(self.con.execute("SELECT pg_advisory_xact_lock(hashtext(current_schema() || ':accounts'))"))
        if query.startswith('INSERT OR IGNORE INTO '):
            query = query.replace('INSERT OR IGNORE INTO ', 'INSERT INTO ', 1) + ' ON CONFLICT DO NOTHING'
        try:
            return Cursor(self.con.execute(query.replace('?', '%s'), values))
        except psycopg.IntegrityError as exc:
            raise sqlite3.IntegrityError('Account constraint violation') from exc


@contextmanager
def accounts():
    with connect() as con:
        yield Accounts(con)


def login_attempt(peer, now):
    from fastapi import HTTPException
    with connect() as con:
        con.execute('SELECT pg_advisory_xact_lock(hashtext(%s))', ('login:'+peer,))
        con.execute('DELETE FROM login_attempts WHERE stamp < %s', (now-60,))
        count = con.execute('SELECT count(*) AS n FROM login_attempts WHERE peer=%s', (peer,)).fetchone()['n']
        if count >= 8:
            raise HTTPException(429, 'Too many sign-in attempts. Try again in one minute.')
        con.execute('INSERT INTO login_attempts VALUES (%s,%s)', (peer,now))
