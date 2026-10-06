"""Recover inconsistent model bookkeeping without weakening evidence checks."""
from copy import deepcopy
from types import SimpleNamespace

from app.ai import output_qa, providers
from rubric_fixtures import qa_review, repair_evidence
from test_implementation import qa_fixture

REAL_QA = output_qa.run


def issue(slide):
    return {**repair_evidence(), 'slides':[slide], 'criterion':'spatial_layout',
            'severity':'blocking', 'accuracy':'not_applicable', 'message':'Caption overlaps its chart.'}


def inconsistent(payload, slide):
    value = qa_review(payload)
    audit = next(a for a in value['slide_audits'] if a['ordinal'] == slide)
    next(c for c in audit['checks'] if c['criterion'] == 'spatial_layout')['status'] = 'blocking'
    return value


def test_correction_includes_rejected_response_slide_and_criterion(tmp_path, monkeypatch):
    record = qa_fixture(tmp_path, 2)
    requests = []
    def provider(role, system, payload, **kwargs):
        requests.append(deepcopy(payload))
        if len(requests) == 1:
            return {'status':'completed', 'data':inconsistent(payload, 2)}
        if len(requests) == 2:
            assert 'Slide 2' in payload['validation_error']
            assert 'spatial_layout' in payload['validation_error']
            assert payload['previous_response'] == inconsistent(payload, 2)
            assert 'Do not change an adverse verdict to pass' in payload['correction_instruction']
        return {'status':'completed', 'data':qa_review(payload, [issue(2)])}
    monkeypatch.setattr(providers, 'generate', provider)
    checks = REAL_QA(SimpleNamespace(ensure_active=lambda:None), record)
    assert len(requests) == 3
    assert checks['output_qa_coverage']['status'] == 'passed'
    assert checks['output_qa_visual']['status'] == 'failed'
    assert checks['output_qa_visual']['findings'][0]['output_slide'] == 1


def test_32_slide_review_recovers_only_inconsistent_batch_and_reaches_synthesis(tmp_path, monkeypatch):
    record = qa_fixture(tmp_path, 32)
    requests = []
    def provider(role, system, payload, **kwargs):
        requests.append((payload['stage'], list(payload['expected'])))
        if payload['stage'] == 'slide_review' and payload['expected'] == list(range(25, 31)):
            return {'status':'completed', 'data':inconsistent(payload, 28)}
        findings = [issue(28)] if 28 in payload['expected'] else []
        return {'status':'completed', 'data':qa_review(payload, findings)}
    monkeypatch.setattr(providers, 'generate', provider)
    checks = REAL_QA(SimpleNamespace(ensure_active=lambda:None), record)
    batches = record['output_qa']['batches']
    assert set(i for b in batches for i in b['response']['reviewed']) == set(range(1, 33))
    assert requests[-1] == ('deck_synthesis', list(range(1, 33)))
    assert len(requests) == 11
    assert requests.count(('slide_review', list(range(1, 6)))) == 1
    assert record['output_qa_recoveries'] == [{'ordinals':list(range(25, 31)),
        'reason':'inconsistent_rubric', 'strategy':'split_batch'}]
    assert checks['output_qa_coverage']['status'] == 'passed'
    assert checks['output_qa_visual']['status'] == 'failed'
    assert len(checks['output_qa_visual']['findings']) == 1
    assert checks['output_qa_visual']['findings'][0]['output_slide'] == 27


def test_irreparable_single_slide_stays_incomplete_with_bounded_requests(tmp_path, monkeypatch):
    record = qa_fixture(tmp_path, 2)
    requests = []
    def provider(role, system, payload, **kwargs):
        requests.append(list(payload['expected']))
        return {'status':'completed', 'data':inconsistent(payload, payload['expected'][0])}
    monkeypatch.setattr(providers, 'generate', provider)
    checks = REAL_QA(SimpleNamespace(ensure_active=lambda:None), record)
    assert requests == [[1,2], [1,2], [1], [1]]
    assert checks['output_qa_coverage']['status'] == 'error'
    assert 'Slide 1' in checks['output_qa_coverage']['findings'][0]['message']
    assert 'synthesis' not in record['output_qa']


def test_synthesis_reference_correction_has_exact_ids_and_preserves_finding(tmp_path, monkeypatch):
    record=qa_fixture(tmp_path,2)
    requests=[]
    def provider(role,system,payload,**kwargs):
        requests.append(deepcopy(payload))
        if payload['stage']=='slide_review': return {'status':'completed','data':qa_review(payload)}
        finding=issue(2)
        if 'reference_errors' not in payload:
            finding['object_ids']=['invented-output-ordinal-id']
        else:
            error=payload['reference_errors'][0]
            assert error['slides']==[2] and error['unknown_ids']==['invented-output-ordinal-id']
            assert error['allowed_ids']
            finding['object_ids']=[error['allowed_ids'][0]]
        return {'status':'completed','data':qa_review(payload,[finding])}
    monkeypatch.setattr(providers,'generate',provider)
    checks=REAL_QA(SimpleNamespace(ensure_active=lambda:None),record)
    assert len(requests)==3
    assert record['output_qa']['synthesis']['reviewed']==[1,2]
    assert checks['output_qa_visual']['status']=='failed'
    assert checks['output_qa_visual']['findings'][0]['message']=='Caption overlaps its chart.'


def test_qa_geometry_disambiguates_height_from_bottom(tmp_path):
    record=qa_fixture(tmp_path,1)
    manifest=output_qa.prepare(record['candidate'],record['checks']['render_verification'])
    contract=manifest[0]['template_contract']
    assert contract['content_box']==(.7,.4,11.7,6.05)
    assert contract['region_edges']['content_box']=={'left':.7,'top':.4,'right':12.4,'bottom':6.45}
    obj=manifest[0]['objects'][0]
    assert obj['edges']['bottom']==obj['box'][1]+obj['box'][3]
    compact=output_qa.synthesis_slide(manifest[0])
    assert compact['template_contract']['region_edges']['content_box']['bottom']==6.45
