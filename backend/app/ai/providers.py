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
PROVIDERS = {'openai':'OPENAI', 'anthropic':'ANTHROPIC', 'gemini':'GEMINI', 'vercel':'AI_GATEWAY'}
REDESIGN_ROLES = ('planner', 'element_roles', 'redesigner')
GENERATION_ROLES = ('outline', 'author', 'extractor', 'generator')
MAX_PROMPT_CHARS = 300000


class RequestPreparationError(ValueError):
    def __init__(self, code, message, **metadata):
        super().__init__(message)
        self.code, self.metadata = code, metadata


def prompt_text(payload, provider):
    value = {k:v for k,v in payload.items() if k!='schema'} if provider in ('openai','vercel') else payload
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'))


GATEWAY_DEFAULTS = {'redesigner':'openai/gpt-6-luna',
                    'generator':'anthropic/claude-opus-5.5',
                    'reviewer':'anthropic/claude-opus-5.5'}


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
    group='redesigner' if role in REDESIGN_ROLES else 'generator' if role in GENERATION_ROLES else 'reviewer'
    # Keep old planner settings as a fallback for existing deployments. The new
    # workflow-specific settings always win, including during repair calls.
    legacy='reviewer' if group=='reviewer' else 'planner'
    explicit=setting('STEVENS_AI_'+group.upper(),setting('STEVENS_AI_'+legacy.upper(),setting('STEVENS_AI_PROVIDER','openai')))
    preferred=('vercel','openai','anthropic','gemini') if group=='redesigner' else ('vercel','openai','gemini','anthropic')
    provider=next((p for p in preferred if configured(p)),preferred[0]) if explicit=='auto' else explicit
    if provider not in PROVIDERS:
        return {'provider':provider,'model':'','configured':False}
    name=PROVIDERS[provider]+'_MODEL'
    default=GATEWAY_DEFAULTS[group] if provider=='vercel' else DEFAULTS[name]
    model=setting('STEVENS_AI_'+group.upper()+'_MODEL',setting('STEVENS_AI_'+legacy.upper()+'_MODEL',setting('STEVENS_AI_MODEL',setting(name,default))))
    result={'provider':provider,'model':model,'configured':configured(provider)}
    if provider=='openai':result['reasoning_effort']=reasoning_effort(role)
    if provider=='vercel':
        effort_key={'redesigner':'AI_GATEWAY_REDESIGN_REASONING_EFFORT',
                    'generator':'AI_GATEWAY_GENERATOR_REASONING_EFFORT',
                    'reviewer':'AI_GATEWAY_REVIEW_REASONING_EFFORT'}[group]
        result['reasoning_effort']=setting(effort_key,'low' if group=='reviewer' else setting('AI_GATEWAY_REASONING_EFFORT','low'))
        result['model_provider']=model.split('/')[0]
    return result


def capabilities():
    designer,generator,reviewer=role_config('planner'),role_config('author'),role_config('reviewer')
    def independent(config):
        return config.get('model_provider',config['provider']) != reviewer.get('model_provider',reviewer['provider'])
    return {'planner':designer, 'redesigner':designer, 'generator':generator, 'reviewer':reviewer,
            'configured':all(c['configured'] for c in (designer,generator,reviewer)),
            'redesign_configured':designer['configured'] and reviewer['configured'],
            'generation_configured':generator['configured'] and reviewer['configured'],
            'independent_providers':independent(designer),
            'generation_independent_providers':independent(generator)}


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
    from slide_engine import templates
    system=templates.prompt(system)
    attempts=[]
    for _ in range(2):
        from .. import activity
        import time
        config=role_config(role);started=time.monotonic()
        details={'provider':config['provider'],'model':config['model'],'attempt':len(attempts)+1}
        activity.emit(role,'request_attempt',**details)
        try:
            result=_generate_once(role,system,payload,images,max_tokens)
        except Exception as exc:
            activity.emit(role,'request_attempt','error',**details,error_type=type(exc).__name__,duration_ms=round((time.monotonic()-started)*1000))
            raise
        activity.emit(role,'request_attempt',result['status'],**details,http_status=result.get('http_status'),
            duration_ms=round((time.monotonic()-started)*1000),**usage_counts(result.get('usage',{})))
        attempts.append(result['status'])
        retryable=result['status'] in ('timeout','provider_error') or (
            result['status']=='invalid_response' and result.get('failure_stage') in ('response_json','response_content','structured_output'))
        if not retryable: break
    return {**result,'request_attempts':len(attempts),'attempt_statuses':attempts}


def usage_counts(usage):
    """Normalize reported usage; never estimate missing provider counts."""
    def count(*keys):
        return next((int(usage[k]) for k in keys if isinstance(usage.get(k),(int,float)) and not isinstance(usage[k],bool)),None)
    inp=count('input_tokens','prompt_tokens','promptTokenCount')
    out=count('output_tokens','completion_tokens','candidatesTokenCount')
    # Anthropic reports cache input separately; Gemini separates thinking output.
    if inp is not None:inp+=sum(count(k) or 0 for k in ('cache_creation_input_tokens','cache_read_input_tokens'))
    if out is not None and 'candidatesTokenCount' in usage:out+=count('thoughtsTokenCount') or 0
    total=count('total_tokens','totalTokenCount')
    if total is None and inp is not None and out is not None:total=inp+out
    return {k:v for k,v in {'input_tokens':inp,'output_tokens':out,'tokens':total}.items() if v is not None}


def token_limit(sess):
    value = int(setting('STEVENS_AI_MAX_TOKENS', '0'))
    return value if value > 0 else None


def request_limit():
    value = int(setting('STEVENS_AI_MAX_CALLS', '0'))
    return value if value > 0 else None


def reserve_output_qa(sess, slide_count, redesign=False):
    """Protect one complete ordered review from planning and repair calls.

    Estimates include overlapping batches, full-deck synthesis, and retries.
    Only explicit positive caps apply. Zero/unset disables cumulative limits;
    request timeouts, execution deadlines and bounded repairs still apply.
    """
    batches = (slide_count + 4) // 5
    sess.qa_call_reserve = 2 * (batches + 1)
    cap = token_limit(sess)
    sess.qa_token_reserve = min(cap, 24000 * (batches + 1) + 5000 * slide_count) if cap is not None else 0


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
            limit = request_limit()
            reserve = getattr(sess, 'qa_call_reserve', 8) if role != 'output_qa' else 0
            token_reserve = getattr(sess, 'qa_token_reserve', 0) if role != 'output_qa' else 0
            if role not in ('reviewer', 'output_qa'):
                remaining = getattr(sess, 'redesign_review_remaining', 0)
                reserve += remaining
                token_reserve += 8000 * remaining
            upload_token_limit = token_limit(sess)
            estimate = request_token_estimate(system, payload, images, max_tokens)
            if ((limit is not None and sess.calls >= limit-reserve)
                    or (upload_token_limit is not None and sess.tokens + estimate > upload_token_limit-token_reserve)):
                reason = ' Remaining budget is reserved for mandatory output QA.' if role != 'output_qa' and token_reserve else ''
                return {'status':'budget_exceeded', 'message':f'Insufficient upload budget for this {role} request ({sess.calls} requests, {sess.tokens} recorded tokens across attempts).'+reason+' Output remains blocked unless every required check passes.'}
            sess.calls += 1
        except ValueError:
            return {'status':'cancelled', 'message':'Processing was cancelled or expired.'}
    config=role_config(role)
    base={'provider':config['provider'],'model':config['model']}
    if not config['configured']:
        return {**base,'status':'not_configured','message':f'Configure {PROVIDERS.get(config["provider"],"provider")}_API_KEY for {role} in the server environment or backend/.env.'}
    encoded=[]
    failure_stage='request_preparation'
    try:
        import time
        read_timeout=max(30,min(300,int(setting('STEVENS_AI_REQUEST_TIMEOUT','180'))))
        if sess and sess.execution_deadline:
            read_timeout=min(read_timeout,max(1,int(sess.execution_deadline-time.time()-15)))
        request_timeout=(15,read_timeout)
        prompt=prompt_text(payload, config['provider'])
        if len(prompt)>MAX_PROMPT_CHARS:
            raise RequestPreparationError('prompt_too_large',
                f'AI review metadata is too large ({len(prompt):,} characters; limit {MAX_PROMPT_CHARS:,}). Reduce repeated review metadata or split the review.',
                prompt_chars=len(prompt), prompt_limit=MAX_PROMPT_CHARS)
        for label,path in images:
            data=Path(path).read_bytes()
            if len(data)>8*1024*1024:
                raise RequestPreparationError('image_too_large', 'A review image exceeds the supported 8 MiB size.', image_bytes=len(data))
            encoded.append((label,base64.b64encode(data).decode('ascii')))
        if config['provider']=='vercel':
            if not re.fullmatch(r'[A-Za-z0-9._-]+/[A-Za-z0-9._:/-]+',config['model']):raise ValueError('Use creator/model for AI Gateway')
            effort=config['reasoning_effort']
            if effort not in ('provider-default','none','minimal','low','medium','high','xhigh','max'):raise ValueError('Invalid reasoning effort')
            base['reasoning_effort']=effort
            content=[{'type':'text','text':prompt}]
            for label,data in encoded:
                content += [{'type':'text','text':label},
                            {'type':'image_url','image_url':{'url':f'data:image/png;base64,{data}','detail':'high'}}]
            fmt=({'type':'json_schema','json_schema':{'name':'slide_'+role,'strict':True,'schema':strict_schema(payload['schema'])}}
                 if payload.get('schema') else {'type':'json_object'})
            body={'model':config['model'],'messages':[{'role':'system','content':system},{'role':'user','content':content}],
                  'response_format':fmt,'max_tokens':max_tokens,'stream':False}
            if effort!='provider-default':body['reasoning']={'effort':effort}
            response=requests.post('https://ai-gateway.vercel.sh/v1/chat/completions',
                headers={'Authorization':'Bearer '+setting('AI_GATEWAY_API_KEY').strip()},
                json=body,timeout=request_timeout)
        elif config['provider']=='openai':
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
            if response.status_code == 402:
                # Classify known causes, without echoing provider bodies (which
                # may contain submitted text or credentials).
                try:
                    error = response.json().get('error', {})
                    detail = str(error.get('message', '')).lower() if isinstance(error, dict) else ''
                except (ValueError, AttributeError):
                    detail = ''
                key_budget = 'api key budget' in detail or 'api-key budget' in detail
                message = ('Vercel API key spending budget exceeded (HTTP 402). A team owner must raise or remove this key budget in AI Gateway Budgets & Spend. Team credits can still be available.'
                    if config['provider']=='vercel' and key_budget else
                    f"{config['provider']} billing blocked this request (HTTP 402). Check provider credits and spending budgets. This is not the app's request/token limit.")
                return {**base,'status':'billing_error','http_status':402,'billing_reason':'api_key_budget' if key_budget else 'credits_or_budget','message':message}
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
                               (usage.get('input_tokens',0)+usage.get('output_tokens',0)) or
                               (usage.get('prompt_tokens',0)+usage.get('completion_tokens',0)))
        if config['provider']=='vercel':
            choice=data['choices'][0]
            if choice.get('finish_reason')=='length':return {**base,'status':'truncated','message':'Planner/reviewer output reached its token limit.'}
            message=choice.get('message',{})
            if choice.get('finish_reason')=='content_filter' or message.get('refusal'):
                return {**base,'status':'refused','message':'The provider declined this request.'}
            if choice.get('finish_reason')!='stop':
                return {**base,'status':'invalid_response','message':'The provider did not complete its response.'}
            output=message['content']
            if not isinstance(output,str):raise ValueError('Missing structured text')
        elif config['provider']=='openai':
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
    except RequestPreparationError as exc:
        return {**base,'status':'invalid_response','failure_stage':'request_preparation',
                'error_type':type(exc).__name__,'error_code':exc.code, **exc.metadata, 'message':str(exc)}
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
