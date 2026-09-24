"""Optional preservation-mode visual check through the configured reviewer."""
from pathlib import Path
from pydantic import ValidationError
from . import providers
from .pipeline import VisualReview, REVIEW_SYSTEM


def review_slide_result(png_path):
    if not Path(png_path).is_file():
        return {'status':'invalid_response','findings':[],'message':'A rendered slide is required.'}
    response=providers.generate('reviewer',REVIEW_SYSTEM,
        {'required_objects':[], 'instruction':'Inspect this candidate image. Object IDs are unavailable; use empty object_ids lists. Do not infer missing source content.',
         'schema':VisualReview.model_json_schema()},[('Candidate slide',png_path)],max_tokens=6000)
    result={k:v for k,v in response.items() if k!='data'}
    result['findings']=[]
    if response['status']!='completed':return result
    try:
        value=VisualReview.model_validate(response['data'])
        verdict='failed' if any(f.severity=='blocking' for f in value.findings) else 'needs_review' if value.findings else 'passed'
        if verdict!=value.verdict or any(f.object_ids for f in value.findings):raise ValueError('Invalid review')
        result['findings']=[{'type':f.category,'severity':f.severity,'note':f.message} for f in value.findings]
        return result
    except (ValidationError,ValueError,TypeError,KeyError):
        return {**result,'status':'invalid_response','message':'Optional visual response could not be validated.'}
