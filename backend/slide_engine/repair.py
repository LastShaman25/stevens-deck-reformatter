"""Bounded local text reflow. Never changes diagram/chart proportions or text."""

from slide_engine.package import save_deck
from pathlib import Path
from copy import deepcopy
from pptx import Presentation
from pptx.util import Inches
from pptx.oxml.ns import qn
from .preserve import marker


def repair(source, candidate, report, max_cycles=3):
    from app.qa.geometry import estimate_overflow
    from app.qa.artifact_coverage import audit
    from app.qa.style_audit import audit as style_audit

    def measure(prs):
        issues=[f for s in prs.slides for f in style_audit(s,int(prs.slide_width),int(prs.slide_height))]
        return (sum(f['sev']=='fail' for f in issues),sum(f['type']=='occlusion' for f in issues),sum(f['type']=='overflow' for f in issues))

    history=[]
    for cycle in range(max_cycles):
        prs=Presentation(candidate)
        before=measure(prs)
        changes=[]
        def reflow(shapes, si, bottom, root=None):
            for shape in shapes:
                if shape._element.tag == qn('p:grpSp'):
                    ext=shape._element.xpath('./p:grpSpPr/a:xfrm/a:chExt')
                    off=shape._element.xpath('./p:grpSpPr/a:xfrm/a:chOff')
                    if ext and off:
                        reflow(shape.shapes,si,int(off[0].get('y'))+int(ext[0].get('cy')),root or marker(shape))
                    continue
                # Only plain text boxes; grouped/filled visuals and tables are untouched.
                if not shape.has_text_frame or not shape.text.strip() or not (root or marker(shape)).startswith('sss:'):
                    continue
                if shape._element.xpath('./p:spPr/a:prstGeom') and not shape._element.xpath('./p:nvSpPr/p:cNvSpPr[@txBox="1"]'):
                    continue
                if shape.top+shape.height>bottom and shape.top<bottom:
                    old_height=shape.height
                    shape.height=bottom-shape.top
                    if not estimate_overflow(shape)[0]:
                        changes.append({'output_slide':si,'shape':marker(shape),'root':root,'old_height':old_height,'new_height':shape.height})
                    else:
                        shape.height=old_height
                # Resolve a hard bounds defect first; do not let unrelated optional
                # expansions cause the whole proposal to roll back.
                if before[0] > 0:
                    continue
                over,ratio=estimate_overflow(shape)
                if not over:continue
                lower=bottom
                for other in shapes:
                    if other is shape or other.top is None:continue
                    if other.top>=shape.top+shape.height and other.left<shape.left+shape.width and other.left+other.width>shape.left:
                        lower=min(lower,int(other.top-Inches(.08)))
                wanted=int(shape.height*ratio*1.08)
                height=min(wanted,lower-shape.top)
                if height>shape.height+Inches(.04):
                    changes.append({'output_slide':si,'shape':marker(shape),'root':root,'old_height':shape.height,'new_height':height})
                    shape.height=height
        for si,slide in enumerate(prs.slides):
            from . import template_policy as T
            # Cover text has dedicated placeholder regions; AI handles any overflow.
            if T.is_cover(slide) or T.is_preserved(slide): continue
            reflow(slide.shapes,si,int(Inches(T.CONTENT[1]+T.CONTENT[3])))
        if not changes:break
        proposed=Path(candidate).with_name(f'repair-{cycle}.pptx')
        save_deck(prs,proposed)
        updated=deepcopy(report)
        for change in changes:
            for p in updated['placements']:
                if p['source_id']==change['shape'][4:] and p['output_slide']==change['output_slide']:
                    p['bounds'][3]=change['new_height']
        checked=audit(source,proposed,updated)
        after=measure(Presentation(proposed))
        accepted=checked['status']=='passed' and after[0]<=before[0] and after[1]<=before[1] and after[2]<=before[2] and (after[0]<before[0] or after[2]<before[2])
        history.append({'cycle':cycle+1,'before':before,'after':after,'accepted':accepted,'changes':changes})
        if not accepted:
            proposed.unlink()
            break
        proposed.replace(candidate)
        report['placements']=updated['placements']
    report['repair_count']=sum(h['accepted'] for h in history)
    report['repair_history']=history
    for correction in report['corrections']:
        outputs=report['source_to_output_slides'][str(correction['index'])]
        changed=any(h['accepted'] and any(c['output_slide'] in outputs for c in h['changes']) for h in history)
        for action in correction['actions']:
            if action['action'] in ('dense','layout','overlap'):
                action['status']='applied' if changed else 'no_change'
                action['message']='Expanded text boxes into available space and reverified content.' if changed else 'No safe measurable local reflow was found; inspect remaining findings.'
    return report
