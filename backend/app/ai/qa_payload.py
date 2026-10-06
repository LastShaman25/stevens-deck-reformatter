"""Lossless sharing of repeated QA metadata, without dropping review evidence."""
from collections import Counter
from copy import deepcopy
import json

from . import providers


SHARED_FIELDS = {'template_contract', 'template_context', 'note_comparison',
                 'excluded_chrome', 'preservation'}
FORMAT = ('Metadata sharing: a field named FIELD_ref stands for the complete '
          'FIELD value in shared_metadata[FIELD_ref]. Resolve these references '
          'before reviewing each slide. Shared definitions apply to every referring '
          'slide, including all template rules, named edges and object IDs. '
          'Copy actual object IDs from the resolved objects in your response, '
          'never the metadata reference names. No evidence is omitted.')


def compact(payload, provider):
    """Keep small requests unchanged; share identical values in large requests.

    Run again on validation corrections, which can add a substantial response.
    The full local manifest/ledger and the caller's payload remain untouched.
    """
    if len(providers.prompt_text(payload, provider)) <= providers.MAX_PROMPT_CHARS * .65:
        return payload
    counts = Counter()
    def signature(key, value):
        return key, json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',', ':'))
    def count(value):
        if isinstance(value,dict):
            for key, child in value.items():
                if key == 'schema': continue
                if key in SHARED_FIELDS:
                    sig = signature(key,child)
                    if len(sig[1]) > 100: counts[sig] += 1
                count(child)
        elif isinstance(value,list):
            for child in value: count(child)
    count(payload)
    definitions, references = {}, {}
    def encode(value):
        if isinstance(value,dict):
            result = {}
            for key, child in value.items():
                sig = signature(key,child) if key in SHARED_FIELDS else None
                if sig and counts[sig] > 1 and key+'_ref' not in value:
                    if sig not in references:
                        reference = f'{key}_{len(definitions)+1}'
                        references[sig] = reference
                        definitions[reference] = deepcopy(child)
                    result[key+'_ref'] = references[sig]
                else:
                    result[key] = deepcopy(child) if key == 'schema' else encode(child)
            return result
        if isinstance(value,list): return [encode(child) for child in value]
        return value
    result = encode(payload)
    if not definitions: return payload
    result['shared_metadata'] = definitions
    result['shared_metadata_format'] = FORMAT
    return result if len(providers.prompt_text(result,provider)) < len(providers.prompt_text(payload,provider)) else payload
