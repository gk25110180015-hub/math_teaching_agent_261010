"""Read-only delivery of explicit, hash-verified lecture checkpoint files."""
import json
import re
from pathlib import Path

from .util import AgentError, canonical, digest, within


def checkpoint_items(store, workspace: Path, run_id: str, include_bytes=False):
    workspace = workspace.resolve()
    build_root = (workspace / 'b' / run_id[:16]).resolve()
    with store.connect() as connection:
        run = store.row(connection, run_id)
        plan = store.current_plan(connection, run)
        rows = connection.execute('SELECT * FROM steps WHERE run_id=? ORDER BY created_at,step_key,input_hash', (run_id,)).fetchall()
    result = []
    for row in rows:
        match = re.fullmatch(r'section\.(S[0-9]+)', row['step_key'])
        if not match:
            continue
        sid = match[1]
        item = {'step_key': row['step_key'], 'section_id': sid, 'status': 'PARTIAL',
                'created_at': row['created_at'], 'checkpoint_hash': row['output_hash'],
                'teacher_review': 'NOT_RUN', 'downloads': [],
                'plan_binding': 'UNKNOWN',
                'plan_binding_notice': '当前计划关联未核验；可能为历史部分结果，不能据此认定当前计划已完成。',
                'notice': '仅为已保存章节的部分结果，全文及教师复核尚未完成。'}
        try:
            checkpoint = json.loads(row['output_json'])
            if digest(checkpoint) != row['output_hash'] or checkpoint['generated']['section_id'] != sid:
                raise ValueError('Checkpoint hash or section identity mismatch')
            if isinstance(checkpoint.get('plan_hash'), str) and type(checkpoint.get('plan_revision')) is int:
                current = plan and checkpoint['plan_hash'] == plan['hash'] and checkpoint['plan_revision'] == plan['revision']
                item.update(plan_binding='CURRENT' if current else 'STALE',
                    plan_binding_notice='记录的计划身份与当前计划一致；仍为待复核部分结果。' if current else '记录属于其他计划版本，仅供查看历史部分结果。',
                    plan_hash=checkpoint['plan_hash'], plan_revision=checkpoint['plan_revision'])
            source = within(workspace, checkpoint['source_key'])
            if (not source.is_relative_to(build_root) or source.name != 'lecture.tex'
                    or source.parent.name != 'source' or not source.parent.parent.name.startswith('s' + sid + '_')):
                raise ValueError('Checkpoint source does not belong to this run and section')
            source_bytes = source.read_bytes()
            if digest(source_bytes) != checkpoint['source_hash']:
                raise ValueError('Checkpoint source hash mismatch')
            candidates = [('source', f'{sid}-partial.tex', 'application/x-tex', source_bytes, checkpoint['source_hash']),
                          ('checkpoint', f'{sid}-checkpoint.json', 'application/json', canonical(checkpoint).encode('utf-8'), row['output_hash'])]
            compiled = checkpoint.get('report', {}).get('compile', {})
            if compiled.get('pdf_path') and compiled.get('pdf_sha256'):
                pdf = Path(compiled['pdf_path']).resolve()
                expected = (source.parent.parent / 'build' / 'lecture.pdf').resolve()
                if pdf != expected or not pdf.is_relative_to(build_root):
                    raise ValueError('Checkpoint PDF is outside its exact recorded section build')
                pdf_bytes = pdf.read_bytes()
                if digest(pdf_bytes) != compiled['pdf_sha256'] or not pdf_bytes.startswith(b'%PDF-'):
                    raise ValueError('Checkpoint PDF hash or signature mismatch')
                candidates.append(('pdf', f'{sid}-partial.pdf', 'application/pdf', pdf_bytes, compiled['pdf_sha256']))
            item['compile_status'] = compiled.get('status', 'NOT_RECORDED')
            for kind, name, media_type, body, expected_hash in candidates:
                token = digest([run_id, row['step_key'], row['input_hash'], row['output_hash'], kind])
                entry = {'id': token, 'kind': kind, 'name': name, 'media_type': media_type,
                         'sha256': expected_hash, 'url': f'/api/runs/{run_id}/partials/{token}'}
                if include_bytes:
                    entry['_body'] = body
                item['downloads'].append(entry)
        except (OSError, ValueError, KeyError, TypeError) as error:
            item.update(status='PARTIAL_UNAVAILABLE', downloads=[],
                        reason='部分章节的来源、哈希或所属任务校验失败，停止下载：' + type(error).__name__)
        result.append(item)
    return result


def download_checkpoint(store, workspace, run_id, token):
    if not re.fullmatch(r'[a-f0-9]{64}', token):
        raise AgentError('PARTIAL_NOT_FOUND', '部分产物不存在', 404)
    for item in checkpoint_items(store, workspace, run_id, include_bytes=True):
        for artifact in item['downloads']:
            if artifact['id'] == token:
                return artifact
    raise AgentError('PARTIAL_NOT_FOUND', '部分产物不存在或来源哈希校验未通过，原记录保留', 404)
