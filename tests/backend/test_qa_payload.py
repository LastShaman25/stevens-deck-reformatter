"""Whole-deck synthesis must fit without losing slides or reported defects."""
from copy import deepcopy
from types import SimpleNamespace
import pytest

from app.ai import output_qa, providers, qa_payload
from rubric_fixtures import qa_review, repair_evidence
from test_implementation import qa_fixture
from test_openai import openai_config
from test_ai_pipeline import config

REAL_QA = output_qa.run


def test_dense_32_slide_synthesis_keeps_content_findings_and_every_image(tmp_path, monkeypatch):
    record = qa_fixture(tmp_path, 32)
    manifest = output_qa.prepare(record['candidate'], record['checks']['render_verification'])
    for slide in manifest:
        slide['objects'] = [{
            'id':f"source/{slide['ordinal']}/object/{i}", 'kind':'text', 'content':f'Exact content {i}',
            'box':[1,2,3,4], 'text_margins':{'left':.1,'right':.1,'top':.2,'bottom':.2},
            'text_fit_ratio':.73, 'font_sizes':[18], 'parent':None, 'editable':True,
            'locked_geometry':False, 'native_title':False, 'layer':i,
        } for i in range(50)]
    monkeypatch.setattr(output_qa, 'prepare', lambda *a:deepcopy(manifest))
    finding = {**repair_evidence(), 'slides':[28], 'criterion':'spatial_layout',
               'severity':'blocking', 'accuracy':'not_applicable', 'message':'Chart caption overlap.'}
    observed = []
    def provider(role, system, payload, images, **kwargs):
        observed.append(payload['stage'])
        assert len(providers.prompt_text(payload, 'openai')) < providers.MAX_PROMPT_CHARS
        if payload['stage'] == 'deck_synthesis':
            assert payload['expected'] == list(range(1,33)) and len(images) == 32
            assert len(payload['slides']) == 32
            for original, packed in zip(manifest, payload['slides']):
                assert packed['text'] == original['text'] and packed['notes'] == original['notes']
                unpacked = [dict(zip(packed['object_columns'], row)) for row in packed['objects']]
                assert unpacked == [{k:o[k] for k in ('id','kind','content')} for o in original['objects']]
            retained = [f for b in payload['prior_reviews'] for f in b['response']['findings']]
            assert any(all(f[k] == v for k,v in finding.items()) for f in retained)
            for batch in payload['prior_reviews']:
                for audit in batch['response']['slide_audits']:
                    assert len(audit['checks']) == 8
        value = qa_review(payload, [finding] if 28 in payload['expected'] else [])
        for audit in value['slide_audits']:
            for check in audit['checks']:
                check['evidence'] = 'Synthetic detailed evidence. ' * 20
        return {'status':'completed', 'data':value}
    monkeypatch.setattr(providers, 'generate', provider)
    checks = REAL_QA(SimpleNamespace(ensure_active=lambda:None), record)
    assert observed[-1] == 'deck_synthesis'
    assert checks['output_qa_coverage']['status'] == 'passed'
    assert checks['output_qa_visual']['status'] == 'failed'
    assert len(checks['output_qa_visual']['findings']) == 1
    assert len(record['output_manifest'][0]['objects'][0]) > 3  # Full local evidence retained.


def test_oversize_prompt_reports_safe_diagnostic_before_image_io(openai_config, monkeypatch):
    def no_network(*a, **kw):
        raise AssertionError('Oversized local request must not reach the API')
    monkeypatch.setattr(providers.requests, 'post', no_network)
    result = providers._generate_once('output_qa', 'Review',
        {'private':'x' * providers.MAX_PROMPT_CHARS}, images=[('slide','missing-private-image.png')])
    assert result['error_code'] == 'prompt_too_large'
    assert result['prompt_chars'] > result['prompt_limit']
    assert result['failure_stage'] == 'request_preparation'
    assert 'private' not in result['message']


def test_synthesis_view_does_not_mutate_local_evidence():
    item = {'ordinal':1,'text':'Text','notes':'Notes', 'objects':[{'id':'a','kind':'text','content':'Exact', 'box':[1,2,3,4]}],
            'template_context':[], 'original':{'source_ordinal':1,'image':'private-path','sha256':'hash'}}
    original = deepcopy(item)
    packed = output_qa.synthesis_slide(item)
    assert item == original
    assert packed['original'] == {'source_ordinal':1}


def unpack_shared(payload):
    definitions=payload.get('shared_metadata',{})
    def visit(value):
        if isinstance(value,dict):
            return {key[:-4] if key.endswith('_ref') and isinstance(child,str) and child in definitions else key:
                    deepcopy(definitions[child]) if key.endswith('_ref') and isinstance(child,str) and child in definitions else visit(child)
                    for key,child in value.items() if key not in ('shared_metadata','shared_metadata_format')}
        if isinstance(value,list): return [visit(child) for child in value]
        return value
    return visit(payload)


@pytest.mark.parametrize('count',[98,100])
def test_large_deck_synthesis_and_reference_retry_keep_all_evidence(tmp_path,monkeypatch,count):
    record=qa_fixture(tmp_path,count)
    manifest=output_qa.prepare(record['candidate'],record['checks']['render_verification'])
    for slide in manifest:
        slide['template_contract']['additional_rules']='Preserve the exact diagram and its readable labels. '*35
        slide['notes']='Unique notes for slide '+str(slide['ordinal'])+': '+('Keep these source notes intact. '*12)
        slide['original']={'source_ordinal':slide['ordinal'],'image':slide['image'],'sha256':slide['sha256']}
        slide['pdf_import_evidence']={'page':slide['ordinal'],'preservation':'Exact source typography preserved as images. '*8,
                                     'source_font_evidence':[{'image_sha256':str(slide['ordinal']),'bounds':[1,2,3,4]}]}
    original=deepcopy(manifest)
    monkeypatch.setattr(output_qa,'prepare',lambda *a:deepcopy(manifest))
    finding={**repair_evidence(),'slides':[count-1],'criterion':'spatial_layout',
             'severity':'blocking','accuracy':'not_applicable','message':'The final chart overlaps its caption.'}
    requests=[]
    def provider(role,system,payload,images,**kwargs):
        requests.append(deepcopy(payload))
        assert len(providers.prompt_text(payload,'openai')) <= providers.MAX_PROMPT_CHARS
        result=qa_review(payload,[finding] if count-1 in payload['expected'] else [])
        if payload['stage']=='deck_synthesis':
            assert payload['expected']==list(range(1,count+1))
            assert len(images)==count*2  # Every original and final screenshot.
            assert payload.get('shared_metadata')
            expanded=unpack_shared(payload)
            assert len(providers.prompt_text(expanded,'openai'))>providers.MAX_PROMPT_CHARS
            for before,after in zip(original,expanded['slides']):
                assert after==output_qa.synthesis_slide(before)
            assert any(f['message']==finding['message'] for b in expanded['prior_reviews'] for f in b['response']['findings'])
            if 'reference_errors' not in payload:
                result['findings'][0]['object_ids']=['incorrect-object-id']
            else:
                assert expanded['previous_response']['findings'][0]['message']==finding['message']
                result['findings'][0]['object_ids']=[payload['reference_errors'][0]['allowed_ids'][0]]
        return {'status':'completed','data':result}
    monkeypatch.setattr(providers,'generate',provider)
    checks=REAL_QA(SimpleNamespace(ensure_active=lambda:None),record)
    assert checks['output_qa_coverage']['status']=='passed'
    assert checks['output_qa_visual']['status']=='failed'  # No defect was waived to fit.
    assert len([p for p in requests if p['stage']=='deck_synthesis'])==2
    assert manifest==original and record['output_manifest']==original
    assert record['output_qa_calls'][-1]['shared_metadata_entries']>0


@pytest.mark.parametrize('provider',['openai','vercel','anthropic','gemini'])
def test_metadata_sharing_is_lossless_and_leaves_schema_and_input_untouched(provider):
    contract={'layout':'body','region_edges':{'content_box':{'bottom':6.45}},'rule':'Source equation Δ = 42. '*180}
    payload={'slides':[{'ordinal':i,'template_contract':deepcopy(contract)} for i in range(100)],
             'schema':output_qa.Review.model_json_schema(),
             'previous_response':{'findings':[{'message':'Retain this defect.','slides':[97]}]},
             'reference_errors':[{'unknown_ids':['wrong'],'allowed_ids':['exact/id']}],
             'validation_error':'Correct the ID.'}
    before=deepcopy(payload)
    packed=qa_payload.compact(payload,provider)
    assert len(providers.prompt_text(packed,provider))<providers.MAX_PROMPT_CHARS
    assert unpack_shared(packed)==before and payload==before
    assert packed['schema']==payload['schema']
