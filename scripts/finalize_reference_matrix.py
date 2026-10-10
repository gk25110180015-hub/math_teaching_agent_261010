"""Render all physical pages of each last candidate, even when citations block release."""
import hashlib
import json
from collections import Counter
from pathlib import Path
import sys
PROJECT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PROJECT/"src"))
from math_agent.pdfcheck import inspect_pdf

report_path=PROJECT/"reports"/"reference_matrix.json"
report=json.loads(report_path.read_text(encoding="utf-8"))
target=Path(report["output_root"]).resolve()
if not target.is_relative_to((PROJECT/"workspace").resolve()):raise ValueError("Unexpected matrix output root")
report["preexisting_source_citation_issues"]=[{"dataset_id":"CH01","line":314,"citation":"BradyWeil"},{"dataset_id":"CH02","line":722,"citation":"NCBISteadyState"},{"dataset_id":"CH03","line":650,"citation":"NCBIEnzyme"},{"dataset_id":"CH03","line":1388,"citation":"BradyWeil"}]
for case in report["cases"]:
    if not case["attempts"]:continue
    attempt=case["attempts"][-1]
    folder=Path(attempt["output_root"])
    pdf=folder/"build"/"slides.pdf"
    if not pdf.exists():continue
    try:
        measured=inspect_pdf(pdf,folder/"pages",beamer=True)
        (folder/"pdf.json").write_text(json.dumps(measured,ensure_ascii=False,indent=2),encoding="utf-8")
        attempt.update(page_count=measured["page_count"],rendered_page_count=len(measured["pages"]),render_status=measured["status"],overlay_status=(measured.get("overlay_map") or {}).get("status"),page_issue_count=sum(len(p.get("issues",[])) for p in measured["pages"]),pdf_sha256=hashlib.sha256(pdf.read_bytes()).hexdigest(),draft_pdf_path=str(pdf),pdf_evidence=str(folder/"pdf.json"))
        rendered=json.loads((folder/"render.json").read_text(encoding="utf-8"))
        actual_frames=len((measured.get("overlay_map") or {}).get("frames",[]))
        expected_frames=len(rendered["frame_plan"])
        fatal=any(i.get("rule_id") in {"COMPILE_FAILED","LATEX_ERROR","TEX_FATAL","INCOMPLETE_CONDITIONAL","UNDEFINED_CONTROL"} for i in attempt.get("compile_issues",[]))
        attempt["pdf_completeness"]="COMPLETE_DRAFT" if actual_frames==expected_frames and attempt["overlay_status"]=="PASS" and not fatal else "PARTIAL_OR_UNVERIFIED"
        attempt["expected_frame_count"]=expected_frames
        attempt["actual_frame_count"]=actual_frames
        attempt["exact_blocking_issues"]=[i for i in attempt.get("compile_issues",[])+attempt.get("render_issues",[]) if i.get("severity")=="blocking"]
        frame_lookup={f["frame_id"]:f for f in rendered["frame_plan"]}
        attempt["exact_geometry_issues"]=[{"physical_page":p["physical_page"],"frame_id":p.get("frame_id"),"source_unit_ids":[s["unit_id"] for s in frame_lookup.get(p.get("frame_id"),{}).get("segments",[]) if "unit_id" in s],"image_path":p["image_path"],"issues":p.get("issues",[])} for p in measured["pages"] if p.get("issues")]
        attempt["geometry_rule_counts"]=dict(Counter(i["rule_id"] for p in measured["pages"] for i in p.get("issues",[])))
        attempt["geometry_blocking_rule_counts"]=dict(Counter(i["rule_id"] for p in measured["pages"] for i in p.get("issues",[]) if i.get("severity")=="blocking"))
        attempt["draft_note"]="This PDF belongs to this fresh attempt; compile remains FAIL because unresolved source citations/overflow cannot be waived by PDF existence"
    except Exception as exc:attempt["render_exception"]={"type":type(exc).__name__,"message":str(exc)}
    report_path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    (target/"matrix.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({"case":case["dataset_id"]+"/"+case["theme"],"pages":attempt.get("page_count"),"render":attempt.get("render_status")}),flush=True)
manifest=json.loads((PROJECT/"reference_index"/"manifest.json").read_text(encoding="utf-8"))
names={f"CH{i:02}":n for i,n in enumerate(("第一章","第二章","第三章"),1)}
changed=[]
for item in manifest["files"]:
    original=Path(report["source_root"])/names[item["dataset_id"]]/item["relative_path"]
    if hashlib.sha256(original.read_bytes()).hexdigest()!=item["sha256"]:changed.append(str(original))
report["original_file_verification"]={"checked_files":len(manifest["files"]),"changed_files":changed,"status":"PASS" if not changed else "FAIL"}
lines=["# 三章实际源 → 双模板六组验收矩阵","","六组均实际读取用户原讲义并尝试默认/FDU主题。方法是确定性源保真转换，真实 API 未调用；教师视觉审核 NOT_RUN。前轮按 normalsize → small → footnotesize → 完整语义边界拆分逐候选实测；代码修复后在新目录复测最终候选，前轮所有源码、PDF和日志保留。","","| 数据集 | 模板 | 编译验收 | PDF完整性 | 最后候选物理页 | 已渲染页 | 来源原文检查 | 页面几何 | 教师审核 |","|---|---|---|---|---:|---:|---|---|---|"]
for case in report["cases"]:
    a=case["attempts"][-1]
    lines.append(f"| {case['dataset_id']} | {case['theme']} | {a.get('compile_status')} | {a.get('pdf_completeness')} | {a.get('page_count')} | {a.get('rendered_page_count')} | {a.get('fidelity_status')} | {a.get('render_status')} | NOT_RUN |")
lines += ["","## 具体阻塞与修复证据","","- 三份原讲义存在未定义文献引用：CH01 第314行 BradyWeil；CH02 第722行 NCBISteadyState；CH03 第650行 NCBIEnzyme、第1388行 BradyWeil。未发现配套 bibitem/bibliography，不编造参考条目，也不删除引用。","- 实测发现的 CRLF 重复、条件分支跨帧、boxed 数学环境切分、solution 环境重定义等实现错误已分别复现并修复，保留旧失败产物。当前 parser/Beamer 离线回归30项PASS；这不是API或教师验收。","- CH03 U0028 大TikZ图采用局部等比例坐标调整，未启用transform shape，节点文字不缩放；U0051长custom列表在完整item边界分页并重复必要上下文；U0076编号改用局部默认数字标签。原文payload全部独立核对。","- 上一轮巨大越界对象对应首overlay被Beamer移到画布外的隐藏解答。实现者实际核对过CH01页9与CH03页122/123图像；这仅是抽样诊断，不替代教师逐页验收。未知越界不豁免；本轮检查器实测规则与精确物理页、frame、单元、bbox见JSON。","- 每组最后一个候选的全部物理页（包含 overlay）已尝试渲染，未因产生PDF而冒称编译验收通过。前面的失败候选保留源码/PDF/日志，不宣称逐页验收。",f"- 51 个原始参考文件重新 SHA-256 核对：{report['original_file_verification']['status']}；未改变原件。","",f"全部候选与检查证据：`{target}`。","","原始参考 PDF 的实测基线见 reference_index/baseline_metrics.json：三组讲义 9/10/16 页、课件 54/51/93 页；共233物理页已经实际渲染。它们不是当前新转换通过证据。",""]
for case in report["cases"]:
    a=case["attempts"][-1]
    lines.extend([f"### {case['dataset_id']} / {case['theme']}",""])
    for issue in a.get("exact_blocking_issues",[]):lines.append(f"- {issue['rule_id']}: {issue['message']}")
    lines.extend([f"- 页面几何blocking统计：`{json.dumps(a.get('geometry_blocking_rule_counts',{}),ensure_ascii=False)}`。",f"- 页面几何所有规则统计（含review）：`{json.dumps(a.get('geometry_rule_counts',{}),ensure_ascii=False)}`。",""])
lines=[line.replace("离线回归30项PASS","离线回归31项PASS（另T07/T09两项PASS，T31独立Windows阻塞回归PASS）") for line in lines]
(PROJECT/"reports"/"reference_matrix.md").write_text("\n".join(lines),encoding="utf-8")
report_path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
(target/"matrix.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
