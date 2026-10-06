"""Bounded readability repair for isolated small lines on text-only PDF pages."""
from pptx.util import Inches, Pt
from pptx.oxml.ns import qn


def enlarge_small_text(slide, placements, region):
    # Mixed figures/diagrams require their original spatial relationships. Never
    # reflow those pages or disturb equations composed of overlapping objects.
    if any(s._element.tag in (qn('p:pic'), qn('p:grpSp')) or s.has_table or s.has_chart for s in slide.shapes):
        return
    text = [s for s in slide.shapes if s.has_text_frame and s.text.strip()]
    x,y,w,h = [Inches(v) for v in region]
    ordered = sorted(text,key=lambda s:(s.top,s.left))
    for shape in ordered:
        runs=[r for p in shape.text_frame.paragraphs for r in p.runs if r.font.size]
        size=max((r.font.size.pt for r in runs),default=11)
        if size >= 11: continue
        factor=11/size
        # Overlay links are handled by the uniform content transform. Avoid
        # independent line growth that could separate link text and its hitbox.
        if any(s._element.xpath('.//a:hlinkClick') and s.left < shape.left+shape.width
               and s.left+s.width > shape.left and s.top < shape.top+shape.height
               and s.top+s.height > shape.top for s in slide.shapes if s != shape): continue
        width=int(shape.width*factor)
        height=max(int(shape.height*factor),int(Pt(11*1.3)))
        if shape.left+width > x+w: continue
        following=[s for s in ordered if s.top > shape.top]
        overlapping=[s for s in following if s.left < shape.left+width and s.left+s.width > shape.left]
        shift=max(0,shape.top+height+Pt(2)-min((s.top for s in overlapping),default=y+h))
        if max([shape.top+height]+[s.top+s.height+shift for s in following]) > y+h: continue
        # Only grow a stand-alone line, never an inline fragment/superscript.
        if any(s != shape and s.top <= shape.top < s.top+s.height
               and s.left < shape.left+width and s.left+s.width > shape.left for s in text): continue
        shape.width=width; shape.height=height
        for r in runs: r.font.size=Pt(r.font.size.pt*factor)
        for s in following: s.top+=int(shift)
        # Link hitboxes must follow the same native text, not remain at old y.
        for s in slide.shapes:
            if s in text or not s._element.xpath('.//a:hlinkClick'): continue
            if s.top >= shape.top+height: s.top+=int(shift)
    for placement in placements:
        shape=next((s for s in slide.shapes if s.name.split('|',1)[0]=='sss:'+placement['source_id']),None)
        if shape is not None: placement['bounds']=[shape.left,shape.top,shape.width,shape.height]
