"""Per-processing-job template selection; never mutate shared template globals."""
from contextlib import contextmanager
from contextvars import ContextVar
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace
from zipfile import ZipFile, ZIP_DEFLATED
import os
import tempfile

ASSETS=Path(__file__).resolve().parents[1]/'assets'
FILES={'stevens':'stevens_template.pptx','cpe':'CPE_template.potx'}
_selected=ContextVar('presentation_template',default='stevens')


def current_id():
    return _selected.get()


@contextmanager
def use(template_id):
    if template_id not in FILES: raise ValueError('Choose CPE or Stevens format.')
    token=_selected.set(template_id)
    try: yield
    finally: _selected.reset(token)


def path(template_id=None):
    ident=template_id or current_id()
    if ident not in FILES: raise ValueError('Choose CPE or Stevens format.')
    source=ASSETS/FILES[ident]
    if source.suffix=='.pptx': return str(source)
    # python-pptx expects a presentation main part. Preserve every other byte
    # of the bundled POTX, including all four masters and their relationships.
    digest=sha256(source.read_bytes()).hexdigest()
    cache=Path(tempfile.gettempdir())/'stevens-template-cache'
    cache.mkdir(exist_ok=True)
    destination=cache/f'{digest}.pptx'
    if not destination.exists():
        fd,name=tempfile.mkstemp(dir=cache,suffix='.pptx');os.close(fd)
        try:
            with ZipFile(source) as src, ZipFile(name,'w',ZIP_DEFLATED) as out:
                for item in src.infolist():
                    blob=src.read(item.filename)
                    if item.filename=='[Content_Types].xml':
                        blob=blob.replace(b'presentationml.template.main+xml',b'presentationml.presentation.main+xml')
                    out.writestr(item,blob)
            os.replace(name,destination)
        finally:
            Path(name).unlink(missing_ok=True)
    return str(destination)


def layouts(prs):
    return [layout for master in prs.slide_masters for layout in master.slide_layouts]


def profile():
    from . import template_policy as T
    values=dict(T.STEVENS)
    if current_id()=='cpe':
        values.update(
            OPENING_LAYOUT='Title slide 1',CLOSING_LAYOUT='end slide',
            CONTENT_LAYOUT='1-line - 1 tect box',SECTION_LAYOUT='Section break',
            CONTENT=(.66,.40,11.48,5.55),
            COVER_TITLE=(.73,3.05,7.84,2.25),COVER_DETAILS=(.73,5.45,8.20,1.35),
            COVER_SUPPORT=(.73,1.15,8.20,1.65),
            CLOSING_TITLE=(.73,.53,7.84,1.61),CLOSING_DETAILS=(.73,3.90,8.20,2.57),
            SECTION_TITLE=(.60,1.44,7.27,2.5),SECTION_DETAILS=(.60,4.15,7.27,1.6),
            SECTION_SUPPORT=(8.10,1.4,3.85,4.35),
            TEMPLATE_ROLE_RULE='Selected format: CPE. Opening uses Title slide 1: dark slate background, white text on the left and complete College of Professional Education / Stevens branding in the right panel. Closing uses end slide with white text on the left and the same right-hand branding. Interior slides are white with the CPE mark at bottom-right; keep the entire footer clear. Section break uses the light gray geometric artwork. Follow these CPE references and supplied geometry, with no red tower or statue artwork.')
    return SimpleNamespace(**values)


def prompt(system):
    if current_id()!='cpe' or 'Selected format: CPE.' in system: return system
    # Remove the Stevens-specific opening paragraph and role rule before adding
    # the selected contract. Shared content/faithfulness policy remains intact.
    from . import template_policy as T
    system=system.replace(T.STEVENS['TEMPLATE_ROLE_RULE'],'')
    start=system.find('On a text-only opening keep the mostly red template')
    end=system.find('For PDF line boxes and mathematics',start)
    if start>=0 and end>start: system=system[:start]+system[end:]
    for start_text,end_text in (
        ('Section headers are the explicit exception:', 'Ambiguous images stay.'),
        ('The first output page uses the mostly red Title Slide template.', 'Identify titles in ordinary text boxes'),
        ('Section headers MUST omit the bottom-left Stevens wordmark', 'Compare photo/title hierarchy'),
        ('The opening MUST be mostly red with a faint tower', 'For redesign tasks EVERY'),
    ):
        start=system.find(start_text);end=system.find(end_text,start)
        if start>=0 and end>start: system=system[:start]+system[end:]
    system=system.replace('statue-photo closing','CPE closing').replace('Stevens statue-photo closing','CPE closing')
    system=system.replace('approved statue-photo\nclosing artwork','approved CPE\nclosing artwork')
    system=system.replace('approved statue closing template','approved CPE closing template')
    system=system.replace('right-hand title/details regions','left-hand title/details regions')
    system=system.replace('right-hand text regions','left-hand text regions')
    system=system.replace('bottom-left','bottom-right').replace('red template artwork','dark template artwork')
    system=system.replace("approved opening's red artwork and top-right mark", "approved opening's dark artwork and right-panel mark")
    system=system.replace('known red contrast field','known dark contrast field')
    return system+'\n'+profile().TEMPLATE_ROLE_RULE
