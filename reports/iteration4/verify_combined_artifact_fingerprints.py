"""Read-only patch/candidate consistency proof; write only this report's metadata."""
from pathlib import Path
import hashlib
import json
import re

folder=Path(__file__).parent
root=folder.parents[1]
names=['cached-teaching-quality-combined.patch','cached-teaching-quality-combined.candidate.py',
       'reviewer_math_v5.candidate.md','reviewer_math_v6.candidate.md','teaching-quality-combined-02.log',
       'teaching-quality-combined-02.xml']
records={}
for name in names:
    path=folder/name;data=path.read_bytes()
    records[name]={'raw_sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data),
                   'modified_timestamp_ns':path.stat().st_mtime_ns}
patch=(folder/names[0]).read_text(encoding='utf-8').splitlines(keepends=True)
file_diffs={};index=0
while index<len(patch):
    if not patch[index].startswith('--- a/'):
        raise ValueError('Unexpected patch record')
    name=patch[index][6:].strip();index+=1
    assert patch[index].startswith('+++ b/');index+=1
    hunks=[]
    while index<len(patch) and not patch[index].startswith('--- a/'):
        header=patch[index];index+=1
        match=re.match(r'@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@',header)
        if not match:raise ValueError('Invalid hunk header')
        body=[]
        while index<len(patch) and not patch[index].startswith(('@@ ','--- a/')):
            body.append(patch[index]);index+=1
        hunks.append((int(match[1]),int(match[2] or 1),int(match[3]),int(match[4] or 1),body))
    file_diffs[name]=hunks

def reverse_patch(after,hunks):
    lines=after.splitlines(keepends=True);output=[];position=0
    for old_start,old_count,new_start,new_count,body in hunks:
        begin=new_start-1
        output.extend(lines[position:begin]);position=begin
        used=restored=0
        for line in body:
            if line[0] in ' +':
                assert lines[position]==line[1:]
                position+=1;used+=1
            if line[0] in ' -':
                output.append(line[1:]);restored+=1
        assert (used,restored)==(new_count,old_count)
    output.extend(lines[position:]);return ''.join(output)

mapping={'src/math_agent/pipeline.py':'cached-teaching-quality-combined.candidate.py',
         'src/math_agent/prompts/reviewer_math.md':'reviewer_math_v5.candidate.md'}
proofs={}
base_hashes=json.loads((folder/'cached-teaching-quality-base.json').read_text(encoding='utf-8'))
for target,candidate in mapping.items():
    restored=reverse_patch((folder/candidate).read_text(encoding='utf-8'),file_diffs[target])
    # Production files were LF at this frozen baseline; test both raw newline
    # encodings without requiring the live source to remain unmodified now.
    options={ending:hashlib.sha256(restored.replace('\n',ending).encode('utf-8')).hexdigest()
             for ending in ('\n','\r\n')}
    expected=base_hashes[target.replace('/','\\')]
    matches=[repr(ending) for ending,value in options.items() if value==expected]
    assert matches, (target,options,expected)
    proofs[target]={'candidate':candidate,'reverse_patch_matches_frozen_base_raw_sha256':expected,
                   'matching_newline_encodings':matches}
result={'status':'PASS','files':records,'patch_candidate_consistency':proofs,
        'explanation':'A520... identifies the .patch; 6cf9... identifies the full .candidate.py loaded for 105 PASS. These are different artifacts, not conflicting hashes of one file.',
        'production_modified':False,'frozen_v5_modified':False,'frozen_v6_modified':False,
        'tests_rerun':False}
(folder/'combined-artifact-verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'status':result['status'],'patch_sha256':records[names[0]]['raw_sha256'],
                  'full_candidate_sha256':records[names[1]]['raw_sha256'],
                  'reverse_patch_matches_both_frozen_sources':True},ensure_ascii=False))
