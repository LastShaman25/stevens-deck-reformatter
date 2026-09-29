"""Owned session snapshots and fenced mutations shared by every API/worker instance."""
import json
import os
import shutil
import tempfile
import time
import uuid
from contextlib import contextmanager, nullcontext
from contextvars import ContextVar
from pathlib import Path
from threading import Lock
from . import db, objects

cache = ContextVar('shared_request_sessions', default=None)
worker = ContextVar('shared_worker', default=None)
SKIP = {'job_lock','active_jobs','execution_deadline'}


def portable(value, root, destination='@workspace'):
    if isinstance(value, str): return value.replace(root,destination)
    if isinstance(value, dict): return {k:portable(v,root,destination) for k,v in value.items()}
    if isinstance(value, (list,tuple,set)): return [portable(v,root,destination) for v in value]
    return value


def encode(sess):
    return portable({k:v for k,v in vars(sess).items() if k not in SKIP and not k.startswith('_cloud')},sess.dir)


def decode(row, directory=None):
    from ..sessions import Session
    sess=Session.__new__(Session)
    directory=directory or tempfile.mkdtemp(prefix='stevens-shared-')
    sess.__dict__.update(portable(row['state'],'@workspace',directory))
    sess.dir=directory
    sess.id=row['id'];sess.lifecycle=row['lifecycle']
    sess.job_lock=Lock();sess.active_jobs=0;sess.execution_deadline=None
    sess.ai_check=set(sess.ai_check)
    sess._cloud_version=row['version'];sess._cloud_snapshot=row['snapshot']
    sess._cloud_materialized=False;sess._cloud_new=False
    if sess.generation:
        sess.history[sess.generation['generation_id']]=sess.generation
    return sess


def row(sid, con=None):
    if con is None:
        with db.connect() as connection:return row(sid,connection)
    return con.execute('SELECT * FROM processing_sessions WHERE id=%s',(sid,)).fetchone()


def materialize(sess):
    if not sess._cloud_materialized:
        objects.restore(sess._cloud_snapshot,sess.dir)
        Path(sess.previews_dir).mkdir(parents=True,exist_ok=True)
        sess._cloud_materialized=True


def active(sess):
    now=time.time()
    with db.connect() as con:
        record=con.execute('''SELECT s.lifecycle,s.expires,s.close_after,s.touched,u.active,l.expires AS login_expires
            FROM processing_sessions s JOIN users u ON u.id=s.owner_id LEFT JOIN logins l ON l.token=s.login_id
            WHERE s.id=%s''',(sess.id,)).fetchone()
    if not record or record['lifecycle']!='active' or not record['active'] or not record['login_expires'] or now>=record['login_expires'] or now>=record['expires'] or (record['close_after'] and now>=record['close_after']):
        raise ValueError('Job closed, sign-in revoked, or workspace expired.')


def create(connection=None):
    from .. import sessions
    from ..auth import current_user
    user=current_user.get()
    if not user:raise ValueError('Shared workspaces require authentication.')
    sid=uuid.uuid4().hex
    directory=tempfile.mkdtemp(prefix='stevens-shared-')
    sess=sessions.Session(sid,directory)
    with (nullcontext(connection) if connection is not None else db.connect()) as con:
        con.execute('SELECT pg_advisory_xact_lock(hashtext(%s))',('workspaces:'+user['id'],))
        count=con.execute("SELECT count(*) AS n FROM processing_sessions WHERE owner_id=%s AND lifecycle='active' AND expires>%s",(user['id'],time.time())).fetchone()['n']
        if count>=3:
            shutil.rmtree(directory)
            raise ValueError('Finish or cancel an existing job first (maximum three).')
        con.execute('''INSERT INTO processing_sessions(id,owner_id,login_id,state,touched,expires)
            VALUES (%s,%s,%s,%s::jsonb,%s,%s)''',(sid,user['id'],user['token'],json.dumps(encode(sess)),sess.touched,sess.expires))
    sess._cloud_version=0;sess._cloud_snapshot=None;sess._cloud_materialized=True;sess._cloud_new=True
    if cache.get() is not None:cache.get()[sid]=sess
    return sess


def get(sid, include_closed=False):
    if not isinstance(sid,str) or len(sid)!=32:return None
    cached=(cache.get() or {}).get(sid)
    if cached:
        return cached if include_closed or cached.lifecycle=='active' else None
    record=row(sid)
    if not record or (not include_closed and (record['lifecycle']!='active' or time.time()>=record['expires'])):return None
    sess=decode(record)
    with db.connect() as con:
        task=con.execute("SELECT result FROM processing_tasks WHERE session_id=%s AND state IN ('queued','running')",(sid,)).fetchone()
    if task and task['result']:
        sess.progress=task['result'].get('progress',{'stage':'queued'})
        # Preserve the last complete candidate; never claim partial QA is ready.
        if sess.generation:sess.generation['progress']=sess.progress
    if cache.get() is not None:cache.get()[sid]=sess
    return sess


def save(sess, lease=None, completed_task=None, result=None):
    active(sess)
    snapshot=objects.snapshot(sess) if sess._cloud_materialized else sess._cloud_snapshot
    old=sess._cloud_snapshot
    with db.connect() as con:
        updated=con.execute('''UPDATE processing_sessions SET state=%s::jsonb,snapshot=%s,version=version+1,
            touched=%s,close_after=%s WHERE id=%s AND version=%s AND lifecycle='active'
            AND ((%s::text IS NULL AND lease IS NULL) OR (lease=%s AND lease_until>%s)) RETURNING version''',
            (json.dumps(encode(sess)),snapshot,sess.touched,sess.close_after,sess.id,sess._cloud_version,lease,lease,time.time())).fetchone()
        if not updated:
            if snapshot!=old:objects.remove(snapshot)
            raise ValueError('Workspace changed or was cancelled. Reload before continuing.')
        if completed_task:
            completed=con.execute("UPDATE processing_tasks SET state='completed',result=%s::jsonb,updated=%s WHERE id=%s AND lease=%s AND state='running' RETURNING id",
                (json.dumps(result),time.time(),completed_task,lease)).fetchone()
            if not completed:raise ValueError('Task changed before publication; candidate was not released.')
    sess._cloud_version=updated['version'];sess._cloud_snapshot=snapshot;sess._cloud_new=False
    # Older immutable snapshots may be a queued task's baseline. Cleanup owns them.


@contextmanager
def job(sess):
    from .. import sessions
    active(sess)
    owner=worker.get()
    if owner:
        materialize(sess)
        token=sessions.active_session.set(sess)
        try:yield sess
        finally:sessions.active_session.reset(token)
        return
    lease=uuid.uuid4().hex
    with db.connect() as con:
        result=con.execute('''UPDATE processing_sessions SET lease=%s,lease_until=%s WHERE id=%s
            AND lifecycle='active' AND (lease IS NULL OR lease_until<%s)
            AND NOT EXISTS (SELECT 1 FROM processing_tasks WHERE session_id=%s AND state IN ('queued','running'))
            RETURNING version''',(lease,time.time()+120,sess.id,time.time(),sess.id)).fetchone()
        if not result or result['version']!=sess._cloud_version:raise ValueError('Session is busy or changed. Reload it.')
    token=sessions.active_session.set(sess)
    try:
        materialize(sess);sess.touched=time.time()
        yield sess
        save(sess,lease)
    finally:
        sessions.active_session.reset(token)
        with db.connect() as con:
            con.execute('UPDATE processing_sessions SET lease=NULL,lease_until=0 WHERE id=%s AND lease=%s',(sess.id,lease))


def delete(sid):
    with db.connect() as con:
        con.execute("UPDATE processing_sessions SET lifecycle='closing' WHERE id=%s",(sid,))
        con.execute("UPDATE processing_tasks SET state='cancelled',error='Job cancelled.' WHERE session_id=%s AND state IN ('queued','running')",(sid,))
    cached=(cache.get() or {}).get(sid)
    if cached:cached.lifecycle='closing';cached._cloud_new=False
    return purge(sid)


def purge(sid):
    with db.connect() as con:
        item=row(sid,con)
        if not item:return True
        if item['lease'] and item['lease_until']>time.time():return False
    try:objects.purge(sid)
    except Exception:
        with db.connect() as con:con.execute("UPDATE processing_sessions SET lifecycle='purge_failed' WHERE id=%s",(sid,))
        return False
    with db.connect() as con:con.execute("DELETE FROM processing_sessions WHERE id=%s AND lifecycle!='active'",(sid,))
    return True


def cancel_owner(uid, login_id=None):
    with db.connect() as con:
        rows=con.execute('SELECT id FROM processing_sessions WHERE owner_id=%s'+(' AND login_id=%s' if login_id else ''),(uid,login_id) if login_id else (uid,)).fetchall()
    for item in rows:delete(item['id'])


def sweep():
    with db.connect() as con:
        now=time.time()
        con.execute("UPDATE processing_sessions SET lifecycle='closing' WHERE expires<%s OR close_after<%s OR (touched<%s AND lease_until<%s AND NOT EXISTS (SELECT 1 FROM processing_tasks t WHERE t.session_id=processing_sessions.id AND t.state IN ('queued','running')))",(now,now,now-3600,now))
        rows=con.execute("SELECT id FROM processing_sessions WHERE lifecycle!='active'").fetchall()
        tickets=con.execute('DELETE FROM upload_tickets WHERE expires<%s RETURNING object_key',(now,)).fetchall()
    for item in rows:delete(item['id'])
    for ticket in tickets:objects.remove(ticket['object_key'])


@contextmanager
def scope():
    value={};token=cache.set(value)
    try:
        yield value
        for sess in value.values():
            if sess._cloud_new and sess.lifecycle=='active':save(sess)
    finally:
        cache.reset(token)
        for sess in value.values():
            path=Path(sess.dir).resolve()
            if path.parent==Path(tempfile.gettempdir()).resolve() and path.name.startswith('stevens-shared-'):
                shutil.rmtree(path,ignore_errors=True)
