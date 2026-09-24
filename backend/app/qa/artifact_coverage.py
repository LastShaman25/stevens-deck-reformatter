"""Reopen and inspect actual output objects; provenance only locates them."""
from collections import Counter
from pptx import Presentation
from slide_engine import inventory
from slide_engine.preserve import marker


def audit(source_path, candidate_path, report):
    source = inventory.inspect(source_path)
    prs = Presentation(candidate_path)
    mapping = report['source_to_output_slides']
    reverse = {o: int(s) for s, outputs in mapping.items() for o in outputs}
    numbers = {str(s.part.partname): reverse.get(i, -1) for i,s in enumerate(prs.slides)}
    found, findings = {}, []
    covered_outputs = [o for outputs in mapping.values() for o in outputs]
    if sorted(covered_outputs) != list(range(len(prs.slides))) or set(mapping) != {str(i) for i in range(source.slide_count)}:
        findings.append({'code': 'INVALID_SLIDE_MAPPING'})
    source_prs = Presentation(source_path)
    source_numbers = {str(s.part.partname):i for i,s in enumerate(source_prs.slides)}
    repeats = set()
    for oi, slide in enumerate(prs.slides):
        connection_ids = {x.get('id'): x.get('name','').split('|',1)[0].rsplit('/',1)[-1] for x in slide._element.xpath('.//p:cNvPr') if x.get('name','').startswith('sss')}
        for sh in slide.shapes:
            name = marker(sh)
            if name.startswith('sss-repeat:'):
                sid = name[len('sss-repeat:'):]
                item = next((x for x in source.items if x.id == sid), None)
                title = source_prs.slides[item.slide].shapes.title if item else None
                valid_repeat = item and title is not None and item.origin == 'slide' and item.shape_id == title.shape_id and oi in mapping[str(item.slide)][1:] and (sid,oi) not in repeats
                repeats.add((sid,oi))
                if not valid_repeat or inventory.signature(sh, slide.part, numbers, connection_ids) != item.signature:
                    findings.append({'code': 'INVALID_STRUCTURAL_REPEAT', 'output_slide': oi, 'id': sid})
                continue
            if not name.startswith('sss:'):
                findings.append({'code': 'UNEXPLAINED_OBJECT', 'output_slide': oi})
                continue
            sid = name[4:]
            expected_placements = [p for p in report['placements'] if p['source_id']==sid and p['output_slide']==oi]
            if len(expected_placements)!=1 or list((sh.left,sh.top,sh.width,sh.height)) != expected_placements[0].get('bounds'):
                findings.append({'code':'PLACEMENT_ALTERED','id':sid,'output_slide':oi})
            if sh._element.xpath('.//a:rPr/a:solidFill//a:alpha[@val="0"] | .//a:defRPr/a:solidFill//a:alpha[@val="0"]'):
                findings.append({'code':'INVISIBLE_TEXT','id':sid,'output_slide':oi})
            found.setdefault(sid, []).append((oi, inventory.signature(sh, slide.part, numbers, connection_ids)))
            if any(el.get('hidden') == '1' for el in sh._element.xpath('.//p:cNvPr')):
                findings.append({'code': 'HIDDEN_CONTENT', 'id': sid, 'output_slide': oi})
    for item in source.items:
        if item.disposition == 'excluded_by_policy':
            continue
        records = found.pop(item.id, [])
        if not records:
            findings.append({'code': 'MISSING', 'id': item.id, 'source_slide': item.slide})
            continue
        if any(oi not in mapping.get(str(item.slide), []) for oi,_ in records):
            findings.append({'code': 'WRONG_SLIDE', 'id': item.id})
        expected = item.signature
        if len(records) == 1:
            actual = records[0][1]
        else:
            actual = dict(records[0][1])
            actual['text'] = [t for _,r in records for t in r['text']]
            actual['emphasis'] = [t for _,r in records for t in r['emphasis']]
            actual['links'] = [t for _,r in records for t in r['links']]
            if 'table' in expected:
                for _,r in records[1:]:
                    if not r.get('table') or r['table'][0]!=expected['table'][0]:
                        findings.append({'code':'TABLE_HEADER_ALTERED','id':item.id})
                actual['table'] = [row for index,(_,r) in enumerate(records) for row in (r['table'] if index==0 else r['table'][1:])]
            if any({k:v for k,v in r.items() if k not in ('text','links','emphasis','table')} !=
                   {k:v for k,v in expected.items() if k not in ('text','links','emphasis','table')} for _,r in records):
                findings.append({'code': 'DUPLICATED_OR_ALTERED_OBJECT', 'id': item.id})
        if actual != expected:
            changed=sorted(k for k in set(expected)|set(actual) if expected.get(k)!=actual.get(k))
            findings.append({'code': 'ALTERED_OR_DUPLICATED', 'id': item.id, 'source_slide': item.slide,
                             'message': f'Source slide {item.slide+1}, shape {item.shape_id}: exported {", ".join(changed)} differs from the source.',
                             'expected': expected, 'actual': actual})
    findings.extend({'code': 'INVENTED', 'id': sid} for sid in found)
    for si, expected in source.notes.items():
        outputs = mapping.get(str(si), [])
        if not outputs or inventory.user_notes(prs.slides[outputs[0]]) != expected:
            findings.append({'code': 'NOTES_ALTERED', 'source_slide': si})
        elif inventory.notes_links(prs.slides[outputs[0]],numbers) != inventory.notes_links(source_prs.slides[si],source_numbers):
            findings.append({'code':'NOTES_LINK_ALTERED','source_slide':si})
        for oi in outputs[1:]:
            if inventory.user_notes(prs.slides[oi]):
                findings.append({'code': 'NOTES_DUPLICATED', 'source_slide': si, 'output_slide': oi})
    findings.extend({'code': 'UNSUPPORTED', **x} for x in source.unsupported)
    return {'status': 'failed' if findings else 'passed', 'findings': findings,
            'candidate_sha256': inventory.sha256(candidate_path), 'source_sha256': source.source_sha256,
            'counts': dict(Counter(x.signature['kind'] for x in source.items)), 'items': len(source.items)}
