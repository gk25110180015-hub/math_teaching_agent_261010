"""Read-only manuscript audit and provenance-backed chapter/bibliography copies.

No TeX expansion, network lookup or invented bibliography is performed.  File
writes are explicit new copies; caller-owned originals are never overwritten.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re

from .parsing import (_group, _inactive_regions, _mask_verbatim,
                      _masked_intervals, _structural_tokens, preflight_tex,
                      uncomment)


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _active(text: str) -> str:
    clean = uncomment(_mask_verbatim(text))
    return _masked_intervals(clean, _inactive_regions(clean))


def _document(text: str) -> tuple[str, int, int]:
    clean = _active(text)
    begin = list(re.finditer(r"\\begin\{document\}", clean))
    end = list(re.finditer(r"\\end\{document\}", clean))
    if len(begin) != 1 or len(end) != 1 or begin[0].end() >= end[0].start():
        raise ValueError("Expected exactly one complete document environment")
    return clean, begin[0].end(), end[0].start()


def citation_keys(text: str) -> list[str]:
    """Active body citations only; macro-definition #1 is not a citation key."""
    clean, begin, end = _document(text)
    keys = []
    pattern = r"\\(?:cite|citep|citet|nocite|upcite)\*?(?:\s*\[[^\]]*\]){0,2}\s*\{([^}]+)\}"
    for match in re.finditer(pattern, clean[begin:end]):
        for key in match[1].split(","):
            key = key.strip()
            if not key or not re.fullmatch(r"[A-Za-z0-9:._+/-]+|\*", key):
                raise ValueError("Dynamic or malformed citation keys require source review")
            if key not in keys:
                keys.append(key)
    return keys


def bibliography_entries(text: str, source_name: str = "manuscript.tex") -> dict:
    clean, begin, end = _document(text)
    environments = list(re.finditer(r"\\begin\{thebibliography\}\s*\{[^}]*\}", clean[begin:end]))
    if len(environments) > 1:
        raise ValueError("Multiple bibliography environments require explicit source selection")
    if not environments:
        return {}
    body_start = begin + environments[0].end()
    close = re.search(r"\\end\{thebibliography\}", clean[body_start:end])
    if not close:
        raise ValueError("Unclosed bibliography")
    body_end = body_start + close.start()
    matches = list(re.finditer(r"\\bibitem(?:\s*\[[^\]]*\])?\s*\{([^}]+)\}", clean[body_start:body_end]))
    entries = {}
    for index, match in enumerate(matches):
        key = match[1].strip()
        if not re.fullmatch(r"[A-Za-z0-9:._+/-]+", key) or key in entries:
            raise ValueError("Duplicate or malformed bibliography key: " + key)
        start = body_start + match.start()
        finish = body_start + matches[index + 1].start() if index + 1 < len(matches) else body_end
        raw = text[start:finish]
        if any(issue.get("severity") == "blocking" for issue in preflight_tex(raw)):
            raise ValueError("Unsafe or incomplete bibliography entry: " + key)
        if re.search(r"\\(?:input|include|includegraphics|documentclass|usepackage|RequirePackage|def|gdef|edef|xdef|let|newcommand|renewcommand|providecommand|section|chapter|bibliography|bibliographystyle)\b", _active(raw)):
            raise ValueError("Bibliography entry contains unsupported structural commands: " + key)
        entries[key] = {"key": key, "raw_tex": raw, "sha256": _hash(raw),
                        "source_file": source_name, "source_text_sha256": _hash(text),
                        "start": start, "end": finish,
                        "start_line": text.count("\n", 0, start) + 1,
                        "end_line": text.count("\n", 0, finish) + 1}
    return entries


def chapter_spans(text: str) -> list[dict]:
    """Numbered top-level sections are chapters in the supplied ctexart book."""
    clean, begin, end = _document(text)
    starts = []
    stack = []
    bibliography_start = end
    for start, finish, command, environment in _structural_tokens(clean, begin, end):
        if command.startswith(r"\begin"):
            if environment == "thebibliography" and not stack:
                bibliography_start = start
            stack.append(environment)
        elif command.startswith(r"\end"):
            if stack and stack[-1] == environment:
                stack.pop()
        elif not stack and re.match(r"\\section(?:\[|\{)", command):
            title, _ = _group(clean, finish - 1)
            starts.append((start, title))
    chapters = []
    for index, (start, title) in enumerate(starts):
        finish = starts[index + 1][0] if index + 1 < len(starts) else bibliography_start
        # Bibliography display setup belongs to neither chapter mathematics nor
        # chapter extraction. Preserve it separately in the original manuscript.
        if index + 1 == len(starts):
            trailer = re.search(r"\\clearpage\s*\\renewcommand\{\\refname\}", clean[start:finish])
            if trailer:
                finish = start + trailer.start()
        raw = text[start:finish]
        chapters.append({"index": index + 1, "title": title, "start": start, "end": finish,
                         "start_line": text.count("\n", 0, start) + 1,
                         "end_line": text.count("\n", 0, finish) + 1,
                         "raw_tex": raw, "sha256": _hash(raw)})
    return chapters


def complete_bibliography(source_text: str, manuscript_text: str, *,
                          source_name: str = "source.tex",
                          manuscript_name: str = "manuscript.tex") -> dict:
    """Append only missing cited entries, exactly copied from the named source.

    Existing bibliography values always win. Conflicting definitions are reported
    and never silently replaced. Unavailable keys remain unresolved, never waived.
    """
    clean, _, end = _document(source_text)
    citations = citation_keys(source_text)
    existing = bibliography_entries(source_text, source_name)
    available = bibliography_entries(manuscript_text, manuscript_name)
    requested = list(available) if "*" in citations else citations
    missing = [key for key in requested if key not in existing]
    unresolved = [key for key in missing if key not in available]
    added = [key for key in missing if key in available]
    conflicts = [key for key in requested if key in existing and key in available
                 and re.sub(r"\s+", "", uncomment(existing[key]["raw_tex"]))
                 != re.sub(r"\s+", "", uncomment(available[key]["raw_tex"]))]
    output = source_text
    if added:
        entries = "".join(available[key]["raw_tex"] for key in added)
        if not entries.endswith("\n"):
            entries += "\n"
        provenance_comment = "% Bibliography entries copied verbatim from the recorded manuscript; see provenance JSON.\n"
        if re.search(r"\\begin\{thebibliography\}", clean):
            close = re.search(r"\\end\{thebibliography\}", clean)
            if close is None:
                raise ValueError("Bibliography close missing")
            insert = close.start()
            output = source_text[:insert] + "\n" + provenance_comment + entries + source_text[insert:]
        else:
            block = ("\n" + provenance_comment + r"\begin{thebibliography}{99}" + "\n" + entries
                     + r"\end{thebibliography}" + "\n")
            output = source_text[:end] + block + source_text[end:]
    return {"schema_version": 1, "operation": "complete_bibliography", "text": output,
            "status": "NEEDS_SOURCE" if unresolved or conflicts else "PREPARED_NOT_COMPILED",
            "source_name": source_name, "source_text_sha256": _hash(source_text),
            "manuscript_name": manuscript_name, "manuscript_text_sha256": _hash(manuscript_text),
            "output_text_sha256": _hash(output), "citations": citations,
            "added_keys": added, "unresolved_keys": unresolved, "conflicting_keys": conflicts,
            "entries": [available[key] for key in added],
            "compile_status": "NOT_RUN", "teacher_visual_review": "NOT_RUN"}


def extract_chapter(manuscript_text: str, index: int, *, manuscript_name: str = "manuscript.tex") -> dict:
    chapters = chapter_spans(manuscript_text)
    chapter = next((item for item in chapters if item["index"] == index), None)
    if chapter is None:
        raise ValueError("Numbered chapter is not present")
    _, begin, _ = _document(manuscript_text)
    # Keep preamble and original chapter number. Body is an exact substring;
    # answers inside literal false branches remain false and remain present.
    text = (manuscript_text[:begin] + "\n" + r"\setcounter{section}{" + str(index - 1) + "}\n"
            + chapter["raw_tex"] + "\n" + r"\end{document}" + "\n")
    prepared = complete_bibliography(text, manuscript_text,
                                    source_name=f"chapter-{index:02}.tex", manuscript_name=manuscript_name)
    prepared.update(operation="extract_chapter", chapter={key: value for key, value in chapter.items() if key != "raw_tex"},
                    manuscript_text_sha256=_hash(manuscript_text), body_exact_substring=True)
    return prepared


def write_prepared_copy(prepared: dict, destination: Path, *, protected_paths=()) -> dict:
    destination = Path(destination).resolve()
    if destination.suffix.lower() != ".tex":
        raise ValueError("Prepared copy must have .tex suffix")
    if destination in {Path(path).resolve() for path in protected_paths}:
        raise ValueError("Original source cannot be an output target")
    sidecar = destination.with_suffix(".provenance.json")
    if destination.exists() or sidecar.exists():
        raise FileExistsError("Prepared copies never overwrite any existing file")
    destination.parent.mkdir(parents=True, exist_ok=True)
    metadata = {key: value for key, value in prepared.items() if key != "text"}
    metadata["output_path"] = str(destination)
    # Exclusive mode also prevents a late race from overwriting an original.
    with destination.open("x", encoding="utf-8", newline="") as handle:
        handle.write(prepared["text"])
    with sidecar.open("x", encoding="utf-8", newline="") as handle:
        json.dump(metadata, handle, ensure_ascii=False, indent=2)
    return metadata


def audit_manuscript(path: Path) -> dict:
    path = Path(path).resolve()
    data = path.read_bytes()
    text = data.decode("utf-8-sig", errors="strict")
    entries = bibliography_entries(text, path.name)
    chapters = chapter_spans(text)
    citations = citation_keys(text)
    clean = _active(text)
    dependencies = []
    for match in re.finditer(r"\\(input|include|includegraphics|bibliography)(?:\[[^\]]*\])?\s*\{([^}]+)\}", clean):
        target = match[2]
        candidate = path.parent / target
        suffixes = {"input": (".tex",), "include": (".tex",), "includegraphics": (".pdf", ".png", ".jpg", ".eps"), "bibliography": (".bib",)}[match[1]]
        choices = [candidate] if candidate.suffix else [candidate.with_suffix(suffix) for suffix in suffixes]
        safe = [item for item in choices if item.resolve().is_relative_to(path.parent)]
        found = next((item for item in safe if item.is_file()), None)
        dependencies.append({"kind": match[1], "target": target,
                             "status": "PRESENT" if found else "MISSING_OR_UNSAFE",
                             "source_line": text.count("\n", 0, match.start()) + 1})
    return {"schema_version": 1, "path": str(path), "size_bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(), "line_count": text.count("\n") + 1,
            "chapters": [{key: value for key, value in chapter.items() if key != "raw_tex"} for chapter in chapters],
            "bibliography": entries, "citations": citations,
            "unresolved_keys": [key for key in citations if key not in entries and key != "*"],
            "dependencies": dependencies, "preflight_issues": preflight_tex(text),
            "compile_status": "NOT_RUN", "teacher_visual_review": "NOT_RUN"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    audit = commands.add_parser("audit")
    audit.add_argument("manuscript", type=Path)
    audit.add_argument("--output", type=Path)
    extract = commands.add_parser("extract")
    extract.add_argument("manuscript", type=Path)
    extract.add_argument("--chapter", type=int, required=True)
    extract.add_argument("--output", type=Path, required=True)
    supplement = commands.add_parser("supplement")
    supplement.add_argument("source", type=Path)
    supplement.add_argument("--manuscript", type=Path, required=True)
    supplement.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.action == "audit":
        result = audit_manuscript(args.manuscript)
        if args.output:
            if args.output.resolve() == args.manuscript.resolve():
                raise ValueError("Audit cannot overwrite its input")
            args.output.parent.mkdir(parents=True, exist_ok=True)
            with args.output.open("x", encoding="utf-8") as handle:
                json.dump(result, handle, ensure_ascii=False, indent=2)
        else:
            print(json.dumps(result, ensure_ascii=True, indent=2))
        return 0
    reference = args.manuscript.read_bytes().decode("utf-8-sig")
    if args.action == "extract":
        prepared = extract_chapter(reference, args.chapter, manuscript_name=args.manuscript.name)
        protected = [args.manuscript]
    else:
        source = args.source.read_bytes().decode("utf-8-sig")
        prepared = complete_bibliography(source, reference, source_name=args.source.name, manuscript_name=args.manuscript.name)
        protected = [args.manuscript, args.source]
    metadata = write_prepared_copy(prepared, args.output, protected_paths=protected)
    print(json.dumps({key: value for key, value in metadata.items() if key != "entries"}, ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
