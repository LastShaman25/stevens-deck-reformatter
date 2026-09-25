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
from . import template_policy as T


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


def build(src_path, out_path, template_path, revisions=None, source_decisions=None):
    from app import brand as B
    inv = inventory.inspect(src_path)
    source, dest = Presentation(src_path), Presentation(template_path)
    source_decisions=source_decisions or {}
    if source_decisions:
        from app.ai.source_decisions import validate
        for key,value in source_decisions.items():
            decision=validate(value,source,int(key),inv.source_sha256)
            if decision.action=='keep_original' and not T.canvas_matches(source.slide_width,source.slide_height,(dest.slide_width,dest.slide_height)):
                raise ValueError('An unchanged source slide must have the template canvas dimensions.')
            for item in inv.items:
                if item.id in decision.remove_ids:
                    item.disposition='excluded_by_policy'
                    item.policy_reason='source-decision: redundant non-content artwork; independent paired QA required'
    revisions = {int(k): v for k, v in (revisions or {}).items()}
    # Remove template example slides, retain its theme/layouts/artwork.
    for sid in list(dest.slides._sldIdLst):
        dest.part.drop_rel(sid.rId)
        dest.slides._sldIdLst.remove(sid)
    layout = next((x for x in dest.slide_layouts if x.name == B.L_TITLE_ONLY), dest.slide_layouts[6])
    cover_layout = next(x for x in dest.slide_layouts if x.name == B.L_TITLE)
    section_layout = next(x for x in dest.slide_layouts if x.name == 'Section Header')
    # Hide only the content master's furniture. Keep the section layout's own
    # photo and top-right logo; do not mutate the shared master or cover layout.
    section_layout._element.set('showMasterSp','0')
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
        keep_original=source_decisions.get(str(idx),{}).get('action')=='keep_original'
        if keep_original: split=False
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
            plans.append({'source_slide': idx, 'page': page, 'placements': placements,'keep_original':keep_original})
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
        section = source_decisions.get(str(plan['source_slide']),{}).get('slide_kind')=='section'
        slide = dest.slides.add_slide(cover_layout if plan['source_slide']==0 and plan['page']==0 else section_layout if section else layout)
        for sh in list(slide.shapes):
            slide.shapes._spTree.remove(sh._element)
        slides.append(slide)
    imported = set()
    source_slide_numbers = {s.part: i for i,s in enumerate(source.slides)}
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
                    elif rel.target_part in source_slide_numbers:
                        target_idx = source_slide_numbers[rel.target_part]
                        target = slides[mapping[str(target_idx)][0]].part
                    else:
                        target = import_part(rel.target_part)
                    node.set(key, new_part.relate_to(target, rel.reltype, rel.is_external))

    # Import unchanged slides with their original layout, master, theme and notes.
    # No shape rewriting, extra branding, scaling or font normalization is allowed.
    for out_idx,plan in enumerate(plans):
        if not plan['keep_original']: continue
        from pptx.opc.constants import RELATIONSHIP_TYPE as RT
        part=source.slides[plan['source_slide']].part
        part.slide._element.cSld.set('name','sss:preserved:'+part.slide._element.cSld.get('name',''))
        part._partname=PackURI(f'/ppt/slides/sss-preserved-{out_idx+1}.xml')
        old=dest.slides._sldIdLst[out_idx].rId
        rid=dest.part.relate_to(import_part(part),RT.SLIDE)
        T.register_master(dest,part.slide)
        dest.slides._sldIdLst[out_idx].set(qn('r:id'),rid)
        dest.part.drop_rel(old)
        slides[out_idx]=part.slide

    for out_idx, plan in enumerate(plans):
        if plan['keep_original']: continue
        src_slide = source.slides[plan['source_slide']]
        dst_slide = slides[out_idx]
        objects = {(origin, sh.shape_id): (part, sh) for origin, part, sh in inventory.source_objects(src_slide)}
        cover = T.is_cover(dst_slide)
        decision=source_decisions.get(str(plan['source_slide']))
        cover_pictures=[e for e in (decision or {}).get('elements',[]) if e['role']=='image'
                        and e.get('artwork_action','retain')=='retain' and not e.get('contains_logo')]
        if cover and len(cover_pictures)==1:
            selected=next((s for (origin,sid),(_,s) in objects.items()
                           if cover_pictures[0]['id'].endswith(f'/{origin}/{sid}')),None)
            if selected is not None and selected._element.tag==qn('p:pic'):
                # Replace the bundled campus photo, rather than stacking a
                # second photograph on it. The separate burgundy/mark artwork stays.
                for artwork in list(dst_slide.slide_layout.shapes):
                    if artwork.shape_id==7 and artwork.name=='Picture 6' and artwork._element.tag==qn('p:pic'):
                        artwork._element.getparent().remove(artwork._element)
                dst_slide.slide_layout._element.set('showMasterSp','0')
                dst_slide._element.cSld.set('name','sss:cover-source-photo')
        extracted = T.cover_roles(src_slide, source.slide_height,decision,T.regions(dst_slide)[:2]) if cover or T.is_section(dst_slide) else {}
        plan['element_extraction'] = extracted
        region = T.background_region(dst_slide)
        rx,ry,rw,rh = [Inches(v) for v in region]
        # Fit the actual native canvas, including any source bleed, into the safe box.
        rects = [(s.left,s.top,s.width,s.height) for _,s in objects.values()
                 if all(v is not None for v in (s.left,s.top,s.width,s.height))]
        left=min([0]+[r[0] for r in rects]); top=min([0]+[r[1] for r in rects])
        right=max([source.slide_width]+[r[0]+r[2] for r in rects])
        bottom=max([source.slide_height]+[r[1]+r[3] for r in rects])
        scale = min(rw/(right-left),rh/(bottom-top))
        dx = rx+(rw-(right-left)*scale)/2-left*scale
        dy = ry+(rh-(bottom-top)*scale)/2-top*scale
        # A source slide background is not a source shape. Preserve its contrast
        # in a bounded, independently reconstructible panel, behind native content.
        background=T.solid_background(src_slide)
        removed={(p.origin,p.shape_id) for p in inv.items if p.slide==plan['source_slide'] and p.disposition=='excluded_by_policy'}
        extracted_ids={e['source_id'] for e in (decision or {}).get('logo_extractions',[])}
        removed.update((p.origin,p.shape_id) for p in inv.items if p.id in extracted_ids)
        if not T.needs_source_background(src_slide,dst_slide,source.slide_height,removed,decision): background=None
        if background:
            from pptx.enum.shapes import MSO_SHAPE
            panel=dst_slide.shapes.add_shape(MSO_SHAPE.RECTANGLE,rx,ry,rw,rh)
            panel.name=T.BACKGROUND_NAME
            panel.fill.solid(); panel.fill.fore_color.rgb=RGBColor.from_string(background)
            panel.line.fill.background()
        shape_ids = {}
        cloned = []
        for placement in plan['placements']:
            part, original = objects[(placement['origin'], placement['shape_id'])]
            extraction=next((e for e in (decision or {}).get('logo_extractions',[]) if e['source_id']==placement['source_id']),None)
            if extraction:
                from . import logo_assets
                from io import BytesIO
                blob,evidence=logo_assets.extract(original,extraction['region'])
                if extraction.get('placement')=='template_logo':
                    _,reuse=logo_assets.template_logo(blob,cover,dst_slide)
                    placement['bounds']=reuse['bounds']
                    placement['logo_extraction']={**evidence,'template_reuse':reuse}
                    continue
                pw,ph=evidence['pixel_size']
                # Fit inside the support/content box at >=100 source pixels/inch.
                # The layout agent can move it, but may not distort or restyle it.
                w=min(1.15,pw/100,region[2]);h=w*ph/pw
                if h>min(1.4,region[3]): h=min(1.4,region[3]);w=h*pw/ph
                shape=dst_slide.shapes.add_picture(BytesIO(blob),rx+rw-Inches(w),ry,Inches(w),Inches(h))
                set_marker(shape,'sss:'+placement['source_id']+'|extracted|logo')
                placement['bounds']=[shape.left,shape.top,shape.width,shape.height]
                placement['logo_extraction']=evidence
                continue
            source_role=next((e for e in source_decisions.get(str(plan['source_slide']),{}).get('elements',[])
                              if e['id']==placement['source_id']),{})
            is_logo=source_role.get('role')=='logo' or source_role.get('contains_logo',False)
            is_code=source_role.get('role')=='code'
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
            extracted_role = extracted.get(original.shape_id) if placement['origin']=='slide' else None
            is_title = (extracted_role or {}).get('role')=='title' or (not cover and original == src_slide.shapes.title)
            default = (Inches(.5), Inches(.3 if is_title else 1.6), source.slide_width-Inches(1), Inches(.8 if is_title else 4))
            rect = [v if v is not None else default[j] for j,v in enumerate((original.left,original.top,original.width,original.height))]
            shape.left = int(dx + rect[0] * scale)
            shape.top = int(dy + rect[1] * scale)
            shape.width = max(1, int(rect[2] * scale))
            shape.height = max(1, int(rect[3] * scale))
            if extracted_role:
                shape.left,shape.top,shape.width,shape.height = [Inches(v) for v in extracted_role['box']]
                placement['element_role']=extracted_role['role']
            elif cover and original._element.tag==qn('p:pic') and source_role.get('role')=='image' and not is_logo:
                # Place the actual picture, not its former whole-slide position.
                # Multiple related visuals retain their geometry for the planner.
                if len(cover_pictures)==1:
                    x,y,w,h=T.COVER_SUPPORT
                    factor=min(Inches(w)/original.width,Inches(h)/original.height)
                    shape.width=int(original.width*factor);shape.height=int(original.height*factor)
                    shape.left=Inches(x)+(Inches(w)-shape.width)//2
                    shape.top=Inches(y)+(Inches(h)-shape.height)//2
            elif is_title and original.has_text_frame and original.text.strip():
                shape.left,shape.top = Inches(.7),Inches(.4)
                shape.width,shape.height = Inches(T.CONTENT[2]),Inches(1.1)
            span = placement['paragraph_range']
            if span is not None:
                ps = [p for p in shape.text_frame.paragraphs if inventory.normalize(p.text)]
                keep = {p._p for p in ps[span[0]:span[1]]}
                for p in list(shape.text_frame.paragraphs):
                    if p._p not in keep:
                        p._p.getparent().remove(p._p)
                shape.top = Inches(1.6)
                shape.height = Inches(4.85)
                shape.left = Inches(.7)
                shape.width = Inches(T.CONTENT[2])
                if extracted_role:
                    shape.left,shape.top,shape.width,shape.height = [Inches(v) for v in extracted_role['box']]
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
                    col.width = int(Inches(T.CONTENT[2])/len(table.columns))
                for row in table.rows:
                    row.height = int(Inches(4.85)/len(table.rows))
            placement['bounds'] = [shape.left,shape.top,shape.width,shape.height]
            prefix = 'sss-repeat:' if placement['structural_repeat'] else 'sss:'
            set_marker(shape, prefix + placement['source_id'] + ('|logo' if is_logo else '|code' if is_code else '|title' if is_title else ''))
            # Standardize text without collapsing runs or touching source emphasis.
            for _, child in inventory.walk_shapes([shape]):
                frames = [child.text_frame] if child.has_text_frame else []
                if child.has_table:
                    frames += [c.text_frame for row in child.table.rows for c in row.cells]
                for tf in frames:
                    if is_logo or is_code:
                        # Treat wordmark typography as artwork, not body text.
                        if is_logo:
                            for p in tf.paragraphs:
                                for r in p.runs:
                                    if r.font.size: r.font.size=Pt(r.font.size.pt*scale)
                        if is_code:
                            tf.word_wrap=False
                            tf.auto_size=MSO_AUTO_SIZE.NONE
                        continue
                    # Keep the source line layout until the planner changes its
                    # geometry. A font floor alone crowds PDF lines/equations.
                    if extracted_role or span is not None:
                        tf.word_wrap = True
                    if extracted_role and extracted_role.get('font_size'):
                        tf.margin_top=tf.margin_bottom=tf.margin_left=tf.margin_right=0
                    tf.auto_size = MSO_AUTO_SIZE.NONE
                    for p in tf.paragraphs:
                        for r in p.runs:
                            r.font.name = B.FONT
                            r.font.size = Pt(B.TITLE_PT if is_title else (r.font.size or p.font.size or Pt(20)).pt * scale)
                            # Honor explicit white text on filled visuals. Preserve color semantics
                            # for diagrams; structural lint will expose unsupported palette decisions.
                            if extracted_role:
                                r.font.color.rgb = RGBColor.from_string(B.WHITE if cover else B.INK)
                                if not is_title: r.font.size=Pt(extracted_role.get('font_size',max(16,r.font.size.pt)))
                            elif r.font.color.type is None and not child.has_table:
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
            'source_decisions':source_decisions,
            'source_to_output_slides': mapping, 'corrections': corrections,
            'slides': [{'index': i, 'source_index': p['source_slide'], 'kind': 'cover' if T.is_cover(slides[i]) else 'content',
                        'layout': slides[i].slide_layout.name, 'template_contract':T.contract(slides[i]),
                        'element_extraction':p.get('element_extraction',{}), 'hard_issues': 0} for i,p in enumerate(plans)],
            'llm_used': False, 'vision_used': False, 'repair_count': 0}
