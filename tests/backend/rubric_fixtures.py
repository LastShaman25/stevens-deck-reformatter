from app.ai.rubric import CRITERIA


def passed_checks(findings=()):
    return [{'criterion':c,'status':('blocking' if any(f['criterion']==c and f['severity']=='blocking' for f in findings)
            else 'review' if any(f['criterion']==c and f['severity']=='review' for f in findings)
            else 'warning' if any(f['criterion']==c for f in findings) else 'passed'),
            'evidence':'Synthetic contract fixture; not a visual assessment.'} for c in CRITERIA]


def role_map(objects):
    return {'slide_purpose':'Synthetic role coverage', 'elements':[{
        'id':o['id'],'role':'unknown','related_ids':[], 'alignment':'uncertain',
        'alignment_reference':'none','confidence':'low','reason':'Synthetic classification.'} for o in objects]}


def source_choice(payload):
    result=role_map(payload['objects'])
    result.update(slide_kind='cover' if payload['source_slide']==0 else 'content',
                  action='redesign',matches_template=False,reason='Synthetic decision.',remove_ids=[])
    text=[o for o in payload['objects'] if o.get('origin')=='slide' and o.get('content')]
    for entry in result['elements']:
        if any(o['id']==entry['id'] for o in text):
            entry['role']='title' if entry['id']==text[0]['id'] else 'subtitle'
    return result


def repair_evidence(**values):
    return {'object_ids':[],'region':'Synthetic content panel','evidence':'Synthetic comparison.',
            'required_correction':'Restore the synthetic source spacing.',
            'acceptance_condition':'Rendered content has the source spacing and no overlap.',**values}


def qa_review(payload, findings=None):
    return {'reviewed':payload['expected'],'summary':'Synthetic contract fixture','findings':findings or [],
            'slide_audits':[] if payload['stage']=='deck_synthesis' else
                [{'ordinal':i,'checks':passed_checks([f for f in findings or [] if i in f['slides']])} for i in payload['expected']]}
