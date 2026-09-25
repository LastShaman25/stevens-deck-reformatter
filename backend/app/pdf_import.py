"""Processing-only PDF import: editable text and faithful raster graphic regions.

The original PDF remains the paired visual authority. Never call a page screenshot
an editable redesign. Scans need OCR and are rejected explicitly rather than lost.
"""
from io import BytesIO
from pathlib import Path
import hashlib
import fitz
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE


def compact(text):
    return ''.join(text.split())


def regions(boxes):
    merged=[]
    for rect in boxes:
        rect=fitz.Rect(rect)
        if rect.is_empty: continue
        again=True
        while again:
            again=False
            for other in list(merged):
                if (rect+(-1,-1,1,1)).intersects(other):
                    rect |= other; merged.remove(other); again=True
        merged.append(rect)
    return merged


def convert(pdf_path, pptx_path, preview_path):
    with fitz.open(pdf_path) as doc:
        if doc.needs_pass: raise ValueError('Upload an unlocked PDF.')
        if not 1<=len(doc)<=100: raise ValueError('PDF redesign supports 1–100 pages.')
        if doc.embfile_count(): raise ValueError('PDF attachments cannot be preserved in this workflow. Remove attachments before uploading.')
        from slide_engine.template_policy import CANVAS
        prs=Presentation();prs.slide_width,prs.slide_height=CANVAS
        canvas_w,canvas_h=(v/914400 for v in CANVAS)
        evidence=[];characters=0
        for i,page in enumerate(doc):
            if page.first_widget or page.first_annot:
                raise ValueError(f'PDF page {i+1} has form fields or annotations; flatten them in your PDF editor first.')
            blocks=page.get_text('dict')['blocks']
            lines=[line for block in blocks if block['type']==0 for line in block['lines']]
            source_text=''.join(span['text'] for line in lines for span in line['spans'])
            if not source_text.strip():
                raise ValueError(f'PDF page {i+1} has no extractable text. Run OCR on scanned pages before uploading for redesign.')
            characters+=len(source_text)
            if len(lines)>500 or characters>220000:
                raise ValueError('PDF exceeds the text processing limit; upload a shorter section.')
            if any(line.get('dir',(1,0))!=(1,0) for line in lines):
                raise ValueError(f'PDF page {i+1} has rotated text; normalize its orientation before redesign.')
            size=page.rect
            scale=min(canvas_w/size.width,canvas_h/size.height)
            dx=(canvas_w-size.width*scale)/2;dy=(canvas_h-size.height*scale)/2
            def box(rect):
                r=fitz.Rect(rect)
                return [Inches(dx+r.x0*scale),Inches(dy+r.y0*scale),Inches(max(.001,r.width*scale)),Inches(max(.001,r.height*scale))]
            slide=prs.slides.add_slide(prs.slide_layouts[6])
            page.get_pixmap(matrix=fitz.Matrix(min(2,1600/max(size.width,size.height)),min(2,1600/max(size.width,size.height))),alpha=False).save(preview_path(i))
            drawings=page.get_drawings()
            full_fills=[d for d in drawings if d.get('fill') and d.get('fill_opacity',1)==1
                        and len(d['items'])==1 and d['items'][0][0]=='re'
                        and (fitz.Rect(d['rect']) & size).get_area()>=size.get_area()*.99]
            if full_fills:
                rgb=full_fills[-1]['fill'];slide.background.fill.solid()
                slide.background.fill.fore_color.rgb=RGBColor(*(round(c*255) for c in rgb))
            graphic_boxes=[fitz.Rect(d['rect'])+(-.5,-.5,.5,.5) for d in drawings if d not in full_fills]
            graphic_boxes += [b['bbox'] for b in blocks if b['type']==1]
            # Work on a private page copy: strip only native text. Images and
            # vector graphics retain source pixels and layer order within each region.
            layer=fitz.open();layer.insert_pdf(doc,from_page=i,to_page=i)
            graphic_page=layer[0]
            for line in lines: graphic_page.add_redact_annot(line['bbox'],fill=False)
            graphic_page.apply_redactions(images=0,graphics=0,text=0)
            graphic_count=0
            for rect in regions(graphic_boxes):
                rect=(rect+(-.5,-.5,.5,.5)) & size
                if rect.is_empty: continue
                resolution=min(2,3000/max(size.width,size.height))
                pix=graphic_page.get_pixmap(matrix=fitz.Matrix(resolution,resolution),clip=rect,alpha=True)
                # White-on-white background drawings have no visible information.
                # Do not turn them into a large opaque picture on the new cover.
                from PIL import Image
                pixels=Image.open(BytesIO(pix.tobytes('png'))).convert('RGBA')
                bg=tuple(round(c*255) for c in full_fills[-1]['fill']) if full_fills else (255,255,255)
                flattened=Image.new('RGBA',pixels.size,(*bg,255));flattened.alpha_composite(pixels)
                if all(lo==hi==c for (lo,hi),c in zip(flattened.convert('RGB').getextrema(),bg)): continue
                picture=slide.shapes.add_picture(BytesIO(pix.tobytes('png')),*box(rect))
                picture.name=f'PDF page {i+1} graphic {graphic_count+1}'
                graphic_count+=1
            layer.close()
            textboxes=[]
            for line in lines:
                shape=slide.shapes.add_textbox(*box(line['bbox']));textboxes.append(shape)
                tf=shape.text_frame;tf.clear();tf.word_wrap=False
                tf.margin_left=tf.margin_right=tf.margin_top=tf.margin_bottom=0
                paragraph=tf.paragraphs[0];paragraph.space_before=paragraph.space_after=Pt(0)
                for span in line['spans']:
                    run=paragraph.add_run();run.text=span['text']
                    run.font.name=span['font'].split('+')[-1]
                    run.font.size=Pt(max(1,span['size']*scale*72))
                    run.font.bold=bool(span['flags'] & 16);run.font.italic=bool(span['flags'] & 2)
                    run.font.color.rgb=RGBColor.from_string(f"{span['color']:06X}")
            links=page.get_links()
            for link in links:
                if link['kind'] not in (fitz.LINK_URI,fitz.LINK_GOTO):
                    raise ValueError(f'PDF page {i+1} contains an unsupported link type.')
                shape=slide.shapes.add_shape(MSO_SHAPE.RECTANGLE,*box(link['from']))
                shape.fill.background();shape.line.fill.background()
                if link['kind']==fitz.LINK_URI: shape.click_action.hyperlink.address=link['uri']
                else: shape.name=f"pdf-internal-link:{link['page']}"
            evidence.append({'page':i+1,'text':source_text,'graphics':graphic_count,'links':len(links)})
        for slide in prs.slides:
            for shape in slide.shapes:
                if shape.name.startswith('pdf-internal-link:'):
                    target=int(shape.name.split(':')[1])
                    if not 0<=target<len(prs.slides): raise ValueError('PDF internal link target is missing.')
                    shape.click_action.target_slide=prs.slides[target]
        prs.save(pptx_path)
        reopened=Presentation(pptx_path)
        for page,slide in zip(evidence,reopened.slides):
            text=''.join(s.text for s in slide.shapes if s.has_text_frame)
            if compact(text)!=compact(page['text']): raise ValueError('PDF import text verification failed.')
        return {'status':'passed','pages':len(evidence),'source_pdf_sha256':hashlib.sha256(Path(pdf_path).read_bytes()).hexdigest(),
                'source_pptx_sha256':hashlib.sha256(Path(pptx_path).read_bytes()).hexdigest(),
                'method':'editable text; source graphics preserved as raster regions',
                'page_evidence':[{'page':p['page'],'text_sha256':hashlib.sha256(p['text'].encode()).hexdigest(),
                                  'graphics':p['graphics'],'links':p['links']} for p in evidence]}
