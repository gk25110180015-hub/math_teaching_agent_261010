"""Copy exactly two verified, controlled browser-test examples for local review."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import sqlite3
import zipfile

from math_agent.pdfcheck import probe_pdf


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT / 'workspace/t/3f550a70/r0/w'
DEST = ROOT / 'deliverables'


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def validate_public_bytes(data: bytes, name: str) -> None:
    if re.search(rb'(?i)(?:sk-[a-z0-9_-]{12,}|authorization\s*[:=]\s*bearer\s+[a-z0-9_.-]{8,})', data):
        raise ValueError(f'Credential-like pattern in {name}; contents withheld')
    for key, value in os.environ.items():
        if re.search(r'(?:API_KEY|ACCESS_TOKEN|AUTH_TOKEN|PASSWORD|SECRET)', key, re.I) and len(value) >= 8:
            if value.encode('utf-8') in data:
                raise ValueError(f'Present credential environment value found in {name}; contents withheld')


def controlled_file(row: dict) -> tuple[Path, bytes]:
    path = (WORKSPACE / row['storage_key']).resolve()
    if not path.is_relative_to(WORKSPACE.resolve()) or not path.is_file():
        raise ValueError('Artifact escaped controlled workspace or is missing')
    data = path.read_bytes()
    if sha(data) != row['sha256']:
        raise ValueError(f"Artifact hash mismatch: {row['name']}")
    validate_public_bytes(data, row['name'])
    return path, data


def main() -> None:
    database = WORKSPACE / 'agent.db'
    connection = sqlite3.connect(database.as_uri() + '?mode=ro', uri=True)
    connection.row_factory = sqlite3.Row
    manifest = {
        'schema_version': 1,
        'created_at': datetime.now(timezone.utc).isoformat(),
        'source_database_relative_path': database.relative_to(ROOT).as_posix(),
        'purpose': 'Local demonstration artifacts; not formally accepted teaching materials',
        'provider': 'mock',
        'real_model_api': 'NOT_RUN',
        'windows_compilation': 'Actual XeLaTeX compile from controlled browser-test artifacts',
        'teacher_visual_review': 'NOT_RUN',
        'formal_teaching_acceptance': 'NOT_RUN',
        'secret_scan': 'PASS: credential-like patterns and present credential env values checked; no values recorded',
        'examples': [],
    }
    selections = [
        ('lecture.generate', 'default', 'mock-lecture', 'lecture'),
        ('beamer.from_tex', 'fduclassroom', 'fdu-source-demo', 'slides'),
    ]
    for workflow, theme, folder, basename in selections:
        matches = []
        for row in connection.execute(
            "SELECT * FROM runs WHERE workflow_id=? AND status='AWAITING_USER_REVIEW' ORDER BY updated_at DESC", (workflow,)
        ):
            request = json.loads(row['input_json'])
            if request.get('provider') == 'mock' and request.get('theme') == theme:
                matches.append(dict(row))
        if not matches:
            raise ValueError(f'No verified review-ready {workflow}/{theme} demo')
        run = matches[0]
        rows = [dict(a) for a in connection.execute(
            'SELECT * FROM artifacts WHERE run_id=? AND revision=?', (run['id'], run['active_plan_revision'])
        )]
        artifacts = {row['name']: row for row in rows}
        if len(artifacts) != len(rows):
            raise ValueError('Ambiguous same-name artifacts')
        _, build_data = controlled_file(artifacts['build_manifest.json'])
        build = json.loads(build_data)
        if build['compiler']['status'] != 'PASS' or build['compiler']['passes'] < 2 or not build['platform'].startswith('Windows-'):
            raise ValueError('A real stable Windows compile is required')
        if build['provider'] != 'mock':
            raise ValueError('Demo must be explicitly mock')
        _, quality_data = controlled_file(artifacts['quality_report.json'])
        quality = json.loads(quality_data)
        if quality['compile']['status'] != 'PASS' or quality['human_visual_review'] != 'NOT_RUN':
            raise ValueError('Unexpected compile or teacher-review state')
        if any(issue.get('severity') == 'blocking' for issue in quality['issues']):
            raise ValueError('Blocking issues prohibit a successful demo selection')
        chosen = [basename + '.pdf', basename + '.tex', 'source_bundle.zip', 'quality_report.json']
        files = {name: controlled_file(artifacts[name]) for name in chosen}
        if sha(files[basename + '.pdf'][1]) != build['pdf_sha256'] or sha(files['source_bundle.zip'][1]) != build['source_bundle_sha256']:
            raise ValueError('Build manifest hashes do not match registered artifacts')
        zip_members = []
        with zipfile.ZipFile(files['source_bundle.zip'][0]) as archive:
            if archive.testzip() is not None:
                raise ValueError('ZIP CRC verification failed')
            for info in archive.infolist():
                path = PurePosixPath(info.filename)
                if path.is_absolute() or '..' in path.parts or '\\' in info.filename or ':' in info.filename:
                    raise ValueError('Unsafe ZIP member')
                if info.is_dir():
                    continue
                if path.suffix.lower() not in {'.tex','.sty','.cls','.png','.jpg','.jpeg','.pdf','.eps','.pgf','.tikz','.md'}:
                    raise ValueError('Unexpected ZIP file type')
                member_data = archive.read(info)
                validate_public_bytes(member_data, info.filename)
                zip_members.append({'path': info.filename, 'bytes': len(member_data), 'sha256': sha(member_data)})
            for expected in build['files']:
                if sha(archive.read(expected['path'])) != expected['sha256']:
                    raise ValueError('Source member does not match original build manifest')
            if archive.read(basename + '.tex') != files[basename + '.tex'][1]:
                raise ValueError('Standalone main TeX differs from source bundle')
        destination = DEST / folder
        destination.mkdir(parents=True, exist_ok=True)
        delivered = []
        for name, (original, data) in files.items():
            target = destination / name
            if target.exists() and target.read_bytes() != data:
                raise ValueError('Refusing to overwrite a different existing deliverable')
            shutil.copyfile(original, target)
            actual_hash = sha(target.read_bytes())
            if actual_hash != artifacts[name]['sha256']:
                raise ValueError('Copy hash mismatch')
            delivered.append({
                'path': target.relative_to(DEST).as_posix(), 'bytes': len(data), 'sha256': actual_hash,
                'source_artifact_id': artifacts[name]['artifact_id'],
                'source_storage_key': artifacts[name]['storage_key'],
                'source_artifact_sha256': artifacts[name]['sha256'], 'copy_hash_check': 'PASS',
            })
        pdf_check = probe_pdf(destination / (basename + '.pdf'))
        if pdf_check['page_count'] < 1:
            raise ValueError('Empty PDF demo')
        manifest['examples'].append({
            'directory': folder, 'source_run_id': run['id'], 'source_revision': run['active_plan_revision'],
            'source_status': run['status'], 'workflow_id': workflow, 'theme': theme,
            'content_origin': 'Deterministic mock lecture' if workflow == 'lecture.generate' else 'Synthetic uploaded TeX fixture; mock planning; actual FDU theme',
            'compiler': build['compiler'], 'platform': build['platform'],
            'original_build_manifest_sha256': sha(build_data),
            'original_build_manifest_artifact_id': artifacts['build_manifest.json']['artifact_id'],
            'quality_statuses': {key: value.get('status') for key, value in quality.items() if isinstance(value,dict) and 'status' in value},
            'pdf_validation': {'status':'PASS', 'method':'pypdfium2 open in credential-free subprocess', **pdf_check},
            'zip_validation': {'status':'PASS', 'crc':'PASS','path_safety':'PASS','original_member_hashes':'PASS','main_tex_matches':'PASS','members':zip_members},
            'files': delivered,
        })
    connection.close()
    (DEST / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    (DEST / 'README.md').write_text('''# 可独立查看的合成示例交付

这两份文件是浏览器端到端测试产生的 **MOCK／合成示例**，内容与规划未调用真实模型 API。PDF 均已在本机 Windows 11 使用真实 XeLaTeX（TeX Live 2024）稳定编译两遍；不是 mock PDF。

| 示例 | PDF | 完整可重编译源包 | 当前状态 |
|---|---|---|---|
| 数列极限讲义（1 页） | [lecture.pdf](mock-lecture/lecture.pdf) | [source_bundle.zip](mock-lecture/source_bundle.zip) | AWAITING_USER_REVIEW |
| 合成 TeX 转 FDU Beamer（5 页，含 overlay） | [slides.pdf](fdu-source-demo/slides.pdf) | [source_bundle.zip](fdu-source-demo/source_bundle.zip) | AWAITING_USER_REVIEW |

每个目录另有主 TeX 和原始 `quality_report.json`。数学审查仍为 NEEDS_REVIEW；FDU 正文区域接壤风险、讲义语义决策落实也保留相应复核状态。**教师人工视觉验收 NOT_RUN，正式教学验收 NOT_RUN**；不能据此认为教材内容、所有页面或真实 API 已通过验收。

`manifest.json` 记录任务／revision、原 artifact ID、源哈希、复制后哈希、真实编译引擎、PDF 页数及 ZIP 成员哈希。已验证两份 PDF 可打开、两份 ZIP 的 CRC 和安全成员路径、源包内容与原编译清单一致。主 TeX 与源包中的对应文件逐字节相同。只复制受控 PDF、主 TeX、ZIP 与质量报告；没有复制数据库或整个工作区。

重编译时先将源 ZIP 解压到新目录，使用已安装的 XeLaTeX 对 `lecture.tex` 或 `slides.tex` 连续编译至少两遍。FDU 示例的主题、字体适配文件和图片依赖在 ZIP 内；仅复制单个 `slides.tex` 不包含这些依赖。无需模型密钥。主题及素材沿用原始参考资源，示例仅用于本地私人审阅，不作公开分发授权说明。

此整理步骤仅核验现有 PDF／ZIP 并复制文件，没有重新调用 API、修改源模块或启动服务。重新编译源包的 Windows 验证另见 `../reports/delivery_validation.md`。
''', encoding='utf-8')
    print(json.dumps({'status':'PASS','manifest':'deliverables/manifest.json','examples':[{'directory':e['directory'],'pages':e['pdf_validation']['page_count'],'copied_files':len(e['files'])} for e in manifest['examples']]}, ensure_ascii=True))


if __name__ == '__main__':
    main()
