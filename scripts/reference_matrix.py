"""Six real-source deterministic conversion probes; explicitly NO model API call."""
from __future__ import annotations
import argparse
from collections import Counter
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import shutil
import sys

PROJECT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PROJECT/"src"))
from math_agent.parsing import load_project
from math_agent.beamer import render_beamer,check_fidelity
from math_agent.compiler import TexCompiler
from math_agent.pdfcheck import inspect_pdf

def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding="utf-8")

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--root",type=Path,default=PROJECT.parent)
    parser.add_argument("--baseline-only",action="store_true")
    parser.add_argument("--skip-baselines",action="store_true")
    parser.add_argument("--final-only",action="store_true",help="Retest the final safe layout after a scoped renderer fix; retain earlier full matrix folders")
    args=parser.parse_args()
    root=args.root.resolve()
    target=PROJECT/"workspace"/"reference-matrix"/datetime.now().strftime("%Y%m%d-%H%M%S")
    target.mkdir(parents=True)
    report={"schema_version":1,"created_at":datetime.now(timezone.utc).isoformat(),"source_root":str(root),"output_root":str(target),"method":"deterministic source-preserving rendering; NO live API; NO teacher approval", "real_api":"NOT_RUN","teacher_visual_review":"NOT_RUN","cases":[]}
    def save():
        write(target/"matrix.json",report)
        write(PROJECT/"reports"/"reference_matrix.json",report)
        lines=["# 三章实际源 → 双模板验收矩阵","",report["method"],"","这些任务实际读取三份用户讲义，使用确定性源保真转换；没有调用真实 API。编译/渲染与教师逐页视觉审核分别记录。","","| 数据集 | 模板 | 最终状态 | 实测编译 | 物理页 | 全页渲染 | 来源核对 | 教师审核 |","|---|---|---|---|---:|---|---|---|"]
        for case in report["cases"]:
            latest=case["attempts"][-1] if case["attempts"] else {}
            lines.append(f"| {case['dataset_id']} | {case['theme']} | {case['status']} | {latest.get('compile_status','NOT_RUN')} | {latest.get('page_count')} | {latest.get('render_status','NOT_RUN')} | {latest.get('fidelity_status','NOT_RUN')} | NOT_RUN |")
        lines += ["",f"全部候选、TeX、PDF、日志与 JSON：`{target}`。","","失败时未删除任何失败的定义、证明、例题或图表。最后状态由编译问题、来源问题、页面风险和未完成审核共同决定，不能将成功产生 PDF 视作验收通过。",""]
        (PROJECT/"reports"/"reference_matrix.md").write_text("\n".join(lines),encoding="utf-8")
    if not args.baseline_only:
        for index,name in enumerate(("第一章","第二章","第三章"),1):
            input_path=root/name/"大学数学（一）(1).tex"
            source_bytes=input_path.read_bytes();source_hash=hashlib.sha256(source_bytes).hexdigest()
            parsed=load_project(root/name,input_path.name)
            snapshot=target/"inputs"/f"CH{index:02}"/input_path.name
            snapshot.parent.mkdir(parents=True,exist_ok=True);snapshot.write_bytes(source_bytes)
            for theme in ("default","fduclassroom"):
                case={"dataset_id":f"CH{index:02}","theme":theme,"input_sha256":source_hash,"parsed_unit_count":len(parsed["units"]),"opaque_unit_count":sum(u["kind"]=="opaque_tex" for u in parsed["units"]),"source_issues":parsed["issues"],"attempts":[],"status":"RUNNING"}
                report["cases"].append(case);save()
                candidates=(("footnotesize",True),) if args.final_only else (("normalsize",False),("small",False),("footnotesize",False),("footnotesize",True))
                for num,(font,split) in enumerate(candidates,4 if args.final_only else 1):
                    attempt_root=target/f"CH{index:02}-{theme}"/f"attempt-{num}"
                    plan={"title":name,"theme":theme,"sections":parsed["sections"],"omissions":[],"additions":[],"_layout":{"font_size":font,"split_long":split}}
                    attempt={"attempt":num,"font":font,"split_long":split,"output_root":str(attempt_root),"compile_status":"NOT_RUN","render_status":"NOT_RUN","page_count":None}
                    case["attempts"].append(attempt)
                    try:
                        rendered=render_beamer(parsed,plan,attempt_root/"source",root)
                        write(attempt_root/"render.json",rendered)
                        tex=(attempt_root/"source"/"slides.tex").read_text(encoding="utf-8")
                        fidelity=check_fidelity(parsed,{**plan,"_render_scaffold_hash":rendered["render_scaffold_hash"]},tex)
                        write(attempt_root/"fidelity.json",fidelity)
                        attempt["fidelity_status"]=fidelity["status"]
                        attempt["render_issues"]=rendered["issues"]
                        compiled=TexCompiler(r"D:\texlive\2024\bin\windows\xelatex.exe").compile(attempt_root/"source","slides.tex",attempt_root/"build",trusted=True)
                        write(attempt_root/"compile.json",compiled)
                        attempt["compile_status"]=compiled["status"];attempt["compile_issues"]=compiled["issues"]
                        if compiled.get("pdf_path"):
                            inspected=inspect_pdf(Path(compiled["pdf_path"]),attempt_root/"pages",beamer=True)
                            write(attempt_root/"pdf.json",inspected)
                            attempt.update(render_status=inspected["status"],page_count=inspected["page_count"],rendered_page_count=len(inspected["pages"]),overlay_status=(inspected.get("overlay_map") or {}).get("status"),page_issue_count=sum(len(p.get("issues",[])) for p in inspected["pages"]))
                        blocking=[i for i in rendered["issues"] if i.get("severity")=="blocking"]
                        if compiled["status"]=="PASS" and fidelity["status"]=="PASS" and not blocking and attempt["render_status"]=="PASS":
                            case["status"]="NEEDS_REVIEW";save();break
                        rule_ids={i.get("rule_id") for i in compiled["issues"]}
                        if compiled["status"]!="PASS" and any(x not in {"OVERFULL_HBOX","OVERFULL_VBOX","OVERFULL","UNRESOLVED_REFERENCE","FONT_SUBSTITUTION","MISSING_CHARACTER"} and "OVERFULL" not in str(x) for x in rule_ids):
                            case["status"]="BLOCKED";save();break
                    except Exception as exc:
                        attempt["exception"]={"type":type(exc).__name__,"message":str(exc)}
                        case["status"]="BLOCKED";save();break
                    save()
                if case["status"]=="RUNNING":case["status"]="BLOCKED"
                case["original_unchanged"]=hashlib.sha256(input_path.read_bytes()).hexdigest()==source_hash
                save()
                print(json.dumps({"dataset":case["dataset_id"],"theme":theme,"status":case["status"],"attempts":len(case["attempts"])},ensure_ascii=True),flush=True)
    if not args.skip_baselines:
        baseline={"schema_version":1,"created_at":datetime.now(timezone.utc).isoformat(),"status":"MEASURED_PARTIALLY","metrics":[]}
        manifest=json.loads((PROJECT/"reference_index"/"manifest.json").read_text(encoding="utf-8"))
        lookup={f"CH{i:02}":n for i,n in enumerate(("第一章","第二章","第三章"),1)}
        for entry in manifest["files"]:
            if entry.get("subtype")!="reference_pdf":continue
            pdf=root/lookup[entry["dataset_id"]]/entry["relative_path"]
            row={"dataset_id":entry["dataset_id"],"relative_path":entry["relative_path"],"sha256":hashlib.sha256(pdf.read_bytes()).hexdigest(),"physical_page_count":None,"rendered_page_count":None,"logical_frame_count":None,"body_bounds_pt":None,"font_ratios":None,"acceptance_rate":None,"teacher_visual_review":"NOT_RUN"}
            try:
                inspected=inspect_pdf(pdf,target/"reference-pdf-renders"/entry["dataset_id"]/("beamer" if entry["role"]=="beamer_reference" else "lecture"),beamer=entry["role"]=="beamer_reference")
                details=target/"reference-pdf-renders"/entry["dataset_id"]/("beamer.json" if entry["role"]=="beamer_reference" else "lecture.json")
                write(details,inspected)
                row.update(physical_page_count=inspected["page_count"],rendered_page_count=len(inspected["pages"]),logical_frame_count=len(inspected["overlay_map"]["frames"]) if (inspected.get("overlay_map") or {}).get("status")=="PASS" else None,inspection_status=inspected["status"],evidence=str(details),reason="Actual original PDF rendered on all physical pages; body/font calibration and human acceptance remain unmeasured")
            except Exception as exc:row.update(inspection_status="BLOCKED",reason=str(exc))
            baseline["metrics"].append(row)
            write(PROJECT/"reference_index"/"baseline_metrics.json",baseline)
    save()
    print(json.dumps({"report":str(PROJECT/"reports"/"reference_matrix.json"),"root":str(target)},ensure_ascii=True))

if __name__=="__main__":main()
