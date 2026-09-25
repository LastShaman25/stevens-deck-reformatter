import hashlib
from pathlib import Path
import pytest
import requests
from fastapi.testclient import TestClient
from app import sessions, generations
from app.main import app
from app.qa import gemini
from test_regressions import fixture


@pytest.fixture
def sess(tmp_path):
    s=sessions.create()
    Path(s.source_path).write_bytes(fixture(tmp_path).read_bytes())
    from app.grounded import analyze
    s.analysis=analyze(s.source_path)
    yield s
    sessions.delete(s.id)


def fake_render(candidate,directory):
    return {'status':'passed','findings':[],'candidate_sha256':generations.sha256(candidate)}


def test_release_and_stale_version(sess,monkeypatch):
    monkeypatch.setattr(generations.render_verify,'check',fake_render)
    r=generations.build(sess)
    # The synthetic source may produce review findings; these must be scoped.
    ids=[f['id'] for f in r['findings'] if f['severity']=='review']
    if ids:
        generations.decide(sess,generations.Decision(generation_id=r['generation_id'],candidate_sha256=r['candidate_sha256'],finding_ids=ids,rationale='Inspected synthetic fixture'))
    assert r['state']=='ready',r['findings']
    client=TestClient(app)
    base=f'/api/sessions/{sess.id}'
    response=client.get(base+'/download',params={'generation_id':r['generation_id']})
    assert response.status_code==200
    assert hashlib.sha256(response.content).hexdigest()==r['candidate_sha256']
    Path(r['candidate']).write_bytes(b'changed')
    assert client.get(base+'/download',params={'generation_id':r['generation_id']}).status_code==409


def test_required_verifier_crash_blocks_final(sess,monkeypatch):
    def crash(*args):raise RuntimeError('Injected renderer failure')
    monkeypatch.setattr(generations.render_verify,'check',crash)
    r=generations.build(sess)
    assert r['state']=='error'
    client=TestClient(app);base=f'/api/sessions/{sess.id}'
    assert client.get(base+'/download',params={'generation_id':r['generation_id']}).status_code==409
    assert client.get(base+'/download',params={'generation_id':r['generation_id'],'draft':True}).status_code==409
    assert client.post(base+'/benchmark',json={'generation_id':r['generation_id']}).status_code==410
    with pytest.raises(ValueError):
        generations.decide(sess,generations.Decision(generation_id=r['generation_id'],candidate_sha256=r['candidate_sha256'],finding_ids=[r['findings'][-1]['id']],rationale='Cannot override'))


def test_revision_invalidates_and_indices_404(sess,monkeypatch):
    monkeypatch.setattr(generations.render_verify,'check',fake_render)
    r=generations.build(sess)
    client=TestClient(app);base=f'/api/sessions/{sess.id}'
    for index in [-1,99]:
        assert client.post(f'{base}/slides/{index}/revise',json={'tags':[]}).status_code==404
        assert client.post(f'{base}/slides/{index}/ai-check',json={'enabled':False}).status_code==404
        assert client.get(f'{base}/slides/{index}/preview?variant=before').status_code==404
    assert client.post(f'{base}/slides/0/revise',json={'tags':['split']}).status_code==200
    assert sess.generation is None
    assert client.get(base+'/download',params={'generation_id':r['generation_id']}).status_code==409
    assert client.get(base+'/download',params={'generation_id':r['generation_id'],'draft':True}).status_code==409
    image = Path(r['directory'], 'render', 'slide-0.png')
    image.parent.mkdir(exist_ok=True)
    image.write_bytes(b'previous-preview')
    preview = f'{base}/slides/0/preview?variant=after&generation_id={r["generation_id"]}'
    assert client.get(preview).content == b'previous-preview'
    assert client.get(base).json()['preview_generation']['generation_id'] == r['generation_id']
    assert client.post(base+'/decisions',json={'generation_id':r['generation_id'],
        'candidate_sha256':r['candidate_sha256'],'finding_ids':['old'], 'rationale':'Old candidate'}).status_code==409
    Path(r['candidate']).write_bytes(b'changed')
    assert client.get(preview).status_code==409


def test_active_job_not_expired_or_deleted(sess):
    with sessions.job(sess):
        sess.touched-=sessions.TTL_SECONDS+1
        sessions.sweep()
        assert sessions.get(sess.id) is sess
        assert sessions.delete(sess.id) is False
        assert sessions.get(sess.id) is None
        with pytest.raises(ValueError):
            with sessions.job(sess):pass
    assert not Path(sess.dir).exists()


@pytest.mark.parametrize('fault,status',[(requests.Timeout(),'timeout'),(requests.HTTPError(),'provider_error'),(ValueError(),'invalid_response')])
def test_ai_failures_are_not_clean(tmp_path,monkeypatch,fault,status):
    monkeypatch.setattr(gemini,'available',lambda:True)
    monkeypatch.setattr(gemini,'_key',lambda:'mock-key')
    def fail(*args,**kwargs):raise fault
    monkeypatch.setattr(gemini.requests,'post',fail)
    p=tmp_path/'slide.png';p.write_bytes(b'test')
    assert gemini.review_slide_result(str(p))['status']==status


@pytest.mark.renderer
def test_real_renderer_preserves_fixture(tmp_path):
    from app.grounded import build_deck
    from app.qa.render_verify import check
    src=fixture(tmp_path);out=tmp_path/'out.pptx';build_deck(src,out)
    result=check(out,tmp_path/'render')
    assert result['status']=='passed',result['findings']
    assert len(result['pages'])==3
