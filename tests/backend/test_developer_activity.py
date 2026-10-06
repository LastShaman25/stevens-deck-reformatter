import json
import pytest
from fastapi.testclient import TestClient
from app import auth, activity
from app.main import app
from app.ai import providers
from test_implementation import isolation, login


def test_developer_role_logs_without_admin_or_private_deck_access(monkeypatch):
    admin=login('admin')
    issued=admin.post('/api/admin/codes',json={'name':'Developer','role':'developer'})
    assert issued.status_code==200
    dev=login(issued.json()['code'])
    member=login(admin.post('/api/admin/codes',json={'name':'Member','role':'member'}).json()['code'])
    assert dev.get('/api/admin/users').status_code==403
    assert member.get('/api/developer/activity').status_code==403
    job=member.post('/api/jobs',json={'topic':'private content','audience':'test'}).json()['id']
    assert dev.get('/api/jobs/'+job).status_code==404
    with auth.database() as con:
        owner=con.execute("SELECT id FROM users WHERE email='Member'").fetchone()['id']
    token=auth.current_user.set({'id':owner})
    try:
        activity.emit('reviewer','model_request','completed',model='test-model',duration_ms=120,
            prompt='private content',key='secret-key',response='private reply')
    finally:auth.current_user.reset(token)
    response=dev.get('/api/developer/activity')
    assert response.status_code==200
    events=response.json()['events']
    assert events[-1]['timestamp'].endswith('+00:00')
    assert events[-1]['model']=='test-model' and events[-1]['duration_ms']==120
    assert all(v not in response.text for v in ('private content','secret-key','private reply'))
    assert admin.get('/api/developer/activity').status_code==200
    # Fresh role authorization is checked on every request; revocation invalidates cookies.
    uid=dev.get('/api/auth/status').json()['user']['id']
    assert admin.patch('/api/admin/users/'+uid,json={'role':'member','active':True}).status_code==200
    assert dev.get('/api/developer/activity').status_code==401


def test_provider_attempt_events_and_retention(monkeypatch):
    admin=login('admin')
    uid=admin.get('/api/auth/status').json()['user']['id']
    token=auth.current_user.set({'id':uid})
    monkeypatch.setattr(providers,'_generate_once',lambda *a,**k:{'status':'timeout'})
    try:providers.generate('reviewer','private system',{'secret':'private prompt'})
    finally:auth.current_user.reset(token)
    events=admin.get('/api/developer/activity').json()['events']
    assert len([e for e in events if e['action']=='request_attempt' and e['status']=='started'])==2
    assert events[-1]['status']=='timeout' and 'duration_ms' in events[-1]
    assert 'private' not in json.dumps(events)
    with auth.database() as con:
        con.execute('UPDATE activity_events SET stamp=0')
    assert admin.get('/api/developer/activity').json()['events']==[]


def test_generation_failure_logs_type_without_private_exception_text():
    admin=login('admin');uid=admin.get('/api/auth/status').json()['user']['id']
    token=auth.current_user.set({'id':uid})
    @activity.operation('author','generate_deck')
    def fail(sess):raise ValueError('private document content')
    try:
        with pytest.raises(ValueError):fail(None)
    finally:auth.current_user.reset(token)
    value=admin.get('/api/developer/activity')
    event=value.json()['events'][-1]
    assert event['status']=='error' and event['error_type']=='ValueError'
    assert 'duration_ms' in event
    assert 'private document content' not in value.text

@pytest.mark.parametrize('usage,expected',[
    ({'input_tokens':100,'output_tokens':20,'total_tokens':120},(100,20,120)),
    ({'prompt_tokens':100,'completion_tokens':20,'total_tokens':120},(100,20,120)),
    ({'input_tokens':10,'output_tokens':20,'cache_read_input_tokens':70,'cache_creation_input_tokens':20},(100,20,120)),
    ({'promptTokenCount':100,'candidatesTokenCount':10,'thoughtsTokenCount':10,'totalTokenCount':120},(100,20,120)),
])
def test_provider_token_categories(usage,expected):
    result=providers.usage_counts(usage)
    assert tuple(result[k] for k in ('input_tokens','output_tokens','tokens'))==expected
    assert providers.usage_counts({})=={}


def test_job_summary_counts_retry_usage_once_and_excludes_approval_wait(monkeypatch):
    from types import SimpleNamespace
    from app.sessions import active_session
    admin=login('admin');uid=admin.get('/api/auth/status').json()['user']['id']
    member=login(admin.post('/api/admin/codes',json={'name':'Member','role':'member'}).json()['code'])
    assert member.get('/api/developer/jobs').status_code==403
    sess=SimpleNamespace(id='job-retry',owner_user_id=uid,workflow='preserve',original_name='private.pdf',template_id='cpe')
    clock=[activity.time.time()]
    monkeypatch.setattr(activity.time,'time',lambda:clock[0])
    token=active_session.set(sess)
    responses=iter([
        {'status':'invalid_response','failure_stage':'structured_output','usage':{'prompt_tokens':100,'completion_tokens':10,'total_tokens':110}},
        {'status':'completed','usage':{'prompt_tokens':200,'completion_tokens':20,'total_tokens':220}},
    ])
    monkeypatch.setattr(providers,'_generate_once',lambda *a,**k:next(responses))
    try:
        activity.emit('planner','plan_outline',scope='job_operation',operation_id='plan')
        clock[0]+=2
        activity.emit('planner','plan_outline','completed',scope='job_operation',operation_id='plan',duration_ms=2000)
        clock[0]+=600 # Human approval is not processing time.
        activity.emit('formatter','format_deck',scope='job_operation',operation_id='format')
        providers.generate('reviewer','private input',{})
        activity.emit('reviewer','model_step','replayed',tokens=330,input_tokens=300,output_tokens=30)
        clock[0]+=3
        activity.emit('formatter','format_deck','completed',scope='job_operation',operation_id='format',duration_ms=3000)
    finally:active_session.reset(token)
    result=admin.get('/api/developer/jobs')
    assert result.status_code==200 and 'private' not in result.text
    summary=next(j for j in result.json()['jobs'] if j['job_id']==sess.id)
    assert summary['tokens']==330 and summary['input_tokens']==300 and summary['output_tokens']==30
    assert summary['requests']==2 and summary['usage_complete']
    assert summary['duration_ms']==5000 and summary['status']=='completed'
    assert summary['input_category']=='pdf' and summary['output_category']=='pptx / pdf'
    assert summary['template_id']=='cpe'
    # Summary is independent of the detail page size.
    page=admin.get('/api/developer/activity',params={'job_id':sess.id,'limit':2}).json()
    assert len(page['events'])==2 and page['next_before'] is not None
    older=admin.get('/api/developer/activity',params={'job_id':sess.id,'limit':500,'before':page['next_before']}).json()
    assert not set(e['id'] for e in page['events']) & set(e['id'] for e in older['events'])
    assert all(e['job_id']==sess.id for e in older['events'])
    assert len(older['events'])+len(page['events'])==summary['event_count']
    assert admin.get('/api/developer/activity',params={'before':'invalid'}).status_code==400


def test_summary_overlapping_operations_and_legacy_unknown():
    def event(second,action,status,op=None,**extra):
        return {'id':str(second),'job_id':'job','timestamp':f'2026-10-02T00:00:{second:02d}+00:00',
                'agent':'test','action':action,'status':status,**({'scope':'job_operation','operation_id':op} if op else {}),**extra}
    items=[event(0,'generate_deck','started','a'),event(1,'render','started','b'),event(3,'render','completed','b'),
           event(5,'generate_deck','completed','a'),event(6,'model_step','completed',tokens=900)]
    summary=activity.summarize(items)
    assert summary['duration_ms']==5000 and summary['tokens'] is None
    legacy=activity.summarize([event(6,'model_step','completed',tokens=900)])
    assert legacy['duration_ms'] is None and legacy['input_tokens'] is None


@pytest.mark.parametrize('digest,state,expected',[(None,'error','error'),('hash','error','completed_with_findings'),('hash','ready','completed')])
def test_caught_generation_outcome_is_logged_truthfully(digest,state,expected):
    from types import SimpleNamespace
    admin=login('admin');uid=admin.get('/api/auth/status').json()['user']['id']
    sess=SimpleNamespace(id='caught-outcome',owner_user_id=uid,generation=None)
    @activity.operation('formatter','format_deck')
    def build(sess):
        sess.generation={'candidate_sha256':digest,'state':state,'processing_complete':True}
        return sess.generation
    build(sess)
    result=admin.get('/api/developer/jobs').json()['jobs'][0]
    assert result['status']==expected
