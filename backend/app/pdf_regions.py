"""Conservative PDF chrome detection and source-font fidelity regions.

These decisions are recorded in the import receipt and independently reviewed
against the untouched PDF. No inference from presentation text is executable.
"""
from collections import Counter
from io import BytesIO
import hashlib
import math
import fitz


def lines(blocks):
    return [line for block in blocks if block['type'] == 0 for line in block['lines']]


def text(line):
    return ''.join(s['text'] for s in line['spans'])


def footer_key(line, size):
    box = fitz.Rect(line['bbox'])
    if box.y0 < size.height * .94 or max(s['size'] for s in line['spans']) > size.height * .025:
        return None
    return (text(line).strip(), tuple(round(v / size.height, 3) for v in (box.y0, box.y1)))


def repeated_footer(doc):
    counts = Counter()
    cover = lines(doc[0].get_text('dict')['blocks'])
    main_copy = ''.join(''.join(text(line).split()).casefold() for line in cover
                        if fitz.Rect(line['bbox']).y0 < doc[0].rect.height * .9)
    for page in doc:
        counts.update({key for line in lines(page.get_text('dict')['blocks'])
                       if (key := footer_key(line, page.rect)) and key[0]})
    # Repetition alone does not make a citation/copyright notice decorative.
    # Require running copy that duplicates the source cover's actual content.
    return {key for key, count in counts.items() if count >= max(3, math.ceil(len(doc) * .8))
            and len(''.join(key[0].split())) >= 6
            and ''.join(key[0].split()).casefold() in main_copy}


def frame_key(drawing, size):
    """Recognize an isolated perimeter rule, never a diagram/table border.

    Repetition across the deck is required separately. A filled panel, compound
    drawing or frame inset into the content area is not an eligible decoration.
    """
    if (len(drawing.get('items',[])) != 1 or drawing['items'][0][0] != 're'
            or drawing.get('color') is None or (drawing.get('stroke_opacity') or 0) <= 0
            or (drawing.get('fill') is not None and (drawing.get('fill_opacity') or 0) > 0)):
        return None
    r = fitz.Rect(drawing['rect'])
    width = drawing.get('width') or 0
    if not 0 < width <= min(size.width,size.height)*.025: return None
    normalized = ((r.x0-size.x0)/size.width,(r.y0-size.y0)/size.height,
                  (r.x1-size.x0)/size.width,(r.y1-size.y0)/size.height)
    if any(abs(a-b) > .02 for a,b in zip(normalized,(0,0,1,1))): return None
    return (tuple(round(v,3) for v in normalized),tuple(round(c,3) for c in drawing['color']),
            round(width/min(size.width,size.height),3))


def repeated_frames(doc):
    counts = Counter()
    for page in doc:
        counts.update({key for drawing in page.get_drawings()
                       if (key := frame_key(drawing,page.rect)) is not None})
    return {key for key,count in counts.items() if count >= max(3,math.ceil(len(doc)*.6))}


def edge_shadow_axis(image, size):
    """Only tiny raster strips spanning an outer page edge are candidates."""
    rect=fitz.Rect(image['bbox'])
    if (image['height']<=16 and rect.height<=size.height*.02 and rect.width>=size.width*.995
            and (abs(rect.y0-size.y0)<=size.height*.01 or abs(rect.y1-size.y1)<=size.height*.01)):
        return 'horizontal'
    if (image['width']<=16 and rect.width<=size.width*.02 and rect.height>=size.height*.995
            and (abs(rect.x0-size.x0)<=size.width*.01 or abs(rect.x1-size.x1)<=size.width*.01)):
        return 'vertical'
    return None


def repeated_edge_shadows(doc):
    """Prove repeated perimeter shading contains no text, logo or diagram.

    Every row of a horizontal strip (column of a vertical strip) must be one
    uniform neutral color and alpha. Identical bytes/placement must recur.
    """
    from PIL import Image
    candidates={};counts=Counter()
    for page in doc:
        image_info=page.get_image_info()
        if not any(edge_shadow_axis(info,page.rect) for info in image_info): continue
        # Some PyMuPDF versions omit the separate soft-mask bytes from text
        # blocks. Reject resource images of masked dimensions as well, instead
        # of mistaking their solid RGB plane for the visible artwork.
        masked_sizes={(entry[2],entry[3]) for entry in page.get_images(full=True) if entry[1]}
        found=[]
        for block in page.get_text('dict',clip=fitz.INFINITE_RECT())['blocks']:
            if block['type']!=1 or not (axis:=edge_shadow_axis(block,page.rect)): continue
            if block.get('mask') or (block['width'],block['height']) in masked_sizes: continue
            if sum(all(abs(a-b)<.01 for a,b in zip(info['bbox'],block['bbox'])) for info in image_info)!=1:
                continue
            with Image.open(BytesIO(block['image'])) as source:
                pixels=source.convert('RGBA')
            stripes=pixels.height if axis=='horizontal' else pixels.width
            for index in range(stripes):
                strip=pixels.crop((0,index,pixels.width,index+1) if axis=='horizontal'
                                  else (index,0,index+1,pixels.height))
                extrema=strip.getextrema()
                if any(lo!=hi for lo,hi in extrema) or len({extrema[i][0] for i in range(3)})!=1:
                    break
            else:
                key=(tuple(round(v,3) for v in block['bbox']),hashlib.sha256(block['image']).hexdigest())
                found.append((key,tuple(block['bbox'])))
        candidates[page.number]=found
        counts.update({key for key,_ in found})
    repeated={key for key,count in counts.items() if count>=max(3,math.ceil(len(doc)*.8))}
    return {page:[bounds for key,bounds in found if key in repeated]
            for page,found in candidates.items() if any(key in repeated for key,_ in found)}


def chrome(page, blocks, drawings, repeated):
    """Only repeated tiny footer copy plus its adjacent navigation furniture.

    Unique footnotes/captions, source logos and external links stay untouched.
    Navigation requires multiple internal links and a confirmed repeated footer.
    """
    excluded = [line for line in lines(blocks) if footer_key(line, page.rect) in repeated]
    links = page.get_links()
    nav = [link for link in links if link['kind'] in (fitz.LINK_GOTO, fitz.LINK_NAMED)
           and fitz.Rect(link['from']).y0 >= page.rect.height * .93]
    cutoff = min((fitz.Rect(link['from']).y0 for link in nav), default=page.rect.height)
    active = bool(excluded) and len(nav) >= 4
    nav_area = fitz.Rect(page.rect.width, cutoff, page.rect.width, page.rect.height)
    for link in nav: nav_area |= fitz.Rect(link['from'])
    def furniture(drawing):
        r = fitz.Rect(drawing['rect'])
        if r.y0 < cutoff: return False
        in_controls = ((nav_area + (-1,-1,1,1)).contains(r) and
                       r.width < page.rect.width * .1 and r.height < page.rect.height * .03)
        footer_band = (drawing.get('fill') is not None and len(drawing['items']) == 1
                       and drawing['items'][0][0] == 're' and r.width >= page.rect.width * .3
                       and r.height <= page.rect.height * .035
                       and any(r.intersects(fitz.Rect(line['bbox'])) for line in excluded))
        return in_controls or footer_band
    # Remove only confirmed controls and their footer bands. Nearby body copy
    # and unique footnotes remain, even when their bounds touch the controls.
    removed_drawings = [d for d in drawings if active and furniture(d)]
    return excluded, removed_drawings, nav if active else []


def cover_title(blocks, excluded):
    candidates = [b for b in blocks if b['type'] == 0 and b['lines']
                  and all(l not in excluded for l in b['lines'])]
    if not candidates:
        return []
    block = max(candidates, key=lambda b: max(s['size'] for l in b['lines'] for s in l['spans']))
    title = block['lines']
    sizes = [max(s['size'] for s in l['spans']) for l in title]
    # Multiline headings must share typography and be vertically stacked.
    if max(sizes) - min(sizes) > .5 or any(
            fitz.Rect(b['bbox']).y0 <= fitz.Rect(a['bbox']).y0 for a, b in zip(title, title[1:])):
        return [max(title, key=lambda l: max(s['size'] for s in l['spans']))]
    return title


def title_backdrop(page, title, lines_, drawings, images):
    if not title:
        return [], []
    bounds = fitz.Rect(title[0]['bbox'])
    for line in title[1:]: bounds |= fitz.Rect(line['bbox'])
    seeds = [d for d in drawings if d.get('fill') is not None
             and fitz.Rect(d['rect']).get_area() < page.rect.get_area() * .4
             and (fitz.Rect(d['rect']) & bounds).get_area() > bounds.get_area() * .85]
    if not seeds:
        return [], []
    region = fitz.Rect(seeds[0]['rect'])
    selected = list(seeds)
    for d in seeds: region |= fitz.Rect(d['rect'])
    changed = True
    while changed:
        changed = False
        for d in drawings:
            r = fitz.Rect(d['rect'])
            if d in selected or r.get_area() >= page.rect.get_area() * .4: continue
            if (region + (-2, -2, 2, 2)).intersects(r + (-.1, -.1, .1, .1)):
                selected.append(d); region |= r; changed = True
    shadows = []
    for image in images:
        r = fitz.Rect(image['bbox'])
        if not (region + (-6, -6, 6, 6)).intersects(r): continue
        from PIL import Image
        from io import BytesIO
        pixels = Image.open(BytesIO(image['image'])).convert('RGB')
        # Low-resolution neutral edge strips/corners, outside the title itself.
        # A real photograph/logo overlapping the backdrop makes it ambiguous.
        shadow = (min(image['width'], image['height']) <= 10 and not r.intersects(bounds)
                  and r.get_area() < page.rect.get_area() * .03
                  and all(max(rgb)-min(rgb) <= 2 for rgb in pixels.getdata()))
        if shadow: shadows.append(image)
        elif region.intersects(r): return [], []
    if any(l not in title and region.intersects(fitz.Rect(l['bbox'])) for l in lines_): return [], []
    return selected, shadows


def needs_source_font(line):
    # PDF subset/TeX/custom fonts cannot safely be substituted with Arial. Their
    # Unicode maps may even spell a visible summation as "X". Preserve pixels.
    native = ('arial', 'helvetica', 'times', 'courier', 'calibri', 'aptos', 'symbol')
    return any(s['text'].strip() and not s['font'].split('+')[-1].lower().startswith(native)
               for s in line['spans'])


def fidelity_regions(lines_, graphic_boxes, seeds):
    """Expand to whole intersecting objects, then merge until regions are disjoint.

    A clipped line raster can duplicate its neighbor or lose an equation index.
    Whole-object closure keeps connected equations/figures together exactly once.
    """
    pending = [fitz.Rect(l['bbox']) for l in seeds]
    objects = [fitz.Rect(l['bbox']) for l in lines_] + [fitz.Rect(b) for b in graphic_boxes]
    changed = True
    while changed:
        changed = False
        for i, region in enumerate(pending):
            for box in objects:
                if region.intersects(box) and not region.contains(box):
                    region |= box; changed = True
            for j in range(i + 1, len(pending)):
                if region.intersects(pending[j]):
                    region |= pending.pop(j); changed = True; break
            pending[i] = region
            if changed: break
    return pending
