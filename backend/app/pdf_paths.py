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


def remove_paths(page, drawings):
    if not drawings: return 0
    # Work against all page streams together: graphics state can cross streams.
    data=b'\n'.join(page.parent.xref_stream(x) for x in page.get_contents())
    replacements=[]; numbers=[]; points=[]; stack=[]; matrix=page.transformation_matrix
    clipping=False; in_text=False
    targets=[path_bounds(d) for d in drawings]
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
                points.extend(fitz.Point(*numbers[j:j+2])*matrix for j in range(0,len(numbers),2))
            elif op==b're' and len(numbers)==4:
                x,y,w,h=numbers
                points.extend(fitz.Point(a,b)*matrix for a,b in ((x,y),(x+w,y),(x+w,y+h),(x,y+h)))
            elif op in (b'W',b'W*'): clipping=True
            elif op in (b'S',b's',b'f',b'F',b'f*',b'B',b'B*',b'b',b'b*',b'n'):
                if points and not clipping and op!=b'n':
                    bounds=(min(p.x for p in points),min(p.y for p in points),
                            max(p.x for p in points),max(p.y for p in points))
                    if any(all(abs(a-b)<.025 for a,b in zip(bounds,target)) for target in targets):
                        replacements.append((start,end,b'n'))
                points=[]; clipping=False
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
