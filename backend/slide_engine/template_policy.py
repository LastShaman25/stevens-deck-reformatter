"""Geometry contract for the bundled Stevens template (coordinates in inches).

The content box deliberately ends above the master's footer, logo and rule.
Opening uses the mostly red Title Slide; closing uses the statue-photo 1_Title Slide. Names in the bundled file are misleading; visual roles are explicit.
"""
from pptx.util import Inches
import math

CONTENT = (.70, .40, 11.70, 6.05)
OPENING_LAYOUT = 'Title Slide'
CLOSING_LAYOUT = '1_Title Slide'
TEMPLATE_ROLE_RULE = ('Opening/first page: Title Slide, mostly burgundy/red with a faint tower on the left and a white Stevens mark at top-right; NO campus/statue photograph. Closing/thank-you page: 1_Title Slide, statue photograph on the left and burgundy on the right. Despite its name, 1_Title Slide is the CLOSING artwork. Do not use Thank You Slide (balloon photograph). Never swap these roles.')
COVER_TITLE = (4.648, 2.739, 7.962, 2.255)
COVER_SUPPORT = (.55, 2.74, 3.60, 3.50)
# The left edge of the burgundy panel slopes right toward the bottom; keep
# the entire details block, including bottom notes, clear of that diagonal.
COVER_DETAILS = (5.114, 5.021, 7.496, 1.664)
CLOSING_TITLE = (7.967, 2.80, 4.643, 2.15)
CLOSING_DETAILS = (7.75, 5.021, 4.86, 1.664)
# Start below the complete top-right mark, rather than using the layout's
# oversized title placeholder whose top edge shares the logo's vertical band.
SECTION_TITLE = (7.236, 2.50, 5.374, 3.22)
SECTION_DETAILS = (7.50, 5.90, 5.11, 1.02)
SECTION_SUPPORT = (.45, 1.15, 5.95, 5.30)
BACKGROUND_NAME = 'template-source-background'
EMU = 914400
CANVAS = (12192000, 6858000)


def retain_opening_artwork(prs):
    """Keep filled date-placeholder artwork when replacing sample cover text.

    The bundled date field masks the right end of the opening's bottom rule.
    Removing its text must not also remove this visible part of the reference.
    Materialize only its native fill/geometry as fixed layout artwork.
    """
    from copy import deepcopy
    layout=next(l for l in prs.slide_layouts if l.name==OPENING_LAYOUT)
    for shape in list(layout.shapes):
        if not shape.is_placeholder or not shape._element.xpath('./p:nvSpPr/p:nvPr/p:ph[@type="dt"]'):
            continue
        if not shape._element.xpath('./p:spPr/a:solidFill'): continue
        name=f'template-placeholder-artwork-{shape.shape_id}'
        if any(s.name==name for s in layout.shapes): continue
        element=deepcopy(shape._element)
        for ph in element.xpath('./p:nvSpPr/p:nvPr/p:ph'): ph.getparent().remove(ph)
        for body in element.xpath('./p:txBody'): body.getparent().remove(body)
        prop=element.xpath('./p:nvSpPr/p:cNvPr')[0]
        prop.set('name',name);prop.set('id',str(max(s.shape_id for s in layout.shapes)+1))
        layout.shapes._spTree.insert_element_before(element,'p:extLst')


def canvas_matches(width, height, expected=CANVAS):
    # Decimal inches from PDF import can round one EMU below the native size.
    return all(abs(a-b)<=2 for a,b in zip((width,height),expected))


def is_cover(slide):
    return slide.slide_layout.name == OPENING_LAYOUT


def is_closing(slide):
    return slide.slide_layout.name == CLOSING_LAYOUT


def is_section(slide):
    return slide.slide_layout._element.get('type') == 'secHead'


def regions(slide):
    if is_closing(slide): return (CLOSING_TITLE, CLOSING_DETAILS, SECTION_SUPPORT)
    if is_cover(slide): return (COVER_TITLE, COVER_DETAILS, COVER_SUPPORT)
    if is_section(slide): return (SECTION_TITLE, SECTION_DETAILS, SECTION_SUPPORT)
    return (CONTENT,)


def is_preserved(slide):
    return slide._element.cSld.get('name','').startswith('sss:preserved:')


def unchanged_blob(part):
    """Ignore only the nonvisual slide-name marker; all rendering data stays exact."""
    from lxml import etree
    from pptx.oxml.ns import qn
    if part.content_type not in ('application/vnd.openxmlformats-officedocument.presentationml.slide+xml',
                                 'application/vnd.openxmlformats-officedocument.presentationml.slideMaster+xml'):
        return part.blob
    element=etree.fromstring(part.blob); csld=element.find(qn('p:cSld'))
    if csld is not None:
        name=csld.get('name','')
        while name.startswith('sss:preserved:'): name=name[len('sss:preserved:'):]
        if name: csld.set('name',name)
        else: csld.attrib.pop('name',None)
    # Layout numeric IDs must be unique across merged masters. Relationships and
    # ordering still participate in the fingerprint; these IDs have no visual role.
    for node in element.findall('./'+qn('p:sldLayoutIdLst')+'/'+qn('p:sldLayoutId')):
        node.attrib.pop('id',None)
    return etree.tostring(element,method='c14n',exclusive=True)


def register_master(prs,slide):
    """Imported slide masters must also belong to presentation.xml's master list."""
    from pptx.opc.constants import RELATIONSHIP_TYPE as RT
    from pptx.oxml.xmlchemy import OxmlElement
    from pptx.oxml.ns import qn
    master=slide.slide_layout.slide_master.part
    rid=prs.part.relate_to(master,RT.SLIDE_MASTER)
    listing=prs._element.get_or_add_sldMasterIdLst()
    if any(e.get(qn('r:id'))==rid for e in listing): return
    ids=[int(e.get('id')) for e in listing]
    for owner in prs.slide_masters:
        ids += [int(e.get('id')) for e in owner._element.xpath('./p:sldLayoutIdLst/p:sldLayoutId')]
    next_id=max([2147483647]+ids)+1
    entry=OxmlElement('p:sldMasterId')
    entry.set('id',str(next_id))
    entry.set(qn('r:id'),rid); listing.append(entry)
    for node in master.slide_master._element.xpath('./p:sldLayoutIdLst/p:sldLayoutId'):
        next_id+=1;node.set('id',str(next_id))


def contains(rect, region, tolerance=.015):
    x,y,w,h = rect; a,b,c,d = region
    return x >= a-tolerance and y >= b-tolerance and x+w <= a+c+tolerance and y+h <= b+d+tolerance


def contract(slide):
    if is_closing(slide):
        return {'layout':CLOSING_LAYOUT, 'slide_kind':'closing', 'title_box':CLOSING_TITLE,
                'details_box':CLOSING_DETAILS, 'protected_footer':None,
                'rule':TEMPLATE_ROLE_RULE+' Use the approved closing artwork, white title and short closing points on the burgundy right panel. Keep the photo and logo clear. Do not apply interior footer rules or add a bottom-left wordmark.'}
    if is_preserved(slide):
        return {'slide_kind':'unchanged_source','layout':slide.slide_layout.name,
                'section_header':is_section(slide),
                'bottom_left_logo':'omit on section headers; preserve the original top-right mark' if is_section(slide) else 'follow the source slide type',
                'rule':'Source-first decision: this already matches the template. Preserve it exactly, including its original master, logo, picture, fonts and positions. Do not add an interior frame or extra logo. QA must verify source equivalence and the keep decision.'}
    if is_section(slide):
        return {'layout':slide.slide_layout.name, 'slide_kind':'section',
                'title_box':SECTION_TITLE, 'details_box':SECTION_DETAILS, 'support_box':SECTION_SUPPORT,
                'protected_footer':None, 'bottom_left_logo':'omit',
                'rule':'Use the Section Header photo/title composition. Omit the bottom-left Stevens wordmark; preserve complete top-right branding with its original typography. Do not add an interior frame, footer wordmark or a miniature source slide. Use dark title/details text on the white right panel. Interior footer restrictions do not apply.'}
    if is_cover(slide):
        return {'layout':OPENING_LAYOUT, 'slide_kind':'cover', 'title_box':COVER_TITLE,
                'details_box':COVER_DETAILS, 'support_box':COVER_SUPPORT,
                'title_and_details_text_color':'white on the inherited red template field',
                'protected_footer':None,
                'approved_template_artwork':'Mostly red/burgundy field, faint tower on the left, white Stevens mark at top-right and a bottom rule. There is no inherited campus or statue photo on the opening.',
                'rule':TEMPLATE_ROLE_RULE+' Extract native title and details into the right-hand named regions. Preserve meaningful source visuals in support_box; never paste an old cover/background inset. No added template photo and no interior footer logo.'}
    return {'layout':slide.slide_layout.name, 'slide_kind':'content', 'content_box':CONTENT,
            'protected_footer':(0,6.65,13.333333, .85),
            'rule':'Every editable element, including source footers/logos, must stay inside content_box. The inherited bottom-left Stevens logo and footer band must remain uncovered.'}


def solid_background(slide):
    """Resolve explicit RGB solid backgrounds without mutating source XML."""
    for owner in (slide, slide.slide_layout, slide.slide_layout.slide_master):
        bg = owner._element.xpath('./p:cSld/p:bg/p:bgPr/a:solidFill/a:srgbClr')
        if bg: return bg[0].get('val')
        if owner._element.xpath('./p:cSld/p:bg'): return None
    return None


def background_region(slide):
    return regions(slide)[-1]


def needs_source_background(source_slide,destination_slide,height,removed=(),decision=None):
    if is_cover(destination_slide) or is_closing(destination_slide): return False
    if not (is_cover(destination_slide) or is_section(destination_slide)): return True
    from . import inventory
    extracted=cover_roles(source_slide,height,decision,regions(destination_slide)[:2])
    # Cover text now lives on the template's red field. An obsolete source fill
    # need not cover the campus photo when no retained elements depend on it.
    # A photo or decorative rule does not require an opaque full-canvas panel.
    # Keep contrast support only for retained text not transferred to template text boxes.
    return any(s.has_text_frame and s.text.strip() and (origin,s.shape_id) not in removed and not (origin=='slide' and s.shape_id in extracted)
               for origin,_,s in inventory.source_objects(source_slide))


def check(candidate):
    from pptx import Presentation
    prs = Presentation(candidate); findings=[]
    for i,slide in enumerate(prs.slides):
        if i == 0 and not is_cover(slide):
            findings.append({'code':'FIRST_PAGE_TEMPLATE','criterion':'brand_consistency',
                'severity':'blocking','output_slide':0,'object_ids':[],
                'message':'Recompose the first output page with the mostly red Title Slide opening layout before reviewing or releasing it.'})
        if i == 0 and is_cover(slide) and not is_preserved(slide):
            if any(s.name==BACKGROUND_NAME for s in slide.shapes):
                findings.append({'code':'COVER_SOURCE_PANEL','criterion':'spatial_layout',
                    'severity':'blocking','output_slide':0,'object_ids':[BACKGROUND_NAME],
                    'message':'Remove the obsolete source background panel from the red opening artwork; place source text in the right-hand template regions.'})
            titles=[s for s in slide.shapes if s.has_text_frame and s.text.strip()
                    and (s.name.endswith('|title') or s.name=='authored-title')]
            if not titles:
                findings.append({'code':'COVER_TITLE_MISSING','criterion':'structure_sequence',
                    'severity':'blocking','output_slide':0,'object_ids':[],
                    'message':'Identify the source title and place native title text in the cover title box.'})
        if is_preserved(slide): continue # Independently checked against the entire source part graph.
        # Group descendants are checked in absolute coordinates by the AI editor;
        # root containment also protects the inherited master from whole-group moves.
        from app.ai.layout import nodes
        for ident,shape,box,parent,locked in nodes(slide):
            if shape.rotation:
                x,y,w,h=box; angle=math.radians(shape.rotation)
                bw=abs(w*math.cos(angle))+abs(h*math.sin(angle))
                bh=abs(w*math.sin(angle))+abs(h*math.cos(angle))
                box=(x+(w-bw)/2,y+(h-bh)/2,bw,bh)
            if not any(contains(box, r) for r in regions(slide)):
                findings.append({'code':'TEMPLATE_CONTENT_BOUNDS','criterion':'spatial_layout',
                    'severity':'blocking','output_slide':i,'object_ids':[ident],
                    'message':'Place this element inside its template content region; leave the inherited logo and footer uncovered.'})
            if is_cover(slide) and (ident.endswith('|title') or ident=='authored-title') and not contains(box,COVER_TITLE):
                findings.append({'code':'COVER_TITLE_POSITION','criterion':'spatial_layout',
                    'severity':'blocking','output_slide':i,'object_ids':[ident],
                    'message':'Place the extracted cover title in the first-page template title box.'})
            if is_cover(slide) and shape.has_text_frame and shape.text.strip() and not ident.endswith(('|logo','|code')) and not parent:
                if not any(contains(box,r) for r in (COVER_TITLE,COVER_DETAILS)):
                    findings.append({'code':'COVER_TEXT_POSITION','criterion':'spatial_layout',
                        'severity':'blocking','output_slide':i,'object_ids':[ident],
                        'message':'Keep cover notes, footers and metadata in the right-hand text regions, not over the opening artwork.'})
    return {'status':'failed' if findings else 'passed','findings':findings}


def cover_roles(slide, height, decision=None, text_regions=(COVER_TITLE,COVER_DETAILS)):
    """Conservative native extraction before any layout change; AI rechecks roles later.

    Ordinary text boxes can be titles. Never require a PowerPoint title placeholder.
    Keep uncertain graphics intact rather than deleting presumed decoration.
    """
    cover=text_regions in ((COVER_TITLE,COVER_DETAILS),(CLOSING_TITLE,CLOSING_DETAILS))
    def flow_details(elements,roles):
        x,y,w,h=text_regions[1];gap=.025
        ordered=sorted(elements,key=lambda s:((s.top or 0),(s.left or 0)))
        result={}
        for font in range(18,10,-1):
            capacity=max(1,int(w*72/(font*.55)))
            lines=[sum(max(1,math.ceil(len(line)/capacity)) for line in s.text.splitlines()) for s in ordered]
            heights=[count*font*1.22/72+.015 for count in lines]
            if sum(heights)+gap*max(0,len(ordered)-1)<=h:break
        total=sum(heights) or 1
        factor=min(1,(h-gap*max(0,len(ordered)-1))/total)
        for s,size in zip(ordered,heights):
            size*=factor
            result[s.shape_id]={'role':roles.get(s.shape_id,'supporting_text'),'font_size':font,
                'box':(x,y,w,size),'basis':'cover text flow with measured line allowance'}
            y+=size+gap
        return result
    text = [s for s in slide.shapes if s.has_text_frame and s.text.strip()
            and (cover or (s.top or 0) < height*.9)]
    if not text: return {}
    if decision:
        # Use the pre-composition semantic decision. Never promote a logo/statistic
        # into a cover heading merely because it has the largest font.
        roles={int(e['id'].rsplit('/',1)[-1]):e['role'] for e in decision['elements']
               if e['id'].rsplit('/',2)[-2]=='slide'}
        titles=[s for s in text if roles.get(s.shape_id)=='title']
        if not titles: raise ValueError('Cover extraction requires a semantically identified native title.')
        details=[s for s in text if (roles.get(s.shape_id) in ('subtitle','author','body')
                 or (cover and roles.get(s.shape_id) in ('footer','caption','unknown')))]
        result={}
        for elements,region,role in ((titles,text_regions[0],'title'),(details,text_regions[1],'supporting_text')):
            if cover and role=='supporting_text':
                result.update(flow_details(elements,roles));continue
            x,y,w,h=region
            ordered=sorted(elements,key=lambda s:((s.top or 0),(s.left or 0)))
            weights=[max(1,len(s.text.splitlines())) for s in ordered];total=sum(weights) or 1
            for s,weight in zip(ordered,weights):
                size=h*weight/total
                result[s.shape_id]={'role':role if role=='title' else roles[s.shape_id],
                    'box':(x,y,w,size),'basis':'validated source semantic role'}
                y+=size
        return result
    def rank(s):
        sizes=[r.font.size.pt for p in s.text_frame.paragraphs for r in p.runs if r.font.size]
        sizes += [p.font.size.pt for p in s.text_frame.paragraphs if p.font.size]
        return (max(sizes or [18]), -(s.top or 0))
    native=slide.shapes.title
    title=next((s for s in text if native is not None and s.shape_id==native.shape_id),None)
    if title is None: title=max(text,key=rank)
    result={title.shape_id:{'role':'title','box':text_regions[0],'basis':'native title or largest source text'}}
    details=sorted([s for s in text if s is not title],key=lambda s:((s.top or 0),(s.left or 0)))
    if cover:
        result.update(flow_details(details,{}));return result
    x,y,w,h=text_regions[1]
    weights=[max(1,len(s.text.splitlines())) for s in details]
    total=sum(weights) or 1
    for s,weight in zip(details,weights):
        size=h*weight/total
        result[s.shape_id]={'role':'subtitle' if len(result)==1 else 'supporting_text',
                           'box':(x,y,w,size),'basis':'source reading order after title extraction'}
        y+=size
    return result
