import json
from types import SimpleNamespace
import pytest
from PIL import Image
from app.ai import providers, pipeline
from test_ai_pipeline import config


@pytest.fixture
def gateway(config,monkeypatch):
    config.write_text('AI_GATEWAY_API_KEY=vck-test-secret\nSTEVENS_AI_PROVIDER=vercel\n')
    monkeypatch.delenv('STEVENS_AI_PLANNER');monkeypatch.delenv('STEVENS_AI_REVIEWER')
    return config


def response(content='{"ok":true}',finish='stop',**message):
    return {'choices':[{'finish_reason':finish,'message':{'content':content,**message}}],
            'usage':{'prompt_tokens':120,'completion_tokens':40,'total_tokens':160}}


def test_gateway_environment_selection_refresh_and_no_fallback(gateway,monkeypatch):
    assert providers.role_config('author')['model']=='anthropic/claude-sonnet-5.5'
    assert providers.role_config('output_qa')['model']=='anthropic/claude-opus-5.5-fast'
    monkeypatch.setenv('STEVENS_AI_MODEL','openai/gpt-6-sol-fast')
    assert providers.role_config('planner')['model']=='openai/gpt-6-sol-fast'
    monkeypatch.setenv('STEVENS_AI_REVIEWER_MODEL','spacexai/grok-4.7')
    assert providers.role_config('reviewer')['model']=='spacexai/grok-4.7'
    assert providers.capabilities()['independent_providers']
    gateway.write_text('OPENAI_API_KEY=sk-test\nSTEVENS_AI_PROVIDER=vercel\n')
    assert not providers.capabilities()['configured']


def test_gateway_wire_format_images_schema_and_secret_redaction(gateway,monkeypatch,tmp_path):
    path=tmp_path/'image.png';Image.new('RGB',(50,30),'white').save(path)
    seen={}
    def post(url,**kw):
        seen.update(url=url,**kw)
        return SimpleNamespace(status_code=200,json=lambda:response())
    monkeypatch.setattr(providers.requests,'post',post)
    result=providers.generate('reviewer','Return JSON',{'schema':pipeline.VisualReview.model_json_schema()},[('Candidate',path)])
    assert result['data']=={'ok':True} and result['usage']['total_tokens']==160
    assert seen['url']=='https://ai-gateway.vercel.sh/v1/chat/completions'
    assert seen['headers']=={'Authorization':'Bearer vck-test-secret'}
    body=seen['json'];assert body['reasoning']=={'effort':'medium'}
    assert body['model']=='anthropic/claude-opus-5.5-fast'
    assert body['response_format']['json_schema']['strict'] is True
    assert body['messages'][1]['content'][-1]['image_url']['url'].startswith('data:image/png;base64,')
    assert 'vck-test-secret' not in json.dumps(result)+json.dumps(body)
    monkeypatch.setenv('AI_GATEWAY_REVIEW_REASONING_EFFORT','provider-default')
    providers.generate('reviewer','JSON',{})
    assert 'reasoning' not in seen['json']


@pytest.mark.parametrize('data,status',[
    (response(finish='length'),'truncated'),(response(finish='content_filter'),'refused'),
    (response(refusal='secret response'),'refused'),(response(finish='tool_calls'),'invalid_response'),
    (response(content=None),'invalid_response'),(response(content='broken JSON'),'invalid_response'),
    ({'choices':[]},'invalid_response'),
])
def test_incomplete_gateway_review_never_passes(gateway,monkeypatch,data,status):
    monkeypatch.setattr(providers.requests,'post',lambda *a,**kw:SimpleNamespace(status_code=200,json=lambda:data))
    result=providers.generate('reviewer','JSON',{})
    assert result['status']==status and 'secret response' not in json.dumps(result)


@pytest.mark.parametrize('code,status',[(401,'authentication_error'),(403,'permission_error'),(404,'model_unavailable'),(429,'rate_limited'),(500,'provider_error')])
def test_gateway_http_errors_hide_response_and_key(gateway,monkeypatch,code,status):
    monkeypatch.setattr(providers.requests,'post',lambda *a,**kw:SimpleNamespace(status_code=code,text='vck-test-secret'))
    result=providers.generate('planner','JSON',{})
    assert result['status']==status and 'vck-test-secret' not in json.dumps(result)
