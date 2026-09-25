"""Native PPTX composition plus independent reopened-artifact verification."""
import hashlib
import json
from pathlib import Path
from PIL import Image
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.chart.data import CategoryChartData, XyChartData
from pptx.enum.chart import XL_CHART_TYPE, XL_LEGEND_POSITION
from .. import grounded, brand
from .graphics import render_plot, render_equation


def text(shape, lines, size):
    tf = shape.text_frame
    tf.clear(); tf.word_wrap = True
    tf.margin_left = tf.margin_right = Inches(.04)
    for i, line in enumerate(lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.text = line
        p.font.name = 'Arial'; p.font.size = Pt(size)
        p.font.color.rgb = RGBColor.from_string(brand.INK)
        p.space_after = Pt(14)


def compose(spec, path, assets, pages=()):
    assets = Path(assets); assets.mkdir(parents=True, exist_ok=True)
    prs = Presentation(grounded.TEMPLATE_PATH)
    for item in list(prs.slides._sldIdLst):
        prs.part.drop_rel(item.rId); prs.slides._sldIdLst.remove(item)
    layout = next(l for l in prs.slide_layouts if l.name == 'Title Only')
    manifest = []
    for index, content in enumerate(spec.slides):
        slide = prs.slides.add_slide(layout)
        for sh in list(slide.shapes):
            sh._element.getparent().remove(sh._element)
        title = slide.shapes.add_textbox(Inches(.72), Inches(.4), Inches(11.7), Inches(1.4))
        title.name = 'authored-title'
        text(title, [content.title], 40)
        visual = any(v is not None for v in (content.chart, content.plot, content.equation, content.figure_page, content.table))
        body = slide.shapes.add_textbox(Inches(.75), Inches(2), Inches(4.0 if visual else 11.5), Inches(4.4))
        body.name = 'authored-body'
        text(body, content.bullets, 20 if sum(map(len, content.bullets)) < 600 else 18)
        image_hash = None
        if content.chart:
            chart = content.chart
            if chart.kind == 'scatter':
                data = XyChartData()
                for series in chart.series:
                    target = data.add_series(series.name)
                    for x, y in zip(chart.categories, series.values): target.add_data_point(float(x), y)
            else:
                data = CategoryChartData(); data.categories = chart.categories
                for series in chart.series: data.add_series(series.name, series.values)
            kinds = {'bar': XL_CHART_TYPE.BAR_CLUSTERED, 'column': XL_CHART_TYPE.COLUMN_CLUSTERED,
                     'line': XL_CHART_TYPE.LINE, 'pie': XL_CHART_TYPE.PIE, 'area': XL_CHART_TYPE.AREA,
                     'scatter': XL_CHART_TYPE.XY_SCATTER}
            native = slide.shapes.add_chart(kinds[chart.kind], Inches(5), Inches(2), Inches(7.2), Inches(4.3), data).chart
            native.font.name = 'Arial'; native.font.size = Pt(14)
            native.has_title = False
            native.has_legend = len(chart.series) > 1 or chart.kind == 'pie'
            if native.has_legend:
                native.legend.position = XL_LEGEND_POSITION.TOP
                native.legend.include_in_layout = False
            if chart.kind != 'pie':
                for axis, label in ((native.category_axis, chart.x_label), (native.value_axis, chart.y_label)):
                    if label:
                        axis.has_title = True; axis.axis_title.text_frame.text = label
        elif content.table:
            data = [content.table.headers]+content.table.rows
            table = slide.shapes.add_table(len(data),len(data[0]),Inches(5),Inches(2),Inches(7.2),Inches(4.3)).table
            for ri, row in enumerate(data):
                for ci, value in enumerate(row):
                    cell = table.cell(ri,ci); cell.text = value
                    for p in cell.text_frame.paragraphs:
                        p.font.name='Arial'; p.font.size=Pt(14); p.font.color.rgb=RGBColor.from_string(brand.INK)
        elif visual:
            image = assets/f'visual-{index}.png'
            if content.plot: render_plot(content.plot, image)
            elif content.equation: render_equation(content.equation, image)
            else:
                page = next((p for p in pages if p['page'] == content.figure_page), None)
                if not page: raise ValueError('Figure source page does not exist.')
                image = Path(page['image'])
            with Image.open(image) as im: w, h = im.size
            scale = min(7.2/w, 4.3/h)
            picture = slide.shapes.add_picture(str(image), Inches(5+(7.2-w*scale)/2), Inches(2+(4.3-h*scale)/2),
                                             width=Inches(w*scale), height=Inches(h*scale))
            picture.name = 'authored-visual'
            picture._element.nvPicPr.cNvPr.set('descr', content.equation or ('Plot: '+', '.join(content.plot.functions) if content.plot else f'Source PDF page {content.figure_page}'))
            image_hash = hashlib.sha256(image.read_bytes()).hexdigest()
        references = '\n'.join(f'PDF page {c.page}: {c.quote}' for c in content.citations)
        notes = content.notes+'\n'+references+'\nAuthoring specification:\n'+content.model_dump_json()
        slide.notes_slide.notes_text_frame.text = notes
        manifest.append({'id': content.id, 'title': content.title, 'bullets': content.bullets,
                         'notes': notes, 'chart': content.chart.model_dump() if content.chart else None,
                         'image_sha256': image_hash, 'table':content.table.model_dump() if content.table else None})
    prs.save(path)
    return manifest


def audit(path, manifest):
    prs = Presentation(path)
    findings = []
    def fail(i, message):
        findings.append({'code': 'AUTHORED_CONTENT_MISMATCH', 'severity': 'blocking', 'output_slide': i, 'message': message})
    if len(prs.slides) != len(manifest): fail(0, 'Slide count differs from approved authored content.')
    for i, (slide, wanted) in enumerate(zip(prs.slides, manifest)):
        named = {s.name: s for s in slide.shapes}
        if named.get('authored-title') is None or named['authored-title'].text != wanted['title']: fail(i, 'Title differs.')
        if named.get('authored-body') is None or named['authored-body'].text != '\n'.join(wanted['bullets']): fail(i, 'Body text differs.')
        if slide.notes_slide.notes_text_frame.text != wanted['notes']: fail(i, 'Notes or source specification differs.')
        charts = [s.chart for s in slide.shapes if s.has_chart]
        if wanted['chart']:
            if len(charts) != 1: fail(i, 'Expected one native chart.')
            else:
                actual = [{'name': s.name, 'values': list(s.values)} for s in charts[0].series]
                if actual != wanted['chart']['series']: fail(i, 'Chart series values differ.')
                if wanted['chart']['kind'] == 'scatter':
                    from lxml import etree
                    ns = {'c':'http://schemas.openxmlformats.org/drawingml/2006/chart'}
                    for series in charts[0]._chartSpace.findall('.//c:ser', ns):
                        xs = [float(node.text) for node in series.findall('.//c:xVal/c:numRef/c:numCache/c:pt/c:v',ns)]
                        if xs != [float(x) for x in wanted['chart']['categories']]: fail(i, 'Scatter x values differ.')
                if wanted['chart']['kind'] != 'scatter':
                    if [c.label for c in charts[0].plots[0].categories] != wanted['chart']['categories']: fail(i, 'Chart categories differ.')
        elif charts: fail(i, 'Unexpected chart.')
        pictures = [s for s in slide.shapes if s.shape_type == 13]
        if wanted['image_sha256']:
            if len(pictures) != 1 or hashlib.sha256(pictures[0].image.blob).hexdigest() != wanted['image_sha256']: fail(i, 'Figure bytes differ.')
        elif pictures: fail(i, 'Unexpected picture.')
        tables = [s.table for s in slide.shapes if s.has_table]
        if wanted.get('table'):
            expected = [wanted['table']['headers']]+wanted['table']['rows']
            if len(tables)!=1 or [[c.text for c in row.cells] for row in tables[0].rows] != expected: fail(i, 'Table values differ.')
        elif tables: fail(i, 'Unexpected table.')
    return {'status': 'failed' if findings else 'passed', 'findings': findings}
