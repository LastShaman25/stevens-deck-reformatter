"""Opt-in real-file reproduction through the same HTTP endpoints as the browser.

No mock providers, fabricated QA, automatic approval, or fixture substitutions.
The source is read-only. Processing artifacts stay in the app session; the report
contains hashes, check statuses, request counts and download results, not slide text.
"""
import argparse
import hashlib
import json
import sys
import time
from io import BytesIO
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import httpx

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from app.ai.providers import setting
from app.generations import QA_REQUIRED


def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def read_status(client, sid):
    """Retry read-only progress requests; never repeat a generation POST."""
    for attempt in range(3):
        try:
            response=client.get(f'/api/sessions/{sid}',timeout=20)
            response.raise_for_status()
            return response.json()
        except httpx.TransportError:
            if attempt==2: raise
            time.sleep(2)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--report',type=Path,required=True)
    parser.add_argument('--url',default='http://localhost:8000')
    parser.add_argument('--resume-session',help='Collect the existing job after a connection interruption; does not upload or generate again.')
    parser.add_argument('--live',action='store_true',required=True,
                        help='Authorizes sending this file to the configured AI providers.')
    args=parser.parse_args()
    source=args.source.resolve();before=digest(source)
    previous={}
    if args.report.exists():
        previous=json.loads(args.report.read_text(encoding='utf-8'))
        if not args.resume_session or previous.get('session_id')!=args.resume_session or previous.get('source_sha256')!=before:
            parser.error('Choose a new report path, or resume its matching session and unchanged source.')
    started=time.monotonic()
    with httpx.Client(base_url=args.url,timeout=2800,trust_env=False) as client:
        response=client.post('/api/auth/code',json={'code':setting('STEVENS_ADMIN_CODE','admin')})
        response.raise_for_status()
        auth=client.get('/api/auth/status').json()
        client.headers['X-CSRF-Token']=auth['csrf']
        if args.resume_session:
            sid=args.resume_session;session=read_status(client,sid)
        else:
            response=client.post('/api/sessions',files={'file':(source.name,source.read_bytes(),'application/pdf')})
            response.raise_for_status();session=response.json();sid=session['session_id']
        print(json.dumps({'session_id':sid,'source_sha256':before,'pages':session['slide_count']}),flush=True)
        events=previous.get('events',[]);last=None
        args.report.parent.mkdir(parents=True,exist_ok=True)
        def checkpoint():
            args.report.write_text(json.dumps({'passed':False,'state':'running_or_interrupted',
                'source_sha256':before,'session_id':sid,'events':events},indent=2),encoding='utf-8')
        checkpoint()
        # Keep the long generation response off the progress/download connection
        # pool, and bound each progress request independently of generation.
        with httpx.Client(base_url=args.url,timeout=2800,trust_env=False,
                          cookies=client.cookies,headers=client.headers) as worker, ThreadPoolExecutor(max_workers=1) as executor:
            future=None if args.resume_session else executor.submit(worker.post,f'/api/sessions/{sid}/generate',json={'mode':'ai','repair_passes':1})
            while future is None or not future.done():
                state=read_status(client,sid)
                generation=state.get('generation') or {}
                progress=generation.get('progress',{})
                if future is None and progress.get('stage')=='finished': break
                if time.monotonic()-started>2800: raise TimeoutError('Existing generation did not finish within the observation window.')
                if progress!=last:
                    event={'elapsed_seconds':round(time.monotonic()-started),**progress}
                    events.append(event);print(json.dumps(event),flush=True);last=progress
                    checkpoint()
                time.sleep(5)
            if future is not None:
                try:
                    response=future.result();response.raise_for_status();generation=response.json()['generation']
                except httpx.TransportError:
                    generation=read_status(client,sid).get('generation') or {}
                    if generation.get('progress',{}).get('stage')!='finished': raise
        statuses={k:v['status'] for k,v in generation['checks'].items()}
        downloads={}
        for format in ('pptx','pdf'):
            result=client.get(f'/api/sessions/{sid}/download',params={'generation_id':generation['generation_id'],'format':format})
            downloads[format]={'status_code':result.status_code,'bytes':len(result.content),
                               'sha256':hashlib.sha256(result.content).hexdigest() if result.status_code==200 else None}
            if result.status_code==200:
                if format=='pptx':
                    from pptx import Presentation
                    downloads[format]['slides']=len(Presentation(BytesIO(result.content)).slides)
                else:
                    import fitz
                    with fitz.open(stream=result.content,filetype='pdf') as pdf: downloads[format]['slides']=len(pdf)
        qa=generation.get('qa_execution',{});count=generation['built_slides']
        passed=(generation['state']=='ready' and all(statuses.get(k)=='passed' for k in QA_REQUIRED+('ai_redesign',))
                and qa.get('complete') and qa.get('redesign_reviewed_slides')==qa.get('reviewed_slides')==count
                and all(v['status_code']==200 and v.get('slides')==count for v in downloads.values())
                and downloads['pptx']['sha256']==generation['candidate_sha256'] and digest(source)==before)
        report={'passed':passed,'source_sha256':before,'source_unchanged':digest(source)==before,
                'session_id':sid,'generation_id':generation['generation_id'],'state':generation['state'],
                'checks':statuses,'qa_execution':generation.get('qa_execution'),'usage':generation.get('usage'),
                'warning_count':sum(f.get('severity')=='warning' for f in generation.get('findings',[])),
                'changed_objects':(generation.get('ai_pipeline') or {}).get('changed_objects',0),
                'reused_paired_reviews':len((generation.get('ai_pipeline') or {}).get('reused_reviews',[])),
                'repair_stop_reason':generation.get('repair_stop_reason'),
                'resumed_existing_job':bool(args.resume_session),
                'downloads':downloads,'elapsed_seconds':None if args.resume_session else round(time.monotonic()-started),
                'collection_elapsed_seconds':round(time.monotonic()-started),'events':events}
        args.report.parent.mkdir(parents=True,exist_ok=True)
        args.report.write_text(json.dumps(report,indent=2),encoding='utf-8')
        print(json.dumps({k:v for k,v in report.items() if k!='events'}),flush=True)
        return 0 if passed else 3


if __name__=='__main__':raise SystemExit(main())
