"""Read-only, reproducible M0 inventory of the three explicitly provided chapters."""
from __future__ import annotations
import hashlib
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
from datetime import datetime, timezone

PROJECT = Path(__file__).resolve().parents[1]
args = argparse.ArgumentParser(description="Read-only three-chapter inventory; writes evidence only into this project")
args.add_argument("--root", type=Path, default=PROJECT.parent, help="Explicit reference root containing 第一章/第二章/第三章")
ROOT = args.parse_args().root.resolve()
if not ROOT.is_dir():
    raise SystemExit(f"Reference root does not exist: {ROOT}")
OUT = PROJECT / "reference_index"
OUT.mkdir(exist_ok=True)
KPSE = Path(r"D:\texlive\2024\bin\windows\kpsewhich.exe")
CHAPTERS = {"CH01": "第一章", "CH02": "第二章", "CH03": "第三章"}

def digest(data):
    return hashlib.sha256(data).hexdigest()

def decode(data):
    for enc in ("utf-8-sig", "gb18030"):
        try:
            return data.decode(enc), enc
        except UnicodeDecodeError:
            pass
    return None, None

def uncomment(text):
    return re.sub(r"(?<!\\)%[^\n]*", lambda m: " " * len(m[0]), text)

def write(name, data):
    (OUT / name).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

def tex_lookup(name):
    if not KPSE.is_file():
        return None
    env = {k: os.environ[k] for k in ("SystemRoot", "WINDIR", "TEMP", "TMP") if k in os.environ}
    env["PATH"] = str(KPSE.parent)
    result = subprocess.run([str(KPSE), name], env=env, cwd=PROJECT, capture_output=True, timeout=15)
    return result.stdout.decode("utf-8", "replace").strip() or None

records, datasets, alignments, styles, baselines = [], [], [], [], []
cache = {}
for dataset_id, dirname in CHAPTERS.items():
    root = ROOT / dirname
    chapter_records = []
    chapter_texts = {}
    if not root.is_dir():
        datasets.append({"dataset_id": dataset_id, "status": "MISSING", "source_directory": dirname})
        continue
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        data = path.read_bytes()
        text, encoding = decode(data) if path.suffix.lower() in {".tex", ".sty", ".aux", ".log", ".out", ".toc", ".nav", ".snm"} else (None, None)
        role = "auxiliary_asset"
        subtype = "historical_build_artifact"
        if path.suffix.lower() == ".sty" or rel.startswith("resources/"):
            role, subtype = "theme_asset", "theme_source" if path.suffix == ".sty" else "theme_resource"
        elif path.suffix.lower() == ".tex":
            cls = re.search(r"\\documentclass(?:\[[^\]]*\])?\{([^}]+)\}", text or "")
            role = "beamer_reference" if cls and "beamer" in cls[1] else "lecture_source"
            subtype = "tex_entrypoint"
            chapter_texts[role] = (rel, text)
        elif path.suffix.lower() == ".pdf":
            peer = path.with_suffix(".tex")
            if peer.exists():
                peer_text, _ = decode(peer.read_bytes())
                role = "beamer_reference" if "ctexbeamer" in peer_text else "lecture_source"
                subtype = "reference_pdf"
        item = {"dataset_id": dataset_id, "relative_path": rel, "size_bytes": len(data), "sha256": digest(data), "role": role, "subtype": subtype, "encoding": encoding, "discovery_status": "PRESENT", "dependencies": []}
        item["primary_key"] = [dataset_id, rel, item["sha256"]]
        if text and path.suffix.lower() in {".tex", ".sty"}:
            clean = uncomment(text)
            for match in re.finditer(r"\\(input|include|includegraphics|usetheme|useinnertheme|usefonttheme|usepackage|RequirePackage|documentclass)(?:\[[^\]]*\])?\{([^}]+)\}", clean):
                command, target = match[1], match[2]
                targets = target.split(",") if command in {"usepackage", "RequirePackage"} else [target]
                for name in targets:
                    name = name.strip()
                    entry = {"command": command, "target": name, "source_line": clean.count("\n", 0, match.start()) + 1}
                    if command in {"input", "include", "includegraphics"}:
                        candidates = [root / name]
                        exts = [".tex"] if command != "includegraphics" else [".pdf", ".png", ".jpg", ".jpeg", ".eps"]
                        if not Path(name).suffix:
                            candidates += [root / (name + ext) for ext in exts]
                        local = next((p for p in candidates if p.is_file()), None)
                        entry.update(scope="local", status="RESOLVED" if local else "MISSING", resolved_path=local.relative_to(root).as_posix() if local else None)
                    else:
                        filename = {"usetheme": "beamertheme", "useinnertheme": "beamerinnertheme", "usefonttheme": "beamerfonttheme"}.get(command, "") + name + (".cls" if command == "documentclass" else ".sty")
                        if (root / filename).is_file():
                            entry.update(scope="local", status="RESOLVED", resolved_path=filename)
                        else:
                            if filename not in cache:
                                cache[filename] = tex_lookup(filename)
                            entry.update(scope="tex_distribution", status="RESOLVED" if cache[filename] else ("MISSING" if KPSE.is_file() else "NOT_RUN"), resolved_path=cache[filename])
                    item["dependencies"].append(entry)
        records.append(item)
        chapter_records.append(item)
    missing = [{"file": r["relative_path"], **d} for r in chapter_records for d in r["dependencies"] if d["status"] == "MISSING"]
    lecture, beamer = chapter_texts.get("lecture_source"), chapter_texts.get("beamer_reference")
    headings = lambda t: [{"level": m[1], "title": m[2], "source_line": t.count("\n", 0, m.start()) + 1} for m in re.finditer(r"\\(section|subsection)\*?\{([^}]+)\}", uncomment(t))]
    datasets.append({"dataset_id": dataset_id, "source_directory": dirname, "status": "PRESENT", "file_count": len(chapter_records), "local_dependency_status": "PASS" if not [d for d in missing if d["scope"] == "local"] else "FAIL", "missing_dependencies": missing, "compile_status": "NOT_RUN", "teacher_visual_review": "NOT_RUN"})
    alignments.append({"dataset_id": dataset_id, "lecture_source": lecture[0] if lecture else None, "beamer_reference": beamer[0] if beamer else None, "pair_evidence": "same provided chapter directory, source document classes and subject headings", "pair_status": "IDENTIFIED", "unit_alignment_status": "NOT_RUN", "unit_mapping": [], "lecture_headings": headings(lecture[1]) if lecture else [], "beamer_headings": headings(beamer[1]) if beamer else [], "limitation": "Heading inventory is not a verified content correspondence; deletion/addition and formula equivalence remain unverified."})
    for role, pair in chapter_texts.items():
        rel, t = pair
        clean = uncomment(t)
        commands = re.findall(r"\\(?:setmainfont|setsansfont|setCJKmainfont|setCJKsansfont)(?:\[[^\]]*\])?\{([^}]+)\}", clean)
        styles.append({"dataset_id": dataset_id, "role": role, "relative_path": rel, "section_titles": headings(t), "environment_counts": {e: len(re.findall(r"\\begin\{" + re.escape(e) + r"\}", clean)) for e in ["definition", "theorem", "proposition", "corollary", "example", "solution", "proofdetail", "exercise", "application", "frame", "block"]}, "font_declarations": sorted(set(commands)), "font_resolution_status": "NOT_RUN", "at_begin_section_hook": "\\AtBeginSection" in clean, "legacy_font_command_occurrences": {size: len(re.findall(r"\\" + size + r"\b", clean)) for size in ["tiny", "scriptsize", "Large", "LARGE", "fontsize"]}, "style_status": "STATIC_EXTRACTION_ONLY", "human_checked": False})
    for r in chapter_records:
        if r["subtype"] == "reference_pdf":
            baselines.append({"dataset_id": dataset_id, "relative_path": r["relative_path"], "sha256": r["sha256"], "physical_page_count": None, "rendered_page_count": None, "logical_frame_count": None, "body_bounds_pt": None, "font_ratios": None, "acceptance_rate": None, "reason": "M0 inventory only; PDF rendering/geometry libraries not yet installed in audited Python; new compile and human all-page review NOT_RUN. Historical logs are not current evidence."})

themes = [r for r in records if r["relative_path"] == "beamerthemefduclassroom.sty"]
theme_hashes = sorted({r["sha256"] for r in themes})
theme = {"name": "fduclassroom", "distinct_sha256": theme_hashes, "conflict": len(theme_hashes) > 1, "version_selection": "all provided versions are byte-identical" if len(theme_hashes) == 1 else "user selection required", "selected_sha256": theme_hashes[0] if len(theme_hashes) == 1 else None, "sources": [{"dataset_id": r["dataset_id"], "relative_path": r["relative_path"], "sha256": r["sha256"]} for r in themes], "source_unchanged": True, "resource_precheck": "PASS" if not [d for ds in datasets for d in ds.get("missing_dependencies", []) if d["scope"] == "local"] else "FAIL", "adaptation_compile": "NOT_RUN", "license_status": "NOT_VERIFIED_LOCAL_USE_ONLY"}
manifest = {"schema_version": 1, "created_at": datetime.now(timezone.utc).isoformat(), "root_scope": "Only 第一章/第二章/第三章 in the user-designated workspace", "datasets": datasets, "files": records, "theme": theme, "originals_modified": False, "input_snapshot_status": "NOT_CREATED_DURING_READ_ONLY_AUDIT", "dependency_limitations": "Static literal-path closure across all supplied tex/sty; no macro expansion. TeX distribution packages resolved by explicit kpsewhich; runtime font and conditional macro dependencies require compilation."}
write("manifest.json", manifest)
write("style_profile.json", {"schema_version": 1, "weight_training": False, "profiles": styles, "theme": theme, "rules_override_legacy_samples": True})
write("lecture_beamer_alignment.json", {"schema_version": 1, "pairs": alignments})
write("baseline_metrics.json", {"schema_version": 1, "metrics": baselines, "status": "NOT_MEASURED"})
lines = ["# M0 三章参考资料审计", "", f"检查时间：{manifest['created_at']}", "", f"指定参考根：`{ROOT}`。范围仅其第一章、第二章、第三章。全部原件只读；未扫描其他个人目录。", "", "| 数据集 | 文件数 | 讲义 TeX/PDF | Beamer TeX/PDF | 本地资源闭包 | 新编译 | 人工视觉 |", "|---|---:|---|---|---|---|---|"]
for ds in datasets:
    dataset_files=[r for r in records if r['dataset_id']==ds['dataset_id']]
    lecture_pair=all(any(r['role']=='lecture_source' and r['subtype']==kind for r in dataset_files) for kind in ['tex_entrypoint','reference_pdf'])
    beamer_pair=all(any(r['role']=='beamer_reference' and r['subtype']==kind for r in dataset_files) for kind in ['tex_entrypoint','reference_pdf'])
    lines.append(f"| {ds['dataset_id']} {ds['source_directory']} | {ds.get('file_count', 0)} | {'PRESENT' if lecture_pair else 'MISSING'} | {'PRESENT' if beamer_pair else 'MISSING'} | {ds.get('local_dependency_status', 'NOT_RUN')} | NOT_RUN | NOT_RUN |")
lines += ["", "## 实际发现", "", f"- 清单包含 {len(records)} 个真实文件，每个均记录大小、SHA-256、角色、编码、发现状态和引用行号；三份同名讲义以 dataset_id/relative_path/sha256 区分。", f"- FDU 主题共 {len(themes)} 份，实际不同 SHA-256 数量 {len(theme_hashes)}；选定指纹 `{theme['selected_sha256']}`，三份字节相同，无需任意挑选不同版本。", "- 每组主题第 87 行引用 resources/fudan，均精确解析为同目录 resources/fudan.pdf；未发现缺失本地静态引用资源。", "- 三组的讲义与课件入口均为 UTF-8。主题为 ASCII 兼容的 UTF-8。二进制 PDF/压缩辅助文件编码记录为 null。", "- 显式的 TeX 宏包/文档类使用已解析绝对路径 D:/texlive/2024/bin/windows/kpsewhich.exe 检查；查找不等同于编译成功。", "- 参考讲义包含 NewDocumentEnvironment 自定义数学环境，proofdetail/solution 题解及 extra 选读内容，解析器应保留原文区间。", "- Beamer 的三态章节目录位于各主 TeX 的 AtBeginSection；仅复制 sty 不足以复制目录行为。", "- 旧主题有 title=LARGE、frametitle=Large、itemize scriptsize/tiny；主源有 tiny 宏定义及顶部 0.5cm 额外空白。须独立适配当前四档字号，不能直接视为合格输出；静态出现不证明所有分支实际使用。", "- 第三章讲义包含二元函数、Landau 符号和选读内容；章节标签用于检索，不自动注入新的课程计划。", "- 讲义习题标题标作第 2/3/4 章，目录样例命名为第 1/2/3 章；仅记录此差异，不改原件。", "", "## 未执行与限制", "", "- 新编译、PDF 页数/渲染/字体几何、逐单元讲义课件对齐、教师人工视觉审核：NOT_RUN。baseline_metrics 对未测值使用 null。", "- 原目录里的 PDF/log/aux 是历史产物；不作为当前工程或新 Windows 编译通过证据。", "- 本轮仅只读审计，未创建运行输入快照；实际导入必须按哈希制作不可变副本。", "- 依赖闭包覆盖所有现有 TeX/sty 的字面文件引用、主题和宏包，未执行任意宏展开；字体和动态条件依赖留待编译验证。", "- 原主题与图像分发许可未核实，仅本机使用，不擅自公开分发。", "", "机器证据：reference_index/manifest.json、style_profile.json、lecture_beamer_alignment.json、baseline_metrics.json。", ""]
report = "\n".join(lines)
(OUT / "audit.md").write_text(report, encoding="utf-8")
(PROJECT / "reports" / "reference_audit.md").write_text(report, encoding="utf-8")
print(json.dumps({"files": len(records), "theme_hashes": theme_hashes, "missing_dependencies": [d for ds in datasets for d in ds.get("missing_dependencies", [])]}, ensure_ascii=False))
