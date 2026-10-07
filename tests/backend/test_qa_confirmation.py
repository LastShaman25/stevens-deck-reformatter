"""Focused visual rechecks may refute evidenced mistakes, never waive real QA."""
from copy import deepcopy
import hashlib
import json
from types import SimpleNamespace

from PIL import Image
import pytest

from app.ai import output_qa, providers
from slide_engine.inventory import sha256


@pytest.fixture(autouse=True)
def no_paid_calls(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('Confirmation tests must use their explicit fake provider')
    monkeypatch.setattr(providers, 'generate', forbidden)


def evidence(tmp_path, count=3):
    candidate = tmp_path/'candidate.pptx'
    candidate.write_bytes(b'Immutable candidate identity for the paired review')
    manifest = []
    for ordinal in range(1, count+1):
        image = tmp_path/f'output-{ordinal}.png'
        original = tmp_path/f'original-{ordinal}.png'
        Image.new('RGB', (32, 20), (ordinal*10, 35, 80)).save(image)
        Image.new('RGB', (32, 20), (80, ordinal*10, 35)).save(original)
        # Output ordinals may differ from source ordinals after splitting.
        source_ordinal = 9 if ordinal < 3 else ordinal+10
        manifest.append({'ordinal': ordinal, 'image': str(image), 'sha256': sha256(image),
            'text': f'Output text {ordinal}', 'notes': f'Notes {ordinal}',
            'objects': [{'id': f'source/{source_ordinal}/object/7', 'content': 'Retained panel'}],
            'template_contract': {'layout': 'CPE body', 'content_box': [.7, .4, 11.7, 6.05]},
            'original': {'source_ordinal': source_ordinal, 'image': str(original),
                         'sha256': sha256(original)}})
    record = {'candidate': str(candidate), 'candidate_sha256': sha256(candidate),
        'checks': {'render_verification': {'candidate_sha256': sha256(candidate)}},
        'output_qa': {'batches': [{'response': {'findings': ['Original adverse ledger']}}],
                      'synthesis': {'summary': 'Original whole-deck judgment'}},
        'output_qa_calls': [{'stage': 'deck_synthesis', 'request_id': 'original-request'}]}
    return SimpleNamespace(ensure_active=lambda: None), record, manifest


def finding(slides, **changes):
    return {'slides': slides, 'criterion': 'visual_legibility', 'category': 'visual', 'severity': 'blocking',
        'accuracy': 'supported', 'message': 'The candidate omitted the right-hand plot panel.',
        'object_ids': ['source/9/object/7'], 'region': 'Right-hand plot and its labels',
        'evidence': 'The prior reviewer could not locate the right-hand plot.',
        'required_correction': 'Restore the complete plot and its labels.',
        'acceptance_condition': 'Both plot panels and all original labels are fully visible.',
        'defect_key': 'other', **changes}


def decision(index, **changes):
    return {'finding_index': index, 'verdict': 'contradicted', 'confidence': 'high',
        'source_evidence': 'The original shows two side-by-side plot panels with complete axis labels.',
        'candidate_evidence': 'Both panels and the same complete axis labels are visible in the candidate.',
        'comparison': 'The alleged missing right-hand plot is present in both paired images; its labels are readable.',
        'source_region_inspected': True, 'candidate_region_inspected': True,
        'claim_directly_refuted': True, 'acceptance_condition_verified': True, **changes}


def completed(payload, **changes):
    return {'status': 'completed', 'data': {'ordinal': payload['ordinal'],
        'decisions': [decision(item['finding_index'], **changes) for item in payload['findings']]}}


def original_fields(items):
    return [{key: value for key, value in item.items() if key != 'confirmation_notes'} for item in items]


def expected_note(ordinal, **changes):
    review = decision(0, **changes)
    return {'ordinal': ordinal, **{key: review[key] for key in
        ('verdict', 'confidence', 'comparison', 'source_evidence', 'candidate_evidence',
         'acceptance_condition_verified')}}


def test_exact_paired_refutation_preserves_raw_ledger_and_immutable_candidate(tmp_path):
    sess, record, manifest = evidence(tmp_path)
    findings = [finding([2]), finding([1], severity='review'), finding([3], severity='warning')]
    original_findings, original_manifest = deepcopy(findings), deepcopy(manifest)
    original_ledger, original_hash = deepcopy(record['output_qa']), record['candidate_sha256']
    calls = []
    def provider(role, system, payload, *, images, **kwargs):
        ordinal = payload['ordinal']
        expected = manifest[ordinal-1]
        calls.append(deepcopy(payload))
        assert role == 'output_qa' and payload['stage'] == 'finding_confirmation'
        assert payload['candidate_sha256'] == original_hash
        assert images[0][1] == expected['original']['image']
        assert images[1][1] == expected['image']
        assert f'source slide {expected["original"]["source_ordinal"]}' in images[0][0]
        assert f'output {ordinal}' in images[0][0]
        assert f'output slide {ordinal}' in images[1][0]
        assert payload['slide']['objects'] == expected['objects']
        assert payload['slide']['template_contract'] == expected['template_contract']
        assert payload['findings'][0]['finding'] == findings[0 if ordinal == 2 else 1]
        return completed(payload, verdict='contradicted' if ordinal == 2 else 'confirmed')
    result = output_qa.confirm_findings(sess, record, manifest, findings, generate=provider)
    assert original_fields(result) == findings[1:]
    assert result[0]['confirmation_notes'] == [expected_note(1, verdict='confirmed')]
    assert 'confirmation_notes' not in result[1]  # Unreviewed warning keeps no fabricated note.
    assert [call['ordinal'] for call in calls] == [2, 1]
    assert findings == original_findings and manifest == original_manifest
    assert {key: record['output_qa'][key] for key in original_ledger} == original_ledger
    assert sha256(record['candidate']) == record['candidate_sha256'] == original_hash
    assert record['output_qa_calls'][0]['request_id'] == 'original-request'
    receipt = record['output_qa_confirmations'][-1]
    assert receipt['removed_finding_indices'] == [0]
    assert receipt['retained_finding_indices'] == [1, 2]
    assert receipt['input_findings_sha256'] == hashlib.sha256(json.dumps(findings, sort_keys=True).encode()).hexdigest()
    assert all(case['response']['ordinal'] == case['ordinal'] for case in receipt['cases'])
    assert receipt['cases'][0]['source_image_sha256'] == manifest[1]['original']['sha256']
    assert receipt['cases'][0]['output_image_sha256'] == manifest[1]['sha256']


@pytest.mark.parametrize('change', [
    {'verdict': 'confirmed'}, {'verdict': 'uncertain'}, {'confidence': 'medium'}, {'confidence': 'low'},
    {'source_region_inspected': False}, {'candidate_region_inspected': False},
    {'claim_directly_refuted': False}, {'acceptance_condition_verified': False},
    {'source_region_inspected': 'true'}, {'acceptance_condition_verified': 1},
    {'source_evidence': ''}, {'candidate_evidence': 'Seems fine'}, {'comparison': 'No issue'},
    {'source_evidence': 'Visible '*8},
    {key: 'Every relevant region appears satisfactory in this paired visual review.'
     for key in ('source_evidence', 'candidate_evidence', 'comparison')},
])
def test_unconfirmed_or_insufficient_evidence_never_downgrades_original_finding(tmp_path, change):
    sess, record, manifest = evidence(tmp_path)
    findings = [finding([1])]
    result = output_qa.confirm_findings(sess, record, manifest, findings,
                                      generate=lambda role, system, payload, **kw: completed(payload, **change))
    assert original_fields(result) == findings
    key, value = next(iter(change.items()))
    annotated = key in ('verdict', 'confidence') or (key.endswith(('inspected', 'refuted', 'verified')) and type(value) is bool)
    if annotated:
        assert result[0]['confirmation_notes'] == [expected_note(1, **change)]
    else:
        assert 'confirmation_notes' not in result[0]
    assert 'confirmation_notes' not in findings[0]
    assert record['output_qa']['raw_findings'] == findings
    assert result[0]['severity'] == 'blocking'
    assert record['output_qa_confirmations'][-1]['removed_finding_indices'] == []


@pytest.mark.parametrize('failure', ['provider_error', 'exception', 'malformed', 'wrong_ordinal',
                                     'wrong_index', 'omitted', 'duplicate', 'reordered'])
def test_provider_and_response_identity_failures_keep_every_original_finding(tmp_path, failure):
    sess, record, manifest = evidence(tmp_path)
    findings = [finding([1]), finding([1], message='The lower arrow is missing.')]
    def provider(role, system, payload, **kwargs):
        if failure == 'provider_error':
            return {'status': 'error', 'error_code': 'timeout'}
        if failure == 'exception':
            raise RuntimeError('Transport failed')
        if failure == 'malformed':
            return {'status': 'completed', 'data': {'not': 'the required review'}}
        result = completed(payload)
        data = result['data']
        if failure == 'wrong_ordinal': data['ordinal'] = 2
        elif failure == 'wrong_index': data['decisions'][0]['finding_index'] = 99
        elif failure == 'omitted': data['decisions'].pop()
        elif failure == 'duplicate': data['decisions'][1]['finding_index'] = 0
        elif failure == 'reordered': data['decisions'].reverse()
        return result
    assert output_qa.confirm_findings(sess, record, manifest, findings, generate=provider) == findings
    assert record['output_qa_confirmations'][-1]['removed_finding_indices'] == []


@pytest.mark.parametrize('second_verdict', ['confirmed', 'uncertain', 'contradicted'])
def test_multi_slide_claim_requires_refutation_on_every_affected_output(tmp_path, second_verdict):
    sess, record, manifest = evidence(tmp_path)
    findings = [finding([1, 2])]
    def provider(role, system, payload, **kwargs):
        return completed(payload, verdict=second_verdict if payload['ordinal'] == 2 else 'contradicted')
    result = output_qa.confirm_findings(sess, record, manifest, findings, generate=provider)
    assert original_fields(result) == ([] if second_verdict == 'contradicted' else findings)
    if result:
        assert result[0]['confirmation_notes'] == [expected_note(1), expected_note(2, verdict=second_verdict)]
    assert 'confirmation_notes' not in findings[0]
    assert len(record['output_qa_confirmations'][-1]['cases']) == 2


@pytest.mark.parametrize('budget,expected_calls', [(0, 0), (1, 1), (100, 8)])
def test_budget_and_unpaired_or_unknown_pages_cannot_silently_pass(tmp_path, budget, expected_calls):
    sess, record, manifest = evidence(tmp_path, count=10)
    manifest[-1].pop('original')  # Authorized template-only page has no source pair.
    findings = [finding(list(range(1, 11))), finding([99])]
    calls = []
    def provider(role, system, payload, **kwargs):
        calls.append(payload['ordinal'])
        return completed(payload)
    result = output_qa.confirm_findings(sess, record, manifest, findings,
                                      max_cases=budget, generate=provider)
    assert original_fields(result) == findings
    assert result[0].get('confirmation_notes', []) == [expected_note(ordinal) for ordinal in calls]
    assert 'confirmation_notes' not in result[1]
    assert len(calls) == expected_calls
    assert all(ordinal < 10 for ordinal in calls)
    assert record['output_qa_confirmations'][-1]['removed_finding_indices'] == []


@pytest.mark.parametrize('target', ['candidate', 'output_image', 'source_image', 'render_hash'])
@pytest.mark.parametrize('when', ['before', 'during'])
def test_changed_evidence_identity_cannot_remove_any_finding(tmp_path, target, when):
    sess, record, manifest = evidence(tmp_path)
    findings = [finding([1])]
    calls = []
    def change_identity():
        if target == 'render_hash':
            record['checks']['render_verification']['candidate_sha256'] = 'another-candidate'
        elif target == 'candidate':
            from pathlib import Path
            Path(record['candidate']).write_bytes(b'Changed by concurrent generation')
        else:
            item = manifest[0] if target == 'output_image' else manifest[0]['original']
            Image.new('RGB', (32, 20), '#abcdef').save(item['image'])
    if when == 'before': change_identity()
    def provider(role, system, payload, **kwargs):
        calls.append(payload['ordinal'])
        change_identity()
        return completed(payload)
    assert output_qa.confirm_findings(sess, record, manifest, findings, generate=provider) == findings
    assert len(calls) == (0 if when == 'before' else 1)
    receipt = record['output_qa_confirmations'][-1]
    assert receipt['status'] == 'error'
    assert receipt['removed_finding_indices'] == []


def test_selected_template_reference_and_source_pair_are_reviewed_together(tmp_path):
    sess, record, manifest = evidence(tmp_path)
    reference = tmp_path/'cpe-approved.png'
    Image.new('RGB', (32, 20), '#eeeeee').save(reference)
    record['ai_pipeline'] = {'template_references': [
        {'layout': 'CPE body', 'image': str(reference), 'sha256': sha256(reference),
         'label': 'APPROVED CPE INTERIOR'},
        {'layout': 'Stevens opening', 'image': 'unused-missing-image.png',
         'sha256': 'unused', 'label': 'UNRELATED STEVENS OPENING'}]}
    findings = [finding([1])]
    def provider(role, system, payload, *, images, **kwargs):
        assert images[0] == ('APPROVED CPE INTERIOR', str(reference))
        assert [path for _, path in images[1:]] == [manifest[0]['original']['image'], manifest[0]['image']]
        return completed(payload)
    assert output_qa.confirm_findings(sess, record, manifest, findings, generate=provider) == []
    assert record['output_qa_confirmations'][-1]['cases'][0]['template_references'] == [
        {'layout': 'CPE body', 'sha256': sha256(reference)}]


def test_repeated_confirmation_retains_initial_raw_findings_and_every_receipt(tmp_path):
    sess, record, manifest = evidence(tmp_path)
    findings = [finding([1]), finding([2], message='Second independently reported defect.')]
    def provider(role, system, payload, **kwargs):
        return completed(payload, verdict='contradicted' if payload['ordinal'] == 1 else 'uncertain')
    first = output_qa.confirm_findings(sess, record, manifest, findings, generate=provider)
    second = output_qa.confirm_findings(sess, record, manifest, first, generate=provider)
    assert second == first
    assert original_fields(first) == findings[1:]
    assert second[0]['confirmation_notes'] == [expected_note(2, verdict='uncertain')]
    assert record['output_qa']['raw_findings'] == findings
    receipts = record['output_qa_confirmations']
    assert len(receipts) == 2
    assert receipts[0]['input_findings_sha256'] != receipts[1]['input_findings_sha256']
    assert receipts[0]['removed_finding_indices'] == [0]
    assert receipts[1]['removed_finding_indices'] == []
    assert receipts[0]['cases'][0]['original_findings'] == [{'finding_index': 0, 'finding': findings[0]}]
    assert receipts[1]['cases'][0]['original_findings'] == [{'finding_index': 0, 'finding': first[0]}]


def test_confirmed_source_inherited_crop_note_survives_display_checks_without_rewriting_claim(tmp_path):
    sess, record, manifest = evidence(tmp_path)
    findings = [finding([1], message='Redesign introduced an unreadable clipped caption.')]
    review = {'verdict': 'confirmed', 'acceptance_condition_verified': False,
        'source_evidence': 'The original image already truncates the final words of the lower caption.',
        'candidate_evidence': 'The candidate retains that same source crop; its caption remains incomplete.',
        'comparison': 'The truncation is inherited from the original rather than introduced by redesign, but readability still fails.'}
    result = output_qa.confirm_findings(sess, record, manifest, findings,
                                      generate=lambda role, system, payload, **kw: completed(payload, **review))
    assert original_fields(result) == findings
    assert result[0]['confirmation_notes'] == [expected_note(1, **review)]
    checks = output_qa.checks_from_findings(result, manifest)
    visible = checks['output_qa_visual']['findings'][0]
    assert checks['output_qa_visual']['status'] == 'failed'
    assert visible['message'] == findings[0]['message']
    assert visible['confirmation_notes'] == result[0]['confirmation_notes']
    assert record['output_qa']['raw_findings'] == findings
