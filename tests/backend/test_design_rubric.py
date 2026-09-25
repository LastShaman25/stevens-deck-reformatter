from copy import deepcopy
import pytest
from app.ai import element_roles, rubric, pipeline, layout
from rubric_fixtures import passed_checks, role_map, repair_evidence
from test_ai_pipeline import ai_session, config, mocked_provider
from app import generations
from app.ai.output_qa import Finding
from types import SimpleNamespace


@pytest.mark.parametrize('damage',['missing','duplicate','invented','relationship','parent'])
def test_incomplete_role_inventory_is_rejected(damage):
    objects=[{'id':'title','parent':None},{'id':'panel','parent':None}]
    value=role_map(objects)
    if damage=='missing':value['elements'].pop()
    if damage=='duplicate':value['elements'].append(deepcopy(value['elements'][0]))
    if damage=='invented':value['elements'][0]['id']='not-an-object'
    if damage=='relationship':value['elements'][0]['related_ids']=['not-an-object']
    if damage=='parent':value['elements'][0]['alignment_reference']='parent'
    with pytest.raises(ValueError):element_roles.validate(value,objects)


def test_background_dependency_and_center_reference_are_preserved():
    objects=[{'id':'statistic','parent':None},{'id':'red-panel','parent':None}]
    value=role_map(objects)
    value['elements'][0].update(role='body',related_ids=['red-panel'],alignment='center',alignment_reference='related')
    value['elements'][1]['role']='panel'
    result=element_roles.validate(value,objects)
    assert result.elements[0].related_ids==['red-panel']
    assert result.elements[0].alignment_reference=='related'


@pytest.mark.parametrize('damage',['missing','duplicate','silent_blocker'])
def test_qa_cannot_skip_criteria_or_hide_a_blocking_check(damage):
    values=passed_checks()
    if damage=='missing':values.pop()
    if damage=='duplicate':values[-1]=values[0]
    if damage=='silent_blocker':values[2]['status']='blocking'
    with pytest.raises(ValueError):rubric.validate_checks([rubric.CriterionResult.model_validate(v) for v in values],[])


def test_missing_role_phase_stops_planning(ai_session,monkeypatch):
    seen=[]
    def provider(role,*args,**kwargs):
        seen.append(role)
        result=mocked_provider(role,*args,**kwargs)
        if role=='element_roles':result['data']['elements'].pop()
        return result
    monkeypatch.setattr(pipeline.providers,'generate',provider)
    record=generations.build(ai_session,mode='ai',repair_passes=0)
    assert seen==['element_roles','element_roles']
    assert record['checks']['ai_redesign']['status']=='error'


def test_planning_gets_validated_roles_and_template_context(ai_session,monkeypatch):
    def provider(role,system,payload,*args,**kwargs):
        if role=='planner':
            expected={o['id'] for o in payload['objects']+payload['template_context']}
            assert {e['id'] for e in payload['element_roles']['elements']}==expected
            assert payload['template_context']
            assert all(not o['editable'] for o in payload['template_context'])
        return mocked_provider(role,system,payload,*args,**kwargs)
    monkeypatch.setattr(pipeline.providers,'generate',provider)
    record=generations.build(ai_session,mode='ai',repair_passes=0)
    assert record['checks']['ai_redesign']['status']=='passed'


def test_invalid_plan_is_corrected_once_before_editing(ai_session,monkeypatch):
    planning_calls=0
    def provider(role,system,payload,*args,**kwargs):
        nonlocal planning_calls
        result=mocked_provider(role,system,payload,*args,**kwargs)
        if role=='planner':
            planning_calls+=1
            if planning_calls==1:result['data']['objects'].pop()
            if planning_calls==2:assert 'every object exactly once' in payload['validation_error']
        return result
    monkeypatch.setattr(pipeline.providers,'generate',provider)
    record=generations.build(ai_session,mode='ai',repair_passes=0)
    assert record['checks']['ai_redesign']['status']=='passed'
    assert len(record['ai_pipeline']['plan_validation_errors'])==1
    assert planning_calls==4


def test_candidate_roles_retry_before_planner_and_review_gets_template(ai_session,monkeypatch):
    role_calls=0;review_references=[]
    def provider(role,system,payload,*args,**kwargs):
        nonlocal role_calls
        result=mocked_provider(role,system,payload,*args,**kwargs)
        if payload.get('stage')=='identify_elements':
            role_calls+=1
            if role_calls==1:result['data']['elements'][0]['alignment_reference']='parent'
            if role_calls==2:assert 'parent' in payload['validation_error']
        if role=='planner':assert role_calls>=2
        if role=='reviewer':
            review_references.extend(label for label,_ in args[0] if label.startswith('APPROVED TEMPLATE:'))
            assert args[0][-1][0]=='FINAL CANDIDATE TO AUDIT (last image)'
            assert 'ai-render-' in str(args[0][-1][1])
        return result
    monkeypatch.setattr(pipeline.providers,'generate',provider)
    record=generations.build(ai_session,mode='ai',repair_passes=0)
    assert record['checks']['ai_redesign']['status']=='passed'
    assert role_calls==4
    assert 'APPROVED TEMPLATE: 1_Title Slide' in review_references


def test_review_contract_correction_retains_the_observed_defect(ai_session,monkeypatch):
    seen=[]
    def provider(role,system,payload,*args,**kwargs):
        result=mocked_provider(role,system,payload,*args,**kwargs)
        if role=='reviewer':
            seen.append(payload.get('validation_error'))
            if len(seen)<=2:
                finding={**repair_evidence(),'criterion':'spatial_layout','severity':'review','message':'Synthetic panel overlap.'}
                result['data'].update(verdict='needs_review',findings=[finding],rubric=passed_checks([finding]))
                if len(seen)==1:result['data']['verdict']='passed'
                else:assert payload['previous_review']['findings'][0]['message']==finding['message']
        return result
    monkeypatch.setattr(pipeline.providers,'generate',provider)
    record=generations.build(ai_session,mode='ai',repair_passes=0)
    assert 'Inconsistent visual verdict' in seen[1]
    assert record['checks']['ai_visual_review']['status']=='needs_review'
    assert record['checks']['ai_visual_review']['findings'][0]['acceptance_condition']
    assert not record['output_qa_repairs'][0]['accepted']
    assert 'no substantive change' in record['output_qa_repairs'][0]['reason']


def test_each_finding_has_exactly_one_primary_category():
    data={**repair_evidence(),'criterion':'spatial_layout','severity':'blocking','object_ids':[],
          'message':'Two wordmarks overlap; separate them.'}
    assert pipeline.VisualFinding.model_validate(data).criterion=='spatial_layout'
    with pytest.raises(ValueError):pipeline.VisualFinding.model_validate({**data,'criterion':['spatial_layout','brand_consistency']})
    with pytest.raises(ValueError):pipeline.VisualFinding.model_validate({**data,'secondary_criteria':['brand_consistency']})
    with pytest.raises(ValueError):pipeline.VisualFinding.model_validate({**data,'criterion':'stacking'})


def test_blocking_layout_cannot_justify_adverse_branding_checkbox():
    findings=[SimpleNamespace(criterion='spatial_layout',severity='blocking')]
    values=passed_checks([{'criterion':'spatial_layout','severity':'blocking'}])
    rubric.validate_checks([rubric.CriterionResult.model_validate(v) for v in values],findings)
    next(v for v in values if v['criterion']=='brand_consistency')['status']='review'
    with pytest.raises(ValueError):rubric.validate_checks([rubric.CriterionResult.model_validate(v) for v in values],findings)


@pytest.mark.parametrize('criterion',rubric.CRITERIA)
def test_no_category_can_hide_its_own_finding(criterion):
    findings=[SimpleNamespace(criterion=criterion,severity='review')]
    with pytest.raises(ValueError):rubric.validate_checks([rubric.CriterionResult.model_validate(v) for v in passed_checks()],findings)
    values=passed_checks([{'criterion':criterion,'severity':'review'}])
    rubric.validate_checks([rubric.CriterionResult.model_validate(v) for v in values],findings)


def test_final_and_slide_review_share_the_same_category_vocabulary():
    visual=pipeline.VisualFinding.model_json_schema()['properties']['criterion']['enum']
    final=Finding.model_json_schema()['properties']['criterion']['enum']
    assert visual==final==rubric.CRITERIA
    assert set(rubric.channel(c) for c in rubric.CRITERIA)=={'visual','accuracy','sequence'}


@pytest.mark.parametrize('field',['region','evidence','required_correction','acceptance_condition'])
@pytest.mark.parametrize('model',[pipeline.VisualFinding,Finding])
def test_incomplete_repair_handoff_is_rejected(field,model):
    value={**repair_evidence(),'criterion':'spatial_layout','severity':'blocking','message':'Code overlaps its panel.'}
    if model is Finding:value.update(slides=[1],accuracy='not_applicable')
    model.model_validate(value)
    del value[field]
    with pytest.raises(ValueError):model.model_validate(value)
    value[field]='   '
    with pytest.raises(ValueError):model.model_validate(value)
