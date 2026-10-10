"""Conservative lossless source scanner. No TeX expansion or source execution."""
from __future__ import annotations
import hashlib
from io import BytesIO
from pathlib import Path, PurePosixPath
import re
import stat
import zipfile

KINDS = {"definition": "definition", "theorem": "theorem", "proposition": "proposition", "property": "property", "corollary": "corollary", "example": "example_statement", "solution": "example_solution", "proof": "proof", "proofdetail": "proof", "exercise": "exercise", "problem": "exercise", "remark": "remark", "figure": "figure", "table": "table", "explanation": "explanation", "intuition": "introduction"}
LABEL_KINDS = {"定义": "definition", "定理": "theorem", "命题": "proposition", "性质": "property", "推论": "corollary", "例": "example_statement", "例题": "example_statement", "证明": "proof", "解": "example_solution"}
STANDARD_MATH_COMMANDS = {"coth", "setminus", "leqslant", "geqslant", "frac", "dfrac", "tfrac", "lim", "sum", "int", "infty", "sin", "cos", "log", "ln", "sqrt", "left", "right"}
ALLOWED_FILES = {".tex", ".sty", ".cls", ".pdf", ".png", ".jpg", ".jpeg", ".eps", ".bib", ".bst", ".csv", ".dat", ".txt", ".md", ".tikz", ".pgf"}

def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

def _mask_verbatim(text):
    chars=list(text)
    for match in re.finditer(r"\\begin\{(verbatim\*?|Verbatim|lstlisting)\}",text):
        end=re.search(r"\\end\{"+re.escape(match[1])+r"\}",text[match.end():])
        if end:
            a,b=match.end(),match.end()+end.start()
            chars[a:b]=["\n" if c=="\n" else " " for c in text[a:b]]
    masked="".join(chars)
    for match in re.finditer(r"\\verb\*?([^A-Za-z\s])",masked):
        end=masked.find(match[1],match.end())
        if end!=-1:
            chars[match.start():end+1]=" "*(end+1-match.start())
    return "".join(chars)

def _inactive_regions(text):
    """Only literal constant-false TeX branches; no arbitrary condition evaluation."""
    regions=[];depth=0;start=None
    for match in re.finditer(r"\\(if[A-Za-z@]*|fi)(?![A-Za-z@])",text):
        if depth:
            if match[1]=="fi":
                depth-=1
                if depth==0:regions.append((start,match.end()))
            else:depth+=1
        elif match[1]=="iffalse":start=match.start();depth=1
    return regions

def _masked_intervals(text,intervals):
    chars=list(text)
    for a,b in intervals:chars[a:b]=["\n" if c=="\n" else " " for c in text[a:b]]
    return "".join(chars)

def _structural_tokens(text,start,end):
    """Ignore command-like text inside math/group arguments, retain environment nesting."""
    tokens=[];i=start;math=None;brace_depth=0
    while i<end:
        if text[i]=="\\":
            pair=text[i:i+2]
            if pair in {r"\[",r"\("}:
                math=pair;i+=2;continue
            if pair in {r"\]",r"\)"}:
                math=None;i+=2;continue
            match=re.match(r"\\(?:begin|end)\{([^}]+)\}|\\(?:subsection|section)\*?(?:\[[^\]]*\])?\{",text[i:end])
            if match:
                if math is None and brace_depth==0:tokens.append((i,i+len(match[0]),match[0],match[1]))
                if match[1] is None:brace_depth+=1
                i+=len(match[0]);continue
            # An escaped brace/dollar is a symbol, not a syntax delimiter.
            i+=2;continue
        if text[i]=="$":
            token="$$" if text[i:i+2]=="$$" else "$"
            math=None if math==token else token;i+=len(token);continue
        if text[i]=="{":brace_depth+=1
        elif text[i]=="}":brace_depth=max(0,brace_depth-1)
        i+=1
    return tokens

def uncomment(text: str) -> str:
    out = list(text)
    i = 0
    while i < len(text):
        if text[i] == "\\":
            i += 2
            continue
        if text[i] == "%":
            j = text.find("\n", i)
            if j == -1:
                j = len(text)
            out[i:j] = " " * (j-i)
            i = j
        else:
            i += 1
    return "".join(out)

def _group(text, start, left="{", right="}"):
    while start < len(text) and text[start].isspace():
        start += 1
    if start >= len(text) or text[start] != left:
        raise ValueError(f"Expected {left} at character {start}")
    depth, i = 1, start + 1
    while i < len(text):
        if text[i] == "\\":
            i += 2
            continue
        if text[i] == left:
            depth += 1
        elif text[i] == right:
            depth -= 1
            if not depth:
                return text[start+1:i], i+1
        i += 1
    raise ValueError(f"Unclosed {left} at character {start}")

def _optional(text, start):
    while start < len(text) and text[start].isspace():
        start += 1
    if start < len(text) and text[start] == "[":
        return _group(text, start, "[", "]")
    return "", start

def preflight_tex(text: str) -> list[dict]:
    clean = uncomment(_mask_verbatim(text))
    issues = []
    if "^^" in clean:
        issues.append({"rule_id":"SEC-TEX-ENCODING","severity":"blocking","message":"TeX character-code escapes require explicit safe normalization; not executed"})
    # Static protection is deliberately conservative; trusted_local is not a sandbox.
    danger = r"\\(?:openin|openout|read|write|immediate|catcode|csname|endcsname|loop|repeat|directlua|luaexec|special|write18|pdfobj|pdfxform|pdfextension|scantokens|everyjob|everyeof|inputlineno)(?![A-Za-z@])"
    for m in re.finditer(danger, clean):
        issues.append({"rule_id": "SEC-TEX", "severity": "blocking", "message": f"Unsupported file/execution primitive {m[0]}", "source_line": text.count("\n", 0, m.start())+1})
    stack = []
    for m in re.finditer(r"\\(begin|end)\{([^}]+)\}", clean):
        if m[1] == "begin":
            stack.append((m[2], m.start()))
        elif not stack or stack[-1][0] != m[2]:
            issues.append({"rule_id": "TEX-ENV", "severity": "blocking", "message": f"Unmatched end of {m[2]}", "source_line": text.count("\n", 0, m.start())+1})
        else:
            stack.pop()
    for name, pos in stack:
        issues.append({"rule_id": "TEX-ENV", "severity": "blocking", "message": f"Unclosed environment {name}", "source_line": text.count("\n", 0, pos)+1})
    braces=[];i=0
    while i<len(clean):
        if clean[i]=="\\":i+=2;continue
        if clean[i]=="{":braces.append(i)
        elif clean[i]=="}":
            if braces:braces.pop()
            else:issues.append({"rule_id":"TEX-BRACE","severity":"blocking","message":"Unmatched closing brace","source_line":text.count("\n",0,i)+1})
        i+=1
    for pos in braces:
        issues.append({"rule_id":"TEX-BRACE","severity":"blocking","message":"Unclosed brace","source_line":text.count("\n",0,pos)+1})
    return issues

def _declarations(preamble: str) -> dict:
    clean = uncomment(preamble)
    environments = dict(KINDS)
    definitions = []
    command_names = set(STANDARD_MATH_COMMANDS)
    for match in re.finditer(r"\\(newtheorem|NewDocumentEnvironment|newenvironment|renewenvironment|newcommand|renewcommand|providecommand|DeclareMathOperator|newcounter|mdfdefinestyle)\*?", clean):
        start, cmd, p = match.start(), match[1], match.end()
        try:
            name, p = _group(clean, p)
            name = name.lstrip("\\")
            if cmd == "newtheorem":
                _, p = _optional(clean, p)
                label, p = _group(clean, p)
                _, p = _optional(clean, p)
                environments[name] = LABEL_KINDS.get(label, "opaque_tex")
            elif cmd in {"NewDocumentEnvironment", "newenvironment", "renewenvironment"}:
                if cmd == "NewDocumentEnvironment":
                    _, p = _group(clean, p)
                else:
                    _, p = _optional(clean, p)
                    _, p = _optional(clean, p)
                _, p = _group(clean, p)
                _, p = _group(clean, p)
                environments.setdefault(name, "opaque_tex")
            elif cmd == "newcounter":
                _, p = _optional(clean, p)
            else:
                _, p = _optional(clean, p)
                _, p = _optional(clean, p)
                _, p = _group(clean, p)
                command_names.add(name)
            definitions.append({"command": cmd, "name": name, "raw_tex": preamble[start:p]})
        except ValueError:
            # An unfamiliar declaration stays in the original preamble for review.
            continue
    return {"commands": sorted(command_names), "environments": environments, "definitions": definitions}

def semantic_chunks(text: str) -> list[tuple[int,int]]:
    """Split only at complete top-level paragraphs, never inside formula/environment."""
    clean = uncomment(text)
    chunks, start, depth, envs, math, i = [], 0, 0, [], None, 0
    while i < len(clean):
        if clean[i] == "\\":
            m = re.match(r"\\(begin|end)\{([^}]+)\}", clean[i:])
            if m:
                if m[1] == "begin": envs.append(m[2])
                elif envs and envs[-1] == m[2]: envs.pop()
                i += len(m[0]); continue
            if clean[i:i+2] in {r"\[", r"\("}:
                math = clean[i:i+2]; i += 2; continue
            if clean[i:i+2] in {r"\]", r"\)"}:
                math = None; i += 2; continue
            i += 2; continue
        if clean[i] == "$":
            token = "$$" if clean[i:i+2] == "$$" else "$"
            math = None if math == token else token
            i += len(token); continue
        if not math:
            if clean[i] == "{": depth += 1
            elif clean[i] == "}": depth -= 1
            paragraph_break=re.match(r"\r?\n[ \t\r]*\n",clean[i:])
            if paragraph_break and depth == 0 and not envs:
                end = i+len(paragraph_break[0])
                if text[start:end].strip(): chunks.append((start,end))
                start=end; i=end; continue
        i += 1
    if text[start:].strip(): chunks.append((start,len(text)))
    return chunks or ([(0,len(text))] if text.strip() else [])

def parse_tex(text: str, source_name: str = "main.tex") -> dict:
    clean = uncomment(_mask_verbatim(text))
    doc = re.search(r"\\begin\{document\}", clean)
    finish = re.search(r"\\end\{document\}", clean)
    body_start = doc.end() if doc else 0
    body_end = finish.start() if finish else len(text)
    preamble = text[:doc.start()] if doc else ""
    macros = _declarations(preamble)
    env_kinds = macros["environments"]
    units, sections, current_section = [], [], None
    issues = preflight_tex(text)
    inactive=_inactive_regions(clean)
    structural=_masked_intervals(clean,inactive)
    tokens = _structural_tokens(structural,body_start,body_end)
    tokens += [(a,b,"INACTIVE",None) for a,b in inactive if body_start<=a<b<=body_end]
    tokens.sort()
    stack, cursor, environment_start, environment_name = [], body_start, None, None

    def ensure_section():
        nonlocal current_section
        if current_section is None:
            current_section = {"id": f"S{len(sections)+1:02}", "title": "数学内容", "source_unit_ids": []}
            sections.append(current_section)

    def add(start, end, kind=None, env=None):
        if not text[start:end].strip(): return
        ensure_section()
        raw = text[start:end]
        # Article-only title commands are explicitly source scaffolding, not mathematics.
        if not uncomment(raw).strip(): return
        scaffold_only=re.sub(r"\\(?:maketitle|tableofcontents|clearpage|newpage)\b|\\(?:vspace\*?|Needspace|needspace)\{[^{}]*\}","",uncomment(raw)).strip()
        if not scaffold_only and re.search(r"\\(?:maketitle|tableofcontents|clearpage|newpage|vspace|Needspace|needspace)\b",raw):
            kind = "presentation_scaffold"
        if kind is None:
            prefix = re.match(r"\s*\\textbf\{(解|证明)[:：]?\}", raw)
            kind = LABEL_KINDS[prefix[1]] if prefix else "explanation"
        uid = f"U{len(units)+1:04}"
        unit = {"id": uid, "kind": kind, "raw_tex": raw, "source_spans": [{"source_file": source_name, "start": start, "end": end, "start_line": text.count("\n",0,start)+1, "end_line": text.count("\n",0,end)+1}], "section_id": current_section["id"], "section_title": current_section["title"], "semantic_relations": {}, "dependencies": re.findall(r"\\(?:ref|eqref)\{([^}]+)\}", raw), "content_hash": _hash(raw), "environment": env}
        if env=="literal_iffalse":
            unit["source_visibility"]="inactive"
            unit["inactive_reason"]="Complete literal \\iffalse...\\fi interval; original TeX does not render this content; preserved in source snapshot"
        if kind=="explanation" and re.match(r"\s*(?:例如|比如|举例)",raw) and units and units[-1]["kind"]=="definition" and units[-1]["section_id"]==current_section["id"]:
            unit["semantic_relations"]["illustrates"]=units[-1]["id"]
            unit["relation_evidence"]="Explicit illustration cue immediately follows the definition"
        if kind in {"proof", "example_solution"}:
            targets = {"proof": {"theorem", "proposition", "property", "corollary"}, "example_solution": {"example_statement"}}[kind]
            related = next((u for u in reversed(units) if u["section_id"] == current_section["id"] and u["kind"] in targets), None)
            if related: unit["semantic_relations"]["proof_of" if kind == "proof" else "solution_of"] = related["id"]
            else: issues.append({"rule_id": "SOURCE-RELATION", "severity": "review", "unit_id": uid, "message": "Proof/solution has no unambiguous preceding statement in the section"})
        if kind == "opaque_tex":
            unit["unparsed_reason"] = "Unknown/custom environment preserved verbatim; no arbitrary macro expansion"
        units.append(unit)
        current_section["source_unit_ids"].append(uid)

    def add_free(start, end):
        for a,b in semantic_chunks(text[start:end]): add(start+a,start+b)

    for pos,end,command,env_name in tokens:
        if pos < cursor: continue
        if command=="INACTIVE":
            if not stack:
                add_free(cursor,pos);add(pos,end,"opaque_tex","literal_iffalse");cursor=end
            continue
        if command.startswith(r"\begin"):
            if not stack:
                add_free(cursor,pos)
                environment_start, environment_name = pos, env_name
            stack.append(env_name)
        elif command.startswith(r"\end"):
            if stack and stack[-1] == env_name: stack.pop()
            if not stack and environment_start is not None:
                add(environment_start,end,env_kinds.get(environment_name,"opaque_tex"), environment_name)
                cursor, environment_start = end, None
        elif not stack:
            add_free(cursor,pos)
            try:
                title, title_end = _group(clean, end-1)
            except ValueError:
                continue
            current_section = {"id": f"S{len(sections)+1:02}", "title": title, "source_unit_ids": [], "source_heading": "subsection" if command.startswith(r"\subsection") else "section"}
            sections.append(current_section)
            cursor = title_end
    if environment_start is not None:
        add(environment_start,body_end,"opaque_tex",environment_name)
    else:
        add_free(cursor,body_end)
    sections = [s for s in sections if any(u["id"] in s["source_unit_ids"] and u["kind"]!="presentation_scaffold" and u.get("source_visibility")!="inactive" for u in units)]
    label_owners={label:u["id"] for u in units for label in re.findall(r"\\label\{([^}]+)\}",uncomment(u["raw_tex"]))}
    for unit in units:
        unit["reference_labels"]=list(unit["dependencies"])
        unit["dependencies"]=[label_owners[label] for label in unit["reference_labels"] if label in label_owners]
        unit["dependencies"].extend(unit["semantic_relations"].values())
    return {"schema_version": 1, "source_name": source_name, "source_hash": _hash(text), "units": units, "sections": sections, "macros": macros, "preamble": preamble, "issues": issues, "body_span": {"start": body_start, "end": body_end}, "parser": "lossless-scanner-v1", "limitations": ["No TeX macro expansion; opaque units retained", "Relations inferred locally and exposed in plan for confirmation"]}

def decode_tex(data: bytes, encoding: str | None = None) -> tuple[str,str]:
    if encoding:
        return data.decode(encoding, errors="strict"), encoding
    try:
        return data.decode("utf-8-sig", errors="strict"), "utf-8-sig"
    except UnicodeDecodeError as exc:
        raise ValueError("Non-UTF-8 input requires an explicit verified encoding; no replacement characters were inserted") from exc

def _relative_path(name: str) -> PurePosixPath:
    name = name.replace("\\", "/")
    p = PurePosixPath(name)
    if not name or any(ord(c)<32 for c in name) or p.is_absolute() or ":" in name or ".." in p.parts or any(x.endswith((".", " ")) for x in p.parts):
        raise ValueError(f"Unsafe relative path: {name}")
    if any(re.fullmatch(r"(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?", x, re.I) for x in p.parts):
        raise ValueError("Windows device path is not permitted")
    return p

def safe_extract_zip(data: bytes, destination: Path) -> list[str]:
    if len(data) > 50*1024*1024: raise ValueError("ZIP exceeds 50 MiB compressed limit")
    destination = destination.resolve()
    with zipfile.ZipFile(BytesIO(data)) as archive:
        members = archive.infolist()
        if len(members)>1000: raise ValueError("ZIP has too many members")
        if sum(m.file_size for m in members)>200*1024*1024: raise ValueError("ZIP expanded size exceeds limit")
        seen, validated = set(), []
        for member in members:
            p = _relative_path(member.filename)
            folded = str(p).casefold()
            if folded in seen: raise ValueError("Duplicate archive path")
            seen.add(folded)
            if stat.S_ISLNK(member.external_attr >> 16): raise ValueError("Archive symlink rejected")
            if member.flag_bits & 1: raise ValueError("Encrypted ZIP is unsupported")
            if member.file_size > 50*1024*1024 or member.file_size/max(member.compress_size,1)>100: raise ValueError("ZIP compression ratio or member size exceeds limit")
            if not member.is_dir() and p.suffix.lower() not in ALLOWED_FILES: raise ValueError(f"Unsupported archive file: {p.name}")
            target = destination.joinpath(*p.parts)
            if not target.resolve().is_relative_to(destination): raise ValueError("Archive path escapes destination")
            if target.exists(): raise ValueError("Archive extraction never overwrites existing files")
            validated.append((member,target))
        written=[]
        for member,target in validated:
            if member.is_dir(): target.mkdir(parents=True,exist_ok=True); continue
            target.parent.mkdir(parents=True,exist_ok=True)
            content=archive.read(member)
            if len(content)!=member.file_size: raise ValueError("Archive size mismatch")
            target.write_bytes(content)
            written.append(target.relative_to(destination).as_posix())
        return written

def load_project(root: Path, main_file: str) -> dict:
    root=root.resolve()
    files, dependencies, origin_segments, all_issues=[],[],[],[]
    expanded_position=0
    def read_file(name, parents):
        nonlocal expanded_position
        p=_relative_path(name)
        path=root.joinpath(*p.parts).resolve()
        if not path.is_relative_to(root): raise ValueError("Source dependency escapes controlled root")
        if name in parents: raise ValueError("Circular TeX input: "+" -> ".join(parents+[name]))
        if not path.is_file(): raise ValueError(f"Missing TeX input: {name}")
        data=path.read_bytes()
        text,enc=decode_tex(data)
        files.append({"relative_path":name,"sha256":hashlib.sha256(data).hexdigest(),"size_bytes":len(data),"encoding":enc})
        clean=uncomment(text)
        out=[]; pos=0
        def append_chunk(a,b):
            nonlocal expanded_position
            out.append(text[a:b]); origin_segments.append({"expanded_start":expanded_position,"expanded_end":expanded_position+b-a,"source_file":name,"source_start":a,"source_text":text})
            expanded_position+=b-a
        for m in re.finditer(r"\\(?:input|include)\s*\{([^}]+)\}",clean):
            append_chunk(pos,m.start())
            dep=m[1]
            if not Path(dep).suffix: dep+=".tex"
            dep=(p.parent/_relative_path(dep)).as_posix()
            dependencies.append({"source":name,"target":dep,"source_line":text.count("\n",0,m.start())+1,"kind":"input"})
            out.append(read_file(dep,parents+[name]));pos=m.end()
        append_chunk(pos,len(text))
        for m in re.finditer(r"\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}",clean):
            dep=_relative_path(m[1]); candidates=[root/p.parent/dep]
            if not dep.suffix:candidates += [root/p.parent/(str(dep)+ext) for ext in (".pdf",".png",".jpg",".jpeg",".eps")]
            found=next((c for c in candidates if c.is_file() and c.resolve().is_relative_to(root)),None)
            dependencies.append({"source":name,"target":m[1],"kind":"image","resolved":found.relative_to(root).as_posix() if found else None})
            if not found:all_issues.append({"rule_id":"DEPENDENCY","severity":"blocking","message":f"Missing image {m[1]}","source_file":name,"source_line":text.count("\n",0,m.start())+1})
        return "".join(out)
    expanded=read_file(_relative_path(main_file).as_posix(),[])
    parsed=parse_tex(expanded,main_file)
    for unit in parsed["units"]:
        start,end=unit["source_spans"][0]["start"],unit["source_spans"][0]["end"]
        spans=[]
        for origin in origin_segments:
            lo,hi=max(start,origin["expanded_start"]),min(end,origin["expanded_end"])
            if lo<hi:
                a=origin["source_start"]+lo-origin["expanded_start"];b=a+hi-lo
                spans.append({"source_file":origin["source_file"],"start":a,"end":b,"start_line":origin["source_text"].count("\n",0,a)+1,"end_line":origin["source_text"].count("\n",0,b)+1})
        unit["source_spans"]=spans
    parsed.update(files=files,dependencies=dependencies,expanded_tex=expanded,root=str(root))
    parsed["issues"].extend(all_issues)
    return parsed
