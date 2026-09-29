"""Provider adapters. Keys stay in headers; errors never include request bodies."""
import base64
import json
import os
import re
from pathlib import Path
import requests
from dotenv import dotenv_values

ENV_FILE = Path(__file__).resolve().parents[2] / '.env'
DEFAULTS = {'OPENAI_MODEL':'gpt-6-luna', 'ANTHROPIC_MODEL':'claude-sonnet-4-5', 'GEMINI_MODEL':'gemini-3.1-flash-lite'}
PROVIDERS = {'openai':'OPENAI', 'anthropic':'ANTHROPIC', 'gemini':'GEMINI'}


def setting(name, default=''):
    # Read file settings on demand so adding keys does not require server restart.
    value = os.environ.get(name)
    if value:
        return value
    return str(dotenv_values(ENV_FILE).get(name) or default)


def configured(provider):
    if provider not in PROVIDERS or setting('STEVENS_OFFLINE') == '1':
        return False
    value=setting(PROVIDERS[provider]+'_API_KEY').strip()
    return bool(value and not value.lower().startswith(('your_', 'your-', 'replace', 'changeme')))


def role_config(role):
    explicit=setting('STEVENS_AI_PLANNER' if role in ('planner','element_roles','outline','author','extractor') else 'STEVENS_AI_REVIEWER','openai')
    preferred=('openai','anthropic','gemini') if role in ('planner','element_roles') else ('openai','gemini','anthropic')
    provider=next((p for p in preferred if configured(p)),preferred[0]) if explicit=='auto' else explicit
    if provider not in PROVIDERS:
        return {'provider':provider,'model':'','configured':False}
    name=PROVIDERS[provider]+'_MODEL'
    result={'provider':provider,'model':setting(name,DEFAULTS[name]),'configured':configured(provider)}
    if provider=='openai':result['reasoning_effort']=reasoning_effort(role)
    return result


def capabilities():
    planner,reviewer=role_config('planner'),role_config('reviewer')
    return {'planner':planner,'reviewer':reviewer,'configured':planner['configured'] and reviewer['configured'],
            'independent_providers':planner['provider'] != reviewer['provider']}


def reasoning_effort(role):
    base=setting('OPENAI_REASONING_EFFORT','none')
    # Logo identity and paired visual judgments failed at none in the live eval.
    # Keep planning inexpensive; preserve higher explicit global settings.
    return setting('OPENAI_REVIEW_REASONING_EFFORT','low' if base=='none' else base) if role in ('reviewer','output_qa') else base


def _parse(text):
    value=text.lstrip('\ufeff').strip()
    if value.startswith('```'):
        value=re.sub(r'^```(?:json)?\s*|\s*```$','',value)
    return json.loads(value)


def strict_schema(value):
    """Convert Pydantic defaults to OpenAI's all-fields-required JSON schema."""
    if isinstance(value,list):return [strict_schema(v) for v in value]
    if not isinstance(value,dict):return value
    out={k:strict_schema(v) for k,v in value.items() if k!='default'}
    if out.get('type')=='object':
        out['required']=list(out.get('properties',{}))
        out['additionalProperties']=False
    return out


def generate(role, system, payload, images=(), max_tokens=16000):
    """One bounded retry for transport or malformed responses; every attempt consumes budget."""
    attempts=[]
    for _ in range(2):
        result=_generate_once(role,system,payload,images,max_tokens)
        attempts.append(result['status'])
        retryable=result['status'] in ('timeout','provider_error') or (
            result['status']=='invalid_response' and result.get('failure_stage') in ('response_json','response_content','structured_output'))
        if not retryable: break
    return {**result,'request_attempts':len(attempts),'attempt_statuses':attempts}


def token_limit(sess):
    return int(setting('STEVENS_AI_MAX_TOKENS', str(getattr(sess, 'default_token_limit', 500000))))


def reserve_output_qa(sess, slide_count, redesign=False):
    """Protect one complete ordered review from planning and repair calls.

    Estimates include overlapping batches, full-deck synthesis, and retries.
    Explicit configured caps are never increased. Redesign needs source decisions,
    native layout calls, paired per-slide review AND final ordered QA. Its default
    budget therefore scales with deck size, bounded at two million tokens.
    """
    batches = (slide_count + 4) // 5
    sess.qa_call_reserve = 2 * (batches + 1)
    sess.default_token_limit = max(500000, min(2000000, 120000 * slide_count)) if redesign else 500000
    cap = token_limit(sess)
    sess.qa_token_reserve = min(cap, 24000 * (batches + 1) + 5000 * slide_count)


def request_token_estimate(system, payload, images, max_tokens):
    # Conservative admission estimate, not provider billing. Includes Unicode,
    # output allowance, schema, and high-detail images. Actual usage is recorded.
    return (len(system) + len(json.dumps(payload, ensure_ascii=False))) // 2 + 4096 * len(images) + max_tokens


def reserve_redesign_review(sess, slide_count):
    """The redesign workflow has an additional paired, per-slide QA stage."""
    sess.redesign_review_remaining = slide_count


def _generate_once(role, system, payload, images=(), max_tokens=16000):
    from ..sessions import active_session
    sess = active_session.get()
    if sess:
        try:
            sess.ensure_active()
            limit = int(setting('STEVENS_AI_MAX_CALLS', '160'))
            reserve = getattr(sess, 'qa_call_reserve', 8) if role != 'output_qa' else 0
            token_reserve = getattr(sess, 'qa_token_reserve', 0) if role != 'output_qa' else 0
            if role not in ('reviewer', 'output_qa'):
                remaining = getattr(sess, 'redesign_review_remaining', 0)
                reserve += remaining
                token_reserve += 8000 * remaining
            upload_token_limit = token_limit(sess)
            estimate = request_token_estimate(system, payload, images, max_tokens)
            if sess.calls >= limit-reserve or sess.tokens + estimate > upload_token_limit-token_reserve:
                reason = ' Remaining budget is reserved for mandatory output QA.' if role != 'output_qa' and token_reserve else ''
                return {'status':'budget_exceeded', 'message':f'Insufficient upload budget for this {role} request ({sess.calls} requests, {sess.tokens} recorded tokens across attempts).'+reason+' Output remains blocked unless every required check passes.'}
            sess.calls += 1
        except ValueError:
            return {'status':'cancelled', 'message':'Processing was cancelled or expired.'}
    config=role_config(role)
    base={'provider':config['provider'],'model':config['model']}
    if not config['configured']:
        return {**base,'status':'not_configured','message':f'Configure the {role} provider key in backend/.env.'}
    encoded=[]
    failure_stage='request_preparation'
    try:
        import time
        read_timeout=max(30,min(300,int(setting('STEVENS_AI_REQUEST_TIMEOUT','180'))))
        if sess and sess.execution_deadline:
            read_timeout=min(read_timeout,max(1,int(sess.execution_deadline-time.time()-15)))
        request_timeout=(15,read_timeout)
        for label,path in images:
            data=Path(path).read_bytes()
            if len(data)>8*1024*1024:raise ValueError('Image too large')
            encoded.append((label,base64.b64encode(data).decode('ascii')))
        prompt=json.dumps({k:v for k,v in payload.items() if k!='schema'} if config['provider']=='openai' else payload,ensure_ascii=False)
        if len(prompt)>300000:raise ValueError('Slide payload exceeds the supported size')
        if config['provider']=='openai':
            content=[{'type':'input_text','text':prompt}]
            for label,data in encoded:
                content += [{'type':'input_text','text':label},
                            {'type':'input_image','image_url':f'data:image/png;base64,{data}','detail':'high'}]
            effort=reasoning_effort(role)
            if effort not in ('none','low','medium','high','xhigh','max'):raise ValueError('Invalid reasoning effort')
            base['reasoning_effort']=effort
            fmt=({'type':'json_schema','name':'slide_'+role,'strict':True,'schema':strict_schema(payload['schema'])}
                 if payload.get('schema') else {'type':'json_object'})
            response=requests.post('https://api.openai.com/v1/responses',
                headers={'Authorization':'Bearer '+setting('OPENAI_API_KEY').strip()},
                json={'model':config['model'],'instructions':system,
                      'input':[{'role':'user','content':content}], 'text':{'format':fmt},
                      'reasoning':{'effort':effort},'max_output_tokens':max_tokens,
                      'store':False,'service_tier':'default'},timeout=request_timeout)
        elif config['provider']=='anthropic':
            content=[{'type':'text','text':prompt}]
            for label,data in encoded:
                content += [{'type':'text','text':label},{'type':'image','source':{'type':'base64','media_type':'image/png','data':data}}]
            response=requests.post('https://api.anthropic.com/v1/messages',headers={
                'x-api-key':setting('ANTHROPIC_API_KEY'),'anthropic-version':'2023-06-01'},
                json={'model':config['model'],'max_tokens':max_tokens,'temperature':0,'system':system,
                      'messages':[{'role':'user','content':content}]},timeout=request_timeout)
        else:
            if not re.fullmatch(r'[A-Za-z0-9._-]+',config['model']):raise ValueError('Invalid model name')
            parts=[{'text':prompt}]
            for label,data in encoded:
                parts += [{'text':label},{'inlineData':{'mimeType':'image/png','data':data}}]
            response=requests.post(f"https://generativelanguage.googleapis.com/v1beta/models/{config['model']}:generateContent",
                headers={'x-goog-api-key':setting('GEMINI_API_KEY')},json={
                    'systemInstruction':{'parts':[{'text':system}]},'contents':[{'role':'user','parts':parts}],
                    'generationConfig':{'temperature':0,'responseMimeType':'application/json','maxOutputTokens':max_tokens}},timeout=request_timeout)
        if response.status_code!=200:
            status={400:'invalid_request',401:'authentication_error',403:'permission_error',404:'model_unavailable',429:'rate_limited'}.get(response.status_code,'provider_error')
            return {**base,'status':status,'http_status':response.status_code,'message':f"{config['provider']} returned HTTP {response.status_code}. Check key access, model configuration, and quota."}
        failure_stage='response_json'
        data=response.json()
        failure_stage='response_content'
        usage=data.get('usage',data.get('usageMetadata',{}))
        usage={k:v for k,v in usage.items() if isinstance(v,(int,float)) and not isinstance(v,bool)}
        base['usage']=usage
        if sess:
            sess.tokens += int(usage.get('total_tokens') or usage.get('totalTokenCount') or
                               (usage.get('input_tokens',0)+usage.get('output_tokens',0)))
        if config['provider']=='openai':
            if data.get('status')=='incomplete' and (data.get('incomplete_details') or {}).get('reason')=='max_output_tokens':
                return {**base,'status':'truncated','message':'Planner/reviewer output reached its token limit.'}
            if data.get('status')!='completed':
                return {**base,'status':'invalid_response','message':'The provider did not complete its response.'}
            messages=[item for item in data['output'] if item.get('type')=='message']
            if any(item.get('status')!='completed' for item in messages):raise ValueError('Incomplete message')
            parts=[part for item in messages for part in item.get('content',[])]
            if any(part.get('type')=='refusal' for part in parts):
                return {**base,'status':'refused','message':'The provider declined this request.'}
            output=''.join(part.get('text','') for part in parts if part.get('type')=='output_text')
            usage=data.get('usage',{})
        elif config['provider']=='anthropic':
            if data.get('stop_reason')=='max_tokens':return {**base,'status':'truncated','message':'Planner/reviewer output reached its token limit.'}
            if data.get('stop_reason')!='end_turn':return {**base,'status':'invalid_response','message':'The provider did not complete its response.'}
            output=''.join(x.get('text','') for x in data['content'] if x.get('type')=='text')
            usage=data.get('usage',{})
        else:
            candidate=data['candidates'][0]
            if candidate.get('finishReason')=='MAX_TOKENS':
                return {**base,'status':'truncated','message':'Planner/reviewer output reached its token limit.'}
            if candidate.get('finishReason')!='STOP':
                return {**base,'status':'invalid_response','message':'The provider did not complete its response.'}
            output=''.join(p.get('text','') for p in candidate['content']['parts'] if not p.get('thought'))
            usage=data.get('usageMetadata',{})
        usage={k:v for k,v in usage.items() if isinstance(v,(int,float)) and not isinstance(v,bool)}
        if sess:
            sess.ensure_active()
        failure_stage='structured_output'
        return {**base,'status':'completed','data':_parse(output),'usage':usage}
    except json.JSONDecodeError:
        return {**base,'status':'invalid_response','failure_stage':failure_stage,
                'message':'AI returned malformed JSON. The response was rejected; no redesign or QA result was accepted.'}
    except requests.Timeout:
        return {**base,'status':'timeout','message':'AI request exceeded its time limit.'}
    except requests.RequestException:
        return {**base,'status':'provider_error','message':'AI provider connection failed.'}
    except (ValueError,KeyError,IndexError,TypeError,AttributeError,OSError) as exc:
        messages={'request_preparation':'AI request preparation failed (input or configuration).',
                  'response_json':'AI returned an unreadable response.',
                  'response_content':'AI returned an incomplete or invalid response structure.',
                  'structured_output':'AI returned invalid structured output.'}
        return {**base,'status':'invalid_response','failure_stage':failure_stage,'error_type':type(exc).__name__,
                'message':messages[failure_stage]+' No redesign or QA result was accepted.'}
