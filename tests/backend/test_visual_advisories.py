from copy import deepcopy
from app import generations
from rubric_fixtures import passed_checks


def record():
    value={'mode':'ai','candidate_sha256':'exact-bytes','report':{'slide_count':1},'findings':[],
           'checks':{name:{'status':'passed','findings':[]} for name in generations.QA_REQUIRED},
           'ai_pipeline':{'final_reviews':[{'output_slide':0,'candidate_sha256':'exact-bytes',
                           'verdict':'passed','rubric':passed_checks()}]}}
    generations.add_check(value,'structural_formatting',{'status':'needs_review','findings':[
        {'code':'FONT_SIZE','severity':'review','output_slide':0,'message':'Inspect the mathematical superscript.'}]})
    return value


def test_review_estimate_requires_two_completed_qa_gates_on_exact_bytes():
    original=record()
    for bad in ('failed','not_run','error','needs_review'):
        value=deepcopy(original);value['checks']['output_qa_visual']['status']=bad
        generations.resolve_visual_advisories(value)
        assert value['checks']['structural_formatting']['status']=='needs_review'
    value=deepcopy(original);value['ai_pipeline']['final_reviews'][0]['candidate_sha256']='stale'
    generations.resolve_visual_advisories(value)
    assert value['checks']['structural_formatting']['status']=='needs_review'
    generations.resolve_visual_advisories(original)
    assert original['checks']['structural_formatting']['status']=='passed'
    assert original['checks']['structural_formatting']['resolved_advisories'][0]['candidate_sha256']=='exact-bytes'


def test_blocking_or_unknown_checks_are_never_dismissed():
    value=record()
    value['checks']['structural_formatting']['findings'].extend([
        {'code':'FONT_SIZE','severity':'blocking','output_slide':0},
        {'code':'UNKNOWN','severity':'review','output_slide':0}])
    generations.resolve_visual_advisories(value)
    assert len(value['checks']['structural_formatting']['findings'])==2
