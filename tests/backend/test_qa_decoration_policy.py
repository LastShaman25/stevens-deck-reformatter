"""Decoration findings retain material defects without repeated page penalties."""
from copy import deepcopy

from app.ai import output_qa, rubric, source_decisions
from slide_engine import templates


def frame(slides, object_ids, **changes):
    item = dict(slides=slides, object_ids=object_ids, region='Source-page perimeter',
        criterion='brand_consistency', category='visual', severity='review', accuracy='supported',
        message='The retained red frame conflicts with the CPE interior style.',
        evidence='The original red page border is still visible inside the white CPE slide.',
        required_correction='Remove the old page perimeter and retain the source teaching content.',
        acceptance_condition='No source frame remains; all equations, diagram labels and logos survive.',
        defect_key='source_page_frame')
    return {**item, **changes}


def test_overlapping_batches_and_deck_synthesis_keep_one_frame_per_page():
    ids = ['sss:digest/7/slide/2', 'sss:digest/8/slide/2']
    first = frame([8], ids[:1], criterion='instruction_compliance')
    overlap = frame([8], ids[:1], message='The source page outline is obsolete artwork.')
    second = frame([9], ids[1:])
    synthesis = frame([8, 9], ids, severity='blocking',
        message='The entire deck retains obsolete framed page insets.', evidence='New full-deck evidence.')
    contrast = frame([8], ids[:1], criterion='visual_legibility', defect_key='other',
        message='The AdaGrad label is dark on a dark patch.',
        required_correction='Restore the original light label color.',
        acceptance_condition='The complete AdaGrad label has readable contrast.')
    spacing = frame([9], ['sss:digest/8/slide/4'], criterion='spatial_layout', defect_key='other',
        message='The bullet touches its label.', required_correction='Add the missing bullet gap.')
    findings = [first, overlap, second, contrast, spacing, synthesis]
    before = deepcopy(findings)
    result = output_qa.consolidate_findings(findings, {ids[0]:{8}, ids[1]:{9}})
    assert len(result) == 4
    assert findings == before
    frames = [f for f in result if f['defect_key'] == 'source_page_frame']
    assert [f['slides'] for f in frames] == [[8], [9]]
    assert all(f['severity'] == 'blocking' and f['criterion'] == 'brand_consistency' for f in frames)
    assert len(frames[0]['observations']) == 3
    assert frames[0]['observations'][0]['criterion'] == 'instruction_compliance'
    assert frames[0]['observations'][-1]['slides'] == [8, 9]
    assert result[2:4] == [contrast, spacing]


def test_unresolved_object_ownership_and_distinct_artifacts_are_not_merged():
    # Never assume that an unknown ID belongs to one of the listed pages.
    ambiguous = frame([8, 9], ['source-picture'])
    assert output_qa.consolidate_findings([ambiguous]) == [ambiguous]
    first = frame([8], ['sss:digest/7/slide/2'])
    separate = frame([8], ['sss:digest/7/slide/5'])
    backdrop = frame([8], first['object_ids'], defect_key='obsolete_cover_backdrop')
    assert len(output_qa.consolidate_findings([first, separate, backdrop])) == 3


def test_decorations_follow_output_manifest_after_insertions_and_splits():
    # Source slide indices in IDs are not output ordinals after added/split pages.
    ids = ['sss:digest/7/slide/2', 'sss:digest/8/slide/2']
    first = frame([9], ids[:1])
    synthesis = frame([9, 11], ids, severity='blocking')
    result = output_qa.consolidate_findings([first, synthesis], {ids[0]:{9}, ids[1]:{11}})
    assert [item['slides'] for item in result] == [[9], [11]]
    assert [item['object_ids'] for item in result] == [ids[:1], ids[1:]]
    assert all(item['severity'] == 'blocking' for item in result)
    # Same source object copied into two output pages has ambiguous ownership.
    assert output_qa.consolidate_findings([synthesis], {ids[0]:{9, 10}, ids[1]:{11}}) == [synthesis]
    # Never fall back to parsing apparent ordinal components in the IDs.
    aligned = frame([8, 9], ids)
    assert output_qa.consolidate_findings([aligned]) == [aligned]


def test_cpe_prompt_retains_shared_metadata_and_uses_selected_template():
    with templates.use('cpe'):
        qa = templates.prompt(output_qa.SYSTEM)
        designer = templates.prompt(source_decisions.SYSTEM)
    for prompt in (qa, designer):
        assert 'Selected format: CPE.' in prompt
        assert 'source-page' in prompt and 'meaningful' in prompt
        assert 'The opening MUST be mostly red' not in prompt
        assert 'required template red field' not in prompt
    assert 'FIELD_ref refers to the full FIELD value in shared_metadata' in qa
    assert 'semantic arrows, plot borders and equation highlighting must remain' in qa
    assert 'Bounding-box intersection alone does not prove occlusion' in qa
    assert 'source_page_frame' in output_qa.Finding.model_fields['defect_key'].annotation.__args__
