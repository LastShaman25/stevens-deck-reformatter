"""Same-origin API, direct private uploads/downloads and bounded queue advancement."""
import json
import os
import re
import secrets
import time
import uuid
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool
from . import db, objects, state, tasks

router=APIRouter(prefix='/api/cloud')


def own_session(sid,user):
    sess=state.get(sid)
    if not sess or sess.owner_user_id!=user['id']:raise HTTPException(404,'Workspace not found.')
    state.active(sess)
    return sess


def queued(tid):return JSONResponse({'task_id':tid,'status_url':f'/api/cloud/tasks/{tid}'},status_code=202)


class Upload(BaseModel):
    filename:str=Field(min_length=1,max_length=200)
    size:int=Field(gt=0,le=60*1024*1024)
    target:str=Field(max_length=120)


@router.post('/uploads')
def begin_upload(body:Upload,request:Request):
    user=request.state.user
    if body.target!='/api/sessions':
        match=re.fullmatch(r'/api/jobs/([0-9a-f]{32})/pdf',body.target)
        if not match:raise HTTPException(400,'Unsupported upload target.')
        sess=own_session(match[1],user)
        if not sess.creation or sess.creation['approved_hash']:raise HTTPException(409,'Cannot replace an approved source.')
        if body.size>50*1024*1024:raise HTTPException(413,'PDF exceeds 50 MB.')
    suffix=os.path.splitext(body.filename)[1].lower()
    if suffix not in ('.pdf','.pptx') or (body.target!='/api/sessions' and suffix!='.pdf'):
        raise HTTPException(400,'Choose a PowerPoint or PDF file.')
    tid=uuid.uuid4().hex;key=f'{db.namespace()}/uploads/{tid}{suffix}'
    with db.connect() as con:
        con.execute('INSERT INTO upload_tickets VALUES (%s,%s,%s,%s,%s,%s,%s,%s,FALSE)',
                    (tid,user['id'],user['token'],body.target,key,os.path.basename(body.filename),body.size,time.time()+900))
    post=objects.client().generate_presigned_post(objects.bucket(),key,
        Conditions=[['content-length-range',body.size,body.size]],ExpiresIn=300)
    return {'upload_id':tid,'url':post['url'],'fields':post['fields']}


class UploadComplete(BaseModel):
    upload_id:str=Field(pattern=r'^[0-9a-f]{32}$')


@router.post('/uploads/complete')
def complete_upload(body:UploadComplete,request:Request):
    from .. import sessions
    user=request.state.user
    with db.connect() as con:
        ticket=con.execute('SELECT * FROM upload_tickets WHERE id=%s FOR UPDATE',(body.upload_id,)).fetchone()
        if not ticket or ticket['owner_id']!=user['id'] or ticket['login_id']!=user['token'] or ticket['expires']<time.time():raise HTTPException(404,'Upload expired.')
        if ticket['consumed']:raise HTTPException(409,'Upload already submitted.')
        try:size=objects.client().head_object(Bucket=objects.bucket(),Key=ticket['object_key'])['ContentLength']
        except Exception:raise HTTPException(409,'Upload has not completed.')
        if size!=ticket['size']:raise HTTPException(400,'Uploaded file size does not match.')
        sess=sessions.create() if ticket['target']=='/api/sessions' else own_session(ticket['target'].split('/')[3],user)
        frozen=objects.prefix(sess.id)+'inputs/'+uuid.uuid4().hex+os.path.splitext(ticket['filename'])[1].lower()
        objects.client().copy_object(Bucket=objects.bucket(),Key=frozen,CopySource={'Bucket':objects.bucket(),'Key':ticket['object_key']})
        con.execute('UPDATE upload_tickets SET consumed=TRUE WHERE id=%s',(body.upload_id,))
    if sess._cloud_new:state.save(sess)
    try:
        tid=tasks.enqueue(sess,'import' if ticket['target']=='/api/sessions' else 'pdf',{'key':frozen,'filename':ticket['filename']},user)
    except ValueError as exc:raise HTTPException(409,str(exc))
    objects.remove(ticket['object_key'])
    return queued(tid)


@router.get('/tasks/{tid}')
def task_status(tid:str,request:Request):
    row=tasks.get(tid,request.state.user)
    if not row:raise HTTPException(404,'Task not found.')
    return {'state':row['state'],'result':row['result'] if row['state']=='completed' else None,
            'progress':(row['result'] or {}).get('progress') if row['state']!='completed' else None,'error':row['error']}


@router.post('/tasks/{tid}/advance')
async def advance(tid:str,request:Request):
    row=tasks.get(tid,request.state.user)
    if not row:raise HTTPException(404,'Task not found.')
    return await run_in_threadpool(tasks.run_one,tid)


@router.get('/tick')
async def tick(request:Request):
    expected=os.environ.get('CRON_SECRET','')
    if not expected or not secrets.compare_digest(request.headers.get('authorization',''),'Bearer '+expected):
        raise HTTPException(401,'Unauthorized scheduler.')
    await run_in_threadpool(state.sweep)
    return await run_in_threadpool(tasks.run_one)


async def dispatch(request,user):
    """Intercept expensive actions before the legacy synchronous endpoints."""
    path=request.url.path
    match=re.fullmatch(r'/api/(sessions|jobs)/([0-9a-f]{32})/(generate|outline/plan|content|download)',path)
    if not match:
        if request.method=='POST' and (path=='/api/sessions' or re.fullmatch(r'/api/jobs/[0-9a-f]{32}/pdf',path)):
            return JSONResponse({'detail':'Use the direct upload flow; files must not pass through a Vercel Function.'},status_code=413)
        return None
    kind,sid,action=match.groups()
    sess=own_session(sid,user)
    if action=='download' and request.method=='GET':
        from ..api import artifact_bytes
        from ..generations import verify_identity
        try:
            with db.connect() as con:
                pending=con.execute("SELECT 1 FROM processing_tasks WHERE session_id=%s AND state IN ('queued','running')",(sid,)).fetchone()
            if pending:raise ValueError('Processing is still running. QA must finish before download.')
            if not sess.generation or request.query_params.get('generation_id')!=sess.generation['generation_id']:raise ValueError('Stale generation.')
            fmt=request.query_params.get('format','pptx')
            if fmt not in ('pptx','pdf'):raise ValueError('Choose PDF or PowerPoint.')
            with state.job(sess):
                data=artifact_bytes(sess,True,fmt)
                key=objects.prefix(sid)+f'exports/{sess.generation["candidate_sha256"]}.{fmt}'
                mime='application/pdf' if fmt=='pdf' else 'application/vnd.openxmlformats-officedocument.presentationml.presentation'
                objects.put(key,data,mime)
                sess.close_after=min(time.time()+600,sess.expires)
            return JSONResponse({'download_url':objects.signed_download(key,'Stevens-verified.'+fmt,mime)})
        except ValueError as exc:return JSONResponse({'detail':str(exc)},status_code=409)
    if request.method not in ('POST','PUT'):return None
    operations={('sessions','generate'):'redesign',('jobs','generate'):'author',('jobs','outline/plan'):'plan',('jobs','content'):'content'}
    operation=operations.get((kind,action))
    if not operation:return None
    raw=await request.body()
    if len(raw)>1024*1024:return JSONResponse({'detail':'Request content is too large.'},status_code=413)
    try:
        body=json.loads(raw or b'{}')
        if not isinstance(body,dict):raise ValueError('Expected a JSON object.')
        tid=tasks.enqueue(sess,operation,body,user)
        return queued(tid)
    except (ValueError,TypeError) as exc:return JSONResponse({'detail':str(exc)},status_code=409)
