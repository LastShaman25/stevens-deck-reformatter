import json
from copy import deepcopy
import pytest
from fastapi.testclient import TestClient
from app import generations, api
from app.main import app
from app.ai import providers
from test_ai_pipeline import ai_session, config
from test_openai import openai_config, reply, completed


@pytest.mark.parametrize('check',['ai_redesign','ai_visual_review','output_qa_coverage','output_qa_sequence','output_qa_accuracy','output_qa_visual','render_verification'])
@pytest.mark.parametrize('state',['not_run','error','failed','checking','needs_review'])
def test_no_download_bypass_for_unfinished_or_failed_checks(ai_session,check,state):
    record=generations.build(ai_session,mode='ai')
    record['checks'][check]={'status':state,'findings':[]}
    # Even stale readiness and draft=true cannot bypass the backend gate.
    record['state']='ready'
    client=TestClient(app)
    for format in ('pptx','pdf'):
        for draft in (False,True):
            r=client.get(f'/api/sessions/{ai_session.id}/download',params={
                'generation_id':record['generation_id'],'format':format,'draft':draft})
            assert r.status_code==409
    assert not generations.public(record)['download_allowed']


@pytest.mark.parametrize('check',generations.QA_REQUIRED)
def test_manual_approval_never_clears_qa_review(check):
    record={'mode':'ai','state':'ready','checks':{},'findings':[],
            'human_decisions':[{'finding_ids':['qa:0']}]}
    record['checks']={n:{'status':'passed','findings':[]} for n in generations.required_checks(record)}
    finding={'id':'qa:0','severity':'review','check':check}
    record['findings']=[finding]
    record['checks'][check]={'status':'needs_review','findings':[finding]}
    assert not generations.can_approve(record,finding)
    generations.settle(record)
    assert record['state']=='needs_review'
    assert not generations.download_allowed(record)


def test_malformed_json_retry_is_bounded_and_does_not_accept_bad_output(openai_config,monkeypatch):
    seen=[]
    def post(*a,**kw):
        seen.append(kw)
        data=completed({'ok':True})
        if len(seen)==1:data['output'][1]['content'][0]['text']='{"ok":'
        return reply(data)
    monkeypatch.setattr(providers.requests,'post',post)
    r=providers.generate('reviewer','JSON',{})
    assert r['status']=='completed' and r['data']=={'ok':True}
    assert r['attempt_statuses']==['invalid_response','completed']
    seen.clear()
    def always_bad(*a,**kw):
        seen.append(kw);data=completed({});data['output'][1]['content'][0]['text']='private-source-not-json'
        return reply(data)
    monkeypatch.setattr(providers.requests,'post',always_bad)
    r=providers.generate('reviewer','JSON',{})
    assert r['status']=='invalid_response' and len(seen)==2
    assert r['failure_stage']=='structured_output'
    assert 'private-source-not-json' not in json.dumps(r)


def test_invalid_local_input_is_not_retried(openai_config,monkeypatch,tmp_path):
    monkeypatch.setattr(providers.requests,'post',lambda *a,**kw:pytest.fail('Must not send invalid input'))
    r=providers.generate('planner','JSON',{},images=[('missing',tmp_path/'missing.png')])
    assert r['failure_stage']=='request_preparation' and r['request_attempts']==1
