"""Read-only before metrics and source-faithful real-PDF iteration; no model/API calls."""
from __future__ import annotations
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
from statistics import median
import sys

PROJECT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PROJECT/"src"))
from math_agent.parsing import load_project,uncomment
from math_agent.beamer import render_beamer,check_fidelity
from math_agent.compiler import TexCompiler
from math_agent.pdfcheck import inspect_pdf,parse_overlay_map

REPORTS=PROJECT/"reports"/"iteration2"

def dump(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding="utf-8")

def pdf_metrics(path,frame_plan=None):
    import pdfplumber
    density=[];font_counts=Counter();physical=0
    with pdfplumber.open(path) as pdf:
        physical=len(pdf.pages)
        nav=parse_overlay_map(path.with_suffix(".nav"),physical)
        finals={f["physical_pages"][-1] for f in nav.get("frames",[])} if nav.get("status")=="PASS" else set(range(1,physical+1))
        for n,page in enumerate(pdf.pages,1):
            if n not in finals:continue
            # Common interior window gives a comparable proxy, not a clipping verdict.
            chars=[c for c in page.chars if c["x0"]>=18 and c["x1"]<=page.width-18 and c["top"]>=35 and c["bottom"]<=page.height-20 and str(c.get("text","")).strip()]
            for c in chars:
                if re.search(r"[\u3400-\u9fff]",str(c["text"])):font_counts[str(round(c["size"],2))]+=1
            row_bins={round(c["top"]/4) for c in chars}
            bbox=[min(c["x0"] for c in chars),min(c["top"] for c in chars),max(c["x1"] for c in chars),max(c["bottom"] for c in chars)] if chars else None
            density.append({"physical_page":n,"interior_visible_characters":len(chars),"occupied_4pt_row_bins":len(row_bins),"interior_bbox_pt":bbox})
    return {"pdf_path":str(path),"pdf_sha256":hashlib.sha256(path.read_bytes()).hexdigest(),"physical_pages":physical,"logical_frames":len(nav.get("frames",[])) if nav.get("status")=="PASS" else None,"nav_status":nav.get("status"),"overlay_extra_pages":physical-len(finals),"final_overlay_cjk_font_character_counts":dict(font_counts),"median_final_overlay_interior_characters":median([p["interior_visible_characters"] for p in density]) if density else None,"median_final_overlay_4pt_row_bins":median([p["occupied_4pt_row_bins"] for p in density]) if density else None,"final_overlay_density":density,"density_limitations":"Fixed common window x18..width-18/y35..height-20; final overlay only; visible glyph/row proxies, not a teaching-quality grade or source coverage claim"}

def renderer_metrics(rendered):
    frames=rendered["frame_plan"]
    content=[f for f in frames if f["kind"]=="content"]
    content_ids={f["frame_id"] for f in content}
    return {"logical_frames":len(frames),"directory_frames":sum(f["kind"]=="directory" for f in frames),"content_frames":len(content),"content_frame_fonts":dict(Counter(f["text_size"] for f in content)),"content_frames_with_under_60_visible_chars":sum(x["visible_text_count"]<60 for x in rendered["layout_plan"] if x["frame_id"] in content_ids),"unit_split_counts":{u:len(v) for u,v in rendered["source_map"].items() if len(v)>1},"source_payload_fidelity":rendered["fidelity"]["status"]}

def snapshot_before(root):
    destination=REPORTS/"beamer_comparison_before.json"
    if destination.exists():return json.loads(destination.read_text(encoding="utf-8"))
    matrix=json.loads((PROJECT/"reports"/"reference_matrix.json").read_text(encoding="utf-8"))
    manifest=json.loads((PROJECT/"reference_index"/"manifest.json").read_text(encoding="utf-8"))
    report={"created_at":datetime.now(timezone.utc).isoformat(),"method":"No model/API; immutable before metrics from round-1 outputs and original reference Beamer PDFs", "teacher_visual_review":"NOT_RUN","originals":[],"before":[],"code_sha256":{}}
    for filename in ("beamer.py","parsing.py"):
        path=PROJECT/"src"/"math_agent"/filename;data=path.read_bytes()
        report["code_sha256"][filename]=hashlib.sha256(data).hexdigest()
        snapshot=REPORTS/"before-source"/filename;snapshot.parent.mkdir(parents=True,exist_ok=True);snapshot.write_bytes(data)
    names={f"CH{i:02}":name for i,name in enumerate(("第一章","第二章","第三章"),1)}
    for item in manifest["files"]:
        if item.get("role")!="beamer_reference" or item.get("subtype")!="reference_pdf":continue
        path=root/names[item["dataset_id"]]/item["relative_path"]
        tex=path.with_suffix(".tex");source=uncomment(tex.read_text(encoding="utf-8-sig"));body=source.split(r"\begin{document}",1)[-1]
        report["originals"].append({"dataset_id":item["dataset_id"],"source_tex_sha256":hashlib.sha256(tex.read_bytes()).hexdigest(),"section_count":len(re.findall(r"\\section\*?\{",body)),"explicit_body_font_commands":dict(Counter(re.findall(r"\\(large|normalsize|small|footnotesize|scriptsize|tiny)\b",body))),**pdf_metrics(path)})
    for case in matrix["cases"]:
        attempt=case["attempts"][-1];folder=Path(attempt["output_root"])
        rendered=json.loads((folder/"render.json").read_text(encoding="utf-8"))
        report["before"].append({"dataset_id":case["dataset_id"],"theme":case["theme"],"input_sha256":case["input_sha256"],"snapshot_dir":str(folder),"compile_status":attempt["compile_status"],"geometry_status":attempt["render_status"],**renderer_metrics(rendered),"pdf":pdf_metrics(folder/"build"/"slides.pdf")})
    dump(destination,report)
    return report

def after(root,themes,font,tag,complete_bibliography=False):
    before=snapshot_before(root)
    target=PROJECT/"workspace"/"iteration2-beamer"/(datetime.now().strftime("%Y%m%d-%H%M%S")+"-"+tag)
    report={"created_at":datetime.now(timezone.utc).isoformat(),"root":str(target),"real_api":"NOT_RUN","teacher_visual_review":"NOT_RUN","before_evidence":str(REPORTS/"beamer_comparison_before.json"),"cases":[]}
    target.mkdir(parents=True)
    for i,name in enumerate(("第一章","第二章","第三章"),1):
        parsed=load_project(root/name,"大学数学（一）(1).tex")
        provenance=None
        if complete_bibliography:
            from math_agent.manuscript import complete_bibliography as supplement,write_prepared_copy
            original=root/name/"大学数学（一）(1).tex";manuscript=root/"大学数学（一）(1).tex"
            prepared=supplement(original.read_bytes().decode("utf-8-sig"),manuscript.read_bytes().decode("utf-8-sig"),source_name=str(original),manuscript_name=str(manuscript))
            destination=target/"prepared-inputs"/f"CH{i:02}"/"lecture.tex"
            provenance=write_prepared_copy(prepared,destination,protected_paths=[original,manuscript])
            for dependency in parsed.get("dependencies",[]):
                if dependency.get("resolved"):
                    relative=dependency["resolved"];asset=(original.parent/relative).resolve()
                    if asset.is_relative_to(original.parent.resolve()) and asset.is_file():
                        out=destination.parent/relative;out.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(asset,out)
            parsed=load_project(destination.parent,destination.name)
        for theme in themes:
            path=target/f"CH{i:02}-{theme}"
            layout={"split_long":True}
            if font!="auto":layout["font_size"]=font
            plan={"title":name,"theme":theme,"sections":parsed["sections"],"omissions":[],"additions":[],"_layout":layout}
            rendered=render_beamer(parsed,plan,path/"source",root);dump(path/"render.json",rendered)
            fidelity=check_fidelity(parsed,{**plan,"_render_scaffold_hash":rendered["render_scaffold_hash"]},(path/"source"/"slides.tex").read_text(encoding="utf-8"));dump(path/"fidelity.json",fidelity)
            compiled=TexCompiler(r"D:\texlive\2024\bin\windows\xelatex.exe").compile(path/"source","slides.tex",path/"build",trusted=True);dump(path/"compile.json",compiled)
            case={"dataset_id":f"CH{i:02}","theme":theme,"layout":layout,"path":str(path),"source_enrichment":provenance,"compile_status":compiled["status"],"compile_issues":compiled["issues"],"render_issues":rendered["issues"],"fidelity_status":fidelity["status"],**renderer_metrics(rendered)}
            # Current build only. Source-reference errors still yield a diagnosable draft.
            pdf=path/"build"/"slides.pdf"
            if pdf.exists():
                inspected=inspect_pdf(pdf,path/"pages",beamer=True);dump(path/"pdf.json",inspected)
                nav=inspected.get("overlay_map") or {}
                case.update(pdf=pdf_metrics(pdf),geometry_status=inspected["status"],rendered_page_count=len(inspected["pages"]),geometry_blocking_rules=dict(Counter(issue["rule_id"] for page in inspected["pages"] for issue in page.get("issues",[]) if issue.get("severity")=="blocking")),pdf_completeness="COMPLETE_DRAFT" if nav.get("status")=="PASS" and len(nav.get("frames",[]))==len(rendered["frame_plan"]) else "PARTIAL_OR_UNVERIFIED")
            report["cases"].append(case)
            dump(target/"comparison.json",report);dump(REPORTS/"beamer_comparison.json",report)
            print(json.dumps({"case":f"CH{i:02}/{theme}","compile":compiled["status"],"pages":case.get("pdf",{}).get("physical_pages"),"geometry":case.get("geometry_status"),"font":font}),flush=True)
    return report

def main():
    cli=argparse.ArgumentParser();cli.add_argument("--root",type=Path,default=PROJECT.parent);cli.add_argument("--before-only",action="store_true");cli.add_argument("--themes",nargs="+",default=["fduclassroom"]);cli.add_argument("--font",default="auto");cli.add_argument("--tag",default="adaptive");cli.add_argument("--complete-bibliography",action="store_true")
    args=cli.parse_args()
    if args.before_only:snapshot_before(args.root)
    else:after(args.root,args.themes,args.font,args.tag,args.complete_bibliography)

if __name__=="__main__":main()
