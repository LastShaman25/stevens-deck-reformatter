import json
from copy import deepcopy
from types import SimpleNamespace
import pytest
import requests
from PIL import Image
from app.ai import providers, layout, pipeline, optional_review
from app import generations
from test_ai_pipeline import config, ai_session, identity_plan


@pytest.fixture
def openai_config(config,monkeypatch):
    config.write_text('OPENAI_API_KEY=sk-test-not-real\n')
    monkeypatch.delenv('STEVENS_AI_PLANNER')
    monkeypatch.delenv('STEVENS_AI_REVIEWER')
    return config


def completed(data):
    return {'status':'completed','output':[{'type':'reasoning','summary':[]},
        {'type':'message','status':'completed','role':'assistant','content':[{'type':'output_text','text':json.dumps(data)}]}],
        'usage':{'input_tokens':100,'output_tokens':50,'total_tokens':150}}


def reply(data,code=200):
    return SimpleNamespace(status_code=code,json=lambda:data)


def test_openai_default_and_no_silent_provider_fallback(openai_config,monkeypatch):
    cfg=providers.capabilities()
    assert cfg['configured'] and not cfg['independent_providers']
    assert all(cfg[r]['model']=='gpt-6-luna' and cfg[r]['provider']=='openai' for r in ('planner','reviewer'))
    openai_config.write_text('ANTHROPIC_API_KEY=test-anthropic\nGEMINI_API_KEY=test-gemini\n')
    assert not providers.capabilities()['configured']
    monkeypatch.setenv('STEVENS_OFFLINE','1')
    assert providers.generate('planner','JSON',{})['status']=='not_configured'


def test_review_reasoning_is_separate_without_changing_model(openai_config,monkeypatch):
    seen=[]
    monkeypatch.delenv('OPENAI_REVIEW_REASONING_EFFORT',raising=False)
    monkeypatch.setenv('OPENAI_REASONING_EFFORT','none')
    def post(url,**kwargs):
        seen.append(kwargs['json']);return reply(completed({'ok':True}))
    monkeypatch.setattr(providers.requests,'post',post)
    for role in ('planner','reviewer','output_qa'):providers.generate(role,'JSON',{})
    assert [r['reasoning']['effort'] for r in seen]==['none','low','low']
    assert all(r['model']=='gpt-6-luna' for r in seen)
    monkeypatch.setenv('OPENAI_REASONING_EFFORT','medium')
    assert providers.reasoning_effort('reviewer')=='medium'
    monkeypatch.setenv('OPENAI_REVIEW_REASONING_EFFORT','none')
    assert providers.reasoning_effort('reviewer')=='none'


@pytest.mark.parametrize('schema',[layout.LayoutPlan.model_json_schema(),pipeline.VisualReview.model_json_schema()])
def test_responses_request_schema_images_and_usage(openai_config,monkeypatch,tmp_path,schema):
    original=deepcopy(schema);captured={}
    path=tmp_path/'test.png';Image.new('RGB',(100,60),'white').save(path)
    def post(url,**kwargs):
        captured.update(url=url,**kwargs);return reply(completed({'ok':True}))
    monkeypatch.setattr(providers.requests,'post',post)
    result=providers.generate('planner','Return JSON',{'schema':schema},[('Original source',path),('Candidate',path)],max_tokens=16000)
    assert result['status']=='completed' and result['data']=={'ok':True}
    assert result['usage']=={'input_tokens':100,'output_tokens':50,'total_tokens':150}
    assert captured['url']=='https://api.openai.com/v1/responses'
    assert captured['headers']=={'Authorization':'Bearer sk-test-not-real'}
    body=captured['json']
    assert body['model']=='gpt-6-luna' and body['reasoning']=={'effort':'none'}
    assert body['store'] is False and body['service_tier']=='default'
    assert body['max_output_tokens']==16000 and 'temperature' not in body
    assert 'sk-test-not-real' not in json.dumps(body)
    images=[p for p in body['input'][0]['content'] if p['type']=='input_image']
    assert len(images)==2 and all(p['detail']=='high' and p['image_url'].startswith('data:image/png;base64,') for p in images)
    fmt=body['text']['format'];assert fmt['type']=='json_schema' and fmt['strict']
    def check(node):
        if isinstance(node,dict):
            assert 'default' not in node
            if node.get('type')=='object':assert set(node['required'])==set(node['properties']) and node['additionalProperties'] is False
            for child in node.values():check(child)
        elif isinstance(node,list):
            for child in node:check(child)
    check(fmt['schema']);assert schema==original


@pytest.mark.parametrize('data,status',[
    ({'status':'incomplete','incomplete_details':{'reason':'max_output_tokens'}},'truncated'),
    ({'status':'incomplete','incomplete_details':{'reason':'content_filter'}},'invalid_response'),
    ({'status':'failed','error':{'message':'private text'}},'invalid_response'),
    ({'status':'completed','output':[{'type':'message','status':'completed','content':[{'type':'refusal','refusal':'private text'}]}]},'refused'),
    ({'status':'completed','output':[{'type':'message','status':'incomplete','content':[{'type':'output_text','text':'{}'}]}]},'invalid_response'),
    ({'status':'completed','output':[]},'invalid_response'),
    ([], 'invalid_response'),
    ({'status':'completed','output':[{'type':'message','status':'completed','content':[{'type':'output_text','text':'not json'}]}]},'invalid_response'),
])
def test_noncomplete_responses_never_pass(openai_config,monkeypatch,data,status):
    monkeypatch.setattr(providers.requests,'post',lambda *a,**kw:reply(data))
    result=providers.generate('reviewer','JSON',{})
    assert result['status']==status
    assert 'private text' not in json.dumps(result)


@pytest.mark.parametrize('code,status',[(400,'invalid_request'),(401,'authentication_error'),(403,'permission_error'),(404,'model_unavailable'),(429,'rate_limited'),(500,'provider_error')])
def test_openai_http_failure_redaction(openai_config,monkeypatch,code,status):
    monkeypatch.setattr(providers.requests,'post',lambda *a,**kw:reply({'error':'sk-test-not-real'},code))
    result=providers.generate('planner','JSON',{})
    assert result['status']==status and 'sk-test-not-real' not in json.dumps(result)


def test_optional_visual_check_uses_openai(openai_config,monkeypatch,tmp_path):
    from rubric_fixtures import passed_checks
    path=tmp_path/'test.png';Image.new('RGB',(100,60),'white').save(path)
    seen=[]
    def post(url,**kw):
        seen.append(kw['json']['model'])
        return reply(completed({'verdict':'passed','summary':'Readable synthetic image','findings':[],'rubric':passed_checks()}))
    monkeypatch.setattr(providers.requests,'post',post)
    result=optional_review.review_slide_result(str(path))
    assert result['status']=='completed' and result['provider']=='openai' and result['findings']==[]
    assert seen==['gpt-6-luna']


def test_generation_through_actual_openai_adapter(ai_session,monkeypatch):
    from rubric_fixtures import role_map, passed_checks, source_choice
    # The HTTP boundary is mocked; the adapter, schema and pipeline are real.
    monkeypatch.setenv('OPENAI_API_KEY','sk-test-not-real')
    monkeypatch.setenv('STEVENS_AI_PLANNER','openai');monkeypatch.setenv('STEVENS_AI_REVIEWER','openai')
    # ai_session replaces generate; restore its actual implementation without
    # reloading module configuration or reading any real user credentials.
    real_generate=ORIGINAL_GENERATE
    monkeypatch.setattr(providers,'generate',real_generate)
    def post(url,**kw):
        assert url=='https://api.openai.com/v1/responses'
        request=kw['json'];payload=json.loads(request['input'][0]['content'][0]['text'])
        value=role_map(payload['objects']) if payload.get('stage') in ('identify_elements','source_decisions') else identity_plan(payload['objects']) if 'objects' in payload else {'verdict':'passed','summary':'Synthetic review','findings':[],'rubric':passed_checks()}
        if payload.get('stage')=='source_decisions':value=source_choice(payload)
        if 'objects' in value:
            for obj in value['objects']:obj.update(role='keep',font_size=None,color='keep')
        return reply(completed(value))
    monkeypatch.setattr(providers.requests,'post',post)
    r=generations.build(ai_session,mode='ai',repair_passes=0)
    assert r['checks']['ai_redesign']['status']=='passed',r['findings']
    assert r['checks']['ai_visual_review']['status']=='passed'
    assert all(c['provider']=='openai' and c['model']=='gpt-6-luna' for c in r['ai_pipeline']['calls'])
    assert len(r['ai_pipeline']['calls'])==6


ORIGINAL_GENERATE=providers.generate
