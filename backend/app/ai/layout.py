"""AI-editable geometry. Source text, relationships, data and emphasis are immutable."""
from copy import deepcopy
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field
from pptx import Presentation
from pptx.oxml.ns import qn
from pptx.util import Pt
from pptx.dml.color import RGBColor
from slide_engine.preserve import marker
from .. import brand

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
        result.append({'id':ident,'parent':parent,'kind':kind,'box':[max(.000001,round(v,6)) if j>1 else round(v,6) for j,v in enumerate(box)],
                       'content':content,'locked_geometry':locked,'native_title':ident.endswith('|title'),
                       **fit,
                       'font_sizes':sorted({r.font.size.pt for p in shape.text_frame.paragraphs for r in p.runs if r.font.size}) if shape.has_text_frame else []})
    return result


def validate(plan,slide,width,height):
    current=nodes(slide);expected={i for i,*_ in current}
    ids=[e.id for e in plan.objects]
    if len(ids)!=len(set(ids)) or set(ids)!=expected:
        raise ValueError('The AI plan must reference every object exactly once, without adding IDs.')
    lookup={e.id:e for e in plan.objects}
    for ident,shape,box,parent,locked in current:
        edit=lookup[ident];rect=[edit.x,edit.y,edit.w,edit.h]
        if edit.x+edit.w>width+.015 or edit.y+edit.h>height+.015:
            raise ValueError('The AI plan places an object outside the slide.')
        if locked and any(abs(a-b)>.002 for a,b in zip(box,rect)):
            raise ValueError('Rotated/flipped group geometry is locked to preserve meaning.')
        if shape._element.tag in (qn('p:pic'),qn('p:grpSp')) or shape.has_chart:
            if box[3] and abs((edit.w/edit.h)/(box[2]/box[3])-1)>.03:
                raise ValueError('Pictures, charts and groups must retain their aspect ratio.')
        if (edit.font_size is not None or edit.role!='keep' or edit.color!='keep') and not (shape.has_text_frame or shape.has_table):
            raise ValueError('Text styling cannot target a picture, chart or group container.')
        if edit.role=='title' and edit.font_size not in (None,brand.TITLE_PT):
            raise ValueError('Title text must use the approved 40 point size.')
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
                    for p in tf.paragraphs:
                        for r in p.runs:
                            if size is not None:
                                changed |= r.font.size!=Pt(size);r.font.size=Pt(size)
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
    prs.save(out)
    updated['llm_used']=True
    return updated,changes
