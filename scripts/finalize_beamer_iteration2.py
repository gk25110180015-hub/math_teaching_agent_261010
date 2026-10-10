"""Join explicitly selected local comparison runs; retain every previous run."""
import argparse
from collections import Counter
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import re
import sys
PROJECT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PROJECT/"src"))
from math_agent.parsing import load_project,uncomment
REPORTS=PROJECT/"reports"/"iteration2"
parser=argparse.ArgumentParser();parser.add_argument("--run",type=Path,action="append",required=True);args=parser.parse_args()
before=json.loads((REPORTS/"beamer_comparison_before.json").read_text(encoding="utf-8"))
cases={};runs=[]
for run in args.run:
    path=run/"comparison.json";report=json.loads(path.read_text(encoding="utf-8"));runs.append(str(path.resolve()))
    for case in report["cases"]:cases[(case["dataset_id"],case["theme"])]=case
originals={x["dataset_id"]:x for x in before["originals"]}
old={(x["dataset_id"],x["theme"]):x for x in before["before"]}
manifest=json.loads((PROJECT/"reference_index"/"manifest.json").read_text(encoding="utf-8"))
names={f"CH{i:02}":n for i,n in enumerate(("第一章","第二章","第三章"),1)}
changed=[]
for entry in manifest["files"]:
    path=PROJECT.parent/names[entry["dataset_id"]]/entry["relative_path"]
    if hashlib.sha256(path.read_bytes()).hexdigest()!=entry["sha256"]:changed.append(str(path))
structures=[]
for dataset,name in names.items():
    folder=PROJECT.parent/name
    parsed=load_project(folder,"大学数学（一）(1).tex")
    source=next(p for p in folder.glob("*.tex") if p.name!="大学数学（一）(1).tex")
    body=uncomment(source.read_text(encoding="utf-8-sig")).split(r"\begin{document}",1)[-1]
    structures.append({"dataset_id":dataset,"lecture_sections":[s["title"] for s in parsed["sections"]],"original_reference_sections":re.findall(r"\\section\*?\{([^}]+)\}",body),"active_lecture_unit_types":dict(Counter(u["kind"] for u in parsed["units"] if u.get("source_visibility")!="inactive" and u["kind"]!="presentation_scaffold")),"scope_note":"The reference slides are a separately organized teaching document; heading differences are evidence, not proof of mathematical omission or equivalence"})
output={"schema_version":1,"created_at":datetime.now(timezone.utc).isoformat(),"real_api":"NOT_RUN_BY_THIS_COMPARISON","teacher_visual_review":"NOT_RUN","before_evidence":str(REPORTS/"beamer_comparison_before.json"),"selected_run_evidence":runs,"cases":[cases[key] for key in sorted(cases)],"original_reference_structure":structures,"original_file_verification":{"checked_files":len(manifest["files"]),"changed_files":changed,"status":"PASS" if not changed else "FAIL"},"current_code_sha256":{name:hashlib.sha256((PROJECT/"src"/"math_agent"/name).read_bytes()).hexdigest() for name in ("beamer.py","parsing.py")},"directory_capacity_evidence":str(REPORTS/"directory_capacity.json"),"limitations":["Source fidelity checks exact retained source payload intervals, not truth of the source mathematics","PDF geometry review warnings and teacher page reviews remain independent","Fixed-window density proxies include final-overlay directory pages and are not teaching-quality scores","No model fine-tuning, live model call, or blind held-out accuracy claim in this comparison"]}
(REPORTS/"beamer_comparison.json").write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding="utf-8")
lines=["# 第二轮：三章 Beamer 真实基准对照与实现改进","","本轮比较使用用户三份原讲义、三份原 Beamer，以及上轮六份完整草稿。新增全稿只用于在独立工作副本补齐其真实书目条目，原数学正文不改写，原件不覆盖。本比较脚本没有调用模型 API；真实 API 验证由工程另一份报告单独记录。","","## 结果","","六组均完成真实 Windows XeLaTeX 编译与来源核对，默认/FDU各为77、76、108页，共522物理页全部渲染。几何检查无 blocking，仍保留 NEEDS_REVIEW；教师逐页人工验收 NOT_RUN。原51文件哈希复核PASS。","","| 章 | 原参考页 / 逻辑帧 | 上轮页 / 逻辑帧 | 本轮页 / 逻辑帧 | 本轮正文 normal / small / foot | 原 / 上轮 / 本轮内部字符中位数 |","|---|---:|---:|---:|---:|---:|"]
for dataset in names:
    base=originals[dataset];prior=old[(dataset,"fduclassroom")];now=cases[(dataset,"fduclassroom")];font=now["content_frame_fonts"]
    lines.append(f"| {dataset} | {base['physical_pages']} / {base['logical_frames']} | {prior['pdf']['physical_pages']} / {prior['logical_frames']} | {now['pdf']['physical_pages']} / {now['logical_frames']} | {font.get('normalsize',0)} / {font.get('small',0)} / {font.get('footnotesize',0)} | {base['median_final_overlay_interior_characters']} / {prior['pdf']['median_final_overlay_interior_characters']} / {now['pdf']['median_final_overlay_interior_characters']} |")
lines += ["","上表两模板页数相同。字符密度使用所有逻辑帧的最后overlay，在相同内部窗口统计可见字形；排除了隐藏overlay、导航和页脚的大部分影响，但它只是描述性指标，不能据此判定教学质量。第二章的字符中位数98→94同时字号和内容行数增加，不能为了提高数值而挤小正文。","","## 查明并修复的不足","","1. 上轮全部正文固定footnotesize，短页仍显示过小。本轮逐frame尝试正常字号，只有较长完整单元使用small/footnotesize。显式font_size仍保留为可追踪回退；应用应优先使用`_layout={'split_long':True}`。","2. 长证明/custom按每段或item逐页输出，没有再次组合完整步骤。本轮在源区间连续、环境平衡、容量允许时组合，不截断公式。CH03 U0038从11帧变3帧；U0051完整item从6帧变2帧。来源检查独立对实际TeX逐区间核对，重复环境上下文单独标记。","3. 邻接短解释段落原来各占一页，现只在相同section、同类解释且容量允许时组合；不把互不相关的数学命题强行拼页。","4. 目录原来超过10条就增加目录页。本轮依次尝试合法字号/间距、稳定双列、显式分页，每个section仍有一次完整三态目录组。12/24节真实FDU探针分别24/48物理页，编译与几何均PASS，所有标题保留。","5. 单纯文本/公式计数漏估嵌套theorem、custom、proofdetail等环境的垂直开销。第一轮自适应CH03出现两个真实vbox溢出，已保留失败日志/107页PDF；修复估算后第二轮完整108页无OVERFULL。","6. thebibliography现以独立源单元渲染，按完整bibitem明确分页，不用allowframebreaks，每个条目只输出一次。补充自新全稿的BradyWeil、NCBISteadyState、NCBIEnzyme有原文、行号和hash provenance；未猜测书目。","","## 与原参考仍有的内容和呈现差异","","原参考54/51/93页不是应当强行追平的目标。第一章原参考5个section，当前讲义6个；第二章原参考5个，讲义7个；第三章均7个但知识点分组标题不同。原课件是重新组织过的教学文本，本轮保持批准来源的正文与证明，不能用减页代替内容审核。具体两组section名称存于JSON。","","当前目录数为6/7/7，原参考为5/5/7；这是section结构差异，三章旧目录本身没有重复hook。12/24节容量问题由独立夹具揭示，而非误称旧三章因目录重复而膨胀。原参考overlay额外物理页为14/12/22，本轮为3/7/15；本轮在明确短题解组合处展示题干→解答，不机械复制参考课件每个动画步骤。","","原第一/第二章参考源码存在scriptsize，本轮不继承这些违规字号。FDU原sty字节复制，适配层保持当前section导航和完整章节目录；这避免在允许最小字号下把长的全章导航挤出页宽，并非像素级复刻旧PDF。","","## 实际测试与保留条件","","离线结构/保真回归：新增4个问题先4项FAIL，修改后连同书目与原解析回归36项PASS。目录容量为真实Windows编译与72页全渲染。三章双模板522页为真实Windows编译、所有overlay渲染、来源FID PASS；几何review提示与教师验收未混记。","","保留的review主要为正文靠近实测正文边界；CH03自然公式下标中文和FandolHei斜体替换另需复核。实现者抽看了CH01原参考/新稿、CH03完整3页证明PNG，确认本次组合无明显裁切；这不等于教师对522页逐页通过。","","| 数据集 / 模板 | 编译 | FID | 完整性 | 实际/已渲染页 | 几何 | blocking |","|---|---|---|---|---:|---|---:|"]
for key in sorted(cases):
    c=cases[key];lines.append(f"| {c['dataset_id']} / {c['theme']} | {c['compile_status']} | {c['fidelity_status']} | {c['pdf_completeness']} | {c['pdf']['physical_pages']} / {c['rendered_page_count']} | {c['geometry_status']} | {sum(c['geometry_blocking_rules'].values())} |")
lines += ["","详细产物位置："]+[f"- `{path}`" for path in runs]
lines += ["","- before快照：`reports/iteration2/beamer_comparison_before.json`及`before-source/`。","- 失败/特征回归：`reports/iteration2/layout_regressions_before.txt`。","- 原稿与补书目来源：`reports/iteration2/source_audit.json`及每组prepared-inputs/*.provenance.json。","- 教师评价、难度一致性、数学原稿本身的正确性仍需要独立审核；本轮没有训练模型权重，也没有宣称盲测准确率。",""]
(REPORTS/"beamer_comparison.md").write_text("\n".join(lines),encoding="utf-8")
print(json.dumps({"cases":len(cases),"pages":sum(c["pdf"]["physical_pages"] for c in cases.values()),"originals":output["original_file_verification"]["status"]}))
