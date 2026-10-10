"""Package actual six-case Beamer sources, then recompile two clean ZIPs.

No model calls, service startup, source mutation, or teacher approval is performed.
Each archive/build is exclusive; failures and prior outputs remain on disk.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import traceback
import uuid
import zipfile

from math_agent.compiler import TexCompiler
from math_agent.parsing import safe_extract_zip
import pypdfium2 as pdfium

PROJECT = Path(__file__).resolve().parents[2]
REPORTS = PROJECT / 'reports' / 'iteration2'
DESTINATION = PROJECT / 'workspace' / 'iteration2-delivery'
ASSETS = {'.tex', '.sty', '.cls', '.bib', '.bst', '.png', '.jpg', '.jpeg', '.pdf', '.eps', '.pgf', '.tikz', '.svg', '.csv', '.dat'}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def json_bytes(data) -> bytes:
    return (json.dumps(data, ensure_ascii=False, indent=2) + '\n').encode('utf-8')


def write_new(path: Path, data) -> None:
    with path.open('xb') as handle:
        handle.write(json_bytes(data))


def file_hashes(root: Path) -> dict:
    return {p.relative_to(root).as_posix(): sha(p.read_bytes()) for p in sorted(root.rglob('*')) if p.is_file()}


def text_digest(path: Path) -> tuple[int, str]:
    document = pdfium.PdfDocument(path)
    texts = []
    try:
        for index in range(len(document)):
            page = document[index]
            text_page = page.get_textpage()
            try:
                texts.append(text_page.get_text_range())
            finally:
                text_page.close()
                page.close()
        return len(document), sha('\f'.join(texts).encode('utf-8'))
    finally:
        document.close()


def link(label: str, path: Path) -> str:
    return f'[{label}](<{path.resolve().as_posix()}>)'


def prepare(case: dict, comparison_path: Path) -> dict:
    case_name = case['dataset_id'] + '-' + case['theme']
    case_root = Path(case['path']).resolve()
    source = case_root / 'source'
    assert source.is_dir() and source.is_relative_to(PROJECT / 'workspace' / 'iteration2-beamer')
    compiled = json.loads((case_root / 'compile.json').read_text(encoding='utf-8'))
    rendered = json.loads((case_root / 'render.json').read_text(encoding='utf-8'))
    entry = rendered['main_file']
    assert entry == 'slides.tex'
    assert compiled['status'] == case['compile_status'] == 'PASS'
    pdf = Path(case['pdf']['pdf_path'])
    assert sha(pdf.read_bytes()) == case['pdf']['pdf_sha256']
    source_before = file_hashes(source)
    members = {}
    for name in source_before:
        path = source / name
        assert not path.is_symlink() and path.resolve().is_relative_to(source)
        assert path.suffix.lower() in ASSETS, f'Unexpected source member: {name}'
        assert not any(part.startswith('.') for part in Path(name).parts)
        content = path.read_bytes()
        assert not re.search(rb'\bsk-[A-Za-z0-9_-]{8,}', content), 'Possible credential in source'
        members[name] = content
    assert entry in members
    readme = f'''# {case_name} 可编辑课件源包

主文件：{entry}。这些文件来自已经编译的 Beamer case/source 目录，不是原讲义或 prepared-input 副本。
在解压目录用 XeLaTeX 连续编译至少两遍：

    xelatex -no-shell-escape -interaction=nonstopmode -halt-on-error {entry}
    xelatex -no-shell-escape -interaction=nonstopmode -halt-on-error {entry}

本机验证环境为 Windows 11 / TeX Live 2024。需要 ctexbeamer、Fandol 与源码所用 TeX 宏包；系统字体和 TeX 发行版不包含在 ZIP 内。FDU 包包含实际主题 sty 和 resources/fudan.pdf；其它工作流字体与风格适配均已包含。无需模型密钥或网络 API。

原始参考资料保持不变。补入书目只从完整原稿复制，provenance 见与 ZIP 并列交付的 compile_manifest.json。原构建全部物理页已渲染；教师数学与逐页视觉审核仍 NOT_RUN，这份源包是待复核草稿。字体替换等 review 提示见清单，不把编译成功当作教学验收。

旁置 FILE_SHA256.json 包含全部 ZIP 成员与旁置编译清单的 SHA-256；它不包含自身哈希。源包及全部成员哈希另记录于工程 delivery 证据。JSON 元数据留在 ZIP 外，ZIP 可按应用原上传规则重新导入。用户资料、FDU 主题与图片只作本机私人交付，未认定公开再分发许可。
'''
    manifest = {
        'schema_version': 1, 'case': case_name, 'main_file': entry,
        'source_directory': str(source), 'source_files': source_before,
        'comparison_report_sha256': sha(comparison_path.read_bytes()),
        'baseline_compile': {key: compiled.get(key) for key in ('status', 'engine', 'passes', 'issues', 'compile_mode', 'isolation')},
        'baseline_pdf': {'path': str(pdf), 'sha256': sha(pdf.read_bytes()), 'physical_pages': case['pdf']['physical_pages']},
        'source_enrichment': case['source_enrichment'], 'fidelity_status': case['fidelity_status'],
        'real_api': 'NOT_RUN_BY_PACKAGING', 'teacher_visual_review': 'NOT_RUN',
        'system_dependencies_included': False,
    }
    members['README.md'] = readme.encode('utf-8')
    members['MAIN_FILE.txt'] = (entry + '\n').encode('utf-8')
    destination = DESTINATION / case_name
    destination.mkdir(parents=True, exist_ok=True)
    manifest_bytes = json_bytes(manifest)
    hashes = {name: sha(content) for name, content in members.items()}
    hashes['compile_manifest.json'] = sha(manifest_bytes)
    for path, contents in ((destination / 'compile_manifest.json', manifest_bytes), (destination / 'FILE_SHA256.json', json_bytes(hashes))):
        if path.exists():
            assert path.read_bytes() == contents
        else:
            with path.open('xb') as handle:
                handle.write(contents)
    bundle = destination / 'source_bundle-v2.zip'
    if not bundle.exists():
        with zipfile.ZipFile(bundle, 'x', compression=zipfile.ZIP_DEFLATED) as archive:
            for name, content in members.items():
                archive.writestr(name, content)
    with zipfile.ZipFile(bundle) as archive:
        assert archive.testzip() is None
        assert set(archive.namelist()) == set(members)
        for name, content in members.items():
            assert archive.read(name) == content
        for name, expected in hashes.items():
            assert sha(archive.read(name) if name in members else (destination / name).read_bytes()) == expected
    assert file_hashes(source) == source_before
    assert sha(pdf.read_bytes()) == case['pdf']['pdf_sha256']
    result = {
        'case': case_name, 'dataset_id': case['dataset_id'], 'theme': case['theme'],
        'source_directory': str(source), 'main_tex': str(source / entry), 'pdf': str(pdf),
        'pdf_sha256': case['pdf']['pdf_sha256'], 'physical_pages': case['pdf']['physical_pages'],
        'bundle': str(bundle), 'bundle_sha256': sha(bundle.read_bytes()),
        'compile_manifest': str(destination / 'compile_manifest.json'),
        'file_hashes': str(destination / 'FILE_SHA256.json'), 'upload_compatible_bundle': True,
        'members': {name: {'sha256': sha(content), 'size': len(content)} for name, content in members.items()},
        'archive_verification': 'PASS', 'case_files_unchanged': True,
        'original_compile': 'PASS', 'source_fidelity': case['fidelity_status'],
        'clean_recompile': 'NOT_RUN', 'teacher_visual_review': 'NOT_RUN',
    }
    verification = destination / 'bundle_verification-v2.json'
    if verification.exists():
        assert json.loads(verification.read_text(encoding='utf-8')) == result
    else:
        write_new(verification, result)
    print(json.dumps({'case': case_name, 'archive_verification': 'PASS', 'member_count': len(members)}, ensure_ascii=True), flush=True)
    return result


def recompile(case: dict, verification_root: Path, index: int) -> dict:
    extracted = verification_root / f's{index}'
    build = verification_root / f'b{index}'
    extracted_members = safe_extract_zip(Path(case['bundle']).read_bytes(), extracted)
    assert set(extracted_members) == set(case['members'])
    before = file_hashes(extracted)
    for name, entry in case['members'].items():
        assert before[name] == entry['sha256']
    result = TexCompiler(timeout=180).compile(extracted, 'slides.tex', build, trusted=True)
    write_new(verification_root / f'compile-{index}.json', result)
    evidence = {
        'case': case['case'], 'status': result['status'], 'source_zip_sha256': case['bundle_sha256'],
        'extracted': str(extracted), 'build': str(build), 'compile': result,
        'extracted_source_unchanged': before == file_hashes(extracted),
        'extraction': 'application safe_extract_zip',
        'teacher_visual_review': 'NOT_RUN', 'real_api': 'NOT_RUN',
        'new_pdf_all_page_rendering': 'NOT_RUN; existing six-case 522-page rendering remains baseline evidence',
    }
    if result['status'] == 'PASS':
        new_pages, new_text_hash = text_digest(Path(result['pdf_path']))
        old_pages, old_text_hash = text_digest(Path(case['pdf']))
        evidence.update(physical_pages=new_pages, original_physical_pages=old_pages,
                        same_all_page_extracted_text=new_text_hash == old_text_hash,
                        extracted_text_sha256=new_text_hash, original_text_sha256=old_text_hash)
        if new_pages != old_pages or new_pages != case['physical_pages'] or new_text_hash != old_text_hash:
            evidence['status'] = 'FAIL_PDF_CONTENT_MISMATCH'
    if not evidence['extracted_source_unchanged']:
        evidence['status'] = 'FAIL_SOURCE_CHANGED'
    write_new(verification_root / f'recompile-{index}.json', evidence)
    print(json.dumps({'case': case['case'], 'clean_recompile': evidence['status'], 'passes': result['passes']}, ensure_ascii=True), flush=True)
    return evidence


def report(rows: list[dict], summary: Path) -> None:
    text = '''# 第二轮课件交付清单

六组均由真实三章讲义转换，使用完整原稿中可追溯的书目补充；原资料与既有 case 文件未覆盖。全部六组原构建的 Windows XeLaTeX 与来源核验已 PASS，共 522 个物理页已渲染，自动几何仍 NEEDS_REVIEW。以下都是待教师复核的草稿。

ZIP 来自各组实际 `case/source`，包含主 TeX、实际主题/字体/风格适配与所需图片，以及 README、MAIN_FILE。编译与来源清单、逐文件 SHA-256 随 ZIP 旁置提供，JSON 不进入 ZIP，保留应用上传兼容性。请优先下载 v2 ZIP；单独主 TeX 可能缺少相邻依赖。所有链接为本机绝对路径。

| 章节 / 模板 | PDF | 主 TeX | 完整源码 ZIP | 清单 / SHA | 页数 | 新目录重编译 |
|---|---|---|---|---|---:|---|
'''
    for row in rows:
        text += f"| {row['case']} | {link('PDF', Path(row['pdf']))} | {link('slides.tex', Path(row['main_tex']))} | {link('source_bundle-v2.zip', Path(row['bundle']))} | {link('compile_manifest', Path(row['compile_manifest']))} / {link('SHA-256', Path(row['file_hashes']))} | {row['physical_pages']} | {row['clean_recompile']} |\n"
    text += '\n所有六份 ZIP 的成员、CRC 与 SHA-256 均已核对；原 source 与已编译 PDF 哈希保持一致。CH01/default 与 CH03/FDU 通过应用实际 safe_extract_zip 解压，在全新目录使用真实 XeLaTeX 重新编译，检查实际页数和全部页面提取文字是否与基线一致。其它四份未再次重编译，其原 case 编译 PASS 与 ZIP 逐文件哈希一致为本次证据边界。复编译未再次渲染全部页面，原六组全页 PNG 已保留。\n\n'
    text += link('交付及重编译机器记录', summary) + '。其中包含每个 ZIP 的哈希、全部成员哈希和独立编译结果/日志路径；失败也原样保留。\n\n'
    text += '首版 ZIP 将 JSON 清单放在包内，曾被应用上传白名单拒绝，尚未进入编译；' + link('首次失败记录', DESTINATION / 'delivery-20260920-015918.json') + ' 已保留。随后首版按已校验成员独立解压的两份重编译通过，但不作为上传兼容性证据。最终 v2 把 JSON 旁置，重新使用应用解压器及实际编译验证；首版 ZIP、两轮旧日志和旧目录全部保留，不覆盖或删除。\n\n'
    text += '相关证据：' + '；'.join([
        link('三章双模板比较', REPORTS / 'beamer_comparison.md'),
        link('完整原稿来源审计', REPORTS / 'source_audit.md'),
        link('界面与书目回归', REPORTS / 'ui_validation.md'),
        link('第二轮验收草稿', REPORTS / 'acceptance_template.md'),
    ]) + '。\n\n'
    text += '教师数学/逐页视觉验收：NOT_RUN。本次打包/复编译的真实 API 调用：0。原生 trusted_local 不是隔离沙箱。FDU 私人主题与图片的公开再分发许可未认定。真实模型生成的讲义产物仍由主任务确认后另行补入，当前清单不将它们记为通过。\n'
    destination = REPORTS / 'DELIVERABLES.md'
    if destination.exists():
        history = REPORTS / ('DELIVERABLES-before-' + datetime.now().strftime('%Y%m%d-%H%M%S') + '.md')
        with history.open('xb') as handle:
            handle.write(destination.read_bytes())
    with destination.open('w', encoding='utf-8', newline='\n') as handle:
        handle.write(text)


def main() -> int:
    stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    comparison_path = REPORTS / 'beamer_comparison.json'
    comparison = json.loads(comparison_path.read_text(encoding='utf-8'))
    DESTINATION.mkdir(parents=True, exist_ok=True)
    verification_root = PROJECT / 'workspace' / 't' / ('d' + uuid.uuid4().hex[:8])
    verification_root.mkdir(parents=True, exist_ok=False)
    summary_path = DESTINATION / f'delivery-{stamp}.json'
    summary = {'created_at': datetime.now(timezone.utc).isoformat(), 'status': 'RUNNING',
               'real_api': 'NOT_RUN', 'teacher_visual_review': 'NOT_RUN', 'cases': [],
               'verification_root': str(verification_root), 'clean_recompiles': []}
    try:
        for case in comparison['cases']:
            summary['cases'].append(prepare(case, comparison_path))
        assert len(summary['cases']) == 6
        for index, case_name in enumerate(('CH01-default', 'CH03-fduclassroom'), start=1):
            case = next(row for row in summary['cases'] if row['case'] == case_name)
            evidence = recompile(case, verification_root, index)
            summary['clean_recompiles'].append(evidence)
            case['clean_recompile'] = evidence['status']
        summary['status'] = 'PASS' if all(row['status'] == 'PASS' for row in summary['clean_recompiles']) else 'FAIL'
    except Exception as error:
        summary['status'] = 'FAIL'
        summary['error'] = str(error)
        summary['traceback'] = traceback.format_exc()
        traceback.print_exc()
    finally:
        write_new(summary_path, summary)
    if len(summary['cases']) == 6:
        report(summary['cases'], summary_path)
    print(json.dumps({'status': summary['status'], 'summary': str(summary_path), 'verification_root': str(verification_root)}, ensure_ascii=True), flush=True)
    return 0 if summary['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
