"""Artifact identity and release decisions, independent of HTTP/UI state."""
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

POLICY_VERSION = 'owned-authoring-ordered-qa-4'
REQUIRED = ('plan_coverage', 'artifact_coverage', 'structural_formatting', 'render_verification')


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
    finding_ids: list[str]
    rationale: str = Field(min_length=1, max_length=2000)


def settle(record):
    from .ai.output_qa import CHECKS
    required=REQUIRED + CHECKS + ('output_qa_visual',) + (('ai_redesign','ai_visual_review') if record.get('mode')=='ai' else ())
    if record.get('mode') == 'author': required += ('content_grounding',)
    states = [record['checks'].get(k, {}).get('status', 'not_run') for k in required]
    if any(s == 'failed' for s in states):
        record['state'] = 'failed'
    elif any(s in ('error', 'not_run', 'checking') for s in states):
        record['state'] = 'error' if 'error' in states or 'not_run' in states else 'checking'
    else:
        resolved = {fid for d in record['human_decisions'] for fid in d['finding_ids']}
        pending = [f for f in record['findings'] if f['id'] not in resolved]
        if any(f.get('severity') == 'blocking' for f in pending):
            record['state'] = 'failed'
        else:
            record['state'] = 'needs_review' if pending else 'ready'
    return record


def save(record):
    Path(record['directory'], 'generation.json').write_text(json.dumps(record, indent=2), encoding='utf-8')


def add_check(record, name, result):
    record['checks'][name] = result
    for i, item in enumerate(result.get('findings', [])):
        finding = dict(item)
        finding.setdefault('severity', 'blocking' if result['status'] in ('failed', 'error') else 'review')
        finding['check'] = name
        finding['id'] = f'{name}:{i}'
        finding.setdefault('message', finding.get('code', 'Verification finding').replace('_', ' ').capitalize())
        record['findings'].append(finding)


def build(sess, mode='preserve', repair_passes=1):
    gid = uuid.uuid4().hex
    directory = Path(sess.dir, 'generations', gid)
    directory.mkdir(parents=True)
    candidate = directory / 'candidate.pptx'
    record = {'schema_version': 1, 'generation_id': gid, 'source_sha256': sha256(sess.source_path),
              'candidate_sha256': None, 'template_sha256': sha256(grounded.TEMPLATE_PATH),
              'revision_version': sess.revision_version, 'policy_version': POLICY_VERSION,
              'state': 'checking', 'checks': {}, 'findings': [], 'human_decisions': [],
              'source_to_output_slides': {}, 'directory': str(directory), 'candidate': str(candidate),
              'optional_ai': {}, 'report': None, 'mode':mode,'ai_pipeline':None,'progress':{'stage':'preserving'}}
    sess.generation = record
    sess.history[gid] = record
    sess.generated = False
    sess.generation_mode = mode
    try:
        report = grounded.build_deck(sess.source_path, str(candidate), revisions=sess.revisions)
        ai_checks={}
        if mode=='ai':
            from .ai import pipeline
            def progress(**value):
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
        for name, result in output_qa.run(sess, record, evidence).items(): add_check(record, name, result)
    except CoverageError as exc:
        add_check(record, 'plan_coverage', exc.report)
    except Exception as exc:
        add_check(record, 'plan_coverage', {'status': 'error', 'findings': [{'code': 'BUILD_ERROR',
            'severity': 'blocking', 'message': f'Build failed: {type(exc).__name__}: {exc}'}]})
    settle(record)
    record['progress']={'stage':'finished'}
    sess.generated = record['state'] == 'ready'
    save(record)
    return record


def structural(candidate):
    result = brand_lint.lint(candidate)
    findings = [{'code': f['type'].upper(), 'message': f['note'], 'output_slide': s['index'],
                 'severity': 'blocking' if f['sev'] == 'fail' else 'review'}
                for s in result['slides'] for f in s['issues']]
    return {'status': 'failed' if result['total_fail'] else 'needs_review' if findings else 'passed',
            'findings': findings, 'details': result}


def verify_identity(sess, record, ready=True):
    sess.ensure_active()
    if not record or (ready and record['state'] != 'ready'):
        raise ValueError('GENERATION_NOT_READY')
    if record['revision_version'] != sess.revision_version:
        raise ValueError('STALE_REVISION')
    if record['policy_version'] != POLICY_VERSION or record['template_sha256'] != sha256(grounded.TEMPLATE_PATH):
        raise ValueError('STALE_POLICY_OR_TEMPLATE')
    if record['source_sha256'] != sha256(sess.source_path):
        raise ValueError('SOURCE_CHANGED')
    if not Path(record['candidate']).is_file() or sha256(record['candidate']) != record['candidate_sha256']:
        raise ValueError('ARTIFACT_CHANGED')
    if record.get('mode') == 'author':
        from .authoring.service import hash_json
        if record.get('outline_hash') != sess.creation['approved_hash'] or record.get('content_hash') != hash_json(sess.creation['deck']):
            raise ValueError('AUTHORED_CONTENT_CHANGED')
    if ready:
        from .ai.output_qa import CHECKS
        if any(record['checks'].get(name, {}).get('status') not in ('passed','needs_review') for name in CHECKS):
            raise ValueError('OUTPUT_QA_INCOMPLETE')
        for item in record.get('output_manifest', []):
            if not Path(item['image']).is_file() or sha256(item['image']) != item['sha256']:
                raise ValueError('RENDERED_ARTIFACT_CHANGED')


def decide(sess, decision):
    record = sess.generation
    verify_identity(sess, record, ready=False)
    if record['generation_id'] != decision.generation_id or record['candidate_sha256'] != decision.candidate_sha256:
        raise ValueError('STALE_DECISION')
    reviewable = {f['id'] for f in record['findings'] if f['severity'] == 'review'}
    if not decision.finding_ids or not set(decision.finding_ids) <= reviewable:
        raise ValueError('FINDING_CANNOT_BE_APPROVED')
    record['human_decisions'].append({**decision.model_dump(), 'decided_at': datetime.now(timezone.utc).isoformat()})
    settle(record)
    sess.generated = record['state'] == 'ready'
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
    ai=record.get('ai_pipeline')
    value['ai_pipeline']={k:v for k,v in ai.items() if k not in ('attempts','final_reviews')} if ai else None
    if ai:
        value['ai_pipeline']['attempts']=[{k:v for k,v in a.items() if k not in ('plans','reviews')} for a in ai['attempts']]
    value['checks'] = {k: {'status': v['status']} for k,v in record['checks'].items()}
    value['findings'] = [{k:v for k,v in f.items() if k not in ('expected','actual','evidence')} for f in record['findings']]
    value['corrections'] = (record.get('report') or {}).get('corrections', [])
    value['built_slides'] = (record.get('report') or {}).get('slide_count', 0)
    return value
