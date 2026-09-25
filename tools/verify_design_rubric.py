"""Live visual challenge on supplied source-left/candidate-right screenshot pairs."""
import argparse
import json
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'backend')]
from app.ai import providers, output_qa, rubric


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live',action='store_true',required=True,help='Send the supplied images to the configured QA provider.')
    parser.add_argument('--images',type=Path,nargs='+',required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists():parser.error('Choose a new evidence directory.')
    if not all(p.is_file() for p in args.images):parser.error('An image is missing.')
    args.output.mkdir(parents=True)
    results=[]
    for i,path in enumerate(args.images,1):
        payload={'stage':'slide_review','expected':[1], 'rubric_version':rubric.VERSION,
            'context':'The image is a comparison: original source LEFT, generated candidate RIGHT. Audit ONLY the right slide, compare with the left. Ignore surrounding web UI. Slide ordinal is 1 for this independent example. No actual PPTX object inventory is available; do not invent IDs or claim to verify unseen notes/data.',
            'schema':output_qa.Review.model_json_schema()}
        reply=providers.generate('output_qa',output_qa.SYSTEM,payload,[(f'Example {i}: source left / candidate right',path)],max_tokens=10000)
        if reply['status']!='completed':raise RuntimeError('QA call failed: '+reply['status'])
        review=output_qa.Review.model_validate(reply['data'])
        (args.output/f'example-{i}-response.json').write_text(review.model_dump_json(indent=2),encoding='utf-8')
        if review.reviewed!=[1] or [a.ordinal for a in review.slide_audits]!=[1]:raise ValueError('Incomplete slide audit.')
        if any(f.slides!=[1] for f in review.findings):raise ValueError('Unexpected slide reference.')
        rubric.validate_checks(review.slide_audits[0].checks,review.findings)
        record={'example':i,'image_name':path.name,'model':reply.get('model'),'rubric_version':rubric.VERSION,**review.model_dump()}
        (args.output/f'example-{i}.json').write_text(json.dumps(record,indent=2),encoding='utf-8')
        results.append({'example':i,'blocking':sum(f.severity=='blocking' for f in review.findings),
                        'review':sum(f.severity=='review' for f in review.findings),
                        'flagged_criteria':[c.criterion for c in review.slide_audits[0].checks if c.status in ('blocking','review')]})
        print(json.dumps(results[-1]),flush=True)
    (args.output/'summary.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
    return 0 if all(r['blocking'] or r['review'] for r in results) else 3


if __name__=='__main__':raise SystemExit(main())
