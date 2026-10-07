"""Suppress explicitly identified root-page paint paths, preserving text/clips.

Area redaction can remove adjacent article artwork, or retain navigation strokes
whose PDF bounds cross the page edge. Match the actual transformed path instead.
Unrecognized constructs (inline images, malformed graphics state) are left alone.
"""
import re
import fitz


def path_bounds(drawing):
    # MuPDF's reported rect can omit the first segment of a later subpath.
    # Include actual drawing points when matching a multi-part control icon.
    points=[]
    for item in drawing.get('items', []):
        for value in item[1:]:
            if isinstance(value,fitz.Point): points.append(value)
            elif isinstance(value,fitz.Rect): points.extend((value.tl,value.br))
            elif isinstance(value,fitz.Quad): points.extend((value.ul,value.ur,value.ll,value.lr))
    if not points: return tuple(drawing['rect'])
    return (min(p.x for p in points),min(p.y for p in points),max(p.x for p in points),max(p.y for p in points))


def tokens(data):
    i=0; n=len(data); space=b' \t\r\n\x00\x0c'; delimiters=space+b'()<>[]{}/%'
    while i<n:
        if data[i] in space: i+=1; continue
        start=i
        if data[i]==37:
            while i<n and data[i] not in b'\r\n': i+=1
            continue
        if data[i]==40:
            depth=1; i+=1
            while i<n and depth:
                if data[i]==92: i+=2; continue
                if data[i]==40: depth+=1
                elif data[i]==41: depth-=1
                i+=1
            if depth: raise ValueError('Unclosed PDF string')
            yield start,i,b'string'; continue
        if data[i]==60 and data[i:i+2]!=b'<<':
            i=data.find(b'>',i+1)
            if i<0: raise ValueError('Unclosed PDF hex string')
            i+=1; yield start,i,b'string'; continue
        if data[i]==47:
            i+=1
            while i<n and data[i] not in delimiters: i+=1
            yield start,i,b'name'; continue
        if data[i] in delimiters: i+=1
        else:
            while i<n and data[i] not in delimiters: i+=1
        yield start,i,data[start:i]


def isolated_rectangle(ops, points, paint):
    """Prove one closed, axis-aligned rectangle in either native PDF spelling."""
    if ops in ([b're'],[b're',b'h']):
        corners=points
    else:
        closed=bool(ops and ops[-1]==b'h') or paint in (b's',b'b',b'b*')
        edges=ops[:-1] if ops and ops[-1]==b'h' else ops
        if edges == [b'm',b'l',b'l',b'l',b'l'] and len(points)==5:
            if abs(points[-1]-points[0]) > .001: return False
            corners=points[:-1]; closed=True
        elif edges == [b'm',b'l',b'l',b'l'] and len(points)==4:
            corners=points
        else: return False
        if not closed: return False
    if len(corners)!=4: return False
    # Reject diagonals, diamonds, retraced/degenerate paths and compound paths;
    # sharing a perimeter's bounding box alone must never make content removable.
    directions=[]
    for a,b in zip(corners,corners[1:]+corners[:1]):
        dx,dy=abs(a.x-b.x),abs(a.y-b.y)
        if dx<=.001 and dy>.001: directions.append('v')
        elif dy<=.001 and dx>.001: directions.append('h')
        else: return False
    return directions in (['h','v','h','v'],['v','h','v','h'])


def remove_paths(page, drawings, *, stroke_only=False):
    if not drawings: return 0
    if stroke_only:
        # An embedded frame and an unrelated filled panel can have identical
        # rectangular bounds. The root-stream scanner cannot distinguish them
        # by location, and a coincidental removal count would hide that mistake.
        # Refuse the cleanup if *any* visible same-bounds stroke is not one of
        # the selected frames. Same-bounds fill-only backgrounds remain safe.
        properties=('type','color','width','stroke_opacity','fill','fill_opacity',
                    'dashes','lineCap','lineJoin','even_odd','closePath')
        for candidate in page.get_drawings():
            if candidate.get('color') is None or (candidate.get('stroke_opacity') or 0)<=0:
                continue
            matching=[d for d in drawings if all(abs(a-b)<.025 for a,b in
                                                 zip(path_bounds(candidate),path_bounds(d)))]
            if matching and not any(candidate.get('items')==d.get('items') and
                                    all(candidate.get(k)==d.get(k) for k in properties)
                                    for d in matching):
                return 0
    # Work against all page streams together: graphics state can cross streams.
    data=b'\n'.join(page.parent.xref_stream(x) for x in page.get_contents())
    replacements=[]; numbers=[]; points=[]; path_ops=[]; stack=[]; matrix=page.transformation_matrix
    clipping=False; in_text=False
    targets=[(path_bounds(d),d.get('type')) for d in drawings]
    try:
        for start,end,op in tokens(data):
            if op==b'BI': return 0
            if op==b'BT': in_text=True
            if op==b'ET': in_text=False
            if in_text: continue
            if re.fullmatch(rb'[+-]?(?:\d+(?:\.\d*)?|\.\d+)',op):
                numbers.append(float(op)); continue
            if op==b'q': stack.append(fitz.Matrix(matrix))
            elif op==b'Q': matrix=stack.pop()
            elif op==b'cm' and len(numbers)==6: matrix=fitz.Matrix(*numbers)*matrix
            elif op in (b'm',b'l',b'c',b'v',b'y') and len(numbers) in (2,4,6):
                path_ops.append(op)
                points.extend(fitz.Point(*numbers[j:j+2])*matrix for j in range(0,len(numbers),2))
            elif op==b're' and len(numbers)==4:
                path_ops.append(op)
                x,y,w,h=numbers
                points.extend(fitz.Point(a,b)*matrix for a,b in ((x,y),(x+w,y),(x+w,y+h),(x,y+h)))
            elif op==b'h': path_ops.append(op)
            elif op in (b'W',b'W*'): clipping=True
            elif op in (b'S',b's',b'f',b'F',b'f*',b'B',b'B*',b'b',b'b*',b'n'):
                # Perimeter detection accepts only one isolated rectangle.
                # Bounds alone could instead match a meaningful diagonal or
                # compound root path when the real frame is in a Form XObject
                # that this conservative scanner deliberately cannot edit.
                if points and not clipping and op!=b'n' and (not stroke_only or isolated_rectangle(path_ops,points,op)):
                    bounds=(min(p.x for p in points),min(p.y for p in points),
                            max(p.x for p in points),max(p.y for p in points))
                    paint_type = 's' if op in (b'S',b's') else 'f' if op in (b'f',b'F',b'f*') else 'fs'
                    if any((stroke_only or kind is None or kind == paint_type or kind == 'fs') and
                           all(abs(a-b)<.025 for a,b in zip(bounds,target)) for target,kind in targets):
                        if not stroke_only:
                            replacements.append((start,end,b'n'))
                        elif paint_type=='s':
                            replacements.append((start,end,b'n'))
                        elif paint_type=='fs':
                            # MuPDF may coalesce separate fill/stroke operators
                            # into one drawing. Remove only its outline, leaving
                            # even a same-bounds content/background fill intact.
                            replacements.append((start,end,(b'h ' if op in (b'b',b'b*') else b'')+
                                                  (b'f*' if op.endswith(b'*') else b'f')))
                points=[]; path_ops=[]; clipping=False
            numbers=[]
        if stack: return 0
    except (ValueError,IndexError,OverflowError):
        return 0
    if replacements:
        for start,end,value in reversed(replacements): data=data[:start]+value+data[end:]
        xref=page.parent.get_new_xref()
        page.parent.update_object(xref,'<<>>'); page.parent.update_stream(xref,data)
        page.set_contents(xref)
    return len(replacements)
