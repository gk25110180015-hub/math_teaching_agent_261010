"""Iteration 2 regressions: density improvements cannot sacrifice source coverage."""
from math_agent.parsing import parse_tex,preflight_tex
from math_agent.beamer import render_beamer,check_fidelity


def plan(parsed):
    return {"title":"布局回归","theme":"default","sections":parsed["sections"],"omissions":[],"additions":[],"_layout":{"split_long":True}}


def test_short_adjacent_explanations_share_a_readable_frame(tmp_path):
    source=r"\begin{document}\section{数列}首先约定 $n\in\mathbb N$。"+"\n\n"+r"这里 $a_n$ 表示第 $n$ 项。"+"\n\n"+r"由此可以逐项比较数列的取值。\end{document}"
    parsed=parse_tex(source);result=render_beamer(parsed,plan(parsed),tmp_path)
    content=[f for f in result["frame_plan"] if f["kind"]=="content"]
    assert len(content)==1 and len(content[0]["segments"])==3
    assert content[0]["text_size"]=="normalsize"
    assert result["fidelity"]["status"]=="PASS"


def test_long_proof_packs_whole_steps_instead_of_one_paragraph_per_slide(tmp_path):
    steps=[f"第{i}步，"+"这里保留完整的推导条件及数学论证。"*3+fr"\[a_{{{i}}}=a_{{{i-1}}}+1\]" for i in range(1,9)]
    source=r"\begin{document}\section{归纳证明}\begin{proof}"+"\n\n".join(steps)+r"\end{proof}\end{document}"
    parsed=parse_tex(source);p=plan(parsed);result=render_beamer(parsed,p,tmp_path)
    content=[f for f in result["frame_plan"] if f["kind"]=="content"]
    assert 1<len(content)<8
    actual=(tmp_path/"slides.tex").read_text(encoding="utf-8")
    assert not preflight_tex(actual)
    assert all(actual.count(step)==1 for step in steps)
    assert check_fidelity(parsed,{**p,"_render_scaffold_hash":result["render_scaffold_hash"]},actual)["status"]=="PASS"


def test_twelve_sections_use_legal_directory_capacity_before_multiple_pages(tmp_path):
    source=r"\begin{document}"+"".join(fr"\section{{章节{i}}}正文 $x={i}$。" for i in range(1,13))+r"\end{document}"
    parsed=parse_tex(source);result=render_beamer(parsed,plan(parsed),tmp_path)
    directory=[f for f in result["frame_plan"] if f["kind"]=="directory"]
    assert len(directory)==12
    assert {f["text_size"] for f in directory}<={"normalsize","small","footnotesize"}
    actual=(tmp_path/"slides.tex").read_text(encoding="utf-8")
    assert actual.count(r"\color{blue}")==12
    assert result["fidelity"]["status"]=="PASS"


def test_long_directory_uses_two_columns_and_keeps_all_headings(tmp_path):
    source=r"\begin{document}"+"".join(fr"\section{{主题{i}}}内容 $x={i}$。" for i in range(1,25))+r"\end{document}"
    parsed=parse_tex(source);result=render_beamer(parsed,plan(parsed),tmp_path)
    directory=[f for f in result["frame_plan"] if f["kind"]=="directory"]
    assert len(directory)==24
    actual=(tmp_path/"slides.tex").read_text(encoding="utf-8")
    assert r"\begin{columns}[T,onlytextwidth]" in actual
    assert actual.count(r"\color{blue}")==24
    assert actual.count("24. 主题24")==24
    assert not preflight_tex(actual)


def test_bibliography_pages_preserve_each_whole_item_once(tmp_path):
    entries=[fr"\bibitem{{K{i}}} 作者{i}。"+"真实书目完整条目。"*18 for i in range(1,7)]
    source=r"\begin{document}\section{正文}参见\cite{K1}。\begin{thebibliography}{99}"+"\n".join(entries)+r"\end{thebibliography}\end{document}"
    parsed=parse_tex(source);p=plan(parsed);result=render_beamer(parsed,p,tmp_path)
    actual=(tmp_path/"slides.tex").read_text(encoding="utf-8")
    assert 1<len([f for f in result["frame_plan"] if f["title"].startswith("参考文献")])<6
    assert all(actual.count(entry)==1 for entry in entries)
    assert not preflight_tex(actual)
    assert result["fidelity"]["status"]=="PASS"
