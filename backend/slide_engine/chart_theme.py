"""Keep a chart's effective source theme, including implicit series colors."""
from copy import deepcopy
from lxml import etree
from pptx.oxml.ns import qn
from pptx.opc.constants import RELATIONSHIP_TYPE as RT, CONTENT_TYPE as CT
from pptx.opc.package import Part
from pptx.opc.packuri import PackURI
from pptx.parts.chart import ChartPart
from pptx.oxml import parse_xml
from .text_style import source_theme


def effective(shape):
    theme = source_theme(shape)
    elements = theme.find(qn('a:themeElements')) if theme is not None else None
    result = etree.Element(qn('a:themeOverride'), nsmap={'a': 'http://schemas.openxmlformats.org/drawingml/2006/main'})
    overrides = [r.target_part for r in shape.chart.part.rels.values() if r.reltype == RT.THEME_OVERRIDE]
    if len(overrides) > 1:
        raise ValueError('Chart has multiple theme overrides.')
    override = etree.fromstring(overrides[0].blob) if overrides else None
    for name in ('clrScheme', 'fontScheme', 'fmtScheme'):
        node = override.find(qn('a:'+name)) if override is not None else None
        if node is None and elements is not None:
            node = elements.find(qn('a:'+name))
        if node is None:
            raise ValueError('Chart source theme cannot be resolved.')
        result.append(deepcopy(node))
    return result


def preserved_part(shape):
    """Clone before attaching a theme: a kept slide may share this chart part."""
    source = shape.chart.part
    root = effective(shape)
    part = ChartPart.load(source.partname, source.content_type, source.package, source.blob)
    # Preserve exact rIds and chart XML. Only its effective theme representation
    # changes; workbook, chart style and explicit point formatting stay intact.
    # Imported workbook/style parts may already have been renamed. Resolve via
    # these relationships, including their cached target refs, rather than a
    # package lookup that could silently discard a now-stale workbook path.
    parts = {PackURI.from_rel_ref(source.partname.baseURI, r.target_ref): r.target_part
             for r in source.rels.values() if not r.is_external}
    part.rels.load_from_xml(source.partname.baseURI, parse_xml(source.rels.xml), parts)
    for rel in list(part.rels.values()):
        if rel.reltype == RT.THEME_OVERRIDE:
            part.drop_rel(rel.rId)
    override = Part(part.package.next_partname('/ppt/theme/sss-chart-theme%d.xml'),
                    CT.OFC_THEME_OVERRIDE, part.package,
                    etree.tostring(root, xml_declaration=True, encoding='UTF-8', standalone=True))
    part.relate_to(override, RT.THEME_OVERRIDE)
    return part
