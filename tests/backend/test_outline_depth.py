from copy import deepcopy

import pytest

from app.authoring import planning, service
from app.authoring.models import CreationRequest, Outline


def content_map(count=18, pages=True):
    # Six small lessons, each with a concept, a worked example and a derivation.
    return planning.ContentMap(units=[planning.TeachingUnit(
        id=f'u{i}', section=f'Lesson {i//3}', objective=f'Teach distinct objective {i}',
        kind=('concept', 'example', 'derivation')[i%3],
        priority='essential' if i%3 == 0 else 'supporting',
        source_pages=[i//3+1] if pages else []) for i in range(count)], context_pages=[])


def draft_for(content, groups=None):
    units={u.id:u for u in content.units}
    groups=groups or [[u.id] for u in content.units]
    visual={'kind':'text_only','description':'Explain the objective.','reason':'Words are sufficient.'}
    slides=[{'id':'opening','kind':'opening','title':'Introduction','points':['Purpose'],
             'source_pages':[],'visual':visual,'unit_ids':[]}]
    for i, group in enumerate(groups):
        slides.append({'id':f's{i}','kind':'content','title':units[group[0]].objective,
                       'points':[units[u].objective for u in group], 'visual':visual,
                       'source_pages':sorted({p for u in group for p in units[u].source_pages}),
                       'unit_ids':group})
    slides.append({'id':'closing','kind':'closing','title':'Thank you!','points':['Takeaways'],
                   'source_pages':[],'visual':visual,'unit_ids':[]})
    return planning.PlannedOutline(title='A course',rationale='Space for the learning objectives.',slides=slides)


def test_detailed_counts_teaching_units_not_pdf_pages_and_brief_can_be_brief():
    content=content_map()
    detailed=planning.depth_contract(content,'detailed')
    brief=planning.depth_contract(content,'brief')
    standard=planning.depth_contract(content,'standard')
    assert detailed['minimum_content_slides']==18
    assert len(detailed['required_unit_ids'])==18
    assert len(brief['required_unit_ids'])==6
    assert len(standard['required_unit_ids'])==12
    full=draft_for(content)
    planning.validate_coverage(full,content,detailed)
    summarized=draft_for(content,[[f'u{i}'] for i in range(0,18,3)])
    planning.validate_coverage(summarized,content,brief)
    with pytest.raises(ValueError,match='Missing required teaching units'):
        planning.validate_coverage(summarized,content,detailed)
    compressed=draft_for(content,[[f'u{i}',f'u{i+1}',f'u{i+2}'] for i in range(0,18,3)])
    with pytest.raises(ValueError,match='Split slide'):
        planning.validate_coverage(compressed,content,detailed)


@pytest.mark.parametrize('preference',['auto','brief','standard','detailed'])
def test_tiny_topic_is_not_padded_to_a_fixed_slide_count(preference):
    content=content_map(1,pages=False)
    contract=planning.depth_contract(content,preference)
    assert contract['minimum_content_slides']==1
    planning.validate_coverage(draft_for(content),content,contract)


def test_content_map_accounts_for_every_page_without_turning_references_into_a_lesson():
    content=content_map(3)
    pages=[{'page':1},{'page':2}]
    with pytest.raises(ValueError,match='account for source pages'):
        planning.validate_map(content,pages)
    content.context_pages=[planning.ContextPage(page=2,reason='Bibliographic attribution only.')]
    planning.validate_map(content,pages)
    content.context_pages[0].page=1
    with pytest.raises(ValueError,match='context-only'):
        planning.validate_map(content,pages)
    content.context_pages[0].page=99
    with pytest.raises(ValueError,match='missing source page'):
        planning.validate_map(content,pages)


@pytest.mark.parametrize('defect,message',[
    ('unknown','unknown teaching unit'), ('duplicate','Duplicate teaching coverage'),
    ('cover','Opening/closing'), ('padding','must teach a mapped objective'),
    ('provenance','source pages'), ('bookends','one opening first'),
])
def test_outline_cannot_fake_coverage(defect,message):
    content=content_map(6)
    draft=draft_for(content)
    if defect=='unknown':draft.slides[1].unit_ids=['unknown']
    if defect=='duplicate':draft.slides[2].unit_ids=['u0']
    if defect=='cover':draft.slides[0].unit_ids=['u0']
    if defect=='padding':draft.slides[1].unit_ids=[]
    if defect=='provenance':draft.slides[1].source_pages=[2]
    if defect=='bookends':draft.slides[0],draft.slides[-1]=draft.slides[-1],draft.slides[0]
    with pytest.raises(ValueError,match=message):
        planning.validate_coverage(draft,content,planning.depth_contract(content,'detailed'))


def test_capacity_limit_disclosed_without_losing_units_or_overrunning_deck_schema():
    content=content_map(36)
    contract=planning.depth_contract(content,'detailed')
    assert contract['capacity_limited'] and contract['minimum_content_slides']==28
    # Eight pairs and twenty singles retain all 36 units in the available 28 slots.
    groups=[[f'u{i}',f'u{i+1}'] for i in range(0,16,2)]+[[f'u{i}'] for i in range(16,36)]
    draft=draft_for(content,groups)
    planning.validate_coverage(draft,content,contract)
    approved=planning.approved_outline(draft,contract)
    assert len(approved.slides)==30 and '30-slide limit' in approved.rationale
    assert 'abbreviated' in approved.rationale and '36 learning objectives' in approved.rationale
    Outline.model_validate(approved.model_dump())
    assert 'unit_ids' not in approved.slides[1].model_dump()
    # Keeping every unit does not excuse compressing the deck further at capacity.
    draft=draft_for(content,[[f'u{i}',f'u{i+1}'] for i in range(0,36,2)])
    with pytest.raises(ValueError,match='at least 28'):
        planning.validate_coverage(draft,content,contract)


def test_standard_does_not_merge_unrelated_sections_to_meet_a_budget():
    content=content_map(6)
    contract=planning.depth_contract(content,'standard')
    draft=draft_for(content,[['u0','u3'],['u1'],['u4']])
    with pytest.raises(ValueError,match='unrelated sections'):
        planning.validate_coverage(draft,content,contract)


def test_correction_reports_later_omissions_together_with_an_empty_summary_slide():
    content=content_map(9)
    draft=draft_for(content)
    draft.slides=draft.slides[:4]+draft.slides[-1:]
    draft.slides[3].unit_ids=[]
    with pytest.raises(ValueError) as exc:
        planning.validate_coverage(draft,content,planning.depth_contract(content,'detailed'))
    message=str(exc.value)
    assert 'must teach a mapped objective' in message
    assert all(f'u{i}' in message for i in range(2,9))


def test_rationale_cannot_claim_a_shorter_deck_than_the_actual_slides():
    content=content_map(3)
    draft=draft_for(content)
    contract=planning.depth_contract(content,'detailed')
    draft.rationale='Three lessons use 2 content slides and 4 slides total.'
    with pytest.raises(ValueError,match='5 total slides and 3 content slides'):
        planning.validate_coverage(draft,content,contract)
    draft.rationale='3 content slides and 5 slides total, within the 30-slide limit.'
    planning.validate_coverage(draft,content,contract)


def test_full_planner_retries_compressed_detail_and_keeps_manual_outline_edits(monkeypatch):
    sess=service.create(CreationRequest(audience='Graduate students',source='pdf',length_preference='detailed'))
    sess.creation['pages']=[{'page':p,'text':f'Lesson {p}','uncertainty':''} for p in range(1,7)]
    sess.creation['outline']={'title':'Old eight-slide summary'}
    content=content_map()
    compressed=draft_for(content,[[f'u{i}',f'u{i+1}',f'u{i+2}'] for i in range(0,18,3)])
    full=draft_for(content)
    responses=[content.model_dump(),compressed.model_dump(),full.model_dump()]
    requests=[]
    def provider(role,instruction,payload,**kwargs):
        requests.append(deepcopy(payload))
        return {'status':'completed','data':responses.pop(0)}
    monkeypatch.setattr(service.providers,'generate',provider)
    result=service.plan(sess)
    assert len(result['outline']['slides'])==20
    assert 'Split slide' in requests[-1]['repair_instruction']
    assert 'length_preference' not in requests[0]['request']
    assert all('outline' not in payload for payload in requests)
    assert 'planning' not in result
    assert len(sess.creation['planning']['assignments'])==20
    # User edits remain authoritative and do not inherit an automatic depth quota.
    shorter=Outline.model_validate(result['outline'])
    shorter.slides=shorter.slides[:2]+shorter.slides[-1:]
    service.save_outline(sess,shorter,sess.creation['revision'])
    assert 'planning' not in sess.creation
    service.approve(sess,sess.creation['revision'])
    assert sess.creation['approved_hash']


def test_unrepairable_compressed_plan_is_not_saved_or_approved(monkeypatch):
    sess=service.create(CreationRequest(audience='Students',topic='A course',length_preference='detailed'))
    content=content_map(6,pages=False)
    compressed=draft_for(content,[['u0','u1','u2'],['u3','u4','u5']]).model_dump()
    responses=[content.model_dump(),compressed,compressed]
    monkeypatch.setattr(service.providers,'generate',lambda *a,**k:{'status':'completed','data':responses.pop(0)})
    with pytest.raises(ValueError,match='invalid structured content'):
        service.plan(sess)
    assert not responses and sess.creation['outline'] is None and sess.creation['approved_hash'] is None
