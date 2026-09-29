"""One replayable slice; launched in an isolated process by the shared queue."""
import json
import os
import sys
import time
from . import db, objects, replay, state, tasks


def dispatch(sess, operation, body):
    from .. import api, generations
    from ..authoring import service
    from ..authoring.models import DeckSpec
    if operation=='import':
        return api.analyze_into(sess,body['filename'],objects.get(body['key']))
    if operation=='pdf':
        if sess.creation['approved_hash']:raise ValueError('Start a new job to replace an approved source.')
        service.ingest_pdf(sess,objects.get(body['key']))
        return service.public(sess)
    if operation=='plan':return service.plan(sess)
    if operation=='author':return service.generate(sess)
    if operation=='content':
        if body['revision']!=sess.revision_version:raise ValueError('Content revision changed.')
        sess.revision_version+=1;sess.generation=None
        return service.generate(sess,DeckSpec.model_validate(body['deck']),content_edit=True)
    if operation=='redesign':
        options=generations.GenerateRequest.model_validate(body)
        if options.mode!='ai':raise ValueError('Redesign and mandatory QA are required.')
        record=generations.build(sess,mode='ai',repair_passes=options.repair_passes)
        return {'ok':record['state']!='error','generation':generations.public(record),
                'built_slides':(record.get('report') or {}).get('slide_count',0)}
    raise ValueError('Unsupported durable operation.')


def run(tid, lease):
    from .. import auth, sessions
    from ..ai import providers
    task=tasks.get(tid)
    if not task or task['lease']!=lease:return 1
    tasks.fence(tid,lease)
    if providers.capabilities()!=task['configuration']:
        with db.connect() as con:con.execute("UPDATE processing_tasks SET state='failed',error='Model configuration changed; start a fresh operation.' WHERE id=%s AND lease=%s",(tid,lease))
        return 1
    os.environ['STEVENS_AI_REQUEST_TIMEOUT']='60'
    # Request timeout and render timeout fit the finite worker invocation.
    os.environ['STEVENS_RENDER_TIMEOUT']='90'
    with state.scope() as cache:
        live=state.row(task['session_id'])
        sess=state.decode({**live,'state':task['baseline'],'snapshot':task['snapshot']})
        cache[sess.id]=sess
        state.materialize(sess)
        user_token=auth.current_user.set({'id':task['owner_id'],'token':task['login_id']})
        work_token=state.worker.set(task)
        active_token=sessions.active_session.set(sess)
        replay_token=replay.current.set(replay.Replay(task,sess))
        try:
            result=dispatch(sess,task['operation'],task['body'])
            tasks.fence(tid,lease)
            # Candidate identity and successful task completion commit together.
            state.save(sess,lease,completed_task=tid,result=result)
            return 0
        except replay.SliceComplete:return 75
        except Exception as exc:
            # Never publish a partial/replayed candidate after an execution error.
            message=str(exc)[:500] if isinstance(exc,ValueError) else f'Processing failed ({type(exc).__name__}); QA did not authorize release.'
            with db.connect() as con:
                con.execute("UPDATE processing_tasks SET state='failed',error=%s,updated=%s WHERE id=%s AND lease=%s AND state='running'",(message,time.time(),tid,lease))
            return 1
        finally:
            replay.current.reset(replay_token);sessions.active_session.reset(active_token)
            state.worker.reset(work_token);auth.current_user.reset(user_token)


if __name__=='__main__':raise SystemExit(run(*sys.argv[1:3]))
