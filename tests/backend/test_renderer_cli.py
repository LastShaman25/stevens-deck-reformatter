import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
from app import rendering


def test_windows_renderer_prefers_console_launcher(tmp_path):
    gui=tmp_path/'soffice.exe';gui.touch()
    assert rendering.find_soffice(str(gui))==str(gui)
    console=tmp_path/'soffice.com';console.touch()
    assert rendering.find_soffice(str(gui))==str(console)


def test_conversion_and_version_share_private_headless_profile(tmp_path,monkeypatch):
    gui=tmp_path/'soffice.exe';gui.touch()
    console=tmp_path/'soffice.com';console.touch()
    calls=[]
    def run(command,**kwargs):
        calls.append(command)
        if '--convert-to' in command:
            directory=Path(command[command.index('--outdir')+1])
            (directory/'source.pdf').write_bytes(b'%PDF-synthetic')
            return SimpleNamespace(stdout=b'converted',stderr=b'')
        return SimpleNamespace(stdout=b'LibreOffice synthetic test version',stderr=b'')
    monkeypatch.setattr(rendering.subprocess,'run',run)
    pdf=Path(rendering.pptx_to_pdf(tmp_path/'source.pptx',tmp_path/'output',soffice=str(gui)))
    assert len(calls)==2
    for command in calls:
        assert command[0]==str(console) and '--headless' in command and '--norestore' in command
    profiles=[[v for v in command if v.startswith('-env:UserInstallation=')] for command in calls]
    assert profiles[0]==profiles[1] and len(profiles[0])==1
    assert 'stevens-lo-' in profiles[0][0]
    assert (tmp_path/'output').as_uri() not in profiles[0][0]
    assert calls[1][-1]=='--version'
    assert json.loads(pdf.with_suffix('.renderer.json').read_text())['version']=='LibreOffice synthetic test version'


def test_missing_pdf_retains_console_failure_reason(tmp_path,monkeypatch):
    monkeypatch.setattr(rendering.subprocess,'run',lambda *args,**kwargs:SimpleNamespace(
        stdout=b'',stderr=b'Error: source file could not be loaded'))
    with pytest.raises(RuntimeError,match='source file could not be loaded'):
        rendering.pptx_to_pdf(tmp_path/'source.pptx',tmp_path/'out',soffice='soffice')


def test_version_timeout_still_blocks_verification(tmp_path,monkeypatch):
    def run(command,**kwargs):
        if '--version' in command:raise subprocess.TimeoutExpired(command,30)
        directory=Path(command[command.index('--outdir')+1])
        (directory/'source.pdf').write_bytes(b'%PDF-synthetic')
        return SimpleNamespace(stdout=b'',stderr=b'')
    monkeypatch.setattr(rendering.subprocess,'run',run)
    with pytest.raises(RuntimeError,match='version check did not complete'):
        rendering.pptx_to_pdf(tmp_path/'source.pptx',tmp_path/'out',soffice='soffice')
