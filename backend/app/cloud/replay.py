"""Deterministic replay of completed external operations within a durable task.

Cache entries are scoped to one immutable input snapshot, code version, agent
configuration and ordered call signature. They are never treated as QA for a
different candidate. A crash between a provider response and its commit can
repeat that single request; external billing cannot be made exactly-once.
"""
import hashlib
import json
import time
import uuid
import zipfile
from contextvars import ContextVar
from pathlib import Path
from . import db, objects, state, tasks

current=ContextVar('durable_replay',default=None)


class SliceComplete(BaseException): pass


def identifier():
    runner=current.get()
    if not runner:return uuid.uuid4().hex
    runner.ids+=1
    return uuid.uuid5(uuid.UUID(runner.task['id']),str(runner.ids)).hex


def canonical_deck(path):
    digest=hashlib.sha256()
    with zipfile.ZipFile(path) as archive:
        for name in sorted(archive.namelist()):
            digest.update(name.encode()+archive.read(name))
    return digest.hexdigest()


class Replay:
    def __init__(self, task, sess):
        self.task,self.sess=task,sess
        self.ordinal=self.ids=0
        self.deadline=time.monotonic()+240

    def step(self, signature, fn, reserve=150):
        self.ordinal+=1
        tasks.fence(self.task['id'],self.task['lease'])
        signature=hashlib.sha256(json.dumps(state.portable(signature,self.sess.dir),sort_keys=True,default=str).encode()).hexdigest()
        with db.connect() as con:
            cached=con.execute('SELECT signature,value FROM processing_steps WHERE task_id=%s AND ordinal=%s',(self.task['id'],self.ordinal)).fetchone()
        if cached:
            if cached['signature']!=signature:raise ValueError('Replay inputs changed. No cached QA was reused; start a fresh operation.')
            return cached['value']
        if time.monotonic()+reserve>self.deadline:raise SliceComplete()
        value=fn()
        tasks.fence(self.task['id'],self.task['lease'])
        with db.connect() as con:
            owned=con.execute("SELECT id FROM processing_tasks WHERE id=%s AND lease=%s AND state='running' AND lease_until>%s FOR UPDATE",
                (self.task['id'],self.task['lease'],time.time())).fetchone()
            if not owned:raise ValueError('Worker lost ownership before checkpoint.')
            con.execute('INSERT INTO processing_steps VALUES (%s,%s,%s,%s::jsonb)',(self.task['id'],self.ordinal,signature,json.dumps(value)))
            con.execute('UPDATE processing_tasks SET result=%s::jsonb,updated=%s WHERE id=%s AND lease=%s',
                (json.dumps({'progress':{'stage':'processing','completed_steps':self.ordinal}}),time.time(),self.task['id'],self.task['lease']))
        return value


def generate(role, system, payload, images, max_tokens, fn):
    runner=current.get()
    if not runner:return fn()
    signature={'kind':'model','role':role,'system':system,'payload':payload,'max_tokens':max_tokens,
               'images':[(label,hashlib.sha256(Path(path).read_bytes()).hexdigest()) for label,path in images]}
    before=(runner.sess.calls,runner.sess.tokens)
    def execute():
        result=fn()
        return {'result':result,'calls':runner.sess.calls-before[0],'tokens':runner.sess.tokens-before[1]}
    value=runner.step(signature,execute)
    runner.sess.calls=before[0]+value['calls'];runner.sess.tokens=before[1]+value['tokens']
    return value['result']


def render(pptx_path,out_dir,soffice,fn):
    runner=current.get()
    if not runner:return fn()
    signature={'kind':'render','deck':canonical_deck(pptx_path),'renderer':soffice}
    def execute():
        result=Path(fn())
        key=objects.prefix(runner.sess.id)+f'tasks/{runner.task["id"]}/render-{runner.ordinal}.pdf'
        objects.put(key,result.read_bytes(),'application/pdf')
        return {'key':key,'metadata':json.loads(result.with_suffix('.renderer.json').read_text())}
    value=runner.step(signature,execute)
    result=Path(out_dir)/(Path(pptx_path).stem+'.pdf');result.parent.mkdir(parents=True,exist_ok=True)
    result.write_bytes(objects.get(value['key']))
    result.with_suffix('.renderer.json').write_text(json.dumps(value['metadata']))
    return str(result)
