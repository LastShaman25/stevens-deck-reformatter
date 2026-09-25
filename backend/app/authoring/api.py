from pathlib import Path
from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool
from pydantic import BaseModel
from .models import CreationRequest, Outline, DeckSpec
from . import service
from .. import sessions, generations
from ..api import artifact_bytes

router = APIRouter(prefix='/api/jobs')


def job(sid):
    sess = sessions.get(sid)
    if not sess or not sess.creation: raise HTTPException(404, 'Creation job not found or expired.')
    return sess


def action(sid, fn):
    sess = job(sid)
    try:
        with sessions.job(sess):
            sess.creation['error'] = None
            result = fn(sess)
            return result if result is not None else service.public(sess)
    except ValueError as exc:
        if sess.lifecycle == 'active': sess.creation['error'] = str(exc)
        raise HTTPException(409, str(exc))


@router.post('')
def create(body: CreationRequest):
    try: return service.public(service.create(body))
    except ValueError as exc: raise HTTPException(409, str(exc))


@router.get('/{sid}')
def status(sid: str):
    return service.public(job(sid))


@router.post('/{sid}/pdf')
async def upload_pdf(sid: str, file: UploadFile = File(...)):
    data = await file.read(50*1024*1024+1)
    def ingest(sess):
        if sess.creation['approved_hash']: raise ValueError('Start a new job to replace an approved source.')
        service.ingest_pdf(sess, data)
        return service.public(sess)
    return await run_in_threadpool(action, sid, ingest)


@router.get('/{sid}/source/{page}')
def source_preview(sid: str, page: int):
    sess = job(sid)
    with sessions.read_job(sess):
        item = next((p for p in sess.creation['pages'] if p['page'] == page), None)
        if not item: raise HTTPException(404, 'Source page not found.')
        return Response(Path(item['image']).read_bytes(), media_type='image/png')


@router.post('/{sid}/outline/plan')
def plan(sid: str):
    return action(sid, service.plan)


class OutlineEdit(BaseModel):
    revision: int
    outline: Outline


@router.put('/{sid}/outline')
def update_outline(sid: str, body: OutlineEdit):
    return action(sid, lambda sess: service.save_outline(sess, body.outline, body.revision))


class Approval(BaseModel):
    revision: int
    acknowledge_uncertainty: bool = False


@router.post('/{sid}/outline/approve')
def approve(sid: str, body: Approval):
    return action(sid, lambda sess: service.approve(sess, body.revision, body.acknowledge_uncertainty))


@router.post('/{sid}/generate')
def generate(sid: str):
    return action(sid, service.generate)


class ContentEdit(BaseModel):
    revision: int
    deck: DeckSpec


@router.put('/{sid}/content')
def edit_content(sid: str, body: ContentEdit):
    def regenerate(sess):
        if body.revision != sess.revision_version: raise ValueError('Content changed. Reload before editing.')
        sess.revision_version += 1
        sess.generation = None
        return service.generate(sess, body.deck)
    return action(sid, regenerate)


@router.post('/{sid}/decisions')
def decide(sid: str, body: generations.Decision):
    def apply(sess):
        generations.decide(sess, body)
        return service.public(sess)
    return action(sid, apply)


@router.get('/{sid}/preview/{index}')
def preview(sid: str, index: int, generation_id: str):
    sess = job(sid)
    try:
        with sessions.read_job(sess):
            record = sess.generation
            if not record or record['generation_id'] != generation_id: raise ValueError('Stale candidate.')
            generations.verify_identity(sess, record, ready=False)
            if not 0 <= index < record['report']['slide_count']: raise HTTPException(404, 'Slide not found.')
            path = Path(record['directory'], 'render', f'slide-{index}.png')
            if not path.is_file(): raise HTTPException(404, 'Rendered preview unavailable.')
            return Response(path.read_bytes(), media_type='image/png')
    except ValueError as exc: raise HTTPException(409, str(exc))


@router.get('/{sid}/download')
def download(sid: str, generation_id: str, draft: bool=False):
    sess = job(sid)
    try:
        with sessions.read_job(sess):
            if not sess.generation or sess.generation['generation_id'] != generation_id: raise ValueError('Stale candidate.')
            data = artifact_bytes(sess, ready=not draft)
            sess.close_after = min(__import__('time').time()+600, sess.expires)
            return Response(data, media_type='application/vnd.openxmlformats-officedocument.presentationml.presentation',
                headers={'Content-Disposition':'attachment; filename="Stevens-presentation.pptx"'})
    except ValueError as exc: raise HTTPException(409, str(exc))


@router.post('/{sid}/finalize')
@router.post('/{sid}/cancel')
@router.delete('/{sid}')
def finish(sid: str):
    deleted = sessions.delete(sid)
    return {'deleted':deleted, 'status':'purged' if deleted else 'deletion_pending'}


@router.get('/{sid}/lifecycle')
def lifecycle(sid: str):
    sess = sessions._sessions.get(sid)
    return {'status':sess.lifecycle if sess else 'purged'}
