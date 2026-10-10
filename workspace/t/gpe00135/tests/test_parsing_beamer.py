from pathlib import Path
import zipfile
from io import BytesIO
import pytest
from math_agent.parsing import parse_tex, preflight_tex, safe_extract_zip
from math_agent.beamer import render_beamer, check_fidelity
from math_agent.references import theme_status

SOURCE = r'''\documentclass{ctexart}
\newtheorem{mytheorem}{定理}
\begin{document}
\section{数列}
\begin{mytheorem}若 $a_n\to a$，则收敛数列有界。\end{mytheorem}
\begin{proof}由定义取 $\varepsilon=1$，尾项有界，有限前项亦有界。\end{proof}
\begin{example}[例 3]计算 $\lim_{n\to\infty}1/n$。\end{example}
\begin{solution}答案是 $0$。\end{solution}
\end{document}'''

def plan(parsed, omissions=None):
    return {"theme": "default", "title": "数列", "sections": parsed["sections"], "omissions": omissions or [], "additions": []}

def test_T06_explicit_example_omission_preserves_related_solution_identity(tmp_path):
    parsed = parse_tex(SOURCE)
    example = next(u for u in parsed["units"] if u["kind"] == "example_statement")
    solution = next(u for u in parsed["units"] if u["kind"] == "example_solution")
    assert solution["semantic_relations"]["solution_of"] == example["id"]
    omissions = [{"unit_id": u["id"], "kind": "user_authorized_omission", "decision_id": "D1"} for u in (example, solution)]
    render_beamer(parsed, plan(parsed, omissions), tmp_path)
    tex = (tmp_path / "slides.tex").read_text(encoding="utf-8")
    assert "计算" not in tex and "答案是" not in tex
    assert check_fidelity(parsed, plan(parsed, omissions), tex)["status"] == "PASS"

def test_T29_nested_environment_and_exact_spans():
    parsed = parse_tex(SOURCE)
    theorem = next(u for u in parsed["units"] if u["kind"] == "theorem")
    span = theorem["source_spans"][0]
    assert SOURCE[span["start"]:span["end"]] == theorem["raw_tex"]
    assert next(u for u in parsed["units"] if u["kind"] == "proof")["semantic_relations"]["proof_of"] == theorem["id"]

def test_T30_standard_math_macros_are_safe():
    assert not preflight_tex(r"$\coth x\setminus A\leqslant B\geqslant C$")

def test_T45_actual_output_omission_fails_even_with_claimed_source_marker(tmp_path):
    parsed = parse_tex(SOURCE)
    render_beamer(parsed, plan(parsed), tmp_path)
    tex = (tmp_path / "slides.tex").read_text(encoding="utf-8")
    assert check_fidelity(parsed, plan(parsed), tex)["status"] == "PASS"
    modified = tex.replace("尾项有界", "尾项无界")
    assert check_fidelity(parsed, plan(parsed), modified)["status"] == "FAIL"

def test_T38_forbidden_size_is_not_used(tmp_path):
    parsed = parse_tex(SOURCE)
    result = render_beamer(parsed, plan(parsed), tmp_path)
    tex = (tmp_path / "slides.tex").read_text(encoding="utf-8")
    assert "\\scriptsize" not in tex and "\\tiny" not in tex and "shrink" not in tex
    assert {f["text_size"] for f in result["frame_plan"]} <= {"footnotesize", "small", "normalsize", "large"}

@pytest.mark.parametrize("name", ["../escape.tex", "C:/escape.tex", "/escape.tex", "folder/../../escape.tex", "compiler.exe", ".latexmkrc"])
def test_T51_zip_unsafe_members_rejected(tmp_path, name):
    data = BytesIO()
    with zipfile.ZipFile(data, "w") as archive:
        archive.writestr(name, "x")
    with pytest.raises(ValueError):
        safe_extract_zip(data.getvalue(), tmp_path)

def test_T52_dangerous_tex_rejected():
    assert any(i["severity"] == "blocking" for i in preflight_tex(r"\openin0=C:/secret"))

def test_opaque_text_does_not_disappear():
    parsed = parse_tex(r"\begin{document}\begin{mystery}未知内容 $x<1$\end{mystery}\end{document}")
    assert any(u["kind"] == "opaque_tex" and "未知内容" in u["raw_tex"] for u in parsed["units"])

def test_verbatim_does_not_create_false_sections_or_environments():
    source=r'''\begin{document}\begin{verbatim}
\section{伪章节} \begin{fake} % literal
\end{verbatim}\end{document}'''
    parsed=parse_tex(source)
    assert len(parsed["units"])==1
    assert "伪章节" in parsed["units"][0]["raw_tex"]
    assert not parsed["issues"]

def test_long_proof_splits_only_complete_statements(tmp_path):
    proof="\n\n".join("这是一段完整的逻辑步骤。"*10 for _ in range(8))
    parsed=parse_tex(r"\begin{document}\section{证明}\begin{theorem}命题成立。\end{theorem}\begin{proof}"+proof+r"\end{proof}\end{document}")
    confirmed=plan(parsed);confirmed["_layout"]={"font_size":"footnotesize","split_long":True}
    result=render_beamer(parsed,confirmed,tmp_path)
    tex=(tmp_path/"slides.tex").read_text(encoding="utf-8")
    assert len(result["frame_plan"])>3
    assert check_fidelity(parsed,confirmed,tex)["status"]=="PASS"
    assert all(f["text_size"]=="footnotesize" for f in result["frame_plan"] if f["kind"]=="content")

def test_authorized_addition_uses_chosen_section(tmp_path):
    parsed=parse_tex(SOURCE+r" ")
    p=plan(parsed);p["additions"]=[{"id":"A1","decision_id":"D2","new_content":"补充例子","insertion_location":parsed["sections"][0]["id"],"priority":"必须"}]
    result=render_beamer(parsed,p,tmp_path)
    addition=next(f for f in result["frame_plan"] if f["kind"]=="authorized_addition")
    assert addition["section_id"]==p["additions"][0]["insertion_location"]
    tex=(tmp_path/"slides.tex").read_text(encoding="utf-8")
    assert check_fidelity(parsed,p,tex)["status"]=="PASS"
    assert check_fidelity(parsed,p,tex.replace("补充例子","篡改例子"))["status"]=="FAIL"

def test_authorized_math_addition_remains_tex_and_is_independently_audited(tmp_path):
    parsed=parse_tex(SOURCE);p=plan(parsed)
    p["additions"]=[{"id":"A2","decision_id":"D3","new_content":r"新增公式：$x\leqslant 1$。","insertion_location":parsed["sections"][0]["id"],"priority":"必须"}]
    result=render_beamer(parsed,p,tmp_path)
    tex=(tmp_path/"slides.tex").read_text(encoding="utf-8")
    assert r"$x\leqslant 1$" in tex
    assert result["fidelity"]["status"]=="PASS"
    assert check_fidelity(parsed,p,tex.replace(r"$x\leqslant 1$",r"$x\geqslant 1$"))["status"]=="FAIL"

def test_T32_definition_with_explicit_short_illustration_stays_together(tmp_path):
    parsed=parse_tex(r"\begin{document}\section{数列}\begin{definition}数列是定义在正整数上的函数。\end{definition}"+"\n\n"+r"例如 $a_n=1/n$ 是一个数列。\end{document}")
    result=render_beamer(parsed,plan(parsed),tmp_path)
    content=[f for f in result["frame_plan"] if f["kind"]=="content"]
    assert len(content)==1 and len(content[0]["segments"])==2

def test_T42_fdu_missing_resources_never_falls_back(tmp_path):
    (tmp_path/"beamerthemefduclassroom.sty").write_text(r"\includegraphics{resources/fudan}",encoding="utf-8")
    assert not theme_status(tmp_path)["fduclassroom"]["available"]
    parsed=parse_tex(SOURCE);p=plan(parsed);p["theme"]="fduclassroom"
    with pytest.raises(ValueError,match="缺少资源"):
        render_beamer(parsed,p,tmp_path/"output",tmp_path)

def test_T43_different_theme_hashes_require_selection(tmp_path):
    for n,source in [("第一章","%v1"),("第二章","%v2")]:
        p=tmp_path/n;p.mkdir();(p/"beamerthemefduclassroom.sty").write_text(source,encoding="utf-8")
    status=theme_status(tmp_path)["fduclassroom"]
    assert len(status["hashes"])==2 and not status["available"]

def test_T44_theme_copy_does_not_modify_original(tmp_path):
    root=tmp_path/"refs";root.mkdir()
    original=root/"beamerthemefduclassroom.sty";original.write_text(r"\ProvidesPackage{beamerthemefduclassroom}\setbeamerfont{title}{size=\LARGE}",encoding="utf-8")
    before=original.read_bytes()
    parsed=parse_tex(SOURCE);p=plan(parsed);p["theme"]="fduclassroom"
    render_beamer(parsed,p,tmp_path/"output",root)
    assert original.read_bytes()==before
    assert (tmp_path/"output"/original.name).read_bytes()==before
    assert r"\setbeamerfont{title}{size=\large}" in (tmp_path/"output"/"workflow_style.tex").read_text(encoding="utf-8")

def test_windows_crlf_source_does_not_double_carriage_returns(tmp_path):
    source=(r"\newcommand{\localmath}{"+"\n"+r"x+1"+"\n"+"}\n"+SOURCE).replace("\n","\r\n")
    parsed=parse_tex(source)
    result=render_beamer(parsed,plan(parsed),tmp_path)
    assert b"\r\r\n" not in (tmp_path/"slides.tex").read_bytes()
    normalized=(tmp_path/"slides.tex").read_text(encoding="utf-8")
    assert check_fidelity(parsed,{**plan(parsed),"_render_scaffold_hash":result["render_scaffold_hash"]},normalized)["status"]=="PASS"

def test_literal_false_branch_is_preserved_as_inactive_not_cut_across_frames(tmp_path):
    source=r"\begin{document}\section{数列}正文。\iffalse\begin{example}原稿已禁用的例题。\end{example}\fi\begin{definition}定义正文。\end{definition}\end{document}"
    parsed=parse_tex(source)
    inactive=[u for u in parsed["units"] if u.get("source_visibility")=="inactive"]
    assert len(inactive)==1 and inactive[0]["raw_tex"].endswith(r"\fi")
    p=plan(parsed);result=render_beamer(parsed,p,tmp_path)
    assert r"\iffalse" not in (tmp_path/"slides.tex").read_text(encoding="utf-8")
    assert result["inactive_source_units"][0]["unit_id"]==inactive[0]["id"]
    assert result["fidelity"]["status"]=="PASS"

def test_long_list_uses_complete_items_and_balanced_repeated_context(tmp_path):
    source=r"\begin{document}\section{题目}\begin{enumerate}"+"\r\n".join(r"\item "+"这是完整题目。"*20 for _ in range(8))+r"\end{enumerate}\end{document}"
    parsed=parse_tex(source);p=plan(parsed)
    result=render_beamer(parsed,p,tmp_path)
    tex=(tmp_path/"slides.tex").read_text(encoding="utf-8")
    assert 1<len([f for f in result["frame_plan"] if f["kind"]=="content"])<8
    assert tex.count(r"\item "+"这是完整题目。"*20)==8
    assert not preflight_tex(tex)
    assert check_fidelity(parsed,{**p,"_render_scaffold_hash":result["render_scaffold_hash"]},tex)["status"]=="PASS"

def test_named_statement_heading_is_preserved_inside_allowed_block(tmp_path):
    parsed=parse_tex(r"\begin{document}\section{极限}\begin{theorem}[Heine 定理]假设与结论。\end{theorem}\end{document}")
    result=render_beamer(parsed,plan(parsed),tmp_path)
    tex=(tmp_path/"slides.tex").read_text(encoding="utf-8")
    assert r"\begin{block}{定理}" in tex and r"\textbf{Heine 定理}" in tex
    assert result["fidelity"]["status"]=="PASS"

def test_nested_array_in_boxed_display_is_one_lossless_unit(tmp_path):
    formula=r"\[\boxed{\begin{array}{c}x=1\\y=2\end{array}}\]"
    parsed=parse_tex(r"\begin{document}\section{公式}"+formula+r"\end{document}")
    assert len(parsed["units"])==1 and parsed["units"][0]["raw_tex"]==formula
    result=render_beamer(parsed,plan(parsed),tmp_path)
    assert result["fidelity"]["status"]=="PASS"

def test_enumitem_numeric_label_adapter_preserves_item_math(tmp_path):
    source=r"\begin{document}\begin{definition}分类：\begin{enumerate}[label=(\arabic*),leftmargin=2em]\item $x<1$；\item $x\geq1$。\end{enumerate}\end{definition}\end{document}"
    parsed=parse_tex(source);result=render_beamer(parsed,plan(parsed),tmp_path)
    tex=(tmp_path/"slides.tex").read_text(encoding="utf-8")
    assert r"\begin{enumerate}[(1)]" in tex and r"$x\geq1$" in tex
    assert result["fidelity"]["status"]=="PASS"


def test_long_custom_list_splits_complete_items_with_balanced_wrapper(tmp_path):
    source=r"\newenvironment{custom}[1]{\par\textbf{#1}}{\par}\begin{document}\section{推导}\begin{custom}{等价关系}共同前提。\begin{itemize}"+"\n".join(r"\item "+"完整推导。"*30+r"\[x_n\to0\]" for _ in range(6))+r"\end{itemize}尾部结论。\end{custom}\end{document}"
    parsed=parse_tex(source);p=plan(parsed);result=render_beamer(parsed,p,tmp_path)
    content=[f for f in result["frame_plan"] if f["kind"]=="content"]
    assert len(content)==6
    tex=(tmp_path/"slides.tex").read_text(encoding="utf-8")
    assert not preflight_tex(tex)
    assert result["fidelity"]["status"]=="PASS"
    assert tex.count("尾部结论。")==1


def test_tikz_coordinate_adaptation_preserves_original_source_and_label_size(tmp_path):
    source=r"\begin{document}\section{图形}\begin{center}\begin{tikzpicture}[scale=3]\draw (0,0) circle (1);\node at (0,1.2) {坐标};\end{tikzpicture}\end{center}\end{document}"
    parsed=parse_tex(source);p=plan(parsed);p["_layout"]={"font_size":"footnotesize","split_long":True}
    result=render_beamer(parsed,p,tmp_path)
    tex=(tmp_path/"slides.tex").read_text(encoding="utf-8")
    assert r"every picture/.append style={scale=0.75}" in tex
    assert r"\begin{tikzpicture}[scale=3]" in tex
    assert "transform shape" not in tex
    assert result["fidelity"]["status"]=="PASS"


def test_diagram_before_list_is_not_repeated_as_list_context(tmp_path):
    source=r"\newenvironment{custom}[1]{\par\textbf{#1}}{\par}\begin{document}\section{图解}\begin{custom}{几何}\begin{center}\begin{tikzpicture}\draw (0,0)--(1,1);\end{tikzpicture}\end{center}\begin{itemize}"+"\n".join(r"\item "+"解释。"*40 for _ in range(4))+r"\end{itemize}\end{custom}\end{document}"
    parsed=parse_tex(source);result=render_beamer(parsed,plan(parsed),tmp_path)
    tex=(tmp_path/"slides.tex").read_text(encoding="utf-8")
    assert tex.count(r"\begin{tikzpicture}")==1
    assert result["fidelity"]["status"]=="PASS"


def test_article_only_page_layout_commands_do_not_create_blank_beamer_frames(tmp_path):
    source=r"\begin{document}\section{数学}实质内容 $x>0$。"+"\n\n"+r"\Needspace{0.62\textheight}"+"\n\n"+r"\clearpage\end{document}"
    parsed=parse_tex(source);result=render_beamer(parsed,plan(parsed),tmp_path)
    assert len([f for f in result["frame_plan"] if f["kind"]=="content"])==1
    assert len(result["presentation_source_units"])==2
    assert result["fidelity"]["status"]=="PASS"
