import os
import sys
import tempfile
import pytest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'backend'))
os.environ['STEVENS_LEARN'] = '0'
os.environ['STEVENS_OFFLINE'] = '1'
os.environ['STEVENS_AUTH_DB'] = str(Path(tempfile.mkdtemp(prefix='stevens-tests-')) / 'accounts.sqlite3')
os.environ['STEVENS_WORKSPACE_ROOT'] = tempfile.mkdtemp(prefix='stevens-test-jobs-')


@pytest.fixture(autouse=True)
def legacy_boundaries(request, monkeypatch):
    """Existing engine tests isolate their historical boundary; new tests use real auth/QA."""
    if request.node.path.name in ('test_implementation.py','test_developer_activity.py'):
        yield
        return
    from app import auth
    from app.ai import output_qa
    user = {'id':'legacy-test-user', 'email':'Synthetic tester', 'role':'admin', 'active':1, 'csrf':'', 'token':'test-login'}
    monkeypatch.setattr(auth, 'authenticate', lambda req: user)
    token = auth.current_user.set(user)
    monkeypatch.setattr(output_qa, 'run', lambda *args, **kwargs: {k:{'status':'passed','findings':[]} for k in output_qa.CHECKS+('output_qa_visual',)})
    try: yield
    finally: auth.current_user.reset(token)
