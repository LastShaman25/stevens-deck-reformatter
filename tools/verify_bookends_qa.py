"""Live, synthetic opening/content/closing acceptance. Never uses user documents."""
import argparse
import json
import shutil
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'backend'),str(ROOT)]
from app import sessions, generations
from app.authoring import service
from app.authoring.models import CreationRequest, Outline, OutlineSlide, DeckSpec, SlideSpec


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live',action='store_true',required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists(): parser.error('Use a new output folder.')
    args.output.mkdir(parents=True)
    sess=service.create(CreationRequest(topic='A synthetic arithmetic example',audience='Students'))
    outline=Outline(title='An arithmetic example',rationale='Opening, one example, closing.',slides=[
        OutlineSlide(id='opening',kind='opening',title='An arithmetic example',points=['Adding two numbers']),
        OutlineSlide(id='example',kind='content',title='Two plus two',points=['Two plus two equals four.']),
        OutlineSlide(id='closing',kind='closing',title='Thank you',points=['Questions and discussion'])])
    try:
        with sessions.job(sess):
            service.save_outline(sess,outline,0);service.approve(sess,1)
            deck=DeckSpec(slides=[SlideSpec(id=s.id,title=s.title,bullets=s.points,
                equation='2+2=4' if s.id=='example' else None) for s in outline.slides])
            result=service.generate(sess,deck,repair_remaining=0)
            record=sess.generation
            shutil.copytree(record['directory'],args.output/'generation')
            summary={'state':record['state'],'checks':result['generation']['checks'],
                'qa_execution':result['generation']['qa_execution'],'findings':result['generation']['findings'],
                'requests':sess.calls,'tokens':sess.tokens,'download_allowed':generations.download_allowed(record)}
    finally:
        sessions.delete(sess.id)
        if Path(sess.dir).exists(): raise RuntimeError('Synthetic workspace cleanup failed.')
    summary['workspace_removed']=True
    (args.output/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    print(json.dumps(summary),flush=True)
    return 0 if summary['download_allowed'] else 1


if __name__=='__main__':raise SystemExit(main())
