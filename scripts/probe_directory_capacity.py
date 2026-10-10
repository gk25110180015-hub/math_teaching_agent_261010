"""Real Windows checks of complete 12/24-section progress directories."""
import json
from datetime import datetime
from pathlib import Path
import sys
PROJECT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PROJECT/"src"))
from math_agent.parsing import parse_tex
from math_agent.beamer import render_beamer
from math_agent.compiler import TexCompiler
from math_agent.pdfcheck import inspect_pdf

target=PROJECT/"workspace"/"iteration2-directory"/datetime.now().strftime("%Y%m%d-%H%M%S")
report={"real_api":"NOT_RUN","teacher_visual_review":"NOT_RUN","cases":[]}
def write(path,data):
    path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8")
for count in (12,24):
    source=r"\begin{document}"+"".join(fr"\section{{概念{i}：函数极限与定义域}}第{i}节正文，假设 $x>0$。" for i in range(1,count+1))+r"\end{document}"
    parsed=parse_tex(source)
    plan={"title":"完整目录容量实测","theme":"fduclassroom","sections":parsed["sections"],"omissions":[],"additions":[],"_layout":{"split_long":True}}
    path=target/f"sections-{count}"
    rendered=render_beamer(parsed,plan,path/"source",PROJECT.parent);write(path/"render.json",rendered)
    compile_result=TexCompiler(r"D:\texlive\2024\bin\windows\xelatex.exe").compile(path/"source","slides.tex",path/"build",trusted=True);write(path/"compile.json",compile_result)
    case={"section_count":count,"directory_frames":sum(f["kind"]=="directory" for f in rendered["frame_plan"]),"fidelity":rendered["fidelity"]["status"],"compile_status":compile_result["status"],"compile_issues":compile_result["issues"],"path":str(path)}
    if compile_result.get("pdf_path"):
        inspected=inspect_pdf(Path(compile_result["pdf_path"]),path/"pages",beamer=True);write(path/"pdf.json",inspected)
        case.update(physical_pages=inspected["page_count"],all_rendered=len(inspected["pages"])==inspected["page_count"],geometry_status=inspected["status"],blocking_geometry=[{"physical_page":p["physical_page"],"issue":i} for p in inspected["pages"] for i in p.get("issues",[]) if i.get("severity")=="blocking"])
    report["cases"].append(case)
    write(target/"report.json",report);write(PROJECT/"reports"/"iteration2"/"directory_capacity.json",report)
    print(json.dumps({"sections":count,"compile":case["compile_status"],"geometry":case.get("geometry_status"),"pages":case.get("physical_pages")}),flush=True)
