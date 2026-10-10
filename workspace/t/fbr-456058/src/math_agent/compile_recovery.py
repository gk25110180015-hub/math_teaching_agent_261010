"""Preserved local compile attempts and narrowly located layout repair hints."""
from __future__ import annotations

import copy
from pathlib import Path
import re

from .crossrefs import local_reference_gate
from .util import AgentError, digest, write_json


def locate_overfull_units(tex: str, issues: list[dict], current_ids: set[str], all_ids: set[str]) -> dict:
    """Map an entire diagnostic range to one known rendered UNIT; never guess."""
    lines = tex.splitlines()
    markers = [(number, match[1]) for number, line in enumerate(lines, 1)
               if (match := re.fullmatch(r'% UNIT (\S+)', line))]
    seen = [unit_id for _, unit_id in markers]
    if set(seen) != all_ids or len(seen) != len(all_ids):
        return {'status': 'UNMAPPED', 'reason': 'missing/duplicate/unknown rendered UNIT markers', 'issues': []}
    structural = [number for number, line in enumerate(lines, 1)
                  if re.match(r'\\(?:section\*?(?:\{|\[)|end\{document\})', line)]
    boundaries = sorted({number for number, _ in markers} | set(structural) | {len(lines) + 1})
    spans = [(number + 1, next(value for value in boundaries if value > number) - 1, unit_id)
             for number, unit_id in markers]
    body = tex.split(r'\begin{document}', 1)[-1]
    external_body_input = bool(re.search(r'\\(?:input|include|subfile|import|verbatiminput|lstinputlisting)(?![A-Za-z])', body))
    mapped = []
    for original in issues:
        if original.get('severity') != 'blocking':
            continue
        location = original.get('location', {})
        filename = location.get('file')
        if original.get('rule_id') != 'OVERFULL_BOX':
            return {'status': 'UNMAPPED', 'reason': 'non-layout blocking compiler issue', 'issues': []}
        if filename and str(filename).replace('\\', '/') not in {'lecture.tex', './lecture.tex'}:
            return {'status': 'UNMAPPED', 'reason': 'diagnostic is not in the rendered main file', 'issues': []}
        if not filename and external_body_input:
            return {'status': 'UNMAPPED', 'reason': 'implicit file is ambiguous because body includes another input', 'issues': []}
        match = re.search(r'\bat lines?\s+(\d+)(?:--(\d+))?\b', original.get('message', ''))
        if not match:
            return {'status': 'UNMAPPED', 'reason': 'diagnostic has no precise source line interval', 'issues': []}
        first, last = int(match[1]), int(match[2] or match[1])
        matches = [unit_id for start, end, unit_id in spans if start <= first <= last <= end]
        if len(matches) != 1 or matches[0] not in current_ids:
            return {'status': 'UNMAPPED', 'reason': 'range crosses a boundary or belongs outside the current section', 'issues': []}
        unit_id = matches[0]
        mapped.append({**copy.deepcopy(original), 'unit_id': unit_id,
            'compiler_message': original['message'],
            'location': {**location, 'unit_id': unit_id, 'source_file': 'lecture.tex',
                         'source_line': first, 'source_end_line': last},
            'message': original['message'] + '；仅修复定位单元的换行/分段/公式组织，保持全部数学条件、结论、题解与标签；不得删除内容、缩小字号、加容差或隐藏溢出。',
            'evidence': {'rendered_source_sha256': digest(tex.encode('utf-8')),
                         'source_excerpt': '\n'.join(lines[first - 1:last])}})
    if not mapped:
        return {'status': 'UNMAPPED', 'reason': 'no located blocking layout issue', 'issues': []}
    return {'status': 'MAPPED', 'issues': mapped,
            'unit_ids': sorted({issue['unit_id'] for issue in mapped}), 'reason': 'all blocking intervals map exactly'}


def compile_section_attempt(pipeline, spec, generated, completed, plan, draft, attempt, references):
    """Compile to a new directory. Retain all failed sources, logs, PDFs and hashes."""
    from .pipeline import render_lecture
    attempt_root = draft if attempt == 0 and not (draft / 'source').exists() else draft / f'compile-attempt-{attempt}'
    source, build = attempt_root / 'source', attempt_root / 'build'
    source.mkdir(parents=True, exist_ok=False)
    tex = render_lecture(plan['title'], completed + [(spec, generated)], plan)
    source_file = source / 'lecture.tex'
    source_file.write_bytes(tex.encode('utf-8'))
    pipeline.stage('LOCAL_REVIEW', 'compile.section.' + spec['id'])
    result = pipeline.compile(source, 'lecture.tex', build)
    compile_file = attempt_root / 'compile.json'
    write_json(compile_file, result)
    reference_result = local_reference_gate(result, references['pending_labels'])
    snapshot = {'attempt': attempt, 'section_id': spec['id'], 'candidate_hash': digest(generated),
                'source_key': source_file.relative_to(pipeline.settings.workspace).as_posix(),
                'source_hash': digest(source_file.read_bytes()), 'compile_status': result.get('status'),
                'compile_key': compile_file.relative_to(pipeline.settings.workspace).as_posix(),
                'compile_hash': digest(compile_file.read_bytes()), 'teacher_visual_review': 'NOT_RUN'}
    pinned = [source_file, compile_file]
    for path in result.get('log_paths', []):
        file = Path(path).resolve()
        if not file.is_relative_to(build.resolve()) or not file.is_file():
            raise AgentError('COMPILE_FAILED', '编译日志路径缺失或越界，保留源码但不能据此自动定位修复。')
        pinned.append(file)
    if result.get('pdf_path'):
        pdf = Path(result['pdf_path']).resolve()
        if not pdf.is_relative_to(build.resolve()) or not pdf.is_file():
            raise AgentError('COMPILE_FAILED', '编译PDF路径缺失或越界，不能采用检查结果。')
        pinned.append(pdf)
    mapping = {'status': 'NOT_NEEDED', 'issues': []}
    if reference_result['status'] == 'FAIL':
        current_ids = {unit['id'] for unit in generated['units']}
        all_ids = current_ids | {unit['id'] for _, section in completed for unit in section['units']}
        mapping = locate_overfull_units(tex, result.get('issues', []), current_ids, all_ids)
        # Match the diagnostic to an immutable actual compiler log before using it as a repair target.
        logs = [Path(path).read_text(encoding='utf-8', errors='replace').splitlines()
                for path in result.get('log_paths', []) if str(path).endswith('.tex.log')]
        for issue in mapping['issues']:
            number = issue.get('location', {}).get('log_line')
            if not isinstance(number, int) or not any(0 < number <= len(log) and issue['compiler_message'] in log[number - 1]
                                                     for log in logs):
                mapping = {'status': 'UNMAPPED', 'reason': 'diagnostic cannot be verified against its actual log line', 'issues': []}
                break
    write_json(attempt_root / 'compile-layout-mapping.json', mapping)
    pinned.append(attempt_root / 'compile-layout-mapping.json')
    snapshot['mapping'] = mapping
    snapshot['dependencies'] = [{'key': file.relative_to(pipeline.settings.workspace).as_posix(),
                                 'hash': digest(file.read_bytes()), 'error_code': 'LOCAL_REPAIR_CACHE_INVALID'} for file in pinned]
    write_json(attempt_root / 'compile-attempt-evidence.json', snapshot)
    if reference_result['status'] == 'FAIL' and mapping['status'] != 'MAPPED':
        # Preserve the strict original failure; an unclear location is never a whole-section repair licence.
        pipeline.assert_compile(result)
        raise AgentError('COMPILE_FAILED', '编译/引用门禁未通过且无法精确定位到当前单元，未扩大修复范围。')
    return {'source': source, 'compile': result, 'references': reference_result,
            'repair_issues': mapping['issues'], 'evidence': snapshot}


def persist_compile_doubt(recovery, outcome, review_identity, report):
    """Bind the actual failed compile to the existing recovery ledger and budget."""
    recovery.state['pending_compile_layout'] = {
        'source_hash': outcome['evidence']['source_hash'],
        'compile_key': outcome['evidence']['compile_key'],
        'issues': copy.deepcopy(outcome['repair_issues']),
    }
    existing = {(item['key'], item['hash']) for item in recovery.state.get('evidence_dependencies', [])}
    for dependency in outcome['evidence']['dependencies']:
        if (dependency['key'], dependency['hash']) not in existing:
            recovery.state['evidence_dependencies'].append(dependency)
    identity = {**review_identity, 'compile_failure_hash': digest(outcome['evidence'])}
    return recovery.record_review(report['issues'] + outcome['repair_issues'], identity, report)


def reject_layout_suppression(before, after, target_ids):
    """A formatting repair cannot introduce global tolerances, scaling or smaller fonts."""
    command = re.compile(r'\\(?:hfuzz|vfuzz|hbadness|vbadness|tolerance|pretolerance|emergencystretch|'
        r'small|tiny|scriptsize|footnotesize|fontsize|scalebox|resizebox|sloppy|enlargethispage|'
        r'newgeometry|geometry|setlength|addtolength|hsize|textwidth)(?![A-Za-z])')
    old = {unit['id']: unit['tex'] for unit in before['units']}
    for unit in after['units']:
        if unit['id'] in target_ids:
            current = command.findall(unit['tex'])
            if current and unit['tex'] != old[unit['id']]:
                raise AgentError('REPAIR_SCOPE_VIOLATION', '排版修复不得引入缩字号、缩放、全局尺寸或容差命令来隐藏溢出。')
