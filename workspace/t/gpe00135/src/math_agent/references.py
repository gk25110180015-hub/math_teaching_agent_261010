"""Hash-based reference inventory; never changes original chapter assets."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import re
from .parsing import load_project

def theme_status(reference_root: Path | None = None) -> dict:
    root = Path(reference_root) if reference_root else Path(__file__).resolve().parents[2] / "reference_data"
    candidates=[]
    if root.exists():
        chapter_roots=[root/name for name in ("第一章","第二章","第三章") if (root/name).is_dir()]
        scan_roots=chapter_roots or [root]
        for p in (p for folder in scan_roots for p in folder.rglob("beamerthemefduclassroom.sty")):
            if p.is_symlink(): continue
            raw=p.read_bytes(); text=raw.decode("utf-8-sig",errors="strict")
            dependencies=[]
            for m in re.finditer(r"\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}",text):
                rel=m[1]; choices=[p.parent/rel]
                if not Path(rel).suffix: choices += [p.parent/(rel+e) for e in (".pdf",".png",".jpg")]
                found=next((q for q in choices if q.is_file() and q.resolve().is_relative_to(root.resolve())),None)
                dependencies.append({"target":rel,"path":str(found) if found else None,"status":"PRESENT" if found else "MISSING","source_line":text.count("\n",0,m.start())+1})
            candidates.append({"path":str(p),"sha256":hashlib.sha256(raw).hexdigest(),"dependencies":dependencies})
    hashes=sorted({x["sha256"] for x in candidates})
    missing=[d for x in candidates for d in x["dependencies"] if d["status"]=="MISSING"]
    reason="" if candidates and len(hashes)==1 and not missing else "缺少真实 FDU 主题文件" if not candidates else "存在多个不同主题哈希，需明确版本" if len(hashes)>1 else "FDU 主题缺少资源"
    return {"default":{"available":True,"label":"默认模板"},"fduclassroom":{"available":not reason,"label":"FDU Classroom（用户样例主题）","reason":reason,"hashes":hashes,"selected_sha256":hashes[0] if len(hashes)==1 else None,"candidates":candidates,"missing_dependencies":missing,"compile_status":"NOT_RUN","license_status":"NOT_VERIFIED_LOCAL_USE_ONLY"}}

def index_references(root: Path, output_dir: Path) -> dict:
    root,output_dir=Path(root).resolve(),Path(output_dir)
    output_dir.mkdir(parents=True,exist_ok=True)
    manifest={"schema_version":1,"files":[],"datasets":[],"originals_modified":False}
    for index,name in enumerate(("第一章","第二章","第三章"),1):
        folder=root/name; dataset_id=f"CH{index:02}"
        manifest["datasets"].append({"dataset_id":dataset_id,"directory":name,"status":"PRESENT" if folder.is_dir() else "MISSING"})
        if not folder.exists():continue
        for p in sorted(folder.rglob("*")):
            if not p.is_file() or p.is_symlink():continue
            raw=p.read_bytes();role="auxiliary_asset";encoding=None
            if p.suffix==".tex":
                text=raw.decode("utf-8-sig",errors="strict");encoding="utf-8-sig"
                role="beamer_reference" if re.search(r"\\documentclass[^\n]*\{(?:ctex)?beamer\}",text) else "lecture_source"
            elif p.suffix==".sty" or "resources" in p.parts:role="theme_asset"
            elif p.suffix==".pdf" and p.with_suffix(".tex").exists():
                role="beamer_reference" if re.search(r"\\documentclass[^\n]*\{(?:ctex)?beamer\}",p.with_suffix(".tex").read_text(encoding="utf-8-sig")) else "lecture_source"
            digest=hashlib.sha256(raw).hexdigest();rel=p.relative_to(folder).as_posix()
            manifest["files"].append({"dataset_id":dataset_id,"relative_path":rel,"sha256":digest,"size_bytes":len(raw),"role":role,"encoding":encoding,"primary_key":[dataset_id,rel,digest],"discovery_status":"PRESENT"})
    manifest["templates"]=theme_status(root)
    (output_dir/"manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding="utf-8")
    return manifest
