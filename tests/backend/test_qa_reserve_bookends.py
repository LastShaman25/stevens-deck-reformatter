import pytest
from pptx import Presentation
from app import sessions, generations
from app.ai import providers, output_qa, pipeline
from app.authoring import service, composer
from app.authoring.models import CreationRequest, Outline, OutlineSlide, SlideSpec, DeckSpec
from test_ai_pipeline import ai_session, config
from test_openai import openai_config, reply, completed
from test_implementation import qa_fixture
from rubric_fixtures import qa_review

REAL_QA = output_qa.run


@pytest.fixture(autouse=True)
def isolated_sessions(tmp_path, monkeypatch):
    root=tmp_path/'sessions'; root.mkdir()
    monkeypatch.setattr(sessions, '_ROOT', str(root))
    monkeypatch.setattr(sessions, '_sessions', {})
    yield
    for sid in list(sessions._sessions): sessions.delete(sid)


def test_planning_cannot_consume_ordered_qa_reserve(openai_config, monkeypatch):
    monkeypatch.setenv('STEVENS_AI_MAX_TOKENS','500000')
    sess=sessions.create()
    providers.reserve_output_qa(sess, 16)
    sess.tokens=500000-sess.qa_token_reserve-100
    sent=[]
    monkeypatch.setattr(providers.requests,'post',lambda *a,**kw: (sent.append(True) or reply(completed({'ok':True}))))
    token=sessions.active_session.set(sess)
    try:
        assert providers.generate('planner','JSON',{})['status']=='budget_exceeded'
        assert not sent
        assert providers.generate('output_qa','JSON',{},max_tokens=12000)['status']=='completed'
        assert sent
        sess.tokens=499999
        assert providers.generate('output_qa','JSON',{})['status']=='budget_exceeded'
        assert len(sent)==1  # The reserve never bypasses the upload cap.
    finally: sessions.active_session.reset(token)


def test_cumulative_limits_are_opt_in(monkeypatch):
    sess=sessions.create()
    monkeypatch.setattr(providers,'ENV_FILE',__import__('pathlib').Path(sess.dir)/'absent.env')
    monkeypatch.delenv('STEVENS_AI_MAX_TOKENS',raising=False)
    monkeypatch.delenv('STEVENS_AI_MAX_CALLS',raising=False)
    providers.reserve_output_qa(sess,100,redesign=True)
    assert providers.token_limit(sess) is None
    assert providers.request_limit() is None
    monkeypatch.setenv('STEVENS_AI_MAX_TOKENS','500000')
    providers.reserve_output_qa(sess,16,redesign=True)
    assert providers.token_limit(sess)==500000


@pytest.mark.parametrize('role',['planner','reviewer','output_qa'])
def test_unlimited_admission_above_previous_caps(openai_config,monkeypatch,role):
    monkeypatch.setenv('STEVENS_AI_MAX_TOKENS','0')
    monkeypatch.setenv('STEVENS_AI_MAX_CALLS','0')
    sess=sessions.create(); providers.reserve_output_qa(sess,17,redesign=True)
    sess.tokens=5000000; sess.calls=600
    sent=[]
    monkeypatch.setattr(providers.requests,'post',lambda *a,**kw:(sent.append(True) or reply(completed({'ok':True}))))
    token=sessions.active_session.set(sess)
    try:
        assert providers.generate(role,'JSON',{})['status']=='completed'
        assert sent and sess.calls==601
    finally:sessions.active_session.reset(token)


def test_redesign_review_continues_after_one_slide_response_errors(ai_session, monkeypatch):
    from test_ai_pipeline import mocked_provider
    reviewed=[]
    def provider(role,system,payload,*a,**kw):
        if role=='reviewer':
            reviewed.append(len(reviewed))
            if len(reviewed)==1: return {'status':'timeout','message':'Synthetic first-slide review timeout'}
        return mocked_provider(role,system,payload,*a,**kw)
    monkeypatch.setattr(providers,'generate',provider)
    record=generations.build(ai_session,mode='ai',repair_passes=0)
    assert len(reviewed)>=len(Presentation(ai_session.source_path).slides)
    assert record['checks']['ai_visual_review']['status']=='error'
    assert record['checks']['output_qa_coverage']['status']=='passed'
    assert generations.download_allowed(record)
    assert not generations.checks_satisfied(record)


def test_qa_retries_invalid_coverage_and_keeps_partial_ledger(tmp_path, monkeypatch):
    sess=sessions.create(); record=qa_fixture(tmp_path,6); calls=[]
    def provider(role,system,payload,**kw):
        calls.append(payload['stage'])
        result=qa_review(payload)
        if len(calls)==1: result['reviewed'].pop()
        elif len(calls)==2: assert 'validation_error' in payload
        if payload['stage']=='deck_synthesis': return {'status':'timeout','message':'Synthetic timeout'}
        return {'status':'completed','data':result}
    monkeypatch.setattr(providers,'generate',provider)
    checks=REAL_QA(sess,record)
    assert checks['output_qa_coverage']['status']=='error'
    assert len(record['output_qa']['batches'])==2
    assert len(record['output_qa_calls'])==4
    assert len(record['output_qa_validation_errors'])==1


def test_ordered_qa_runs_when_earlier_visual_agent_errors(ai_session, monkeypatch):
    execute=pipeline.execute
    def failure(*a,**kw):
        report,checks,details=execute(*a,**kw)
        checks['ai_redesign']={'status':'error','findings':[]}
        checks['ai_visual_review']={'status':'error','findings':[]}
        return report,checks,details
    monkeypatch.setattr(pipeline,'execute',failure)
    calls=[]
    monkeypatch.setattr(output_qa,'run',lambda *a: (calls.append(True) or {n:{'status':'passed','findings':[]} for n in output_qa.CHECKS+('output_qa_visual',)}))
    record=generations.build(ai_session,mode='ai',repair_passes=0)
    assert calls and record['checks']['output_qa_visual']['status']=='passed'
    assert generations.download_allowed(record)
    assert not generations.checks_satisfied(record)


def test_bookends_are_approved_and_native_layouts_are_audited(tmp_path):
    outline=Outline(title='Functions',rationale='Brief',slides=[OutlineSlide(id='lesson',title='Sine',points=['A periodic function'])])
    outline=service.with_bookends(outline)
    assert [s.kind for s in outline.slides]==['opening','content','closing']
    assert service.with_bookends(outline)==outline
    sess=service.create(CreationRequest(topic='Functions',audience='Students'))
    service.save_outline(sess,outline,0);service.approve(sess,1)
    with pytest.raises(ValueError,match='opening slide first'):
        service.save_outline(sess,outline.model_copy(update={'slides':outline.slides[1:]}),1)
    deck=DeckSpec(slides=[SlideSpec(id=s.id,title=s.title,bullets=s.points) for s in outline.slides])
    candidate=tmp_path/'bookends.pptx'
    manifest=composer.compose(deck,candidate,tmp_path/'assets',kinds=[s.kind for s in outline.slides])
    assert [s.slide_layout.name for s in Presentation(candidate).slides]==['Title Slide','Title Only','1_Title Slide']
    assert composer.audit(candidate,manifest)['status']=='passed'
    manifest[-1]['layout']='Title Only'
    assert composer.audit(candidate,manifest)['status']=='failed'
