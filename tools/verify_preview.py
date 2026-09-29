"""Live Preview acceptance probe. Synthetic content only; requires real model QA.

Set PREVIEW_URL, PREVIEW_TEST_CODE, optional VERCEL_AUTOMATION_BYPASS_SECRET.
This runs paid model calls. It must be explicitly run by an authorized operator.
No human approvals, mocked models or skipped QA are used in this probe.
"""
import hashlib
import io
import json
import os
import re
import time
from pathlib import Path
from urllib.parse import urlsplit

import fitz
import requests
from pptx import Presentation


class Preview:
    def __init__(self):
        self.url=os.environ['PREVIEW_URL'].rstrip('/')
        host=urlsplit(self.url).hostname or ''
        if not self.url.startswith('https://') or not re.fullmatch(r'stevens-deck-reformatter-[a-zA-Z0-9-]+\.vercel\.app',host):
            raise ValueError('Use this project\'s explicit Vercel Preview URL; production is forbidden.')
        self.client=requests.Session()
        self.client.headers['Origin']=self.url
        bypass=os.environ.get('VERCEL_AUTOMATION_BYPASS_SECRET')
        if bypass:self.client.headers['x-vercel-protection-bypass']=bypass
        self.jobs=[];self.evidence={'preview':self.url,'checks':[]}

    def call(self,path,body=None,method=None):
        r=self.client.request(method or ('POST' if body is not None else 'GET'),self.url+path,json=body,timeout=780)
        if 'application/json' not in r.headers.get('Content-Type',''):
            raise RuntimeError(f'Backend routing/protection failure: {path} HTTP {r.status_code}')
        value=r.json()
        if not r.ok:raise RuntimeError(f'{path}: HTTP {r.status_code}: {value.get("detail","request failed")}')
        if r.status_code!=202:return value
        status_url=value['status_url']
        assert re.fullmatch('/api/cloud/tasks/[0-9a-f]{32}',status_url)
        deadline=time.monotonic()+3*3600
        while time.monotonic()<deadline:
            state=self.call(status_url)
            if state['state']=='completed':return state['result']
            if state['state'] in ('failed','cancelled'):raise RuntimeError(state['error'])
            self.call(status_url+'/advance',{})
            time.sleep(1)
        raise RuntimeError('Preview acceptance timed out; no release is authorized.')

    def upload(self,data,name,target='/api/sessions'):
        ticket=self.call('/api/cloud/uploads',{'filename':name,'size':len(data),'target':target})
        # Separate client: never forward app cookies, CSRF or protection secrets to S3.
        result=requests.post(ticket['url'],data=ticket['fields'],files={'file':(name,data)},timeout=180)
        result.raise_for_status()
        return self.call('/api/cloud/uploads/complete',{'upload_id':ticket['upload_id']})

    def verify_export(self,base,record):
        assert record['qa_execution']['complete'], 'Final QA did not complete'
        assert record['qa_execution']['reviewed_slides']==record['built_slides']
        assert record['download_allowed'] and record['state']=='ready', 'Mandatory review has not passed'
        assert not record['human_decisions'], 'This probe never uses human waivers'
        assert all(c['status']=='passed' for c in record['checks'].values()),record['checks']
        counts=[]
        for fmt in ('pptx','pdf'):
            value=self.call(base+'/download?generation_id='+record['generation_id']+'&format='+fmt)
            result=requests.get(value['download_url'],timeout=180)
            result.raise_for_status();data=result.content
            if fmt=='pptx':
                assert hashlib.sha256(data).hexdigest()==record['candidate_sha256']
                counts.append(len(Presentation(io.BytesIO(data)).slides))
            else:
                with fitz.open(stream=data,filetype='pdf') as doc:counts.append(len(doc))
        assert counts==[record['built_slides']]*2
        self.evidence['checks'].append({'workflow':base.split('/')[2], 'slides':counts[0],
            'candidate_sha256':record['candidate_sha256'],'qa':record['checks'],'downloads':['pptx','pdf']})

    def run(self):
        status=self.call('/api/auth/status')
        assert status['cloud'] and status['mode']=='invitation'
        login=self.call('/api/auth/code',{'code':os.environ['PREVIEW_TEST_CODE']})
        self.client.headers['X-CSRF-Token']=login['csrf']
        doc=fitz.open();page=doc.new_page(width=960,height=540)
        page.insert_text((80,100),'Synthetic deployment verification',fontsize=32)
        page.insert_text((80,170),'Two plus two equals four.',fontsize=24)
        data=doc.tobytes();doc.close()
        source=self.upload(data,'synthetic-verification.pdf')
        base='/api/sessions/'+source['session_id'];self.jobs.append(base)
        result=self.call(base+'/generate',{'mode':'ai','repair_passes':1})
        self.verify_export(base,result['generation'])
        job=self.call('/api/jobs',{'source':'topic','topic':'A brief presentation about the arithmetic identity 2 + 2 = 4. Include a simple visual and opening and thank-you closing. No external factual claims.',
                                    'audience':'Students','length_preference':'brief'})
        base='/api/jobs/'+job['id'];self.jobs.append(base)
        job=self.call(base+'/outline/plan',{})
        job=self.call(base+'/outline/approve',{'revision':job['revision'],'acknowledge_uncertainty':True})
        result=self.call(base+'/generate',{})
        self.verify_export(base,result['generation'])
        self.evidence['complete']=True

    def cleanup(self):
        failures=[]
        for base in self.jobs:
            try:
                result=self.call(base+'/cancel' if '/jobs/' in base else base+'/finalize',{})
                if not result.get('deleted'):failures.append(base)
            except Exception:failures.append(base)
        self.evidence['cleanup_pending']=failures
        if failures:self.evidence['complete']=False


if __name__=='__main__':
    probe=Preview()
    try:probe.run()
    finally:
        probe.cleanup()
        directory=Path('.local/verification');directory.mkdir(parents=True,exist_ok=True)
        (directory/'preview.json').write_text(json.dumps(probe.evidence,indent=2))
    assert probe.evidence.get('complete'), 'Preview acceptance or cleanup incomplete'
    print('Live Preview API workflow passed. Browser CORS, OIDC and interruption checklist still required.')
