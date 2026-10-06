"""Check the shipped template and Git's actual handling of local credentials."""
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_shared_helper_template_is_shipped_inside_backend():
    from slide_fixer.rebuild import TEMPLATE_PATH
    assert Path(TEMPLATE_PATH).resolve() == ROOT / 'backend/assets/stevens_template.pptx'
    assert Path(TEMPLATE_PATH).is_file()


def test_git_ignores_credentials_but_keeps_empty_example(tmp_path):
    subprocess.run(['git', 'init', '-q', str(tmp_path)], check=True)
    shutil.copyfile(ROOT / '.gitignore', tmp_path / '.gitignore')
    ignored = ['.env', '.env.local', 'backend/.env', 'backend/.env.production',
               'frontend/.env', 'frontend/.env.development', 'backend/key.env',
               '.local/verification/result.json', 'backend/server.key']
    public = ['backend/.env.example', 'backend/app/main.py',
              'backend/assets/stevens_template.pptx']
    for name in ignored + public:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('synthetic fixture', encoding='utf-8')
    result = subprocess.run(['git', '-C', str(tmp_path), 'ls-files', '--others',
                             '--exclude-standard'], check=True, text=True, capture_output=True)
    visible = set(result.stdout.splitlines())
    assert not visible.intersection(ignored)
    assert set(public) <= visible
