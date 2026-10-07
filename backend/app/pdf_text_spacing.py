"""Recover evidenced PDF bullet spacing lost by text extraction.

Some exporters position the bullet and word separately inside one font span.
The extracted string contains no whitespace even though the visible slide does.
Only a measurable leading bullet gap is restored; equations and other text stay
unchanged. A native tab preserves the source word origin without inventing copy.
"""
import fitz
from pptx.oxml.xmlchemy import OxmlElement
from pptx.util import Inches


BULLETS = frozenset('•●▪◦‣⁃')


def _text(line):
    return ''.join(span['text'] for span in line['spans'])


def _candidate(line):
    text = _text(line)
    return (line.get('dir', (1, 0)) == (1, 0) and len(text) > 1
            and text[0] in BULLETS and not text[1].isspace())


def bullet_tabs(page, lines):
    candidates = [line for line in lines if _candidate(line)]
    if not candidates:
        return {}
    raw = page.get_text('rawdict', flags=fitz.TEXTFLAGS_RAWDICT & ~fitz.TEXT_PRESERVE_IMAGES)
    raw_lines = {}
    for block in raw['blocks']:
        if block['type'] != 0:
            continue
        for line in block['lines']:
            chars = [char for span in line['spans'] for char in span['chars']]
            key = (tuple(round(v, 3) for v in line['bbox']), ''.join(char['c'] for char in chars))
            raw_lines.setdefault(key, []).append((line, chars))
    found = {}
    for line in candidates:
        key = (tuple(round(v, 3) for v in line['bbox']), _text(line))
        matches = raw_lines.get(key, [])
        if len(matches) != 1:
            continue
        original, chars = matches[0]
        if (original.get('dir', (1, 0)) != (1, 0) or len(chars) < 2
                or chars[0]['c'] not in BULLETS or chars[1]['c'].isspace()):
            continue
        size = original['spans'][0]['size']
        gap = chars[1]['origin'][0] - chars[0]['bbox'][2]
        offset = chars[1]['origin'][0] - line['bbox'][0]
        if (gap >= max(1, size*.25) and 0 < offset < size*4
                and abs(chars[1]['origin'][1] - chars[0]['origin'][1]) < size*.1):
            found[id(line)] = offset
    return found


def apply_bullet_tab(paragraph, spans, offset, page_scale):
    """Return equivalent runs and put the following word at its measured x."""
    tab_list = OxmlElement('a:tabLst')
    tab = OxmlElement('a:tab')
    tab.set('pos', str(Inches(offset*page_scale)))
    tab.set('algn', 'l')
    tab_list.append(tab)
    ppr = paragraph._p.get_or_add_pPr()
    ppr.insert_element_before(tab_list, 'a:defRPr', 'a:extLst')
    result = []
    first = True
    for span in spans:
        if first and span['text']:
            result.append({**span, 'text': span['text'][0]+'\t'+span['text'][1:]})
            first = False
        else:
            result.append(span)
    return result


def scale_tabs(paragraph, factor):
    for tab in paragraph._p.xpath('./a:pPr/a:tabLst/a:tab'):
        tab.set('pos', str(round(int(tab.get('pos'))*factor)))
