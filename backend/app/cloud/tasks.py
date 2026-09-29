"""Durable, fenced work queue. HTTP requests never own the lifetime of a deck job."""
import hashlib
import json
import os
import subprocess
import sys
import time
import uuid
import signal
from threading import BoundedSemaphore
from contextlib import nullcontext
from pathlib import Path
from . import db, state

_worker_slot=BoundedSemaphore(1)


def code_version():
    root=Path(__file__).parents[2]
    h=hashlib.sha256()
    paths=list((root/'app').rglob('*.py'))+list((root/'slide_engine').rglob('*.py'))+list((root/'assets').rglob('*'))
    for path in sorted(p for p in paths if p.is_file()):
        h.update(path.relative_to(root).as_posix().encode()+path.read_bytes())
    return h.hexdigest()


def enqueue(sess, operation, body, user, connection=None):
    from ..ai import providers
    if connection is None:state.active(sess)
    with (nullcontext(connection) if connection is not None else db.connect()) as con:
        item=con.execute('SELECT * FROM processing_sessions WHERE id=%s FOR UPDATE',(sess.id,)).fetchone()
        existing=con.execute("SELECT * FROM processing_tasks WHERE session_id=%s AND state IN ('queued','running')",(sess.id,)).fetchone()
        if existing:
            if existing['operation']==operation and existing['body']==body:return existing['id']
            raise ValueError('Another operation is already queued for this workspace.')
        if item['lifecycle']!='active' or (item['lease'] and item['lease_until']>time.time()):
            raise ValueError('Workspace is busy or closed.')
        tid=uuid.uuid4().hex;now=time.time()
        con.execute('''INSERT INTO processing_tasks
          (id,session_id,owner_id,login_id,operation,body,baseline,snapshot,created,updated,code_version,configuration)
          VALUES (%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s,%s,%s,%s,%s::jsonb)''',
          (tid,sess.id,user['id'],user['token'],operation,json.dumps(body),json.dumps(item['state']),item['snapshot'],now,now,code_version(),json.dumps(providers.capabilities())))
        con.execute('UPDATE processing_sessions SET touched=%s WHERE id=%s',(now,sess.id))
    return tid


def get(tid, user=None):
    with db.connect() as con:
        row=con.execute('SELECT * FROM processing_tasks WHERE id=%s',(tid,)).fetchone()
    if user and row and row['owner_id']!=user['id']:return None
    return row


def claim(tid=None):
    now=time.time();lease=uuid.uuid4().hex
    with db.connect() as con:
        query='''SELECT t.* FROM processing_tasks t JOIN processing_sessions s ON s.id=t.session_id
          JOIN users u ON u.id=t.owner_id JOIN logins l ON l.token=t.login_id
          WHERE t.state IN ('queued','running') AND t.lease_until<%s AND s.lease_until<%s
          AND s.lifecycle='active' AND s.expires>%s AND u.active=1 AND l.expires>%s'''
        values=[now,now,now,now]
        if tid:query+=' AND t.id=%s';values.append(tid)
        item=con.execute(query+' ORDER BY t.updated FOR UPDATE OF t,s SKIP LOCKED LIMIT 1',values).fetchone()
        if not item:return None
        if item['code_version']!=code_version():
            con.execute("UPDATE processing_tasks SET state='failed',error='Deployment code changed. Start the operation again.' WHERE id=%s",(item['id'],));return None
        # A bounded invocation is a platform requirement, never a spend budget.
        con.execute("UPDATE processing_tasks SET state='running',lease=%s,lease_until=%s,attempts=attempts+1,updated=%s WHERE id=%s",(lease,now+720,now,item['id']))
        con.execute('UPDATE processing_sessions SET lease=%s,lease_until=%s WHERE id=%s',(lease,now+720,item['session_id']))
        item['lease']=lease
        return item


def fence(tid, lease):
    with db.connect() as con:
        row=con.execute('''SELECT t.id FROM processing_tasks t JOIN processing_sessions s ON s.id=t.session_id
          JOIN logins l ON l.token=t.login_id JOIN users u ON u.id=t.owner_id
          WHERE t.id=%s AND t.lease=%s AND t.lease_until>%s AND t.state='running'
          AND s.lifecycle='active' AND s.expires>%s AND l.expires>%s AND u.active=1''',
          (tid,lease,time.time(),time.time(),time.time())).fetchone()
    if not row:raise ValueError('Worker lease expired or job cancelled.')


def run_one(tid=None):
    # Fluid compute may send concurrent requests to one container. Keep one
    # memory-heavy renderer process per instance; other instances can claim jobs.
    if not _worker_slot.acquire(blocking=False):return {'advanced':False}
    try:return _run_one(tid)
    finally:_worker_slot.release()


def _run_one(tid=None):
    item=claim(tid)
    if not item:return {'advanced':False}
    start=time.monotonic()
    try:
        # Each isolated child owns its local files and model/session contexts.
        # Killing an invocation cannot publish an unverified candidate.
        process=subprocess.Popen([sys.executable,'-m','app.cloud.worker',item['id'],item['lease']],
            stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=os.name!='nt',
            creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        try:
            process.communicate(timeout=600)
            code=process.returncode
        except subprocess.TimeoutExpired:
            if os.name!='nt':os.killpg(process.pid,signal.SIGKILL)
            else:process.kill()
            process.communicate();code=75
    finally:
        with db.connect() as con:
            con.execute('''UPDATE processing_tasks SET state=CASE WHEN state='running' THEN 'queued' ELSE state END,
              lease=NULL,lease_until=0,runtime=runtime+%s,updated=%s WHERE id=%s AND lease=%s''',
              (time.monotonic()-start,time.time(),item['id'],item['lease']))
            con.execute('UPDATE processing_sessions SET lease=NULL,lease_until=0 WHERE id=%s AND lease=%s',(item['session_id'],item['lease']))
    if code not in (0,75):
        with db.connect() as con:
            con.execute("UPDATE processing_tasks SET state='failed',error='Worker exited unexpectedly. Retry this operation; QA has not been bypassed.' WHERE id=%s AND state='queued'",(item['id'],))
    return {'advanced':True,'task_id':item['id']}
