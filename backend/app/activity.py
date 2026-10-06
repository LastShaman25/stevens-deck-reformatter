"""Developer-visible execution metadata. No prompts, responses, paths or keys."""
import json
import time
import uuid
import logging
from contextlib import contextmanager
from functools import wraps
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Request, Query

router=APIRouter(prefix='/api/developer')
FIELDS={'model','provider','attempt','duration_ms','tokens','input_tokens','output_tokens','slides','template_id','http_status','error_type',
        'scope','operation_id','input_category','output_category','workflow'}

def emit(agent,action,status='started',sess=None,**details):
    from .auth import database, current_user
    from .sessions import active_session
    sess=sess or active_session.get()
    user=current_user.get() or {}
    owner=getattr(sess,'owner_user_id',None) or user.get('id')
    if not owner:return
    stamp=time.time()
    # Only call-site labels and an allowlist of operational metadata enter storage.
    metadata={}
    if sess:
        creation=getattr(sess,'creation',None)
        source=(creation or {}).get('request',{}).get('source')
        metadata={'workflow':'generate' if getattr(sess,'workflow','')=='author' else 'reformat',
                  'input_category':('idea' if source=='topic' else source) if source else
                      ('pdf' if getattr(sess,'original_name','').lower().endswith('.pdf') else 'pptx'),
                  'output_category':'pptx / pdf','template_id':getattr(sess,'template_id','stevens')}
    event={'id':uuid.uuid4().hex,'timestamp':datetime.fromtimestamp(stamp,timezone.utc).isoformat(),
        'job_id':getattr(sess,'id',None),'agent':agent,'action':action,'status':status,
        **metadata,
        **{k:v for k,v in details.items() if k in FIELDS and isinstance(v,(str,int,float))}}
    try:
        with database() as con:
            if not con.execute('SELECT 1 FROM users WHERE id=?',(owner,)).fetchone():return
            con.execute('DELETE FROM activity_events WHERE stamp<?',(stamp-86400,))
            con.execute('INSERT INTO activity_events (id,owner_id,job_id,stamp,event) VALUES (?,?,?,?,?)',
                        (event['id'],owner,event['job_id'],stamp,json.dumps(event)))
    except Exception:
        logging.getLogger(__name__).warning('Could not persist activity event.')

@contextmanager
def stage(agent,action,sess=None,**details):
    details={'operation_id':uuid.uuid4().hex,**details}
    start=time.monotonic();emit(agent,action,sess=sess,**details)
    outcome={}
    try:yield outcome
    except BaseException as exc:
        emit(agent,action,'paused' if type(exc).__name__=='SliceComplete' else 'error',sess,error_type=type(exc).__name__, duration_ms=round((time.monotonic()-start)*1000),**details)
        raise
    else:emit(agent,action,outcome.get('status','completed'),sess,duration_ms=round((time.monotonic()-start)*1000),**details)


def operation(agent,action):
    def decorate(fn):
        @wraps(fn)
        def run(sess,*args,**kwargs):
            with stage(agent,action,sess,scope='job_operation') as outcome:
                result=fn(sess,*args,**kwargs)
                record=getattr(sess,'generation',None)
                if action in ('format_deck','generate_deck') and record:
                    outcome['status']=('error' if not record.get('candidate_sha256') else
                        'completed' if record.get('state')=='ready' else 'completed_with_findings')
                return result
        return run
    return decorate


def _authorize(request):
    if request.state.user['role'] not in ('developer','admin'):
        raise HTTPException(403,'Developer access required.')


def summarize(items,now=None):
    """Aggregate all retained events, never the paginated detail window.

    Request attempts own usage. Model-step summaries and cached replay never
    add it again. Unknown historical usage stays unknown rather than zero.
    """
    now=now or time.time()
    first,last=items[0],items[-1]
    starts={}; intervals=[]; terminal=None
    for e in items:
        if e.get('scope')!='job_operation':continue
        key=e.get('operation_id',e['action'])
        stamp=datetime.fromisoformat(e['timestamp']).timestamp()
        if e['status']=='started':starts[key]=stamp;terminal='running'
        else:
            start=starts.pop(key,stamp-e.get('duration_ms',0)/1000)
            intervals.append((start,stamp));terminal=e['status']
            if terminal=='completed' and e['action']=='plan_outline':terminal='awaiting approval'
            elif terminal=='completed' and e['action'] in ('import_deck','import_pdf'):terminal='ready'
    intervals.extend((start,now) for start in starts.values())
    # Nested/overlapping work contributes wall time only once; approval idle time is excluded.
    merged=[]
    for start,end in sorted(intervals):
        if merged and start<=merged[-1][1]:merged[-1]=(merged[-1][0],max(end,merged[-1][1]))
        else:merged.append((start,end))
    requests=[e for e in items if e['action']=='request_attempt' and e['status']!='started']
    def total(key):
        values=[e[key] for e in requests if key in e]
        return sum(values) if values else None
    meta=next((e for e in reversed(items) if e.get('workflow')),last)
    return {'job_id':first['job_id'],'started_at':first['timestamp'],'updated_at':last['timestamp'],
            'status':'running' if starts else terminal or ('created' if first['action']=='job_created' else 'recorded'),
            'duration_ms':round(sum(end-start for start,end in merged)*1000) if intervals else None,
            'workflow':meta.get('workflow','not recorded' if first['job_id'] else 'connection test'),
            'input_category':meta.get('input_category','not recorded' if first['job_id'] else 'text'),
            'output_category':meta.get('output_category','not recorded' if first['job_id'] else 'structured JSON'),
            'template_id':meta.get('template_id'),
            'requests':len(requests),'tokens':total('tokens'),'input_tokens':total('input_tokens'),'output_tokens':total('output_tokens'),
            'usage_complete':bool(requests) and all('input_tokens' in e and 'output_tokens' in e for e in requests),
            'event_count':len(items)}


@router.get('/jobs')
def jobs(request:Request):
    from .auth import database
    _authorize(request)
    with database() as con:
        con.execute('DELETE FROM activity_events WHERE stamp<?',(time.time()-86400,))
        rows=con.execute('SELECT event FROM activity_events ORDER BY stamp ASC').fetchall()
    grouped={}
    for row in rows:
        e=json.loads(row['event'])
        grouped.setdefault(e['job_id'],[]).append(e)
    return {'jobs':sorted((summarize(items) for items in grouped.values()),key=lambda j:j['updated_at'],reverse=True),
            'retention_hours':24}

@router.get('/activity')
def events(request:Request,job_id:str|None=Query(default=None,max_length=64),limit:int=Query(default=200,ge=1,le=500),
           before:str|None=Query(default=None,max_length=128),unassigned:bool=False):
    from .auth import database
    _authorize(request)
    with database() as con:
        con.execute('DELETE FROM activity_events WHERE stamp<?',(time.time()-86400,))
        clauses=[];args=[]
        if job_id:clauses.append('job_id=?');args.append(job_id)
        elif unassigned:clauses.append('job_id IS NULL')
        if before is not None:
            try:
                stamp,eid=json.loads(before)
                if not isinstance(stamp,(int,float)) or not isinstance(eid,str):raise ValueError()
            except (ValueError,TypeError):raise HTTPException(400,'Invalid activity cursor.')
            clauses.append('(stamp<? OR (stamp=? AND id<?))');args.extend((stamp,stamp,eid))
        where=' WHERE '+' AND '.join(clauses) if clauses else ''
        rows=con.execute('SELECT id,event,stamp FROM activity_events'+where+' ORDER BY stamp DESC,id DESC LIMIT ?',(*args,limit+1)).fetchall()
    more=len(rows)>limit;rows=rows[:limit]
    return {'events':[json.loads(row['event']) for row in reversed(rows)],'retention_hours':24,
            'next_before':json.dumps([rows[-1]['stamp'],rows[-1]['id']]) if more else None}
