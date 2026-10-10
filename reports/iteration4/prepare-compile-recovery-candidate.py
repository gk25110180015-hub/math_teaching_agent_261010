"""Build a narrow staged pipeline diff; production source stays untouched."""
from pathlib import Path
import difflib
import hashlib
import json

root = Path(__file__).resolve().parents[2]
folder = Path(__file__).resolve().parent / '待合并'
path = root / 'src/math_agent/pipeline.py'
original = path.read_text(encoding='utf-8')
candidate = original


def replace_once(before, after):
    global candidate
    assert candidate.count(before) == 1, before
    candidate = candidate.replace(before, after, 1)


replace_once('            attempt=0\n            while True:\n',
             "            attempt=0\n            compile_history=[]\n            while True:\n                layout_repair=bool(recovery.state.get('pending_compile_layout'))\n")
replace_once('                if not blocking:\n                    break\n', '''                if not blocking:
                    from .compile_recovery import compile_section_attempt, persist_compile_doubt
                    compiled_attempt=compile_section_attempt(self,spec,generated,completed,plan,draft,attempt,references)
                    source=compiled_attempt['source']
                    compile_result=compiled_attempt['compile']
                    reference_check=compiled_attempt['references']
                    compile_history.append(compiled_attempt['evidence'])
                    report['compile']=compile_result
                    report['references']=reference_check
                    report['compile_attempts']=copy.deepcopy(compile_history)
                    if not compiled_attempt['repair_issues']:
                        if recovery.state.pop('pending_compile_layout',None) is not None:
                            recovery.save()
                        break
                    blocking=persist_compile_doubt(recovery,compiled_attempt,review_identity,report)
                    report['issues']+=compiled_attempt['repair_issues']
                    layout_repair=True
                    write_json(draft/f'compile-review-{attempt}.json',report)
''')
replace_once("                label_missing=any(i.get('rule_id')=='PLANNED_LABEL_MISSING' for i in blocking)\n",
             "                layout_repair=layout_repair or any(i.get('rule_id')=='OVERFULL_BOX' for i in blocking)\n                label_missing=any(i.get('rule_id')=='PLANNED_LABEL_MISSING' for i in blocking)\n")
replace_once("                    if normalization['status']!='PASS':\n", '''                    if layout_repair:
                        from .compile_recovery import reject_layout_suppression
                        reject_layout_suppression(before,generated,target_ids)
                    if normalization['status']!='PASS':
''')
replace_once('''            source = draft/'source'
            source.mkdir()
            tex = render_lecture(plan['title'],completed+[(spec,generated)],plan)
            (source/'lecture.tex').write_bytes(tex.encode('utf-8'))
            self.stage('LOCAL_REVIEW','compile.section.'+sid)
            compile_result = self.compile(source,'lecture.tex',draft/'build')
            write_json(draft/'compile.json',compile_result)
            reference_check = local_reference_gate(compile_result, references['pending_labels'])
            if reference_check['status']=='FAIL':
                self.assert_compile(compile_result)
''', '')
(folder / 'pipeline-compile-recovery.py').write_text(candidate, encoding='utf-8')
patch = ''.join(difflib.unified_diff(original.splitlines(keepends=True), candidate.splitlines(keepends=True),
    fromfile='a/src/math_agent/pipeline.py', tofile='b/src/math_agent/pipeline.py'))
helper = (folder / 'compile_recovery.py').read_text(encoding='utf-8')
patch += ''.join(difflib.unified_diff([], helper.splitlines(keepends=True),
    fromfile='/dev/null', tofile='b/src/math_agent/compile_recovery.py'))
(folder / 'compile-recovery.patch').write_text(patch, encoding='utf-8')
(folder / 'compile-recovery-source-hashes.json').write_text(json.dumps({
    'production_modified': False,
    'pipeline_base_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
    'candidate_sha256': hashlib.sha256((folder / 'pipeline-compile-recovery.py').read_bytes()).hexdigest(),
    'helper_sha256': hashlib.sha256((folder / 'compile_recovery.py').read_bytes()).hexdigest(),
}, indent=2), encoding='utf-8')
print('Staged compile recovery prepared; production source unchanged.')
