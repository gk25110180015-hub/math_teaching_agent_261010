"""Native Windows compile evidence for a synthetic two-overlay fixture, no API."""
import json
from pathlib import Path
import sys
from datetime import datetime
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from math_agent.parsing import parse_tex
from math_agent.beamer import render_beamer
from math_agent.compiler import TexCompiler
from math_agent.pdfcheck import inspect_pdf

project=Path(__file__).resolve().parents[1]
target=project/"workspace"/"beamer-probe"/datetime.now().strftime("%Y%m%d-%H%M%S")
target.mkdir(parents=True)
source=r'''\documentclass{ctexart}
\begin{document}
\section{数列极限}
\begin{definition}若对每个 $\varepsilon>0$，存在 $N\in\mathbb{N}$，当 $n>N$ 时有 $|a_n-a|<\varepsilon$，则称数列收敛于 $a$。\end{definition}
\begin{example}计算 $\lim_{n\to\infty}\frac1n$。\end{example}
\begin{solution}任取 $\varepsilon>0$，取 $N>1/\varepsilon$，当 $n>N$ 时 $|1/n|<\varepsilon$，所以极限为 $0$。\end{solution}
\section{极限唯一性}
\begin{theorem}收敛数列的极限唯一。\end{theorem}
\begin{proof}若两个极限为 $a\ne b$，取 $\varepsilon=|a-b|/3$，由三角不等式得 $|a-b|<2|a-b|/3$，矛盾。\end{proof}
\end{document}'''
parsed=parse_tex(source)
results=[]
for theme in ("default","fduclassroom"):
    folder=target/theme
    plan={"theme":theme,"title":"数列极限","sections":parsed["sections"],"omissions":[],"additions":[]}
    rendered=render_beamer(parsed,plan,folder/"source",project.parent)
    compiled=TexCompiler(r"D:\texlive\2024\bin\windows\xelatex.exe").compile(folder/"source","slides.tex",folder/"build",trusted=True)
    pdf=inspect_pdf(Path(compiled["pdf_path"]),folder/"pages",beamer=True) if compiled.get("pdf_path") else None
    report={"test_kind":"windows_compile_synthetic","theme":theme,"render":rendered,"compile":compiled,"pdf":pdf,"real_api":"NOT_RUN","human_visual":"NOT_RUN"}
    (folder/"result.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    results.append({"theme":theme,"compile_status":compiled["status"],"issues":compiled.get("issues"),"page_count":pdf.get("page_count") if pdf else None,"report":str(folder/"result.json")})
print(json.dumps(results,ensure_ascii=True))
