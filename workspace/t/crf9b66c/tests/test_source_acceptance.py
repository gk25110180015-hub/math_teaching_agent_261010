"""Bounded T07/T09/T31 source acceptance fixtures, not general semantic claims."""
import json
import os
from pathlib import Path

import pytest

from math_agent.parsing import parse_tex
from math_agent.beamer import render_beamer, check_fidelity
from math_agent.compiler import TexCompiler, resolve_xelatex


def confirmed(parsed, omissions=None):
    return {"title":"来源验收", "theme":"default", "sections":parsed["sections"],
            "omissions":omissions or [], "additions":[]}


@pytest.mark.unit
def test_T07_duplicate_example_titles_have_distinct_locations_and_exact_deletion(tmp_path):
    text=r'''\begin{document}
\section{第一节}
\begin{example}[例3]甲题：$x=1$。\end{example}
\begin{solution}甲解：$y=2$。\end{solution}
\section{第二节}
\begin{example}[例3]乙题：$x=3$。\end{example}
\begin{solution}乙解：$y=4$。\end{solution}
\end{document}'''
    parsed=parse_tex(text,source_name="重名例题.tex")
    examples=[u for u in parsed["units"] if u["kind"]=="example_statement"]
    assert len(examples)==2 and all("[例3]" in u["raw_tex"] for u in examples)
    assert examples[0]["id"]!=examples[1]["id"]
    assert examples[0]["section_title"]!=examples[1]["section_title"]
    assert examples[0]["source_spans"][0]["start_line"]!=examples[1]["source_spans"][0]["start_line"]
    selected=examples[1]["id"]
    associated=[u["id"] for u in parsed["units"] if u["semantic_relations"].get("solution_of")==selected]
    assert len(associated)==1
    p=confirmed(parsed,[{"unit_id":uid,"kind":"user_authorized_omission","decision_id":"D-EXACT"} for uid in [selected,*associated]])
    result=render_beamer(parsed,p,tmp_path)
    actual=(tmp_path/"slides.tex").read_text(encoding="utf-8")
    assert "甲题" in actual and "甲解" in actual and "乙题" not in actual and "乙解" not in actual
    assert result["fidelity"]["status"]=="PASS"


@pytest.mark.unit
def test_T09_inseparable_introduction_and_hypothesis_are_retained(tmp_path):
    mixed=r"为引入对数这一概念，以下推导始终假设 $x>0$ 且 $a>0,a\ne1$；这两个条件是后续等式 $a^{\log_a x}=x$ 的定义域条件。"
    text=r"\begin{document}\section{对数}\begin{intuition}"+mixed+r"\end{intuition}\begin{definition}$\log_a x$ 表示满足 $a^y=x$ 的数 $y$。\end{definition}\end{document}"
    parsed=parse_tex(text);p=confirmed(parsed)
    unit=next(u for u in parsed["units"] if mixed in u["raw_tex"])
    assert unit["kind"]=="introduction"
    result=render_beamer(parsed,p,tmp_path)
    actual=(tmp_path/"slides.tex").read_text(encoding="utf-8")
    assert mixed in actual and r"$x>0$" in actual and r"$a>0,a\ne1$" in actual
    assert result["fidelity"]["status"]=="PASS"
    assert check_fidelity(parsed,p,actual.replace(r"$x>0$","无条件"))["status"]=="FAIL"


@pytest.mark.windows_compile
def test_T31_broken_tabularx_blocks_with_exact_source_location_and_preserved_unit(tmp_path):
    if os.name!="nt" or not resolve_xelatex():
        pytest.skip("Actual Windows XeLaTeX unavailable")
    text=r'''\begin{document}
\section{破损表格}
\begin{table}
\begin{tabularx}{\linewidth}{QQ}
变量 & 条件 \\
$x$ & $x>0$ \\
\end{tabularx}
\end{table}
\end{document}'''
    parsed=parse_tex(text,source_name="破损表格.tex")
    table=next(u for u in parsed["units"] if u["kind"]=="table")
    output=tmp_path/"source"
    rendered=render_beamer(parsed,confirmed(parsed),output)
    actual=(output/"slides.tex").read_text(encoding="utf-8")
    assert table["raw_tex"] in actual and rendered["fidelity"]["status"]=="PASS"
    compiled=TexCompiler(timeout=120).compile(output,"slides.tex",tmp_path/"build",trusted=True)
    (tmp_path/"compile_result.json").write_text(json.dumps(compiled,ensure_ascii=False,indent=2),encoding="utf-8")
    assert compiled["status"]=="FAIL" and compiled["pdf_path"] is None
    errors=[i for i in compiled["issues"] if i.get("severity")=="blocking" and i.get("location",{}).get("source_line")]
    assert errors and any(i["location"].get("file","").endswith((".tex",".vrb")) for i in errors),compiled
    assert any("array" in i["message"].lower() for i in errors),compiled
    assert compiled["log_paths"] and all(Path(path).is_file() for path in compiled["log_paths"])
    assert (output/"slides.tex").is_file()
    assert table["id"] in rendered["source_map"]
