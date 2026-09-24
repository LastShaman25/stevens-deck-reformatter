"""Create local contact sheets and a text-free summary from a corpus run."""
import argparse
import json
from collections import Counter
from pathlib import Path
from PIL import Image, ImageDraw

parser=argparse.ArgumentParser()
parser.add_argument('directory',type=Path)
args=parser.parse_args()
summary=[]
for directory in sorted(p for p in args.directory.iterdir() if p.is_dir()):
    result_file=directory/'result.json'
    if not result_file.exists():continue
    r=json.loads(result_file.read_text(encoding='utf-8'))
    report_file=directory/'build.json'
    b=json.loads(report_file.read_text(encoding='utf-8')) if report_file.exists() else {}
    summary.append({'deck':directory.name,'source_sha256':r['source_sha256'],
        'candidate_sha256':r.get('candidate_sha256'),'source_slides':b.get('inventory',{}).get('slide_count'),
        'output_slides':r.get('built_slides'),'artifact':r.get('artifact',{}).get('status'),
        'formatting_hard':r.get('formatting',{}).get('total_fail'),
        'formatting_review':r.get('formatting',{}).get('total_warn'),
        'render':r.get('render',{}).get('status'),
        'render_findings':dict(Counter(f['code'] for f in r.get('render',{}).get('findings',[]))),
        'unsupported':dict(Counter(f.get('reason',f['code']) for f in r.get('plan',{}).get('findings',[]))),
        'source_object_counts':r.get('artifact',{}).get('counts'),
        'repair_cycles':b.get('repair_count'),'renderer':r.get('render',{}).get('renderer')})
    images=sorted((directory/'render').glob('slide-*.png'),key=lambda p:int(p.stem.split('-')[-1]))
    for start in range(0,len(images),12):
        selected=images[start:start+12]
        sheet=Image.new('RGB',(1440,290*((len(selected)+2)//3)),'#ddd')
        draw=ImageDraw.Draw(sheet)
        for n,path in enumerate(selected):
            with Image.open(path) as im:
                im.thumbnail((480,270));x=(n%3)*480;y=(n//3)*290
                sheet.paste(im,(x,y+20));draw.text((x+8,y+3),f'{directory.name} output {start+n+1}',fill='black')
        sheet.save(directory/f'contact-{start//12+1}.png')
(args.directory/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
print(json.dumps(summary,indent=2))
