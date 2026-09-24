"""Local-only corpus evidence. No course files or renders are uploaded."""
import argparse
import json
import sys
from pathlib import Path
from collections import Counter

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT/'backend')]
import os
os.environ['STEVENS_OFFLINE'] = '1'
os.environ['STEVENS_LEARN'] = '0'
from app import grounded
from app.qa import artifact_coverage, brand_lint, render_verify
from slide_engine.inventory import sha256
from slide_engine.preserve import CoverageError

CORPUS = {
    'mgt': 'Slides fixer/reference examples/Original/MGT 612 CPE Module 3 Part 1 Leveraging Values to lead.pptx',
    'ds_m7': 'Accessibility Test Files/DS_M7_inaccessible.pptx',
    'onboarding': 'Accessibility Test Files/Onboarding_inaccessible.pptx',
    'qbr': 'Accessibility Test Files/QBR_inaccessible.pptx',
    'holdout': 'Slides fixer/reference examples/Original/MGT 612 CPE Module 4 Part 2 Using Multisource Feedback.pptx',
}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',required=True)
    parser.add_argument('--render',action='store_true')
    parser.add_argument('--corpus-root',type=Path,default=ROOT/'.local/private')
    args=parser.parse_args()
    base=Path(args.output);base.mkdir(parents=True,exist_ok=False)
    results=[]
    for name,relative in CORPUS.items():
        directory=base/name;directory.mkdir()
        src=args.corpus_root/relative;out=directory/'candidate.pptx'
        record={'name':name,'source':relative,'source_sha256':sha256(src)}
        try:
            report=grounded.build_deck(src,out)
            record['built_slides']=report['slide_count']
            record['candidate_sha256']=sha256(out)
            record['artifact']=artifact_coverage.audit(src,out,report)
            record['formatting']=brand_lint.lint(out)
            record['mapping']=report['source_to_output_slides']
            if args.render:
                record['render']=render_verify.check(out,directory/'render')
            else:
                record['render']={'status':'not_run'}
            (directory/'build.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        except CoverageError as exc:
            record['plan']=exc.report
        except Exception as exc:
            record['error']=f'{type(exc).__name__}: {exc}'
        (directory/'result.json').write_text(json.dumps(record,indent=2),encoding='utf-8')
        results.append(record)
        print(json.dumps({'name':name,'artifact':record.get('artifact',{}).get('status'),
            'formatting_fail':record.get('formatting',{}).get('total_fail'),
            'plan_findings':dict(Counter(f.get('reason',f['code']) for f in record.get('plan',{}).get('findings',[]))),
            'render':record.get('render',{}).get('status'),'error':record.get('error')}),flush=True)
    (base/'results.json').write_text(json.dumps(results,indent=2),encoding='utf-8')


if __name__=='__main__':main()
