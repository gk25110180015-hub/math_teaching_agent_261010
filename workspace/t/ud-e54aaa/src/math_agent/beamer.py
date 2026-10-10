"""Deterministic Beamer rendering, semantic segmentation and independent source audit."""
from __future__ import annotations
import hashlib
import json
from math import ceil
from pathlib import Path
import re
import shutil
from .parsing import _group, _optional, semantic_chunks, uncomment, preflight_tex, _structural_tokens
from .references import theme_status
from .config import text_budgets

BLOCKS={"definition":"定义","theorem":"定理","proposition":"命题","property":"性质","example_statement":"例题","corollary":"推论"}
ALLOWED_SIZES={"large","normalsize","small","footnotesize"}

def escape_text(text):
    return "".join({"\\":r"\textbackslash{}","{":r"\{","}":r"\}","%":r"\%","&":r"\&","#":r"\#","_":r"\_","$":r"\$","~":r"\textasciitilde{}","^":r"\textasciicircum{}"}.get(c,c) for c in str(text))

def unit_body(unit):
    raw=unit["raw_tex"]
    env=unit.get("environment")
    if env and unit["kind"] not in {"opaque_tex","figure","table"}:
        first=re.match(r"\s*\\begin\{"+re.escape(env)+r"\}",raw)
        last=re.search(r"\\end\{"+re.escape(env)+r"\}\s*$",raw)
        if first and last:
            title,start=_optional(raw,first.end())
            return _presentation_tex(((r"\textbf{"+title+r"}\par"+"\n") if title else "")+raw[start:last.start()])
    if unit["kind"] in {"proof","example_solution"}:
        return _presentation_tex(re.sub(r"^\s*\\textbf\{(?:解|证明)[:：]?\}","",raw,count=1))
    return _presentation_tex(raw)

def _presentation_tex(raw):
    # A narrowly specified enumitem -> Beamer display-label adapter, never math rewriting.
    return raw.replace(r"\begin{enumerate}[label=(\arabic*),leftmargin=2em]",r"\begin{enumerate}[(1)]")

def visible_text_count(tex):
    text=uncomment(tex)
    text=re.sub(r"\$\$.*?\$\$|\\\[.*?\\\]|\$[^$]*\$", "",text,flags=re.S)
    text=re.sub(r"\\[a-zA-Z@]+\*?", "",text)
    cjk=sum(1 for c in text if "\u3400"<=c<="\u9fff")
    latin=sum(1 for c in text if c.isascii() and c.isalnum())
    return cjk+(latin+1)//2

def _measure(tex):
    count=visible_text_count(tex)
    displays=len(re.findall(r"\\\[|\$\$|\\begin\{(?:align\*?|equation\*?|gather\*?|cases|matrix|tabularx|tabular)\}",tex))
    linebreaks=len(re.findall(r"\\\\",tex))
    clean=uncomment(tex)
    paragraphs=max(0,len(re.findall(r"\r?\n[ \t\r]*\n",clean))-1)
    nested_blocks=re.findall(r"\\begin\{(theorem|definition|proposition|example|custom|proofdetail|solution)\}",clean)
    block_weights={"theorem":65,"definition":65,"proposition":65,"example":65,"custom":35,"proofdetail":20,"solution":20}
    headings=len(re.findall(r"\\(?:sub)*section\*?\{",clean))
    list_items=len(re.findall(r"\\(?:item|bibitem)(?![A-Za-z@])",clean))
    overhead=sum(block_weights[name] for name in nested_blocks)+headings*40+paragraphs*12+list_items*12
    score=count+displays*65+linebreaks*24+overhead
    return {"visible_text_count":count,"formula_blocks":displays,"explicit_line_breaks":linebreaks,"structural_overhead_score":overhead,"heuristic_score":score,"calibration_status":"uncalibrated","geometry_status":"NOT_RUN"}

def _size(tex):
    metrics=_measure(tex);config=text_budgets()
    for name in ("normalsize","small","footnotesize"):
        budget=getattr(config,name)
        if metrics["visible_text_count"]<=budget.hard and metrics["heuristic_score"]<=budget.soft+80:return name
    return "footnotesize"

def _semantic_boundaries(text):
    """Complete paragraphs/sentences outside math, braces and environments."""
    chunks=semantic_chunks(text)
    # Statement/proof/figure environments supply complete additional boundaries.
    ends=[];stack=[]
    for a,b,command,name in _structural_tokens(uncomment(text),0,len(text)):
        if command.startswith(r"\begin"):stack.append(name)
        elif command.startswith(r"\end") and stack and stack[-1]==name:
            stack.pop()
            if not stack and name in {"theorem","proofdetail","proof","solution","custom","application","center","figure"}:ends.append(b)
    if ends:
        boundaries=sorted({b for a,b in chunks}|set(ends)|{len(text)})
        refined=[];start=0
        for end in boundaries:
            if text[start:end].strip():refined.append((start,end));start=end
        if start<len(text) and refined:refined[-1]=(refined[-1][0],len(text))
        chunks=refined
    if len(chunks)>1:return chunks
    clean=uncomment(text);bounds=[];start=0;depth=0;env=[];math=None;i=0
    while i<len(clean):
        if clean[i]=="\\":
            m=re.match(r"\\(begin|end)\{([^}]+)\}",clean[i:])
            if m:
                if m[1]=="begin":env.append(m[2])
                elif env and env[-1]==m[2]:env.pop()
                i+=len(m[0]);continue
            if clean[i:i+2] in {r"\[",r"\("}:math=clean[i:i+2];i+=2;continue
            if clean[i:i+2] in {r"\]",r"\)"}:math=None;i+=2;continue
            i+=2;continue
        if clean[i]=="$":
            token="$$" if clean[i:i+2]=="$$" else "$";math=None if math==token else token;i+=len(token);continue
        if not math:
            if clean[i]=="{":depth+=1
            elif clean[i]=="}":depth-=1
            elif clean[i] in "。！？" and depth==0 and not env:
                bounds.append((start,i+1));start=i+1
        i+=1
    if start<len(text):bounds.append((start,len(text)))
    return bounds or [(0,len(text))]

def _list_items(text,command="item"):
    clean=uncomment(text);stack=[];items=[]
    for match in re.finditer(r"\\(begin|end)\{([^}]+)\}|\\"+re.escape(command)+r"(?![A-Za-z@])",clean):
        if match[0].startswith(r"\begin"):stack.append(match[2])
        elif match[0].startswith(r"\end"):
            if stack and stack[-1]==match[2]:stack.pop()
        elif not stack:items.append(match.start())
    if len(items)<2:return [(0,len(text))]
    return [(0 if j==0 else a,items[j+1] if j+1<len(items) else len(text)) for j,a in enumerate(items)]

def _unit_segments(unit,split_long):
    """Exact source intervals plus separately labelled repeated environment scaffolds."""
    raw=unit_body(unit)
    complex_container=unit.get("environment") in {"custom","extra","application"} and any(x in raw for x in (r"\begin{tikzpicture}",r"\begin{theorem}",r"\begin{proofdetail}"))
    if not split_long or (_measure(raw)["heuristic_score"]<=400 and not complex_container):return [(0,len(raw),"","")]
    if unit["kind"] in set(BLOCKS) or unit.get("environment") in {"custom","extra","application"}:
        list_begin=re.search(r"\\begin\{(enumerate|itemize)\}",raw)
        if list_begin and re.search(r"\\begin\{(?:tikzpicture|center|theorem|proofdetail|proof)\}",raw[:list_begin.start()]):
            # Repeating a preceding diagram/proof on every item defeats semantic pagination.
            list_begin=None
        if list_begin:
            name=list_begin[1];stack=[];list_close=None
            for match in re.finditer(r"\\(begin|end)\{([^}]+)\}",raw[list_begin.start():]):
                if match[1]=="begin":stack.append(match[2])
                elif stack and stack[-1]==match[2]:
                    stack.pop()
                    if not stack:
                        list_close=(list_begin.start()+match.start(),list_begin.start()+match.end());break
            if list_close:
                _,inner_start=_optional(raw,list_begin.end())
                items=_list_items(raw[inner_start:list_close[0]])
                if len(items)>1:
                    ancestors=[]
                    for _,_,command,environment in _structural_tokens(uncomment(raw),0,list_begin.start()):
                        if command.startswith(r"\begin"):ancestors.append(environment)
                        elif command.startswith(r"\end") and ancestors and ancestors[-1]==environment:ancestors.pop()
                    suffix=raw[list_close[0]:list_close[1]]+"".join(r"\end{"+env+"}" for env in reversed(ancestors))
                    result=[]
                    for j,(a,b) in enumerate(items):
                        prefix=raw[:inner_start] if j else ""
                        if j and name=="enumerate":prefix+=r"\setcounter{enumi}{"+str(j)+"}"
                        result.append((0 if j==0 else inner_start+a,len(raw) if j==len(items)-1 else inner_start+b,prefix,suffix if j<len(items)-1 else ""))
                    return result
        # A definition/statement or exercise cannot lose its assumptions at a paragraph break.
        if unit["kind"] in set(BLOCKS):return [(0,len(raw),"","")]
    begin=re.match(r"\s*\\begin\{(custom|application|extra|enumerate|itemize|thebibliography|idea|warning|remark)\}",raw)
    if begin:
        name=begin[1];closing=re.search(r"\\end\{"+name+r"\}\s*$",raw)
        if closing:
            p=begin.end()
            if name in {"custom","thebibliography"}:_,p=_group(raw,p)
            else:_,p=_optional(raw,p)
            inner=raw[p:closing.start()]
            bounds=_list_items(inner,"bibitem" if name=="thebibliography" else "item") if name in {"enumerate","itemize","thebibliography"} else _semantic_boundaries(inner)
            if len(bounds)>1:
                result=[]
                for j,(a,b) in enumerate(bounds):
                    start=0 if j==0 else p+a
                    end=len(raw) if j==len(bounds)-1 else p+b
                    prefix=raw[:p] if j else ""
                    if j and name=="enumerate":prefix+=r"\setcounter{enumi}{"+str(j)+"}"
                    suffix=raw[closing.start():] if j<len(bounds)-1 else ""
                    result.append((start,end,prefix,suffix))
                return result
    bounds=_semantic_boundaries(raw)
    if bounds:
        bounds[0]=(0,bounds[0][1]);bounds[-1]=(bounds[-1][0],len(raw))
        bounds=[(0 if j==0 else bounds[j-1][1],b) for j,(a,b) in enumerate(bounds)]
    return [(a,b,"","") for a,b in bounds]


def _pack_unit_segments(unit,segments):
    """Pack adjacent complete steps without duplicating their environment scaffolds."""
    raw=unit_body(unit);packed=[]
    capacity=text_budgets().footnotesize.soft+80
    for start,end,prefix,suffix in segments:
        if packed:
            a,b,previous_prefix,previous_suffix=packed[-1]
            candidate=previous_prefix+raw[a:end]+suffix
            # A diagram is a complete visual module; do not crowd it with nearby prose.
            if b==start and r"\begin{tikzpicture}" not in candidate and _measure(candidate)["heuristic_score"]<=capacity and visible_text_count(candidate)<=text_budgets().footnotesize.hard:
                packed[-1]=(a,end,previous_prefix,suffix)
                continue
        packed.append((start,end,prefix,suffix))
    return packed


def _toc_groups(sections):
    """One complete transition group; legal fonts, stable columns, then explicit pages."""
    entries=list(enumerate(sections))
    def divide(items,columns,chars_per_line):
        weights=[max(1,ceil((visible_text_count(s["title"])+4)/chars_per_line)) for _,s in items]
        if columns==1:return [items],sum(weights)
        if len(items)<2:return [items],sum(weights)
        cut=min(range(1,len(items)),key=lambda n:max(sum(weights[:n]),sum(weights[n:])))
        return [items[:cut],items[cut:]],max(sum(weights[:cut]),sum(weights[cut:]))
    choices=[("normalsize",1,10,36),("small",1,12,42),("footnotesize",1,14,48),("normalsize",2,10,17),("small",2,12,20),("footnotesize",2,14,23)]
    for size,columns,rows,width in choices:
        groups,height=divide(entries,columns,width)
        if height<=rows:return [{"text_size":size,"columns":groups}]
    # Greedy page groups retain full headings and original order; never add ellipses.
    result=[];remaining=entries
    while remaining:
        count=1
        for n in range(1,len(remaining)+1):
            _,height=divide(remaining[:n],2,23)
            if height>14:break
            count=n
        columns,_=divide(remaining[:count],2,23)
        result.append({"text_size":"footnotesize","columns":columns})
        remaining=remaining[count:]
    return result

def _omitted(plan):
    omitted=set()
    for item in plan.get("omissions",[]):
        if isinstance(item,str):raise ValueError("Omission requires an explicit authorization record")
        kind=item.get("kind") or item.get("authorization_type") or item.get("category") or item.get("type")
        if kind not in {"user_authorized_omission","policy_omission"}:raise ValueError("Model-suggested omissions cannot be executed")
        if kind=="user_authorized_omission" and not item.get("decision_id"):raise ValueError("User omission lacks decision ID")
        if kind=="policy_omission" and not item.get("policy_evidence"):raise ValueError("Policy omission requires condition/dependency audit evidence")
        if "unit_id" in item:omitted.add(item["unit_id"])
        omitted.update(item.get("unit_ids",[]))
    return omitted

def _normal(tex):
    # Only whitespace/comments are presentation-insensitive. Math operators stay exact.
    return re.sub(r"\s+","",uncomment(tex))

def _scaffold_hash(tex):
    return hashlib.sha256(tex.replace("\r\n","\n").replace("\r","\n").encode("utf-8")).hexdigest()

def check_fidelity(parsed,plan,tex:str)->dict:
    issues=[]
    try:omitted=_omitted(plan)
    except ValueError as exc:return {"status":"FAIL","issues":[{"rule_id":"FID-AUTH","severity":"blocking","message":str(exc)}]}
    by_id={u["id"]:u for u in parsed["units"]}
    # Audit text between actual emitted markers; never trusts source_map metadata.
    pattern=r"% SOURCE-BEGIN ([A-Za-z0-9_.-]+) (\d+) (\d+)\r?\n(.*?)\r?\n% SOURCE-END \1"
    actual={};actual_order=[]
    for m in re.finditer(pattern,tex,re.S):
        uid,start,end=m[1],int(m[2]),int(m[3])
        if uid not in by_id:
            issues.append({"rule_id":"FID-ADDITION","severity":"blocking","message":f"Unknown output source unit {uid}"});continue
        actual.setdefault(uid,[]).append((start,end,m[4]))
        if not actual_order or actual_order[-1]!=uid:actual_order.append(uid)
    expected_order=[uid for section in plan.get("sections",parsed["sections"]) for uid in section.get("source_unit_ids",[]) if uid in by_id and uid not in omitted and by_id[uid]["kind"]!="presentation_scaffold" and by_id[uid].get("source_visibility")!="inactive"]
    if actual_order!=expected_order:
        issues.append({"rule_id":"FID-ORDER","severity":"blocking","message":"Actual output unit order differs from the confirmed content plan","expected":expected_order,"actual":actual_order})
    for uid,unit in by_id.items():
        if unit["kind"]=="presentation_scaffold" or unit.get("source_visibility")=="inactive":continue
        if uid in omitted:
            if uid in actual:issues.append({"rule_id":"FID-OMISSION","severity":"blocking","unit_id":uid,"message":"Authorized deletion remains in output"})
            continue
        body=unit_body(unit);parts=actual.get(uid,[]);position=0
        if not parts:issues.append({"rule_id":"FID-MISSING","severity":"blocking","unit_id":uid,"message":"Source unit absent from actual output"});continue
        for start,end,rendered in parts:
            if start!=position or end<start or end>len(body) or _normal(rendered)!=_normal(body[start:end]):
                issues.append({"rule_id":"FID-CHANGED","severity":"blocking","unit_id":uid,"message":"Actual TeX differs from source or has non-contiguous source intervals"})
            position=end
        if position!=len(body):issues.append({"rule_id":"FID-MISSING","severity":"blocking","unit_id":uid,"message":"Actual source intervals do not cover full original unit"})
    addition_pattern=r"% ADDITION-BEGIN ([A-Za-z0-9_.-]+) ([A-Za-z0-9_.-]+)\r?\n(.*?)\r?\n% ADDITION-END \1"
    actual_additions={}
    for match in re.finditer(addition_pattern,tex,re.S):actual_additions.setdefault(match[1],[]).append(match)
    authorized={a.get("id") or a.get("addition_id"):a for a in plan.get("additions",[])}
    for aid,matches in actual_additions.items():
        if aid not in authorized:issues.append({"rule_id":"FID-ADDITION","severity":"blocking","message":"Unapproved addition in output","addition_id":aid})
    section_titles={s["id"]:escape_text(s["title"]) for s in plan.get("sections",[])}
    for aid,addition in authorized.items():
        matches=actual_additions.get(aid,[])
        if len(matches)!=1:
            issues.append({"rule_id":"FID-ADDITION","severity":"blocking","message":"Authorized addition absent or duplicated","addition_id":aid});continue
        match=matches[0];sid=addition.get("insertion_location")
        current_title=None
        for heading in re.finditer(r"\\section\{",uncomment(tex[:match.start()])):
            try:current_title,_=_group(tex,heading.end()-1)
            except ValueError:pass
        if match[2]!=sid or current_title!=section_titles.get(sid) or _normal(match[3])!=_normal(addition.get("new_content","")):
            issues.append({"rule_id":"FID-ADDITION","severity":"blocking","message":"Addition text or actual section differs from authorization","addition_id":aid})
    # Compare non-source output with renderer-owned scaffold, detecting unmarked injected math.
    expected_scaffold=plan.get("_render_scaffold_hash")
    scaffold=re.sub(pattern,"% SOURCE-PAYLOAD",tex,flags=re.S)
    if expected_scaffold and _scaffold_hash(scaffold)!=expected_scaffold:
        issues.append({"rule_id":"FID-EXTRA","severity":"blocking","message":"Actual non-source output differs from deterministic authorized scaffold"})
    return {"status":"FAIL" if issues else "PASS","issues":issues,"evidence":"Independent comparison of actual source payload strings and exact contiguous original intervals; scaffold fingerprint checked when supplied", "checked_units":len(by_id)-len(omitted),"limitations":["Whitespace/comments ignored; no claim of semantic equivalence for rewritten mathematics"]}

def _custom_preamble(parsed):
    definitions=parsed.get("macros",{}).get("definitions",[])
    out=[r"\newenvironment{proofdetail}{\par\noindent\textbf{证明：}\quad}{\par}",r"\renewenvironment{solution}{\par\noindent\textbf{解：}\quad}{\par}"]
    # Preserve mathematical macros, avoid article layout/counter redefinitions.
    exclude={"textfraction","topfraction","bottomfraction","floatpagefraction","figurename","tablename","bec"}
    for d in definitions:
        if d["command"] in {"newcommand","providecommand","DeclareMathOperator","mdfdefinestyle"} and d["name"] not in exclude:
            out.append(d["raw_tex"])
        elif d["command"] in {"newenvironment","NewDocumentEnvironment"} and d["name"] not in {"definition","theorem","proposition","example","proof","solution","proofdetail","exercise","problem","conclusion","remark","property","corollary"}:
            out.append(d["raw_tex"])
    return "\n".join(out)

def render_beamer(parsed:dict,plan:dict,output_dir:Path,reference_root:Path|None=None)->dict:
    output_dir=Path(output_dir);output_dir.mkdir(parents=True,exist_ok=True)
    omitted=_omitted(plan)
    units={u["id"]:u for u in parsed["units"]}
    unknown=omitted-set(units)
    if unknown:raise ValueError("Unknown omitted units: "+", ".join(sorted(unknown)))
    issues=[];theme_hash=None
    for unit in parsed["units"]:
        if unit["id"] in omitted:continue
        if re.search(r"\\(?:tiny|scriptsize|fontsize|resizebox|scalebox)(?![A-Za-z@])|\\begin\{frame\}\[[^\]]*shrink",uncomment(unit["raw_tex"])):
            issues.append({"rule_id":"B-16","severity":"blocking","unit_id":unit["id"],"message":"Source fragment contains forbidden text size/scaling; explicit faithful adaptation required"})
        if unit.get("reference_labels"):
            issues.append({"rule_id":"FID-NUMBERING","severity":"review","unit_id":unit["id"],"message":"Original cross-reference labels retained; verify displayed theorem/equation numbering against source after compilation","labels":unit["reference_labels"]})
    layout_config=plan.get("_layout",{})
    forced_size=layout_config.get("font_size")
    budgets=text_budgets()
    if forced_size and forced_size not in ALLOWED_SIZES:raise ValueError("Only the four permitted text sizes may be rendered")
    split_long=layout_config.get("split_long",True)
    source_root=Path(parsed["root"]).resolve() if parsed.get("root") else None
    if source_root:
        for dep in parsed.get("dependencies",[]):
            if dep.get("kind")=="image" and dep.get("resolved"):
                resource=(source_root/dep["resolved"]).resolve()
                if not resource.is_relative_to(source_root):raise ValueError("Image outside source snapshot")
                target=output_dir/dep["resolved"];target.parent.mkdir(parents=True,exist_ok=True)
                shutil.copyfile(resource,target)
    theme=plan.get("theme","default")
    theme_line=""
    if theme=="fduclassroom":
        status=theme_status(reference_root)["fduclassroom"]
        if not status["available"]:raise ValueError(status["reason"])
        candidate=status["candidates"][0];source=Path(candidate["path"])
        shutil.copyfile(source,output_dir/source.name);theme_hash=candidate["sha256"]
        for dep in candidate["dependencies"]:
            dep_source=Path(dep["path"]);rel=dep_source.relative_to(source.parent)
            target=output_dir/rel;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(dep_source,target)
        theme_line=r"\usetheme{fduclassroom}"
    elif theme!="default":raise ValueError("Unknown theme")
    adapter=r'''\setbeamerfont{normal text}{size=\normalsize}
\setbeamerfont{title}{size=\large}
\setbeamerfont{subtitle}{size=\normalsize}
\setbeamerfont{frametitle}{size=\large}
\setbeamerfont{framesubtitle}{size=\small}
\setbeamerfont{block title}{size=\normalsize}
\setbeamerfont{block body}{size=\normalsize}
\setbeamerfont{section in toc}{size=\normalsize}
\setbeamerfont{section in head/foot}{size=\footnotesize}
\setbeamerfont{author in head/foot}{size=\footnotesize}
\setbeamerfont{title in head/foot}{size=\footnotesize}
\setbeamerfont{date in head/foot}{size=\footnotesize}
\setbeamertemplate{navigation symbols}{}
\setbeamertemplate{itemize item}{\normalsize\textbullet}
\setbeamertemplate{itemize subitem}{\small\textbullet}
\setbeamercolor{structure}{fg=blue!65!black}
\setbeamercolor{block title}{fg=blue!65!black,bg=blue!8}
\setbeamercolor{block body}{fg=black,bg=blue!3}
'''
    if theme=="default":
        adapter+=r"\setbeamertemplate{footline}{\leavevmode\hbox to\paperwidth{\hfill{\footnotesize\insertframenumber}\hspace*{1em}}\vskip3pt}"+"\n"
    else:
        adapter+=r'''\setbeamertemplate{headline}{\leavevmode
\begin{beamercolorbox}[wd=\paperwidth,ht=3.6ex,dp=1.5ex,center]{palette secondary}
{\footnotesize\strut\insertsectionhead}
\end{beamercolorbox}}
'''
    (output_dir/"workflow_style.tex").write_text(adapter,encoding="utf-8")
    (output_dir/"workflow_fonts.tex").write_text("% ctex fontset=fandol; system fonts are not redistributed.\n",encoding="utf-8")
    lines=[r"\documentclass[aspectratio=169,10pt,fontset=fandol]{ctexbeamer}",r"\usepackage{amsmath,amssymb,mathtools,bm,mathrsfs}",r"\usepackage{graphicx,booktabs,array,tabularx,multirow}",r"\usepackage{tikz,pgfplots,xparse,xstring,mdframed}",r"\usetikzlibrary{arrows.meta,calc,angles,positioning,shapes.geometric,graphs}",r"\pgfplotsset{compat=1.18}",theme_line,r"\input{workflow_style.tex}",r"\input{workflow_fonts.tex}",_custom_preamble(parsed),r"\title{"+escape_text(plan.get("title","数学课件"))+"}",r"\begin{document}"]
    frames=[];source_map={};layouts=[]
    sections=plan.get("sections",parsed["sections"])
    def add_frame(title,body,kind,section_id,text_size="normalsize",segments=None):
        fid=f"F{len(frames)+1:03}"
        content="\n".join(body)
        frames.append({"id":fid,"frame_id":fid,"kind":kind,"title":title,"section_id":section_id,"text_size":text_size,"segments":segments or []})
        lines.extend([f"% FRAME-ID {fid}",r"\begin{frame}[t,fragile]{"+escape_text(title)+"}","\\"+text_size,content,r"\end{frame}"])
        layouts.append({"frame_id":fid,"text_size":text_size,**_measure(content),"split_reason":"complete semantic module or paragraph boundary","geometry_status":"NOT_RUN"})
        return fid
    for ordinal,section in enumerate(sections):
        sid=section["id"];stitle=section["title"]
        lines.append(r"\section{"+escape_text(stitle)+"}")
        # Legal type size/spacing and stable columns precede additional directory pages.
        toc_groups=_toc_groups(sections)
        for group_no,toc in enumerate(toc_groups,1):
            body=[];toc_size=toc["text_size"];columns=toc["columns"]
            if len(columns)>1:body.append(r"\begin{columns}[T,onlytextwidth]")
            for column in columns:
                if len(columns)>1:body.append(r"\begin{column}{0.48\textwidth}")
                for idx,other in column:
                    color="black" if idx<ordinal else "blue" if idx==ordinal else "gray!40"
                    body.append(r"{\color{"+color+"}\\"+toc_size+" "+str(idx+1)+". "+escape_text(other["title"])+r"\par}\vspace{0.22em}")
                if len(columns)>1:body.append(r"\end{column}")
            if len(columns)>1:body.append(r"\end{columns}")
            add_frame("目录" if len(toc_groups)==1 else f"目录（{group_no}/{len(toc_groups)}）",body,"directory",sid,toc_size)
        selected=[]
        for uid in section.get("source_unit_ids",[]):
            if uid not in units:raise ValueError(f"Plan refers to unknown source unit {uid}")
            if uid not in omitted and units[uid]["kind"]!="presentation_scaffold" and units[uid].get("source_visibility")!="inactive":selected.append(units[uid])
        modules=[]
        for unit in selected:
            target=unit["semantic_relations"].get("solution_of") or unit["semantic_relations"].get("proof_of") or unit["semantic_relations"].get("illustrates")
            adjacent_explanations=modules and unit["kind"]=="explanation" and all(u["kind"]=="explanation" for u in modules[-1]) and _measure("\n".join(unit_body(u) for u in [*modules[-1],unit]))["heuristic_score"]<=320
            if modules and (target==modules[-1][0]["id"] or adjacent_explanations):modules[-1].append(unit)
            else:modules.append([unit])
        for module in modules:
            full="\n".join(unit_body(u) for u in module)
            batches=[module] if not split_long or _measure(full)["heuristic_score"]<=400 else [[u] for u in module]
            for batch in batches:
                fragments=[]
                for unit in batch:
                    segments=_unit_segments(unit,split_long)
                    if split_long:segments=_pack_unit_segments(unit,segments)
                    fragments.extend((unit,a,b,prefix,suffix) for a,b,prefix,suffix in segments)
                # Combined short module stays one logical frame; split only long complete paragraphs.
                grouped=[fragments] if not split_long or (len(fragments)==len(batch) and _measure("\n".join(unit_body(u)[a:b] for u,a,b,prefix,suffix in fragments))["heuristic_score"]<=400) else [[f] for f in fragments]
                for continuation,group in enumerate(grouped,1):
                    raw="\n".join(prefix+unit_body(u)[a:b]+suffix for u,a,b,prefix,suffix in group);size=forced_size or _size(raw);rendered=[];segments=[]
                    if _measure(raw)["visible_text_count"]>getattr(budgets,size).hard:
                        issues.append({"rule_id":"VISIBLE-TEXT-BUDGET","severity":"blocking","unit_id":group[0][0]["id"],"message":"Actual visible text estimate exceeds the configured hard budget","visible_text_count":_measure(raw)["visible_text_count"],"hard_budget":getattr(budgets,size).hard})
                    if split_long and _measure(raw)["heuristic_score"]>400:
                        issues.append({"rule_id":"LAYOUT-ESTIMATE","severity":"review","unit_id":group[0][0]["id"],"message":"A complete statement/formula has high uncalibrated geometric score; preserve it and use actual compile/geometry measurements"})
                    for k,(unit,a,b,prefix,suffix) in enumerate(group):
                        uid=unit["id"];kind=unit["kind"]
                        if k and kind in {"example_solution","proof"}:rendered.append(r"\pause")
                        if kind in BLOCKS:rendered.append(r"\begin{block}{"+BLOCKS[kind]+"}")
                        rendered.append("{\\"+size)
                        if r"\begin{enumerate}[(1)]" in prefix+unit_body(unit)[a:b]:
                            rendered.append(r"\setbeamertemplate{enumerate mini template}[default]")
                        coordinate_scale=None
                        if split_long and r"\begin{tikzpicture}" in unit_body(unit)[a:b]:
                            if re.search(r"transform\s+shape",uncomment(unit_body(unit)[a:b])):
                                issues.append({"rule_id":"TIKZ-TEXT-SCALING","severity":"review","unit_id":uid,"message":"TikZ transform shape prevents safe automatic coordinate scaling; inspect the original diagram"})
                            else:
                                coordinate_scale=0.75
                                rendered.extend(["% PRESENTATION-SCAFFOLD isotropic coordinates; node font size unchanged",r"\tikzset{every picture/.append style={scale=0.75}}"])
                        if kind in {"example_solution","proof"}:rendered.append(r"\textbf{"+("证明：" if kind=="proof" else "解：")+"}")
                        if prefix:rendered.extend(["% REPEATED-CONTEXT environment continuation",prefix])
                        rendered.extend([f"% SOURCE-BEGIN {uid} {a} {b}",unit_body(unit)[a:b],f"% SOURCE-END {uid}"])
                        if suffix:rendered.extend(["% PRESENTATION-SCAFFOLD close continued environment",suffix])
                        rendered.append("}")
                        if kind in BLOCKS:rendered.append(r"\end{block}")
                        segments.append({"unit_id":uid,"start":a,"end":b,"content_hash":unit["content_hash"],"repeated_context":prefix,"presentation_scaffold":suffix,"coordinate_scale":coordinate_scale})
                    base_title="参考文献" if all(u.get("environment")=="thebibliography" for u,_,_,_,_ in group) else stitle
                    title=base_title if continuation==1 else f"{base_title}（续{continuation-1}）"
                    fid=add_frame(title,rendered,"content",sid,size,segments)
                    for segment in segments:source_map.setdefault(segment["unit_id"],[]).append({"frame_id":fid,**segment})
        # Additions appear at the confirmed section, preserving priority and attribution.
        for addition in plan.get("additions",[]):
            if addition.get("insertion_location")!=sid:continue
            aid=addition.get("id") or addition.get("addition_id")
            if not aid or not addition.get("decision_id"):raise ValueError("Addition requires an explicit decision and addition ID")
            text=addition.get("new_content","")
            if preflight_tex(text):raise ValueError("Authorized addition failed TeX preflight")
            add_frame(stitle,[r"\normalsize",f"% ADDITION-BEGIN {aid} {sid}",text,f"% ADDITION-END {aid}"],"authorized_addition",sid,segments=[{"addition_id":aid,"decision_id":addition["decision_id"],"priority":addition.get("priority"),"format":"math_tex"}])
    if any(a.get("insertion_location") not in {s["id"] for s in sections} for a in plan.get("additions",[])):
        raise ValueError("Addition insertion location does not exist in the confirmed plan")
    lines.append(r"\end{document}")
    tex="\n".join(lines)+"\n"
    scaffold=re.sub(r"% SOURCE-BEGIN ([A-Za-z0-9_.-]+) (\d+) (\d+)\r?\n(.*?)\r?\n% SOURCE-END \1","% SOURCE-PAYLOAD",tex,flags=re.S)
    scaffold_hash=_scaffold_hash(scaffold)
    # Returned fingerprint is separate from the approved content plan.
    (output_dir/"slides.tex").write_text(tex,encoding="utf-8",newline="")
    return {"main_file":"slides.tex","source_map":source_map,"presentation_source_units":[{"unit_id":u["id"],"source_spans":u["source_spans"],"content_hash":u["content_hash"],"raw_tex":u["raw_tex"],"reason":"Pure article page-layout scaffold; no mathematical content"} for u in parsed["units"] if u["kind"]=="presentation_scaffold"],"inactive_source_units":[{"unit_id":u["id"],"source_spans":u["source_spans"],"content_hash":u["content_hash"],"reason":u["inactive_reason"]} for u in parsed["units"] if u.get("source_visibility")=="inactive"],"frame_plan":frames,"layout_plan":layouts,"issues":issues,"theme_hash":theme_hash,"render_scaffold_hash":scaffold_hash,"fidelity":check_fidelity(parsed,{**plan,"_render_scaffold_hash":scaffold_hash},tex),"geometry_status":"NOT_RUN"}
