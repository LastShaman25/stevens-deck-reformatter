"""Live ordered screenshot QA challenge with deliberately incorrect synthetic content."""
import argparse
import json
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'backend')]
from app import sessions
from app.authoring.composer import compose
from app.authoring.models import DeckSpec,SlideSpec
from app.qa.render_verify import check
from app.ai.output_qa import run


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--live',action='store_true',required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.exists():p.error('Choose a new evidence directory.')
    a.output.mkdir(parents=True)
    s=sessions.create();workspace=Path(s.dir)
    try:
        with sessions.job(s):
            slides=[SlideSpec(id='conclusion',title='Conclusion',bullets=['The experiment measured 84 units.']),
                SlideSpec(id='method',title='Method',bullets=['A calibrated instrument measured the sample.']),
                SlideSpec(id='result',title='Measured result',bullets=['The experiment measured 42 units.'])]
            candidate=workspace/'qa-challenge.pptx';compose(DeckSpec(slides=slides),candidate,workspace/'assets')
            rendering=check(candidate,workspace/'render')
            record={'candidate':str(candidate),'checks':{'render_verification':rendering}}
            evidence={'approved_order':['Method','Measured result','Conclusion'],
                'source_facts':'Synthetic source of truth: the experiment measured exactly 42 units. 84 is incorrect.'}
            results=run(s,record,evidence)
            result={'checks':results,'detected_accuracy':any(f['severity']=='blocking' for f in results['output_qa_accuracy']['findings']),
                    'detected_order':bool(results['output_qa_sequence']['findings'])}
            (a.output/'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
            print(json.dumps(result),flush=True)
        return 0 if result['detected_accuracy'] and result['detected_order'] else 1
    finally:
        sessions.delete(s.id)
        if workspace.exists():raise RuntimeError('QA challenge workspace was not removed.')


if __name__=='__main__':raise SystemExit(main())
