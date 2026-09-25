"""Opt-in synthetic PDF -> AI redesign -> real render and release-gate checkpoint."""
import argparse
import json
import shutil
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'backend')]
import fitz
from app import api, sessions, generations
from app.ai import providers


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--live',action='store_true',required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--math-fixture',action='store_true',help='Also test tightly spaced PDF math and annotation lines.')
    p.add_argument('--cover-footer-fixture',action='store_true',help='Test a white cover background, multiple metadata rows and a low footnote.')
    args=p.parse_args()
    if args.output.exists():p.error('Use a new evidence directory.')
    if not providers.capabilities()['configured']:p.error('Configure the AI providers first.')
    args.output.mkdir(parents=True)
    pdf=fitz.open();page=pdf.new_page(width=960,height=540)
    if args.cover_footer_fixture:
        page.draw_rect((10,10,950,530),color=(1,1,1),fill=(1,1,1))
        for y,text,size in [(60,'Introduction and syllabus',20),(125,'Synthetic Course',42),
                            (185,'Autumn 2026',30),(310,'Presenters: Taylor Example and Jordan Sample',20),
                            (370,'Tuesday 10-11 am in room 101',20),
                            (515,'Questions, corrections and requests for clarification are welcome. Please keep them on topic.',11),
                            (533,'1',10)]:
            page.insert_text((50,y),text,fontsize=size)
    else:
        page.insert_text((50,100),'Synthetic project update',fontsize=32)
        page.insert_text((50,170),'Research and prototype milestones',fontsize=20)
        page.insert_text((50,420),'Presenter: Synthetic reviewer',fontsize=18)
    if args.math_fixture:
        page=pdf.new_page(width=960,height=540)
        page.insert_text((50,60),'Vector product rule',fontsize=30)
        lines=[
            'Let u(t) and v(t) be differentiable vectors in R^3.',
            'Dot product: d/dt [u(t) . v(t)] = u\'(t) . v(t) + u(t) . v\'(t)',
            'Cross product: d/dt [u(t) x v(t)] = u\'(t) x v(t) + u(t) x v\'(t)',
            'Preserve the factor order: the cross product is not commutative.',
            'Example: u(t) = (t, 0, 0), v(t) = (0, t, 0).',
            'Then u(t) x v(t) = (0, 0, t^2).',
            'Its derivative is (0, 0, 2t).',
            'The two product-rule terms are each (0, 0, t).',
        ]
        for i,line in enumerate(lines):page.insert_text((50,105+i*17),line,fontsize=14)
        page.insert_text((50,255),'Check: keep both terms, every prime, and the factor order.',fontsize=10)
    pdf.save(args.output/'input.pdf');pdf.close()
    info=api.analyze_upload('synthetic.pdf',(args.output/'input.pdf').read_bytes())
    s=sessions.get(info['session_id'])
    original_save=generations.save;last=[None]
    def save(record):
        progress=record.get('progress',{})
        if progress!=last[0]:print(json.dumps(progress),flush=True);last[0]=dict(progress)
        original_save(record)
    generations.save=save
    try:
        with sessions.job(s):record=generations.build(s,mode='ai',repair_passes=1)
        shutil.copytree(record['directory'],args.output/'generation')
        shutil.copyfile(s.source_path,args.output/'imported.pptx')
        shutil.copyfile(s.preview_path(0,'before'),args.output/'original.png')
        value=generations.public(record)
        (args.output/'result.json').write_text(json.dumps(value,indent=2),encoding='utf-8')
        print(json.dumps({'state':value['state'],'checks':value['checks'],'pdf_available':value['pdf_available'],'usage':value['usage']}),flush=True)
        return 0 if value['state']=='ready' and value['pdf_available'] else 3
    finally:sessions.delete(s.id)


if __name__=='__main__':raise SystemExit(main())
