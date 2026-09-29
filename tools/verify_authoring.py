"""Explicit live synthetic acceptance: topic + PDF + screenshot QA + cleanup.

Only synthetic inputs are submitted. Evidence copied to --output is deliberate
development evidence; application workspaces must still be deleted. Exit 0 requires
all mandatory checks to complete without blocking findings. Human review remains
explicit when the model reports uncertainty; this script never auto-approves it.
"""
import argparse
import json
import shutil
import sys
import time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'backend'),str(ROOT)]
import fitz
from app import sessions, generations
from app.ai import providers
from app.authoring import service
from app.authoring.models import CreationRequest


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live',action='store_true',required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--cases',nargs='+',choices=['topic','pdf','scanned'],default=['topic','pdf'])
    args=parser.parse_args()
    if args.output.exists(): parser.error('Use a new output directory.')
    args.output.mkdir(parents=True)
    if not providers.capabilities()['configured']: raise SystemExit('Configure the existing provider key before the live checkpoint.')
    outcomes=[]
    for source in args.cases:
        print('START '+source,flush=True)
        req=CreationRequest(source='pdf' if source=='scanned' else source,audience='First-year engineering students',length_preference='brief',
            topic='Explain sine functions with a simple y=sin(x) function plot and the equation integral from 0 to pi of sin(x) dx = 2. Include a native column chart with clearly labeled illustrative measurements A=2 and B=4. Use one major visual per slide and a logical explanation. Keep the presentation concise.')
        sess=service.create(req); directory=Path(sess.dir)
        try:
            with sessions.job(sess):
                if source in ('pdf','scanned'):
                    doc=fitz.open()
                    for title,body in [
                        ('Sine functions','The sine function is y = sin(x). Its period is 2 pi. sin(0)=0, sin(pi/2)=1, sin(pi)=0.'),
                        ('An integral','The definite integral of sin(x) from 0 to pi is 2. This is the area over one positive half-period.'),
                        ('Illustrative measurements','These are synthetic educational measurements, not real experimental results: category A = 2 units; category B = 4 units.')]:
                        page=doc.new_page();page.insert_text((72,72),title,fontsize=20);page.insert_textbox(fitz.Rect(72,120,520,500),body,fontsize=16)
                    if source=='scanned':
                        scanned=fitz.open()
                        for page in doc:
                            target=scanned.new_page(width=page.rect.width,height=page.rect.height)
                            target.insert_image(target.rect,stream=page.get_pixmap(matrix=fitz.Matrix(1.5,1.5)).tobytes('png'))
                        doc.close();doc=scanned
                    service.ingest_pdf(sess,doc.tobytes());doc.close()
                service.plan(sess)
                print(f"OUTLINE {source}: {len(sess.creation['outline']['slides'])} slides",flush=True)
                service.approve(sess,sess.creation['revision'])
                result=service.generate(sess)
                record=sess.generation
                shutil.copytree(record['directory'],args.output/source)
                summary={'source':source,'slide_count':len(sess.creation['outline']['slides']),
                         'state':record['state'],'download_allowed':generations.download_allowed(record),
                         'qa_execution':result['generation']['qa_execution'],'checks':result['generation']['checks'],
                         'findings':result['generation']['findings'],'calls':sess.calls,'tokens':sess.tokens}
                outcomes.append(summary)
                print(json.dumps(summary),flush=True)
        finally:
            sessions.delete(sess.id)
            if directory.exists(): raise RuntimeError('Application workspace cleanup failed.')
        outcomes[-1]['workspace_removed']=True
        (args.output/'summary.json').write_text(json.dumps(outcomes,indent=2),encoding='utf-8')
    return 0 if all(o['download_allowed'] for o in outcomes) else 1


if __name__=='__main__':raise SystemExit(main())
