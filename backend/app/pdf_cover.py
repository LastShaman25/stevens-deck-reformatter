"""Separate simple cover artwork before semantic source decisions.

This never decides that a photo or a logo is decorative. It preserves independent
PDF image/path layers so the source agent can classify each one without removing
a required logo along with a background. Unsupported compositions stay intact.
"""
import hashlib

import fitz

from .pdf_paths import remove_paths, path_bounds


def _visible(drawing):
    return ((drawing.get('fill') is not None and (drawing.get('fill_opacity') or 0) > 0)
            or (drawing.get('color') is not None and (drawing.get('stroke_opacity') or 0) > 0))


def _key(drawing):
    return tuple(round(v, 3) for v in drawing['rect'])


def _image_seq(image, log):
    matches = [i for i, (kind, bounds) in enumerate(log) if kind == 'fill-image'
               and all(abs(a-b) < .02 for a, b in zip(image['bbox'], bounds))]
    return matches[0] if len(matches) == 1 else None


def graphics(page, blocks, drawings, excluded):
    """Preserve ambiguous or unsupported cover graphics with the regular path."""
    try:
        return _graphics(page, blocks, drawings, excluded)
    except (ValueError, RuntimeError, OSError):
        return None


def _graphics(page, blocks, drawings, excluded):
    """Return source-pixel graphic layers, or None to use conservative import.

    Each layer has PNG ``blob``, PDF ``bounds``, ``description`` and JSON-safe
    ``evidence``. All images remain intact, including their native masks/effects.
    Only explicitly supplied excluded paths are omitted. The caller emits native
    PDF text separately as usual. This fast path is limited to an independently
    layered full-bleed cover picture plus foreground images/rectangle panels.
    """
    if page.get_xobjects() or page.get_links():
        return None
    info = [image for image in page.get_image_info(xrefs=True)
            if not (fitz.Rect(image['bbox']) & page.rect).is_empty]
    if not info or len(info) > 8 or any(not image['xref'] for image in info):
        return None
    if not any((fitz.Rect(image['bbox']) & page.rect).get_area() >= page.rect.get_area()*.9
               for image in info):
        return None
    if len({image['digest'] for image in info}) != len(info):
        return None  # A repeated image may have different clipping/effect state.
    if any(abs(image['transform'][1]) > .001 or abs(image['transform'][2]) > .001
           or image['transform'][0] <= 0 or image['transform'][3] <= 0 for image in info):
        return None
    full_fills = [d for d in drawings if d.get('fill') is not None and d.get('fill_opacity') == 1
                  and not (d.get('color') is not None and d.get('stroke_opacity', 0))
                  and (fitz.Rect(d['rect']) & page.rect).get_area() >= page.rect.get_area()*.99]
    # convert() already preserves an initial solid canvas as slide.background.
    # Later opaque full-page panels could hide content and must stay composited.
    if any(d['seqno'] > 0 for d in full_fills):
        return None
    remaining = [drawing for drawing in drawings if _visible(drawing)
                 and drawing not in excluded and drawing not in full_fills]
    if len(remaining) > 20 or any(len(d['items']) != 1 or d['items'][0][0] != 're'
                                or (d.get('color') is not None and d.get('stroke_opacity', 0))
                                for d in remaining):
        return None
    # Same-bounds paths cannot be separated reliably by the exact-path writer.
    if any(sum(_key(other) == _key(d) for other in drawings) != 1 for d in remaining):
        return None
    log = page.get_bboxlog()
    if any(kind not in ('fill-path', 'stroke-path', 'fill-image', 'fill-text', 'ignore-text')
           for kind, _ in log):
        return None
    text_boxes = [(i, fitz.Rect(bounds)) for i, (kind, bounds) in enumerate(log) if kind == 'fill-text']
    targets = []
    for image in info:
        seq = _image_seq(image, log)
        if seq is None:
            return None
        targets.append((seq, 'image', image, fitz.Rect(image['bbox']) & page.rect))
    for drawing in remaining:
        targets.append((drawing['seqno'], 'path', drawing, fitz.Rect(drawing['rect']) & page.rect))
    # The ordinary PDF importer puts native text above graphics. Do not change
    # an intentional overprint/occlusion when decomposing its source layers.
    if any(seq > text_seq and bounds.intersects(text_box)
           for seq, _, _, bounds in targets for text_seq, text_box in text_boxes):
        return None
    result = []
    for seq, kind, target, bounds in sorted(targets, key=lambda entry: entry[0]):
        if bounds.is_empty:
            continue
        layer = fitz.open()
        try:
            layer.insert_pdf(page.parent, from_page=page.number, to_page=page.number)
            clean = layer[0]
            keep = target['digest'] if kind == 'image' else None
            # get_image_info maps identical image bytes to one representative
            # xref. Remove every resource alias, not just that representative.
            remove_images = {entry[0] for entry in clean.get_images(full=True)
                             if fitz.Pixmap(layer, entry[0]).digest != keep}
            for xref in remove_images:
                clean.delete_image(xref)
            # Remove every paint operation at these confirmed non-target path
            # bounds, including separate fill/stroke operations MuPDF coalesces.
            remove_paths(clean, [{'rect': path_bounds(d)} for d in drawings
                                 if kind != 'path' or d is not target])
            expected = [_key(target)] if kind == 'path' else []
            if [_key(d) for d in clean.get_drawings() if _visible(d)] != expected:
                return None
            for block in blocks:
                if block['type'] == 0:
                    for line in block['lines']:
                        clean.add_redact_annot(line['bbox'], fill=False)
            clean.apply_redactions(images=0, graphics=0, text=0)
            resolution = min(3, 3000/max(page.rect.width, page.rect.height))
            # MuPDF caches decoded images during inspection. Reopen the private
            # bytes so replaced aliases cannot render their stale source pixels.
            with fitz.open(stream=layer.tobytes(), filetype='pdf') as render_doc:
                pix = render_doc[0].get_pixmap(matrix=fitz.Matrix(resolution, resolution), clip=bounds, alpha=True)
            blob = pix.tobytes('png')
            evidence = {'kind': kind, 'source_sequence': seq, 'bounds': list(bounds),
                        'pixel_size': [pix.width, pix.height],
                        'image_sha256': hashlib.sha256(blob).hexdigest()}
            if kind == 'image':
                evidence['source_image_digest'] = target['digest'].hex()
            result.append({'blob': blob, 'bounds': bounds,
                           'description': 'Independent PDF cover image; semantic role must be reviewed.' if kind == 'image'
                           else 'Independent PDF cover rectangle panel; semantic role must be reviewed.',
                           'evidence': evidence})
        finally:
            layer.close()
    return result or None
