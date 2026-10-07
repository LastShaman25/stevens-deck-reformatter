"""Artifact identity and release decisions, independent of HTTP/UI state."""
from slide_engine import templates
from . import activity
import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from pydantic import BaseModel, Field, ConfigDict

from slide_engine.inventory import sha256
from slide_engine.preserve import CoverageError
from . import grounded
from .qa import artifact_coverage, brand_lint, render_verify

POLICY_VERSION = 'local-advisory-qa-34'
REQUIRED = ('plan_coverage', 'artifact_coverage', 'structural_formatting', 'render_verification')
QA_REQUIRED = ('ai_visual_review', 'output_qa_coverage', 'output_qa_sequence',
               'output_qa_accuracy', 'output_qa_visual')


def qa_passed(record):
    return all(record.get('checks', {}).get(n, {}).get('status') == 'passed'
               and all(f.get('severity')=='warning' for f in record['checks'][n].get('findings',[]))
               for n in QA_REQUIRED if n in required_checks(record))


def can_approve(record, finding):
    # Accept a completed check's finding independently of unrelated failures.
    # Acceptance records human review without changing the original QA verdict.
    checks = record.get('checks', {})
    name = finding.get('check')
    status = checks.get(name, {}).get('status')
    if name != 'optional_ai' and status not in ('passed', 'needs_review', 'failed'):
        return False
    review_check = name in QA_REQUIRED + ('structural_formatting', 'content_grounding')
    review_check |= name == 'render_verification' and status in ('passed', 'needs_review')
    review_check |= name == 'optional_ai' and finding.get('severity') == 'review'
    return bool(review_check and finding.get('severity') in ('review', 'blocking', 'warning'))


def approved_findings(record):
    decisions = [d for d in record.get('human_decisions', [])
            if d.get('generation_id') == record.get('generation_id')
            and d.get('candidate_sha256') == record.get('candidate_sha256')]
    approved = {fid for d in decisions if d.get('output_slide') is None for fid in d['finding_ids']}
    for finding in record.get('findings', []):
        targets = finding_slides(record, finding)
        accepted = {d['output_slide'] for d in decisions if d.get('output_slide') is not None and finding['id'] in d['finding_ids']}
        if targets and targets <= accepted:
            approved.add(finding['id'])
    return approved


def finding_priority(finding):
    # Existing rubric severity encodes material impact. Never downgrade missing
    # content or incomplete checks based on a display preference.
    return 'low' if finding.get('severity') == 'warning' else 'high'


def finding_slides(record, finding):
    if finding.get('affected_slides'):
        return set(finding['affected_slides'])
    if finding.get('output_slide') is not None:
        return {finding['output_slide']}
    source = next((finding[k] for k in ('source_slide','ai_source_slide','slide') if finding.get(k) is not None), None)
    return set(record.get('source_to_output_slides', {}).get(str(source), [])) if source is not None else set()


class GenerateRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    mode: Literal['preserve','ai'] = 'preserve'
    repair_passes: int = Field(default=1,ge=0,le=2)


class Revision(BaseModel):
    model_config = ConfigDict(extra='forbid')
    tags: list[Literal['split', 'dense', 'layout', 'overlap', 'diagram', 'emphasis']] = Field(default_factory=list)
    instruction: str = Field(default='', max_length=4000)
    reset_emphasis: bool = False


class Decision(BaseModel):
    model_config = ConfigDict(extra='forbid')
    generation_id: str
    candidate_sha256: str
    finding_ids: list[str] = Field(default_factory=list)
    output_slide: int | None = Field(default=None, ge=0)
    rationale: str = Field(min_length=1, max_length=2000)


def required_checks(record):
    from .ai.output_qa import CHECKS
    required=REQUIRED + CHECKS + ('output_qa_visual',) + (('ai_redesign','ai_visual_review') if record.get('mode')=='ai' else ())
    if record.get('mode') == 'author': required += ('content_grounding',)
    if record.get('pdf_import'): required += ('pdf_import',)
    return required


def download_allowed(record):
    # QA remains visible; completion and a produced artifact control availability.
    # Read endpoints also enforce ownership, freshness and artifact identity.
    return bool(record and record.get('processing_complete') and record.get('candidate_sha256'))


def checks_satisfied(record):
    approved = approved_findings(record)
    for name in required_checks(record):
        check=record.get('checks',{}).get(name,{})
        findings=[f for f in record.get('findings',[]) if f.get('check')==name and f.get('severity')!='warning']
        material = [f for f in check.get('findings', []) if f.get('severity') != 'warning']
        if len(material) != len(findings): return False
        if check.get('status')=='passed' and not findings: continue
        if not (check.get('status') in ('passed','needs_review','failed')
                and check.get('findings') and findings
                and all(f['id'] in approved and can_approve(record,f) for f in findings)):
            return False
    return True


def settle(record):
    required=required_checks(record)
    states = [record['checks'].get(k, {}).get('status', 'not_run') for k in required]
    if any(s in ('error', 'not_run', 'checking') for s in states):
        record['state'] = 'error' if 'error' in states or 'not_run' in states else 'checking'
    else:
        resolved = approved_findings(record)
        pending = [f for f in record['findings'] if f['id'] not in resolved and f.get('severity')!='warning']
        if checks_satisfied(record) and not pending:
            record['state'] = 'ready'
        elif any(f.get('severity') == 'blocking' for f in pending) or 'failed' in states:
            record['state'] = 'failed'
        else:
            record['state'] = 'needs_review' if pending or not checks_satisfied(record) else 'ready'
    return record


def save(record):
    render=record.get('checks',{}).get('render_verification',{})
    pages=render.get('pages',[])
    if pages and render.get('candidate_sha256')==record.get('candidate_sha256'):
        pdf=Path(pages[0]['png']).parent/'candidate.pdf'
        if pdf.is_file() and sha256(pdf)==render.get('pdf_sha256'):
            record['pdf_export']={'path':str(pdf),'sha256':render['pdf_sha256'],'candidate_sha256':record['candidate_sha256']}
    Path(record['directory'], 'generation.json').write_text(json.dumps(record, indent=2), encoding='utf-8')


def add_check(record, name, result):
    activity.emit('verifier',name,result['status'])
    # Reverification replaces findings; stale failures must not survive a repair.
    record['findings']=[f for f in record['findings'] if f.get('check')!=name]
    record['checks'][name] = result
    for i, item in enumerate(result.get('findings', [])):
        finding = dict(item)
        finding.setdefault('severity', 'blocking' if result['status'] in ('failed', 'error') else 'review')
        finding['check'] = name
        finding['id'] = f'{name}:{i}'
        finding.setdefault('message', finding.get('code', 'Verification finding').replace('_', ' ').capitalize())
        record['findings'].append(finding)


def resolve_visual_advisories(record):
    """Close heuristic 'inspect the render' warnings with actual paired QA.

    Never waive a blocking check, a provider error, missing review, or any QA
    finding. Keep each dismissed estimate and the exact rendered-review receipt.
    """
    if record.get('mode')!='ai' or not qa_passed(record): return
    digest=record.get('candidate_sha256')
    reviews={v['output_slide']:v for v in (record.get('ai_pipeline') or {}).get('final_reviews',[])
             if v.get('candidate_sha256')==digest and v.get('verdict')=='passed'}
    count=(record.get('report') or {}).get('slide_count',0)
    if not count or set(reviews)!=set(range(count)): return
    criteria={
        'FONT_SIZE':('visual_legibility',),'OVERFLOW':('spatial_layout','visual_legibility'),
        'OCCLUSION':('spatial_layout',),'VISUAL_OCCLUSION':('spatial_layout','visual_legibility'),
        'FONT':('brand_consistency',),'SOURCE_COLOR':('brand_consistency',),
        'UNRESOLVED_STYLE':('brand_consistency','visual_legibility'),
        'BULLET':('brand_consistency','structure_sequence'),'AUTOFIT':('visual_legibility',),
        'RENDER_SMALL_TEXT':('visual_legibility',),'RENDER_FONT_SUBSTITUTION':('brand_consistency','content_accuracy'),
        'RENDER_TEXT_OUTSIDE_OBJECT':('spatial_layout',),'RENDER_GLYPH_UNVERIFIED':('content_accuracy',),
    }
    for name in ('structural_formatting','render_verification'):
        result=record['checks'].get(name,{})
        if result.get('status')!='needs_review': continue
        pending=[];resolved=[]
        for finding in result.get('findings',[]):
            review=reviews.get(finding.get('output_slide'),{})
            passed={c['criterion'] for c in review.get('rubric',[]) if c['status'] in ('passed','warning')}
            required=criteria.get(finding.get('code'))
            if finding.get('severity')=='review' and required and set(required)<=passed:
                resolved.append({**finding,'resolution':'Confirmed by paired visual QA and final ordered QA.',
                                 'candidate_sha256':digest,'review_criteria':list(required)})
            else: pending.append(finding)
        if resolved:
            add_check(record,name,{**result,'findings':pending,'status':'needs_review' if pending else 'passed',
                                   'resolved_advisories':result.get('resolved_advisories',[])+resolved})


@activity.operation('formatter','format_deck')
def build(sess, mode='preserve', repair_passes=1):
    gid = uuid.uuid4().hex
    directory = Path(sess.dir, 'generations', gid)
    directory.mkdir(parents=True)
    candidate = directory / 'candidate.pptx'
    record = {'schema_version': 1, 'generation_id': gid, 'source_sha256': sha256(sess.source_path),
              'candidate_sha256': None, 'template_sha256': sha256(templates.path()),
              'template_id':getattr(sess,'template_id','stevens'), 'revision_version': sess.revision_version, 'policy_version': POLICY_VERSION,
              'state': 'checking', 'checks': {}, 'findings': [], 'human_decisions': [],
              'source_to_output_slides': {}, 'directory': str(directory), 'candidate': str(candidate),
              'optional_ai': {}, 'report': None, 'mode':mode,'ai_pipeline':None,'progress':{'stage':'preserving'}}
    sess.generation = record
    sess.history[gid] = record
    sess.generated = False
    sess.generation_mode = mode
    try:
        from .ai import providers
        # Reserve for the required added closing as well as all source pages.
        providers.reserve_output_qa(sess, len(__import__('pptx').Presentation(sess.source_path).slides)+1, redesign=mode=='ai')
        if getattr(sess,'pdf_import',None):
            receipt=sess.pdf_import
            if sha256(sess.source_pdf)!=receipt['source_pdf_sha256'] or sha256(sess.source_path)!=receipt['source_pptx_sha256']:
                raise ValueError('PDF import changed; upload the original PDF again.')
            record['pdf_import']=receipt
            add_check(record,'pdf_import',{'status':'passed','findings':[]})
        cover_decisions = {}
        if mode == 'preserve':
            from .ai import cover_preparation
            if cover_preparation.needed(sess):
                def cover_progress(**value):
                    activity.emit('pipeline', value.get('stage', 'progress'), 'progress', sess)
                    record['progress'] = value
                    save(record)
                with activity.stage('formatter', 'prepare_cover_artwork', sess):
                    cover_decisions, details = cover_preparation.run(sess, directory, cover_progress)
                record['optional_ai']['cover_preparation'] = details
                if details['status'] != 'completed':
                    add_check(record, 'source_artwork_preparation', {'status': 'needs_review', 'findings': [{
                        'code': 'SOURCE_ARTWORK_REVIEW_INCOMPLETE', 'severity': 'review', 'output_slide': 0,
                        'message': details.get('message', 'Cover artwork needs review; no uncertain elements were removed.')}]})
        with activity.stage('formatter','compose_slides',sess):
            report = grounded.build_deck(sess.source_path, str(candidate), revisions=sess.revisions,
                                        source_decisions=cover_decisions,require_closing=True)
        ai_checks={}
        if mode=='ai':
            from .ai import pipeline
            def progress(**value):
                activity.emit('pipeline',value.get('stage','progress'),'progress',sess)
                record['progress']=value
                save(record)
            report,ai_checks,details=pipeline.execute(sess,candidate,report,directory,repair_passes,progress)
            record['ai_pipeline']=details
            # Early AI exits retain the independently verified baseline render.
            render_result=ai_checks.get('render_verification',{})
            if render_result.get('pages') and not (directory/'render').exists():
                import shutil
                source_render=Path(render_result['pages'][0]['png']).parent
                shutil.copytree(source_render,directory/'render')
        record['report'] = report
        record['candidate_sha256'] = sha256(candidate)
        record['source_to_output_slides'] = report['source_to_output_slides']
        sess.output_path = str(candidate)
        sess.build_report = report
        add_check(record, 'plan_coverage', report['plan_coverage'])
        checks = [('artifact_coverage', lambda: artifact_coverage.audit(sess.source_path, candidate, report)),
                  ('structural_formatting', lambda: structural(candidate)),
                  ('render_verification', lambda: render_verify.check(candidate, directory / 'render'))]
        for name, check in checks:
            try:
                with activity.stage('verifier',name,sess):
                    add_check(record, name, ai_checks[name] if name in ai_checks else check())
            except Exception as exc:
                add_check(record, name, {'status': 'error', 'findings': [{'code': 'VERIFIER_ERROR',
                    'message': f'{name} could not complete: {type(exc).__name__}: {exc}', 'severity': 'blocking'}]})
        for name in ('ai_redesign','ai_visual_review'):
            if name in ai_checks:add_check(record,name,ai_checks[name])
        from .ai import output_qa
        evidence = {'source_slides': [{'ordinal': i+1, 'text':'\n'.join(s.text for s in slide.shapes if s.has_text_frame),
                    'tables':[[[c.text for c in row.cells] for row in s.table.rows] for s in slide.shapes if s.has_table],
                    'charts':[{'series':[{'name':series.name,'values':list(series.values)} for series in s.chart.series]} for s in slide.shapes if s.has_chart],
                    'notes':slide.notes_slide.notes_text_frame.text if slide.has_notes_slide else ''}
                    for i, slide in enumerate(__import__('pptx').Presentation(sess.source_path).slides)],
                    'source_to_output_slides':record['source_to_output_slides']}
        redesign_completed=mode!='ai' or ai_checks.get('ai_redesign',{}).get('status') in ('passed','needs_review')
        diagnostic_reviewed=ai_checks.get('ai_visual_review',{}).get('status') in ('passed','needs_review','failed')
        # QA is independent of planner/per-slide-review success. Its own prepare
        # step checks candidate identity and complete ordered render coverage.
        with activity.stage('reviewer','ordered_output_review',sess):
            for name, result in output_qa.run(sess, record, evidence).items(): add_check(record, name, result)
        if mode=='ai' and (redesign_completed or diagnostic_reviewed):
            # The request's legacy repair_passes controls the initial planner only.
            # Mandatory QA repair cannot be disabled or waived by that setting.
            repair_from_output_qa(sess,record,evidence,None,progress)
            sess.output_path=record['candidate']; sess.build_report=record['report']
    except CoverageError as exc:
        add_check(record, 'plan_coverage', exc.report)
    except Exception as exc:
        add_check(record, 'plan_coverage', {'status': 'error', 'findings': [{'code': 'BUILD_ERROR',
            'severity': 'blocking', 'message': f'Build failed: {type(exc).__name__}: {exc}'}]})
    resolve_visual_advisories(record)
    settle(record)
    record['usage']={'upload_requests':sess.calls,'upload_tokens':sess.tokens,'token_limit':providers.token_limit(sess)}
    record['progress']={'stage':'finished'}
    record['processing_complete']=True
    sess.generated = download_allowed(record)
    save(record)
    return record


def structural(candidate):
    from .ai.pipeline import structural as verified_structure
    return verified_structure(candidate)


def repair_fingerprint(path):
    """Ignore ZIP timestamps and subpixel coordinate roundoff, not actual edits."""
    from zipfile import ZipFile
    from lxml import etree
    digest=hashlib.sha256()
    with ZipFile(path) as archive:
        for name in sorted(archive.namelist()):
            if name=='docProps/core.xml': continue
            data=archive.read(name)
            if name.startswith('ppt/') and name.endswith('.xml'):
                root=etree.fromstring(data,parser=etree.XMLParser(resolve_entities=False,no_network=True))
                # Planner inches round to six decimals; one EMU is not a repair.
                for node in root.iter():
                    if not isinstance(node.tag,str): continue
                    if etree.QName(node).localname in ('off','ext','chOff','chExt'):
                        for key in ('x','y','cx','cy'):
                            if key in node.attrib: node.set(key,str(round(int(node.get(key))/1000)))
                data=etree.tostring(root,method='c14n')
            digest.update(name.encode());digest.update(data)
    return digest.hexdigest()


def repair_from_output_qa(sess,record,evidence,limit,progress):
    """Final QA -> affected slides only -> native edits -> ALL gates and ordered QA.

    Retain the previous candidate unless QA improves without technical regression.
    Failed/incomplete repairs remain recorded and can never authorize a download.
    """
    from copy import deepcopy
    import shutil
    from .ai import pipeline, output_qa
    names=QA_REQUIRED
    def structural_blockers(checks):
        return [f for f in checks.get('structural_formatting',{}).get('findings',[]) if f.get('severity')=='blocking']
    def qa_score(checks):
        fs=[f for n in names for f in checks.get(n,{}).get('findings',[]) if f.get('severity')!='warning']+structural_blockers(checks)
        return (sum(checks.get(n,{}).get('status') in ('error','not_run') for n in names),
                sum(f.get('severity')=='blocking' for f in fs),len(fs),
                sum(checks.get(n,{}).get('status')!='passed' for n in names))
    calls_used=len((record.get('ai_pipeline') or {}).get('calls',[]))
    attempt=-1
    rejected_feedback=[]
    rejected_repairs=0
    while limit is None or attempt+1 < limit:
        attempt+=1
        if qa_passed(record) and not structural_blockers(record['checks']): break
        if any(record['checks'].get(n,{}).get('status') in ('error','not_run',None) for n in names):
            record['repair_stop_reason']='Mandatory QA could not complete. Review the retained candidate and its findings.'
            break
        feedback=[]
        for name in names:
            for finding in record['checks'][name].get('findings',[]):
                if finding.get('severity')=='warning': continue
                affected=finding.get('affected_slides',[finding['output_slide']] if 'output_slide' in finding else [])
                feedback.extend({**finding,'output_slide':i,'from_check':name} for i in sorted(set(affected)))
        feedback.extend({**f,'from_check':'structural_formatting'} for f in structural_blockers(record['checks']) if 'output_slide' in f)
        feedback.extend(deepcopy(rejected_feedback))
        if not feedback:
            record['repair_stop_reason']='QA did not pass and supplied no slide-specific repair evidence. Review the retained candidate and its findings.'
            break
        sess.ensure_active()
        progress(stage='repairing_output_qa',attempt=attempt+1,affected_slides=sorted({f['output_slide'] for f in feedback}))
        work=Path(record['directory'])/f'output-qa-repair-{attempt+1}'; work.mkdir()
        candidate=work/'candidate.pptx'; shutil.copyfile(record['candidate'],candidate)
        history={'attempt':attempt+1,'incoming_findings':deepcopy(feedback),
                 'targets':sorted({f['output_slide'] for f in feedback}),
                 'before_sha256':record['candidate_sha256'],'accepted':False}
        record.setdefault('output_qa_repairs',[]).append(history)
        report,checks,details=pipeline.execute(sess,candidate,record['report'],work/'pipeline',
            repair_passes=0,progress=progress,initial_feedback=feedback,calls_used=calls_used,
            prior_review={'check':record['checks'].get('ai_visual_review',{}),
                          'reviews':record['ai_pipeline'].get('final_reviews',[])})
        calls_used+=len(details['calls']); history['ai_pipeline']=details
        # Preserve total usage and the original attempt ledger for the UI.
        record['ai_pipeline']['calls'].extend(details['calls'])
        record['ai_pipeline']['completed_calls']=calls_used
        history['candidate_sha256']=sha256(candidate)
        if checks.get('ai_redesign',{}).get('status')!='passed' or checks.get('ai_visual_review',{}).get('status')=='error':
            history['reason']='Redesigner or per-slide review did not complete; previous candidate retained.'
            record['repair_stop_reason']=history['reason']+' Review the retained candidate and its findings.'
            break
        if repair_fingerprint(candidate)==repair_fingerprint(record['candidate']):
            rejected=[a for a in details.get('attempts',[]) if not a.get('accepted') and a.get('changed_objects',0)>0 and a.get('reviews')]
            if rejected and rejected_repairs<2:
                rejected_repairs+=1
                rejected_feedback=[{**f,'output_slide':review['output_slide'],
                    'from_check':'rejected_repair','message':'Avoid this defect from the rejected repair: '+f['message']}
                    for review in rejected[-1]['reviews'] for f in review.get('findings',[])]
                history['reason']='Rendered repair introduced a regression; previous candidate retained and rejection feedback sent for another attempt.'
                save(record)
                continue
            history['reason']=('Repeated rendered repairs introduced regressions; previous candidate retained.' if rejected
                               else 'The proposed repair made no substantive change; previous candidate retained.')
            record['repair_stop_reason']=history['reason']+' Review the retained candidate and its findings.'
            break
        proposal=deepcopy(record)
        proposal.update(candidate=str(candidate),candidate_sha256=sha256(candidate),report=report,human_decisions=[])
        proposal['repair_acceptance_checks']=deepcopy(feedback)
        for name,result in checks.items(): add_check(proposal,name,result)
        # Always inspect every final screenshot in order after the targeted edit.
        for name,result in output_qa.run(sess,proposal,evidence).items(): add_check(proposal,name,result)
        history['checks']=deepcopy(proposal['checks'])
        history['output_qa']=proposal.get('output_qa')
        before=qa_score(record['checks']); after=qa_score(proposal['checks'])
        technical=lambda r:sum(c['status']=='error' for n,c in r['checks'].items() if n not in names)+sum(
            f.get('severity')=='blocking' for f in r['findings'] if f['check'] not in names)
        def blocker_scopes(value):
            return {(f.get('criterion',f.get('code')),slide) for f in value['findings'] if f.get('severity')=='blocking'
                    for slide in f.get('affected_slides',[f.get('output_slide')])}
        changed=repair_fingerprint(candidate)!=repair_fingerprint(record['candidate'])
        accept=(changed and after[0]==0 and after<before and technical(proposal)<=technical(record)
                and blocker_scopes(proposal)<=blocker_scopes(record))
        history.update(accepted=accept,before_score=before,after_score=after)
        if not accept:
            history['reason']=('The proposed repair made no substantive change; previous candidate retained.' if not changed
                               else 'Final QA did not improve without regression; previous candidate retained.')
            record['repair_stop_reason']=history['reason']+' Review the retained candidate and its findings.'
            break
        # Promote the exact verified bytes, and preserve stable preview URLs.
        shutil.copyfile(candidate,record['candidate'])
        render=Path(record['directory'])/'render'
        shutil.copytree(work/'pipeline'/'render',render,dirs_exist_ok=True)
        for page in proposal['checks']['render_verification'].get('pages',[]):
            page['png']=str(render/f"slide-{page['output_slide']}.png")
        for item in proposal.get('output_manifest',[]): item['image']=str(render/f"slide-{item['ordinal']-1}.png")
        if proposal.get('output_manifest'):
            proposal['output_manifest_sha256']=hashlib.sha256(json.dumps(proposal['output_manifest'],sort_keys=True).encode()).hexdigest()
        for key in ('candidate_sha256','report','checks','findings','human_decisions','output_manifest','output_manifest_sha256','output_qa'):
            if key in proposal: record[key]=proposal[key]
        record['ai_pipeline']['changed_objects']+=details.get('changed_objects',0)
        record['ai_pipeline']['candidate_sha256']=record['candidate_sha256']
        record['ai_pipeline']['status']=details['status']
        record['ai_pipeline']['final_reviews']=details.get('final_reviews',[])
        record['ai_pipeline']['element_roles'].extend(details.get('element_roles',[]))
        rejected_feedback=[];rejected_repairs=0
        save(record)


def verify_identity(sess, record, ready=True):
    sess.ensure_active()
    if not record or (ready and not download_allowed(record)):
        raise ValueError('GENERATION_NOT_READY')
    if record['revision_version'] != sess.revision_version:
        raise ValueError('STALE_REVISION')
    if record['policy_version'] != POLICY_VERSION or record['template_sha256'] != sha256(templates.path(record.get('template_id','stevens'))) or record.get('template_id','stevens') != getattr(sess,'template_id','stevens'):
        raise ValueError('STALE_POLICY_OR_TEMPLATE')
    if record['source_sha256'] != sha256(sess.source_path):
        raise ValueError('SOURCE_CHANGED')
    if record.get('pdf_import') and sha256(sess.source_pdf)!=record['pdf_import']['source_pdf_sha256']:
        raise ValueError('SOURCE_PDF_CHANGED')
    if not Path(record['candidate']).is_file() or sha256(record['candidate']) != record['candidate_sha256']:
        raise ValueError('ARTIFACT_CHANGED')
    if record.get('mode') == 'author':
        from .authoring.service import hash_json
        if record.get('outline_hash') != sess.creation['approved_hash'] or record.get('content_hash') != hash_json(sess.creation['deck']):
            raise ValueError('AUTHORED_CONTENT_CHANGED')
    if ready:
        settle(record)
        if not download_allowed(record):
            raise ValueError('PROCESSING_NOT_COMPLETE')
        for item in record.get('output_manifest', []):
            if not Path(item['image']).is_file() or sha256(item['image']) != item['sha256']:
                raise ValueError('RENDERED_ARTIFACT_CHANGED')
            original=item.get('original')
            if original and (not Path(original['image']).is_file() or sha256(original['image'])!=original['sha256']):
                raise ValueError('ORIGINAL_RENDER_CHANGED')


def decide(sess, decision):
    record = sess.generation
    verify_identity(sess, record, ready=False)
    if record['generation_id'] != decision.generation_id or record['candidate_sha256'] != decision.candidate_sha256:
        raise ValueError('STALE_DECISION')
    if decision.output_slide is not None:
        if decision.output_slide >= (record.get('report') or {}).get('slide_count', 0):
            raise ValueError('SLIDE_NOT_FOUND')
        ids = [f['id'] for f in record['findings']
               if decision.output_slide in finding_slides(record, f) and can_approve(record, f)]
        # Include hidden reviewable suggestions, leaving system failures open.
        if decision.finding_ids and set(decision.finding_ids) != set(ids):
            raise ValueError('SLIDE_FINDINGS_CHANGED')
        decision = decision.model_copy(update={'finding_ids': ids})
    reviewable = {f['id'] for f in record['findings'] if can_approve(record,f)}
    if not decision.rationale.strip() or not decision.finding_ids or not set(decision.finding_ids) <= reviewable:
        raise ValueError('FINDING_CANNOT_BE_APPROVED')
    record['human_decisions'].append({**decision.model_dump(), 'decided_at': datetime.now(timezone.utc).isoformat()})
    settle(record)
    sess.generated = download_allowed(record)
    save(record)
    return record


def public(record):
    if not record:
        return None
    keys = ('schema_version', 'generation_id', 'source_sha256', 'candidate_sha256', 'revision_version',
            'policy_version', 'state', 'human_decisions', 'source_to_output_slides', 'optional_ai')
    value = {k: record[k] for k in keys}
    value['mode']=record.get('mode','preserve')
    value['progress']=record.get('progress',{})
    value['usage']=record.get('usage',{})
    value['pdf_available']=bool(record.get('pdf_export'))
    value['download_allowed']=download_allowed(record)
    value['processing_complete']=bool(record.get('processing_complete'))
    imported = record.get('pdf_import', {}).get('page_evidence', [])
    value['preserved_image_regions'] = sum(p.get('page_image_regions', 0) + p.get('source_font_regions', 0) +
        (p.get('rasterized_text_lines', 0) if not p.get('source_font_regions') else 0) for p in imported)
    ai=record.get('ai_pipeline')
    value['ai_pipeline']={k:v for k,v in ai.items() if k not in ('attempts','final_reviews')} if ai else None
    if ai:
        value['ai_pipeline']['attempts']=[{k:v for k,v in a.items() if k not in ('plans','reviews')} for a in ai['attempts']]
        value['ai_pipeline']['failure_message']=' '.join(f.get('message','') for f in record['checks'].get('ai_redesign',{}).get('findings',[])) if record['checks'].get('ai_redesign',{}).get('status')=='error' else None
    value['checks'] = {k: {'status': v['status']} for k,v in record['checks'].items()}
    qa=record.get('output_qa',{})
    confirmations=qa.get('confirmations',[])
    confirmation=confirmations[-1] if confirmations else {}
    value['qa_execution']={'requests':sum(c.get('request_attempts',1) for c in record.get('output_qa_calls',[])),
        'redesign_reviewed_slides':len({r['output_slide'] for r in (ai or {}).get('final_reviews',[])}),
        'redesign_review_status':record.get('checks',{}).get('ai_visual_review',{}).get('status'),
        'reviewed_slides':len({i for b in qa.get('batches',[]) for i in b['response']['reviewed']}),
        'total_slides':(record.get('report') or {}).get('slide_count',0),
        'complete':bool(qa.get('synthesis')),
        'confirmation_cases':len(confirmation.get('cases',[])),
        'refuted_findings':len(confirmation.get('removed_finding_indices',[])),
        'confirmation_incomplete':bool(confirmation and confirmation.get('status')!='completed'),
        'error':' '.join(f.get('message','') for f in record['checks'].get('output_qa_coverage',{}).get('findings',[]) if f.get('code') in ('OUTPUT_QA_INCOMPLETE','OUTPUT_QA_NO_RENDER'))}
    value['findings'] = [{**{k:v for k,v in f.items() if k not in ('expected','actual','evidence')},
                          'can_approve':can_approve(record,f),'priority':finding_priority(f)} for f in record['findings']]
    value['repair_stop_reason']=record.get('repair_stop_reason')
    value['corrections'] = (record.get('report') or {}).get('corrections', [])
    value['built_slides'] = (record.get('report') or {}).get('slide_count', 0)
    value['added_slides'] = (record.get('report') or {}).get('added_slides', [])
    value['source_decisions']={key:{'action':choice['action'],'reason':choice['reason'],
        'removed_artwork':len(choice.get('remove_ids',[])),
        'extracted_logos':len(choice.get('logo_extractions',[]))} for key,choice in (record.get('report') or {}).get('source_decisions',{}).items()}
    value['output_qa_repairs']=[{k:v for k,v in attempt.items() if k in ('attempt','targets','accepted','reason','before_score','after_score')}
                                for attempt in record.get('output_qa_repairs',[])]
    return value
