"""Conservative native-object emitter for the grounded pipeline.

Every source object is planned explicitly. Native relationships and geometry are
retained instead of translating a chart, table or diagram into incomplete atoms.
"""
from copy import deepcopy
from pathlib import Path
import math

from pptx import Presentation
from pptx.opc.packuri import PackURI
from pptx.oxml.ns import qn
from pptx.dml.color import RGBColor
from pptx.util import Inches, Pt
from pptx.enum.text import MSO_AUTO_SIZE

from . import inventory


class CoverageError(ValueError):
    def __init__(self, report):
        super().__init__('Source content cannot be preserved with the current supported methods.')
        self.report = report


def marker(shape):
    nodes = shape._element.xpath('.//p:cNvPr')
    return nodes[0].get('name', '').split('|',1)[0] if nodes else ''


def set_marker(shape, value):
    nodes = shape._element.xpath('.//p:cNvPr')
    if nodes:
        nodes[0].set('name', value)


def build(src_path, out_path, template_path, revisions=None):
    from app import brand as B
    inv = inventory.inspect(src_path)
    source, dest = Presentation(src_path), Presentation(template_path)
    revisions = {int(k): v for k, v in (revisions or {}).items()}
    # Remove template example slides, retain its theme/layouts/artwork.
    for sid in list(dest.slides._sldIdLst):
        dest.part.drop_rel(sid.rId)
        dest.slides._sldIdLst.remove(sid)
    layout = next((x for x in dest.slide_layouts if x.name == B.L_TITLE_ONLY), dest.slide_layouts[6])
    plans, mapping, corrections = [], {}, []
    for idx, slide in enumerate(source.slides):
        objects = list(inventory.source_objects(slide))
        body = [sh for origin, _, sh in objects if origin == 'slide' and sh.has_text_frame
                and sh != slide.shapes.title and len(inventory.paragraphs(sh)) > 1]
        revision = revisions.get(idx, {})
        tags = set(revision.get('tags', []))
        dense = any(len(inventory.paragraphs(sh)) > 10 or len(sh.text.split()) > 180 for sh in body)
        # Split only a single text body on a text-only slide. Mixed figures stay associated.
        eligible = len(body) == 1 and all(sh.has_text_frame for origin, _, sh in objects if origin == 'slide')
        tables = [sh for origin, _, sh in objects if origin == 'slide' and sh.has_table]
        table_eligible = len(tables)==1 and all(sh.has_table or sh==slide.shapes.title for origin,_,sh in objects if origin=='slide') and not any(c.span_height>1 for row in tables[0].table.rows for c in row.cells)
        table_split = table_eligible and (len(tables[0].table.rows)>9 or 'split' in tags)
        split = table_split or (eligible and (dense or 'split' in tags or 'dense' in tags))
        split_shape = tables[0] if table_split else body[0] if eligible else None
        pages = 1
        chunks = []
        if split:
            n = len(tables[0].table.rows) if table_split else len(inventory.paragraphs(body[0]))
            step = min(8, max(1, math.ceil(n / 2))) if 'split' in tags else 8
            if table_split:
                chunks = [[a, min(n, a + step)] for a in range(0, n, step)]
            else:
                # Paragraph count alone misses a slide containing several long quotations.
                start, words = 0, 0
                for pos, value in enumerate(inventory.paragraphs(body[0])):
                    count = len(value.split())
                    if pos > start and (pos-start >= step or words+count > 120):
                        chunks.append([start,pos]);start,words=pos,0
                    words += count
                chunks.append([start,n])
            pages = len(chunks)
        mapping[str(idx)] = list(range(len(plans), len(plans) + pages))
        for page in range(pages):
            placements = []
            for origin, part, sh in objects:
                item = next(x for x in inv.items if x.slide == idx and x.origin == origin and x.shape_id == sh.shape_id)
                if item.disposition == 'excluded_by_policy':
                    continue
                # On continuation pages repeat only the source title, explicitly marked structural.
                if page and not (split and sh is split_shape) and sh != slide.shapes.title:
                    continue
                repeat = page > 0 and sh == slide.shapes.title
                placements.append({'source_id': item.id, 'source_slide': idx, 'output_slide': len(plans),
                                   'paragraph_range': chunks[page] if split and not table_split and sh is split_shape else None,
                                   'row_range': chunks[page] if table_split and sh is split_shape else None,
                                   'structural_repeat': repeat, 'origin': origin, 'shape_id': sh.shape_id})
            plans.append({'source_slide': idx, 'page': page, 'placements': placements})
        actions = []
        if 'split' in tags:
            actions.append({'action': 'split', 'status': 'applied' if pages > 1 else 'unsupported',
                            'message': f'Created {pages} output slides.' if pages > 1 else 'Splitting supports a single text body or an unmerged-row table with its title; mixed visuals stay together.'})
        if 'emphasis' in tags:
            actions.append({'action': 'emphasis', 'status': 'no_change' if revision.get('reset_emphasis') else 'needs_input',
                            'message': 'Source emphasis retained.' if revision.get('reset_emphasis') else 'Select reset to source emphasis; a general tag does not identify text.'})
        for tag in tags - {'split', 'emphasis'}:
            actions.append({'action': tag, 'status': 'no_change', 'message': 'Native source geometry retained; verification will identify remaining issues.'})
        corrections.append({'index': idx, 'actions': actions})
    flat = [p for plan in plans for p in plan['placements'] if not p['structural_repeat']]
    coverage = inventory.validate_placements(inv, flat)
    if coverage['status'] != 'passed':
        raise CoverageError(coverage)
    slides = []
    for plan in plans:
        slide = dest.slides.add_slide(layout)
        for sh in list(slide.shapes):
            slide.shapes._spTree.remove(sh._element)
        slides.append(slide)
    imported = set()
    source_slide_numbers = {str(s.part.partname): i for i,s in enumerate(source.slides)}
    used_names = {str(p.partname) for p in dest.part.package.iter_parts()}

    def import_part(part):
        if part in imported:
            return part
        imported.add(part)
        name = str(part.partname)
        if name in used_names:
            path = Path(name)
            n = 1
            while str(path.with_name(f'source{n}_{path.name}')).replace('\\','/') in used_names:
                n += 1
            part._partname = PackURI(str(path.with_name(f'source{n}_{path.name}')).replace('\\','/'))
        used_names.add(str(part.partname))
        for rel in part.rels.values():
            if not rel.is_external:
                import_part(rel.target_part)
        return part

    def copy_relationships(element, old_part, new_part):
        for node in element.iter():
            for key, rid in list(node.attrib.items()):
                if key.startswith('{' + inventory.R + '}'):
                    rel = old_part.rels[rid]
                    if rel.is_external:
                        target = rel.target_ref
                    elif str(rel.target_part.partname) in source_slide_numbers:
                        target_idx = source_slide_numbers[str(rel.target_part.partname)]
                        target = slides[mapping[str(target_idx)][0]].part
                    else:
                        target = import_part(rel.target_part)
                    node.set(key, new_part.relate_to(target, rel.reltype, rel.is_external))

    for out_idx, plan in enumerate(plans):
        src_slide = source.slides[plan['source_slide']]
        dst_slide = slides[out_idx]
        objects = {(origin, sh.shape_id): (part, sh) for origin, part, sh in inventory.source_objects(src_slide)}
        scale = min((dest.slide_width - Inches(1.2)) / source.slide_width,
                    (dest.slide_height - Inches(1.0)) / source.slide_height)
        dx = (dest.slide_width - source.slide_width * scale) / 2
        dy = (dest.slide_height - source.slide_height * scale) / 2
        shape_ids = {}
        cloned = []
        for placement in plan['placements']:
            part, original = objects[(placement['origin'], placement['shape_id'])]
            element = deepcopy(original._element)
            copy_relationships(element, part, dst_slide.part)
            # Remove placeholder binding to an unrelated destination layout.
            for ph in element.xpath('.//p:ph'):
                ph.getparent().remove(ph)
            for c in element.xpath('.//p:cNvPr'):
                old_id = c.get('id')
                new_id = str(dst_slide.shapes._next_shape_id + len(shape_ids) + 1)
                shape_ids[(placement['origin'], old_id)] = new_id
                c.set('id', new_id)
                c.set('name', 'sss-node:' + placement['source_id'].rsplit('/', 1)[0] + '/' + old_id)
            cloned.append((placement['origin'], element))
            dst_slide.shapes._spTree.insert_element_before(element, 'p:extLst')
            shape = list(dst_slide.shapes)[-1]
            from .text_style import materialize
            materialize(original,shape)
            is_title = original == src_slide.shapes.title
            default = (Inches(.5), Inches(.3 if is_title else 1.6), source.slide_width-Inches(1), Inches(.8 if is_title else 4))
            rect = [v if v is not None else default[j] for j,v in enumerate((original.left,original.top,original.width,original.height))]
            shape.left = int(dx + rect[0] * scale)
            shape.top = int(dy + rect[1] * scale)
            shape.width = max(1, int(rect[2] * scale))
            shape.height = max(1, int(rect[3] * scale))
            if is_title and original.has_text_frame and original.text.strip():
                shape.left,shape.top = Inches(.7),Inches(.35)
                shape.width,shape.height = dest.slide_width-Inches(1.4),Inches(1.1)
            span = placement['paragraph_range']
            if span is not None:
                ps = [p for p in shape.text_frame.paragraphs if inventory.normalize(p.text)]
                keep = {p._p for p in ps[span[0]:span[1]]}
                for p in list(shape.text_frame.paragraphs):
                    if p._p not in keep:
                        p._p.getparent().remove(p._p)
                shape.top = Inches(1.6)
                shape.height = dest.slide_height - Inches(2.2)
                shape.left = Inches(.7)
                shape.width = dest.slide_width - Inches(1.4)
            rows = placement.get('row_range')
            if rows is not None:
                table = shape.table
                all_rows = list(table._tbl.tr_lst)
                keep_rows = set(all_rows[rows[0]:rows[1]])
                if rows[0] > 0:
                    keep_rows.add(all_rows[0])
                for row in all_rows:
                    if row not in keep_rows:
                        table._tbl.remove(row)
                shape.left,shape.top = Inches(.7),Inches(1.6)
                for col in table.columns:
                    col.width = int((dest.slide_width-Inches(1.4))/len(table.columns))
                for row in table.rows:
                    row.height = int((dest.slide_height-Inches(2.2))/len(table.rows))
            placement['bounds'] = [shape.left,shape.top,shape.width,shape.height]
            prefix = 'sss-repeat:' if placement['structural_repeat'] else 'sss:'
            set_marker(shape, prefix + placement['source_id'] + ('|title' if is_title else ''))
            # Standardize text without collapsing runs or touching source emphasis.
            for _, child in inventory.walk_shapes([shape]):
                frames = [child.text_frame] if child.has_text_frame else []
                if child.has_table:
                    frames += [c.text_frame for row in child.table.rows for c in row.cells]
                for tf in frames:
                    tf.word_wrap = True
                    tf.auto_size = MSO_AUTO_SIZE.NONE
                    for p in tf.paragraphs:
                        for r in p.runs:
                            r.font.name = B.FONT
                            r.font.size = Pt(B.TITLE_PT if is_title else max(B.BODY_MIN_PT, (r.font.size or p.font.size or Pt(20)).pt * scale))
                            # Honor explicit white text on filled visuals. Preserve color semantics
                            # for diagrams; structural lint will expose unsupported palette decisions.
                            if r.font.color.type is None and not child.has_table:
                                r.font.color.rgb = RGBColor.from_string(B.INK)
                            else:
                                try:
                                    color = r.font.color.rgb
                                    channels = list(color)
                                    if str(color) == 'FF0000':
                                        r.font.color.rgb = RGBColor.from_string(B.RED)
                                    elif max(channels)-min(channels) < 18 and str(color) != B.WHITE:
                                        r.font.color.rgb = RGBColor.from_string(B.INK)
                                except (AttributeError, TypeError):
                                    pass
        for origin, element in cloned:
            for connection in element.xpath('.//a:stCxn | .//a:endCxn'):
                key = (origin, connection.get('id'))
                if key not in shape_ids:
                    raise ValueError('Connector target is not present in the output slide')
                connection.set('id', shape_ids[key])
        if plan['page'] == 0 and src_slide.has_notes_slide:
            src_tf = src_slide.notes_slide.notes_text_frame
            dst_tf = dst_slide.notes_slide.notes_text_frame
            if src_tf is not None and dst_tf is not None:
                body = deepcopy(src_tf._txBody)
                copy_relationships(body, src_slide.notes_slide.part, dst_slide.notes_slide.part)
                dst_tf._txBody.getparent().replace(dst_tf._txBody, body)
    dest.save(out_path)
    return {'source': str(src_path), 'output': str(out_path), 'slide_count': len(slides),
            'coverage': {'ok': True, 'source': len(inv.items), 'placed': len({p['source_id'] for p in flat}),
                         'excluded': [{'id':x.id, 'reason':x.policy_reason} for x in inv.items if x.disposition == 'excluded_by_policy']},
            'plan_coverage': coverage, 'inventory': inv.to_dict(), 'placements': flat,
            'source_to_output_slides': mapping, 'corrections': corrections,
            'slides': [{'index': i, 'source_index': p['source_slide'], 'kind': 'content',
                        'layout': 'Native preserved layout', 'hard_issues': 0} for i,p in enumerate(plans)],
            'llm_used': False, 'vision_used': False, 'repair_count': 0}
