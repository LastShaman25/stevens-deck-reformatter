from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from app import generations, grounded
from app.main import app
from app.ai import providers, output_qa, pipeline
from test_ai_pipeline import ai_session, config


@pytest.mark.parametrize('qa_status',['passed','failed','needs_review','error','not_run'])
def test_local_format_downloads_when_finished_regardless_of_qa(ai_session,monkeypatch,qa_status):
    calls=[]
    def no_redesign(*a,**kw):raise AssertionError('Local formatting must not invoke the AI redesign pipeline')
    monkeypatch.setattr(pipeline,'execute',no_redesign)
    def qa(sess,record,evidence):
        calls.append(True)
        assert not generations.download_allowed(record)
        assert not record.get('processing_complete')
        return {n:{'status':qa_status,'findings':[]} for n in output_qa.CHECKS+('output_qa_visual',)}
    monkeypatch.setattr(output_qa,'run',qa)
    client=TestClient(app)
    response=client.post(f'/api/sessions/{ai_session.id}/generate',json={})
    assert response.status_code==200
    record=ai_session.generation
    assert record['mode']=='preserve' and calls==[True]
    assert record['ai_pipeline'] is None
    assert record['processing_complete'] and generations.download_allowed(record)
    url=f'/api/sessions/{ai_session.id}/download'
    params={'generation_id':record['generation_id']}
    downloaded=client.get(url,params=params)
    assert downloaded.status_code==200
    assert 'verified' not in downloaded.headers['content-disposition']
    assert generations.sha256(Path(record['candidate']))==record['candidate_sha256']
    # Completion, not the verification verdict, controls the wait gate.
    record['processing_complete']=False
    assert client.get(url,params=params).status_code==409
    record['processing_complete']=True
    Path(record['candidate']).write_bytes(b'changed')
    assert client.get(url,params=params).status_code==409


def test_failed_build_without_output_cannot_download(ai_session,monkeypatch):
    def fail(*a,**kw):raise ValueError('No output produced')
    monkeypatch.setattr(grounded,'build_deck',fail)
    record=generations.build(ai_session)
    assert record['processing_complete']
    assert not generations.download_allowed(record)
    assert not Path(record['candidate']).exists()
