from fastapi.testclient import TestClient
from app import generations
from app.main import app
from test_ai_pipeline import ai_session, config


def test_slide_acceptance_covers_hidden_findings_but_not_other_slides(ai_session):
    record=generations.build(ai_session,mode='ai')
    for name in generations.required_checks(record):
        generations.add_check(record,name,{'status':'passed','findings':[]})
    record['report']['slide_count']=3
    record['source_to_output_slides']={'0':[0,1],'1':[2]}
    generations.add_check(record,'output_qa_visual',{'status':'failed','findings':[
        {'severity':'blocking','output_slide':0,'message':'Title layout'},
        {'severity':'warning','output_slide':0,'message':'Cosmetic spacing'},
        {'severity':'review','affected_slides':[0,1],'message':'Compare the two pages'},
        {'severity':'review','source_slide':1,'message':'Review final source'}]})
    generations.settle(record)
    client=TestClient(app);base=f'/api/sessions/{ai_session.id}'
    payload={'generation_id':record['generation_id'],'candidate_sha256':record['candidate_sha256'],
             'output_slide':0,'rationale':'Reviewed the complete slide'}
    assert client.post(base+'/decisions',json={**payload,'output_slide':99}).status_code==409
    assert client.post(base+'/decisions',json={**payload,'finding_ids':['output_qa_visual:3']}).status_code==409
    record['checks']['output_qa_accuracy']['status']='error'
    assert client.post(base+'/decisions',json=payload).status_code==409
    record['checks']['output_qa_accuracy']['status']='passed'
    result=client.post(base+'/decisions',json=payload)
    assert result.status_code==200
    decision=record['human_decisions'][-1]
    assert set(decision['finding_ids'])=={'output_qa_visual:0','output_qa_visual:1','output_qa_visual:2'}
    assert generations.approved_findings(record)=={'output_qa_visual:0','output_qa_visual:1'}
    assert not result.json()['generation']['download_allowed']
    assert client.post(base+'/decisions',json={**payload,'output_slide':1}).status_code==200
    assert 'output_qa_visual:2' in generations.approved_findings(record)
    assert not generations.download_allowed(record)
    assert client.post(base+'/decisions',json={**payload,'output_slide':2}).json()['generation']['download_allowed']
    assert record['checks']['output_qa_visual']['status']=='failed'
    record['candidate_sha256']='changed'
    assert not generations.approved_findings(record)


def test_priority_is_derived_from_materiality_not_client_input():
    assert generations.finding_priority({'severity':'warning'})=='low'
    for severity in ('blocking','review','optional_pending',None):
        assert generations.finding_priority({'severity':severity,'priority':'low'})=='high'


def test_only_low_priority_findings_do_not_block(ai_session):
    record=generations.build(ai_session,mode='ai')
    for name in generations.required_checks(record):
        generations.add_check(record,name,{'status':'passed','findings':[]})
    generations.add_check(record,'output_qa_visual',{'status':'passed','findings':[
        {'severity':'warning','output_slide':0,'message':'Optional caption spacing'}]})
    generations.settle(record)
    public=generations.public(record)
    assert public['download_allowed'] and public['findings'][0]['priority']=='low'
    record['checks']['output_qa_visual']['status']='error'
    generations.settle(record)
    assert not generations.download_allowed(record)
