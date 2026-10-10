"""Prepare separate v6 for later evaluation; frozen v5 and fixtures stay unchanged."""
from pathlib import Path
import hashlib
import json

folder = Path(__file__).parent
source = folder/'reviewer_math_v5.candidate.md'
before = source.read_bytes()
text = before.decode('utf-8').replace('版本 5。', '版本 6。', 1)
text = text.rstrip()+'\n\n'+(folder/'reviewer-v6-context-addendum.txt').read_text(encoding='utf-8')
target = folder/'reviewer_math_v6.candidate.md'
target.write_text(text, encoding='utf-8')
assert source.read_bytes() == before
(folder/'reviewer-v6-candidate-metadata.json').write_text(json.dumps({
    'v5_sha256':hashlib.sha256(before).hexdigest(),
    'v6_sha256':hashlib.sha256(target.read_bytes()).hexdigest(),
    'v5_unchanged':True, 'production_prompt_modified':False, 'fixtures_modified':False,
    'live_api_status':'NOT_RUN', 'teacher_review':'NOT_RUN',
    'purpose':'General condition inheritance and severity refinement; not an exception for any fixture or chapter.'
},ensure_ascii=False,indent=2),encoding='utf-8')
print('Separate v6 prepared; frozen v5 unchanged; no API calls.')
