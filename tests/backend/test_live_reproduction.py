import importlib.util
from pathlib import Path

import httpx
import pytest


spec=importlib.util.spec_from_file_location('live_reproduction',Path(__file__).resolve().parents[2]/'tools'/'reproduce_redesign.py')
reproduction=importlib.util.module_from_spec(spec)
spec.loader.exec_module(reproduction)


def test_progress_connection_interruption_retries_read_only(monkeypatch):
    monkeypatch.setattr(reproduction.time,'sleep',lambda _:None)
    requests=[]
    def transport(request):
        requests.append(request)
        if len(requests)==1: raise httpx.RemoteProtocolError('Disconnected')
        return httpx.Response(200,json={'generation':{'progress':{'stage':'finished'}}})
    with httpx.Client(base_url='http://localhost',transport=httpx.MockTransport(transport)) as client:
        result=reproduction.read_status(client,'existing-job')
    assert result['generation']['progress']['stage']=='finished'
    assert len(requests)==2
    assert all(r.method=='GET' and r.url.path=='/api/sessions/existing-job' for r in requests)


def test_progress_connection_failure_is_bounded(monkeypatch):
    monkeypatch.setattr(reproduction.time,'sleep',lambda _:None)
    requests=[]
    def transport(request):
        requests.append(request)
        raise httpx.ConnectError('Unavailable')
    with httpx.Client(base_url='http://localhost',transport=httpx.MockTransport(transport)) as client:
        with pytest.raises(httpx.ConnectError): reproduction.read_status(client,'existing-job')
    assert len(requests)==3
