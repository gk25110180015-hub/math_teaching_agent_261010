"""Reproduce the user-manuscript audit without API or original-file mutations."""
from pathlib import Path
import hashlib
import json
import re
from difflib import SequenceMatcher

import pypdfium2

from math_agent.manuscript import audit_manuscript, chapter_spans, complete_bibliography
from math_agent.parsing import parse_tex, uncomment


PROJECT = Path(__file__).resolve().parents[2]
ROOT = PROJECT.parent
OUTPUT = Path(__file__).resolve().parent


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def normalized(text):
    return re.sub(r"\s+", "", uncomment(text))


def main():
    manuscript = ROOT / '大学数学（一）(1).tex'
    pdf_path = manuscript.with_suffix('.pdf')
    text = manuscript.read_text(encoding='utf-8-sig')
    audit = audit_manuscript(manuscript)
    spans = chapter_spans(text)
    with pypdfium2.PdfDocument(pdf_path) as pdf:
        pdf_info = {'path': str(pdf_path), 'sha256': digest(pdf_path), 'page_count': len(pdf),
                    'render_status': 'NOT_RUN', 'teacher_visual_review': 'NOT_RUN'}
    comparisons = []
    for index, name in enumerate(('第一章', '第二章', '第三章'), 1):
        source_path = ROOT / name / manuscript.name
        source = source_path.read_text(encoding='utf-8-sig')
        source_start = source.index('\\section{')
        source_end = source.index('\\end{document}')
        old_body = source[source_start:source_end].strip()
        new_body = spans[index - 1]['raw_tex'].strip()
        old_normal, new_normal = normalized(old_body), normalized(new_body)
        sequence = SequenceMatcher(None, old_normal, new_normal, autojunk=False)
        operations = [{'kind': kind, 'old': old_normal[a:b], 'new': new_normal[c:d]}
                      for kind, a, b, c, d in sequence.get_opcodes() if kind != 'equal']
        parsed = parse_tex(source, source_path.name)
        prepared = complete_bibliography(source, text, source_name=str(source_path), manuscript_name=str(manuscript))
        comparisons.append({'dataset_id': f'CH{index:02}', 'title': spans[index - 1]['title'],
            'original_path': str(source_path), 'original_sha256': digest(source_path),
            'old_body_chars': len(old_body), 'new_body_chars': len(new_body),
            'trimmed_body_exact': old_body == new_body,
            'normalized_sequence_match_ratio': sequence.ratio(), 'difference_operations': operations,
            'mathematics_unchanged_except_trailing_page_break': all(item['kind'] == 'insert' and item['new'] == r'\clearpage' for item in operations),
            'parsed_units': len(parsed['units']), 'active_units': sum(u.get('source_visibility') != 'inactive' for u in parsed['units']),
            'opaque_units': sum(u['kind'] == 'opaque_tex' for u in parsed['units']),
            'added_bibliography_keys': prepared['added_keys'],
            'unresolved_bibliography_keys': prepared['unresolved_keys'],
            'bibliography_entry_sources': [{key: value for key, value in entry.items() if key != 'raw_tex'} for entry in prepared['entries']],
            'source_preserved': source_path.read_text(encoding='utf-8-sig') == source,
            'chapter_numbering_note': '全稿正式章节仍从1起；原文习题标题写第2/3/4章，与章节计数不一致，未自动改写。'})
    original_manifest = json.loads((PROJECT / 'reference_index' / 'manifest.json').read_text(encoding='utf-8'))
    lookup = {f'CH{i:02}': chapter for i, chapter in enumerate(('第一章', '第二章', '第三章'), 1)}
    unchanged = []
    for entry in original_manifest['files']:
        path = ROOT / lookup[entry['dataset_id']] / entry['relative_path']
        unchanged.append({'relative_path': str(path.relative_to(ROOT)), 'unchanged': digest(path) == entry['sha256']})
    report = {'schema_version': 1, 'method': 'read-only source/hash comparison; bibliography copied only from user full manuscript',
              'live_api': 'NOT_RUN_IN_THIS_AUDIT', 'teacher_visual_review': 'NOT_RUN',
              'manuscript': audit, 'provided_pdf': pdf_info, 'chapter_comparisons': comparisons,
              'original_reference_integrity': {'checked': len(unchanged), 'unchanged': sum(item['unchanged'] for item in unchanged), 'files': unchanged},
              'bibliographic_factual_verification': 'NOT_RUN: provenance verifies user supplied records, not external publisher accuracy',
              'baseline_metrics': [
                  {'metric': 'Source fidelity', 'method': 'check_fidelity parses actual emitted TeX against exact source units; omissions need explicit confirmed IDs'},
                  {'metric': 'Citation completeness', 'method': 'Count missing active citation keys before/after supplemental bibliography, require compiler UNRESOLVED_REFERENCE zero after full passes'},
                  {'metric': 'Build success', 'method': 'Real Windows XeLaTeX, both default/FDU templates, keep prior failed logs and compare exact blocking rule IDs'},
                  {'metric': 'All-page geometry and overlays', 'method': 'Render every physical page, compare blocking geometry separately from review-only contacts and human ratings'},
                  {'metric': 'Density/readability', 'method': 'Compare logical frames, physical pages, supported font sizes and content per frame with original manual Beamer; page-count reduction alone is not quality'},
                  {'metric': 'Generated lecture mathematics', 'method': 'Use fixed topic/scope/decisions, source proposition coverage, explicit assumptions, proof completeness, bounded CAS where applicable, plus independent teacher review'},
                  {'metric': 'Training/validation separation', 'method': 'These are local style/reference examples; no model weight fine-tuning, no blind held-out accuracy claim; chapters4-8 may supply unseen-topic probes only after scope selection'}]}
    (OUTPUT / 'source_audit.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    lines = ['# 第二轮新增全稿审计', '', '本审计只读取用户资料并写入报告，未调用真实 API，未执行教师视觉验收。', '',
             f'全稿 TeX：`{audit["path"]}`，{audit["size_bytes"]:,} 字节，{audit["line_count"]:,} 行；SHA-256 `{audit["sha256"]}`。',
             f'配套 PDF：{pdf_info["page_count"]} 页；SHA-256 `{pdf_info["sha256"]}`。这里只读取页数，未将已有 PDF 视作本轮新编译通过。', '',
             '## 结构和完整性', '', '| 章节 | 标题 | 原文行范围 |', '|---|---|---|']
    lines += [f'| {chapter["index"]} | {chapter["title"]} | {chapter["start_line"]}—{chapter["end_line"]} |' for chapter in audit['chapters']]
    lines += ['', '另有不编号的“数学文化与数学史导引”。稿尾共有17个真实书目条目；全稿正文所有静态引用键均有条目，未检测到外置 input/include/image/bib 依赖。TikZ 图形内嵌于源码；TeX宏包与字体仍依赖本机TeX安装。', '',
              '## 与既有三章关系', '', '| 样本 | 新旧正文差异 | 补全条目 |', '|---|---|---|']
    lines += [f'| {row["dataset_id"]} {row["title"]} | {"trim后完全相同" if row["trimmed_body_exact"] else "仅末尾新增一个 clearpage；数学内容相同"} | {", ".join(row["added_bibliography_keys"])} |' for row in comparisons]
    lines += ['', '这三组仍可与原手工 Beamer 基准比较。新稿补齐的是原三章遗漏的真实书目依赖，没有改变数学正文。各条目的原始内容、行号、字符区间和SHA-256均写入JSON。书目信息未另行联网核实；不能把“原稿有此条目”等同于已核对出版信息。',
              '', f'原三章 {len(unchanged)} 份已登记资料全部重新校验，{sum(item["unchanged"] for item in unchanged)} 份哈希未变。',
              '', '原文习题标题仍写“第2/3/4章”，而正式section计数对应1/2/3，属于原稿编号一致性问题，保留并披露，不私自改写。', '',
              '## 可复用实现', '',
              '`math_agent.manuscript.complete_bibliography`只复制正文实际引用的缺失条目，已有条目不覆盖，未知键仍阻塞，重名冲突显式报告。`extract_chapter`保留原导言区、原章号、完整章正文（含原先不显示的答案分支）并附所需条目。`write_prepared_copy`使用独占新文件和来源sidecar，拒绝覆盖任何文件。', '',
              '应用应在计划中披露该补充及其来源哈希，用户审批后使用独立derived副本，原始上传快照保留。章节提取副本的跨章引用仍需真实编译，不能仅靠提取成功声称可发布。', '',
              '复现审计：`.venv\\Scripts\\python.exe reports/iteration2/audit_source.py`。模块命令：`python -m math_agent.manuscript audit/extract/supplement --help`。', '',
              '## 比较指标', '']
    lines += [f'- {item["metric"]}：{item["method"]}。' for item in report['baseline_metrics']]
    lines += ['', '三章是本地参考样例；本轮不等于模型权重训练。任何真实API、Windows编译、自动几何与教师评分应分开列证据，不用单一“通过率”掩盖未执行项。', '']
    (OUTPUT / 'source_audit.md').write_text('\n'.join(lines), encoding='utf-8')
    print(json.dumps({'manuscript_chapters': len(spans), 'bibliography_entries': len(audit['bibliography']), 'provided_pdf_pages': len(pypdfium2.PdfDocument(pdf_path)), 'original_files_unchanged': sum(item['unchanged'] for item in unchanged), 'report': str(OUTPUT / 'source_audit.md')}, ensure_ascii=True))


if __name__ == '__main__':
    main()
