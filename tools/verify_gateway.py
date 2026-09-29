"""Opt-in Gateway vision/JSON smoke comparison; not a full-deck quality benchmark."""
import argparse
import json
import os
import sys
import time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from pydantic import BaseModel
from app.ai import providers


class ClosingCheck(BaseModel):
    title: str
    photo_on_left: bool
    stevens_logo_present: bool


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--live',action='store_true',required=True)
    p.add_argument('--image',type=Path,required=True,help='A rendered synthetic Stevens Thank you closing with left-side photo.')
    p.add_argument('--models',nargs='+',required=True)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    if args.output.exists():p.error('Choose a new evidence path.')
    os.environ['STEVENS_OFFLINE']='0';os.environ['STEVENS_AI_REVIEWER']='vercel'
    os.environ['AI_GATEWAY_REVIEW_REASONING_EFFORT']='low'
    catalog=providers.requests.get('https://ai-gateway.vercel.sh/v1/models',timeout=30)
    catalog.raise_for_status();models={m['id']:m for m in catalog.json()['data']}
    rows=[]
    for model in args.models:
        metadata=models.get(model,{})
        compatible='vision' in metadata.get('tags',[]) and 'structured-output' in metadata.get('tags',[])
        if not compatible:
            rows.append({'model':model,'status':'unsupported_catalog_capabilities'});continue
        os.environ['STEVENS_AI_REVIEWER_MODEL']=model
        start=time.monotonic()
        result=providers.generate('reviewer','Read the slide image. Return its title and whether the photo is on the left and a Stevens logo is visible.',
            {'schema':ClosingCheck.model_json_schema()},[('Closing slide',args.image)],max_tokens=2000)
        valid=False
        if result['status']=='completed':
            answer=ClosingCheck.model_validate(result['data'])
            valid=answer.title.strip().lower().rstrip('!')=='thank you' and answer.photo_on_left and answer.stevens_logo_present
        row={'model':model,'status':result['status'],'elapsed_seconds':round(time.monotonic()-start,2),
             'vision_and_json_passed':valid,'usage':result.get('usage',{}),'request_attempts':result.get('request_attempts')}
        rows.append(row);print(json.dumps(row),flush=True)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(rows,indent=2),encoding='utf-8')
    return 0 if all(r.get('vision_and_json_passed') for r in rows) else 1


if __name__=='__main__':raise SystemExit(main())
