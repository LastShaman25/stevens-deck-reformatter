"""AI-editable geometry. Source text, relationships, data and emphasis are immutable."""

from slide_engine.package import save_deck
from copy import deepcopy
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field
from pptx import Presentation
from pptx.oxml.ns import qn
from pptx.util import Pt
from pptx.dml.color import RGBColor
from slide_engine.preserve import marker
from .. import brand
from slide_engine import template_policy as T

EMU=914400


class Edit(BaseModel):
    model_config=ConfigDict(extra='forbid',allow_inf_nan=False)
    id: str
    x: float = Field(ge=0,le=100)
    y: float = Field(ge=0,le=100)
    w: float = Field(gt=0,le=100)
    h: float = Field(gt=0,le=100)
    role: Literal['keep','title','subhead','body','caption'] = 'keep'
    font_size: float | None = Field(default=None,ge=11,le=60)
    color: Literal['keep','ink','red','white'] = 'keep'


class LayoutPlan(BaseModel):
    model_config=ConfigDict(extra='forbid')
    layout: str = Field(min_length=1,max_length=100)
    rationale: str = Field(max_length=2000)
    objects: list[Edit] = Field(max_length=500)


def group_frame(shape,frame):
    sx,sy,ox,oy=frame
    ext=shape._element.xpath('./p:grpSpPr/a:xfrm/a:chExt')[0]
    off=shape._element.xpath('./p:grpSpPr/a:xfrm/a:chOff')[0]
    gx=shape.width/max(1,int(ext.get('cx')));gy=shape.height/max(1,int(ext.get('cy')))
    return sx*gx,sy*gy,ox+sx*(shape.left-int(off.get('x'))*gx),oy+sy*(shape.top-int(off.get('y'))*gy)


def nodes(slide):
    def visit(shapes,frame=(1,1,0,0),parent=None,locked=False):
        sx,sy,ox,oy=frame
        for shape in shapes:
            if shape.name==T.BACKGROUND_NAME: continue
            ident=shape.name
            box=[(ox+sx*shape.left)/EMU,(oy+sy*shape.top)/EMU,sx*shape.width/EMU,sy*shape.height/EMU]
            group=shape._element.tag==qn('p:grpSp')
            rigid=locked or bool(shape.rotation) or bool(shape._element.xpath('./p:spPr/a:xfrm[@flipH="1" or @flipV="1"] | ./p:grpSpPr/a:xfrm[@rot or @flipH="1" or @flipV="1"]'))
            yield ident,shape,box,parent,rigid
            if group:
                yield from visit(shape.shapes,group_frame(shape,frame),ident,rigid)
    return list(visit(slide.shapes))


def describe(slide):
    result=[]
    for ident,shape,box,parent,locked in nodes(slide):
        kind='group' if shape._element.tag==qn('p:grpSp') else 'chart' if shape.has_chart else 'table' if shape.has_table else 'picture' if shape._element.tag==qn('p:pic') else 'shape'
        content=shape.text if shape.has_text_frame else ''
        if shape.has_table:content=[[c.text for c in row.cells] for row in shape.table.rows]
        fit={}
        if shape.has_text_frame:
            from ..qa.geometry import estimate_overflow
            tf=shape.text_frame
            fit={'text_fit_ratio':round(estimate_overflow(shape)[1],3),
                 'text_margins':{side:round(getattr(tf,'margin_'+side)/EMU,4)
                                 for side in ('left','right','top','bottom')}}
        result.append({'id':ident,'parent':parent,'kind':kind,'editable':True,
                       'layer':len(result),'box':[max(.000001,round(v,6)) if j>1 else round(v,6) for j,v in enumerate(box)],
                       'content':content,'locked_geometry':locked,'native_title':ident.endswith('|title'),
                       **fit,
                       'font_sizes':sorted({r.font.size.pt for p in shape.text_frame.paragraphs for r in p.runs if r.font.size}) if shape.has_text_frame else []})
    return result


def template_context(slide):
    """Inherited artwork is visible QA context, never silently editable source content."""
    if slide._element.get('showMasterSp') == '0': return []
    result = []
    for shape in slide.shapes:
        if shape.name==T.BACKGROUND_NAME:
            result.append({'id':shape.name,'parent':None,'editable':False,'kind':'source_background',
                'layer':0,'content':'Preserved source contrast panel; fixed behind content.',
                'box':[v/EMU for v in (shape.left,shape.top,shape.width,shape.height)]})
    for name, owner in [('master',slide.slide_layout.slide_master),('layout',slide.slide_layout)]:
        if name=='master' and slide.slide_layout._element.get('showMasterSp')=='0': continue
        for shape in owner.shapes:
            if shape.is_placeholder: continue
            result.append({'id':f'template:{name}:{shape.shape_id}', 'parent':None,
                'editable':False, 'kind':'template_artwork', 'layer':len(result),
                'provenance':'Approved bundled Stevens template artwork; permitted brand imagery, not new source content.',
                'bounds_note':'These are bounds of the entire artwork object, which may contain a small logo and intentional background bleed. They are NOT the logo bounds. Confirm alleged clipping against the rendered mark and matching approved template screenshot.',
                'name':shape.name, 'content':shape.text if shape.has_text_frame else '',
                'box':[round(v/EMU,6) if v is not None else None
                       for v in (shape.left,shape.top,shape.width,shape.height)]})
    return result


def resize_runs(tf, size):
    """Change the base size without flattening equation/caption run ratios."""
    for paragraph in tf.paragraphs:
        base=max([r.font.size.pt for r in paragraph.runs if r.font.size]+[0])
        for run in paragraph.runs:
            run.font.size=Pt(size*(run.font.size.pt/base if base and run.font.size else 1))


def constrain(plan,slide,findings,roles=None):
    """Execute requested placements through native geometry constraints.

    Pictures fit inside the requested rectangle without distortion. Unrequested
    restyling is discarded; semantic role labels are not implicit style commands.
    Validation and rendered QA still run after this deterministic projection.
    """
    plan=plan.model_copy(deep=True)
    current=nodes(slide);lookup={e.id:e for e in plan.objects}
    if len(lookup)!=len(plan.objects) or set(lookup)!={i for i,*_ in current}: return plan
    if any(e.x>T.CANVAS[0]/EMU or e.y>T.CANVAS[1]/EMU for e in plan.objects): return plan
    affected={ident for f in findings for ident in f.get('object_ids',[])}
    scope=affected & set(lookup)
    if scope:
        scope |= {rid for e in (roles.elements if roles else []) if e.id in scope for rid in e.related_ids} & set(lookup)
        for ident,_,_,parent,_ in current:
            if parent in scope: scope.add(ident)
    style_scope=set(scope)
    # Reflow may displace the next paragraph even if the role classifier did not
    # label it semantically related. Permit those geometric dependencies, while
    # retaining their styles and keeping distant, unrelated objects untouched.
    while scope:
        additions=set()
        for ident,_,box,parent,_ in current:
            if ident in scope: continue
            for owner in scope:
                e=lookup[owner]
                overlap=max(0,min(box[0]+box[2],e.x+e.w)-max(box[0],e.x))*max(0,min(box[1]+box[3],e.y+e.h)-max(box[1],e.y))
                if overlap>.005:
                    additions.add(ident);break
        if not additions: break
        scope |= additions
    for ident,shape,box,parent,locked in current:
        edit=lookup[ident]
        if scope and ident not in scope:
            edit.x,edit.y,edit.w,edit.h=box
        protected=ident.endswith(('|logo','|code'))
        if protected or (affected and ident not in style_scope):
            edit.role='keep';edit.font_size=None;edit.color='keep'
        # Native template titles carry the explicit |title marker. A PDF line
        # called 'title' by the model does not become a new template placeholder.
        if edit.role=='title' and not ident.endswith('|title'):
            edit.role='keep'
        if ident.endswith('|title'):
            edit.role='keep'
            if edit.font_size is not None: edit.font_size=brand.TITLE_PT
        if parent or locked: continue
        original_rect=(edit.x,edit.y,edit.w,edit.h)
        # Protect code characters/typeface without recentering each native text
        # line as if it were an image. Otherwise a requested shared left edge is lost.
        rigid=shape._element.tag in (qn('p:pic'),qn('p:grpSp')) or shape.has_chart or ident.endswith('|logo')
        if rigid:
            factor=min(edit.w/box[2],edit.h/box[3])
            edit.x+=(edit.w-box[2]*factor)/2;edit.y+=(edit.h-box[3]*factor)/2
            edit.w=box[2]*factor;edit.h=box[3]*factor
        regions=T.regions(slide)
        if T.is_cover(slide) and shape.has_text_frame and not protected:
            regions=(T.COVER_TITLE,) if ident.endswith('|title') else (T.COVER_DETAILS,)
        def distance(region):
            x,y,w,h=region
            return max(x-edit.x,0,edit.x+edit.w-x-w)**2+max(y-edit.y,0,edit.y+edit.h-y-h)**2
        x,y,w,h=min(regions,key=distance)
        factor=min(1,w/edit.w,h/edit.h)
        if rigid:edit.w*=factor;edit.h*=factor
        else:edit.w=min(edit.w,w);edit.h=min(edit.h,h)
        edit.x=min(max(edit.x,x),x+w-edit.w);edit.y=min(max(edit.y,y),y+h-edit.h)
        if shape._element.tag==qn('p:grpSp') and original_rect!=(edit.x,edit.y,edit.w,edit.h):
            # Children use absolute coordinates. Transform their proposed boxes
            # with their parent, rather than separating labels from diagrams.
            ox,oy,ow,oh=original_rect
            def descendant(child):
                while child:
                    if child==ident:return True
                    child=next((p for n,_,_,p,_ in current if n==child),None)
                return False
            for child,_,_,cp,_ in current:
                if cp and descendant(cp):
                    e=lookup[child]
                    e.x=edit.x+(e.x-ox)*edit.w/ow;e.y=edit.y+(e.y-oy)*edit.h/oh
                    e.w*=edit.w/ow;e.h*=edit.h/oh
    return plan


def validate(plan,slide,width,height):
    if T.is_preserved(slide):
        raise ValueError('The source-first keep decision forbids editing this slide.')
    current=nodes(slide);expected={i for i,*_ in current}
    ids=[e.id for e in plan.objects]
    if len(ids)!=len(set(ids)) or set(ids)!=expected:
        raise ValueError('The AI plan must reference every object exactly once, without adding IDs.')
    lookup={e.id:e for e in plan.objects}
    parents={ident:parent for ident,_,_,parent,_ in current}
    def protected_owner(ident):
        while ident:
            if ident.endswith(('|logo','|code')): return ident
            ident=parents.get(ident)
        return None
    for ident,shape,box,parent,locked in current:
        edit=lookup[ident];rect=[edit.x,edit.y,edit.w,edit.h]
        owner=protected_owner(ident)
        if owner:
            if edit.font_size is not None or edit.color!='keep' or edit.role!='keep':
                raise ValueError('Source logo/code typography and colors are protected; use geometry-only edits.')
            if owner.endswith('|logo') and box[3] and abs((edit.w/edit.h)/(box[2]/box[3])-1)>.03:
                raise ValueError('Source logos must retain their proportions.')
            if '|extracted|logo' in ident:
                pw,ph=shape.image.size
                if abs((edit.w/edit.h)/(pw/ph)-1)>.005 or min(pw/edit.w,ph/edit.h)<96:
                    raise ValueError('Extracted logos require exact proportions and at least 96 source pixels per inch; do not upscale blurry lettering.')
            if owner!=ident:
                root=next(b for n,_,b,_,_ in current if n==owner); moved=lookup[owner]
                sx=moved.w/root[2];sy=moved.h/root[3]
                wanted=[moved.x+(box[0]-root[0])*sx,moved.y+(box[1]-root[1])*sy,box[2]*sx,box[3]*sy]
                if any(abs(a-b)>.002 for a,b in zip(rect,wanted)):
                    raise ValueError('Multipart source logos must move as one intact group.')
        if edit.x+edit.w>width+.015 or edit.y+edit.h>height+.015:
            raise ValueError('The AI plan places an object outside the slide.')
        regions=T.regions(slide)
        if not any(T.contains(rect,r) for r in regions):
            raise ValueError(f'Object {ident} box {rect} is outside the permitted template regions {regions}. Keep the complete box inside one region and clear the protected logo/footer band.')
        if T.is_cover(slide) and (ident.endswith('|title') or edit.role=='title') and not T.contains(rect,T.COVER_TITLE):
            raise ValueError('The extracted cover title must stay in the first-page title box.')
        if T.is_cover(slide) and shape.has_text_frame and shape.text.strip() and not parent and not owner:
            if not any(T.contains(rect,r) for r in (T.COVER_TITLE,T.COVER_DETAILS)):
                raise ValueError('Cover text, including notes and footers, must stay in the right-hand template text regions; keep the photo clear.')
        if locked and any(abs(a-b)>.002 for a,b in zip(box,rect)):
            raise ValueError('Rotated/flipped group geometry is locked to preserve meaning.')
        if shape._element.tag in (qn('p:pic'),qn('p:grpSp')) or shape.has_chart:
            if box[3] and abs((edit.w/edit.h)/(box[2]/box[3])-1)>.03:
                raise ValueError('Pictures, charts and groups must retain their aspect ratio.')
        if (edit.font_size is not None or edit.role!='keep' or edit.color!='keep') and not (shape.has_text_frame or shape.has_table):
            raise ValueError('Text styling cannot target a picture, chart or group container.')
        if edit.role=='title' and edit.font_size not in (None,brand.TITLE_PT):
            raise ValueError('Title text must use the approved 40 point size.')
    # Reject newly introduced text collisions before paying for a render/review.
    # Existing source collisions still require visual QA; unchanged complex math
    # or intentional text-on-panel containment is not treated as a new collision.
    texts=[(ident,shape,box,parent) for ident,shape,box,parent,locked in current
           if shape.has_text_frame and shape.text.strip()]
    def ink_box(shape,rect,edit=None):
        tf=shape.text_frame
        if tf.word_wrap is not False or len(tf.paragraphs)!=1 or '\n' in shape.text or '\v' in shape.text:
            return rect
        runs=tf.paragraphs[0].runs
        if any((r.font.name or 'Arial')!='Arial' for r in runs): return rect
        # PDF imports use single unwrapped lines. Their generous frame rectangles
        # are not their ink bounds. Estimate Arial advance widths rather than
        # rejecting a caption because its empty right/bottom padding intersects.
        import fitz
        sizes=[r.font.size.pt if r.font.size else 18 for r in runs]
        factor=(edit.font_size/max(sizes)) if edit and edit.font_size and sizes else 1
        width=sum(fitz.get_text_length(r.text,fontname='hebo' if r.font.bold else 'heit' if r.font.italic else 'helv',
                                      fontsize=size*factor) for r,size in zip(runs,sizes))/72
        height=max(sizes or [18])*factor*1.12/72
        x,y,w,h=rect
        ml,mr,mt,mb=(getattr(tf,'margin_'+s)/EMU for s in ('left','right','top','bottom'))
        return (x+ml,y+mt,min(max(.001,w-ml-mr),width),min(max(.001,h-mt-mb),height))
    def intersection(a,b):
        area=max(0,min(a[0]+a[2],b[0]+b[2])-max(a[0],b[0]))*max(0,min(a[1]+a[3],b[1]+b[3])-max(a[1],b[1]))
        return area/max(.000001,min(a[2]*a[3],b[2]*b[3]))
    for i,(aid,ashape,a,ap) in enumerate(texts):
        ae=lookup[aid]; ar=(ae.x,ae.y,ae.w,ae.h)
        for bid,bshape,b,bp in texts[i+1:]:
            if ap!=bp: continue
            be=lookup[bid]; br=(be.x,be.y,be.w,be.h)
            if T.contains(ar,br) or T.contains(br,ar): continue
            if intersection(ink_box(ashape,ar,ae),ink_box(bshape,br,be))>max(.12,intersection(ink_box(ashape,a),ink_box(bshape,b))+.03):
                raise ValueError(f'Text collision between {aid} and {bid}; allocate separate boxes and line spacing.')
    from ..qa.geometry import estimate_overflow
    from pptx.shapes.autoshape import Shape
    for ident,shape,box,parent,locked in current:
        if not shape.has_text_frame or not shape.text.strip(): continue
        edit=lookup[ident]
        # Estimate with the proposed dimensions AND font, without mutating input.
        projected=Shape(deepcopy(shape._element),None)
        # Group descendants have local dimensions; plans use absolute inches.
        projected.width=round(shape.width*edit.w/box[2]); projected.height=round(shape.height*edit.h/box[3])
        if edit.font_size is not None or edit.role=='title':
            resize_runs(projected.text_frame,brand.TITLE_PT if edit.role=='title' else edit.font_size)
        before=estimate_overflow(shape)[1]; after=estimate_overflow(projected)[1]
        styled=edit.font_size is not None or edit.role=='title'
        if after>1.25 and (styled or after>before*1.1):
            raise ValueError(f'Text fit worsens or remains overflowing for {ident}; enlarge the box and spacing before changing font size or title role.')
    return plan


def apply(candidate,out,plans,report):
    prs=Presentation(candidate);updated=deepcopy(report);changes=0
    for index,plan in plans.items():
        slide=prs.slides[index]
        validate(plan,slide,prs.slide_width/EMU,prs.slide_height/EMU)
        lookup={e.id:e for e in plan.objects}
        def visit(shapes,frame=(1,1,0,0)):
            nonlocal changes
            sx,sy,ox,oy=frame
            for shape in shapes:
                if shape.name==T.BACKGROUND_NAME: continue
                edit=lookup[shape.name]
                old=(shape.left,shape.top,shape.width,shape.height)
                shape.left=round((edit.x*EMU-ox)/sx);shape.top=round((edit.y*EMU-oy)/sy)
                shape.width=max(1,round(edit.w*EMU/sx));shape.height=max(1,round(edit.h*EMU/sy))
                changed=tuple(old)!=(shape.left,shape.top,shape.width,shape.height)
                if shape._element.tag==qn('p:grpSp'):
                    changes+=changed
                    visit(shape.shapes,group_frame(shape,frame));continue
                frames=[shape.text_frame] if shape.has_text_frame else []
                if shape.has_table:frames += [c.text_frame for row in shape.table.rows for c in row.cells]
                if edit.role!='keep':
                    name=marker(shape)+('|title' if edit.role=='title' else '')
                    changed |= shape.name!=name
                    shape.name=name
                size=brand.TITLE_PT if edit.role=='title' else edit.font_size
                color={'ink':brand.INK,'red':brand.RED,'white':brand.WHITE}.get(edit.color)
                for tf in frames:
                    if size is not None:
                        changed |= any(r.font.size!=Pt(size) for p in tf.paragraphs for r in p.runs)
                        resize_runs(tf,size)
                    for p in tf.paragraphs:
                        for r in p.runs:
                            if color:
                                from pptx.enum.dml import MSO_COLOR_TYPE
                                changed |= r.font.color.type!=MSO_COLOR_TYPE.RGB or str(r.font.color.rgb)!=color
                                r.font.color.rgb=RGBColor.from_string(color)
                changes+=changed
        visit(slide.shapes)
        for shape in slide.shapes:
            sid=marker(shape)
            if sid.startswith('sss:'):
                for p in updated['placements']:
                    if p['source_id']==sid[4:] and p['output_slide']==index:
                        p['bounds']=[shape.left,shape.top,shape.width,shape.height]
        updated['slides'][index]['layout']=plan.layout
    save_deck(prs,out)
    updated['llm_used']=True
    return updated,changes
