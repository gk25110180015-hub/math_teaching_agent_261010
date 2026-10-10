"""Read the actual retained failed compile, and record candidate-only localization."""
from pathlib import Path
import hashlib
import importlib.util
import json
import re

root = Path(__file__).resolve().parents[2]
folder = Path(__file__).resolve().parent / '待合并'
spec = importlib.util.spec_from_file_location('math_agent.compile_recovery', folder / 'compile_recovery.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
base = root / 'workspace/iteration2-live/b/a45be503af594ce8/sS05_79367048d571'
source, compile_report, log = base / 'source/lecture.tex', base / 'compile.json', base / 'build/pass-2.tex.log'
originals = {str(path): path.read_bytes() for path in (source, compile_report, log)}
tex = originals[str(source)].decode('utf-8')
compiled = json.loads(originals[str(compile_report)])
ids = set(re.findall(r'^% UNIT (\S+)', tex, re.M))
mapped = module.locate_overfull_units(tex, compiled['issues'], {item for item in ids if item.startswith('S05.')}, ids)
assert mapped['status'] == 'MAPPED' and mapped['unit_ids'] == ['S05.U22']
item = mapped['issues'][0]
assert item['compiler_message'] in originals[str(log)].decode('utf-8').splitlines()[item['location']['log_line'] - 1]
unchanged = all(Path(path).read_bytes() == content for path, content in originals.items())
assert unchanged
result = {'status': 'PASS', 'kind': 'READ_ONLY_CANDIDATE_LOCALIZATION', 'mapping': mapped,
    'source_files_unchanged': unchanged,
    'evidence': [{'path': path, 'sha256': hashlib.sha256(content).hexdigest()} for path, content in originals.items()],
    'real_api_requests': 0, 'new_compile': 'NOT_RUN', 'teacher_math_review': 'NOT_RUN', 'teacher_visual_review': 'NOT_RUN'}
destination = root / 'reports/iteration4/compile-recovery-real-U22-mapping.json'
destination.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({'report': str(destination), 'status': result['status'], 'unit_ids': mapped['unit_ids']}, ensure_ascii=False))
