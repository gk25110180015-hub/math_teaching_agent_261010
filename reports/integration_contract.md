# Internal implementation contract

Root owns `settings.py`, `domain.py`, `store.py`, `service.py`, `provider.py`, `worker.py`, `pipeline.py`, `cli.py`, `web/app.py`, lecture templates, math checks, core tests.

Reference agent owns `parsing.py`, `beamer.py`, `references.py`, related tests, reference index and beamer templates. Compiler agent owns `compiler.py`, `pdfcheck.py`, compile tests and environment audit. UI agent owns `web/static/*`, Windows scripts and browser tests.

All APIs use JSON dictionaries, strict request validation. Errors `{error:{code,message},...}`. CSRF bootstrap: `GET /api/session` returns `{csrf_token}` and HttpOnly SameSite=Strict cookie. POST sends `X-CSRF-Token`. Same-origin only.

- `GET /api/runs` -> list of run dictionaries.
- `POST /api/runs` JSON `{workflow_id:'lecture.generate'|'beamer.from_tex',topic,difficulty,provider:'mock'|'live',trusted_input:boolean,theme:'default'|'fduclassroom'}` -> run.
- `POST /api/runs/{id}/attachments` multipart `file` (tex/zip), optional `main_file` -> run. Only before planning; dependencies can be added through a replacement complete ZIP before confirmation.
- `POST /api/runs/{id}/plan` `{}` -> job (asynchronous).
- `GET /api/runs/{id}` -> `{id,status,stage,input,plan,approval,jobs,artifacts,error,...}`. `plan` is null or `{revision,hash,title,sections:[{id,title,source_unit_ids,...}],questions,lecture,omissions,additions,decision_ids,diff,...}`.
- `GET /api/runs/{id}/plan` -> plan. Question `{id,revision,prompt,selection_mode,affected_fields,options:[{id,label,recommended}],...}` always ends in `CUSTOM`.
- `POST /api/runs/{id}/decisions` `{expected_plan_revision,decisions:[{question_id,question_revision,selected_option_ids,custom_input}],omitted_unit_ids?:[...],additions?:[{new_content,insertion_location,priority}]}` -> revised plan. `CUSTOM` requires text. Omitted ids must exist in `input.units`; linked solutions are resolved server-side and shown in plan.
- `POST /api/runs/{id}/plan/confirm` `{expected_plan_revision,expected_plan_hash,action_id}` -> run.
- `POST /api/runs/{id}/execute` `{expected_plan_revision,expected_plan_hash,idempotency_key}` -> job. Repeat is idempotent.
- `POST /api/runs/{id}/retry` `{}` -> job; no reconfirmation of unchanged plan.
- `POST /api/runs/{id}/cancel` `{}` -> run.
- `POST /api/runs/{id}/reviews` `{artifact_id,sha256,verdict:'pass'|'issue',note}` -> run; page image artifacts must each be reviewed. Known blocking errors cannot be overridden.
- `GET /api/runs/{id}/events?after=0` -> event list `{sequence,type,payload,timestamp}`.
- `GET /api/runs/{id}/artifacts` -> list `{artifact_id,name,media_type,sha256,status,metadata}`. Download `/api/artifacts/{artifact_id}`; PDFs inline. Pages PNG have metadata `physical_page`, `frame_id`, `overlay_index`.
- `GET /api/health`, `/api/capabilities` -> env and template summaries without keys.

Persistence SQLite with numbered SQL migrations; `Store` exposes transactions, atomic leases/fencing/checkpoints. Worker CLI `math-agent worker --concurrency 1`; `--once` supported for tests. UI poll 1500 ms and restore localStorage selected run ID.

Compiler: `TexCompiler(xelatex_path: str|None=None, timeout:float=120).compile(source_dir:Path, main_file:str, output_dir:Path, *, trusted:bool, cancel_check:Callable|None=None) -> dict` with `status:PASS|FAIL|BLOCKED|CANCELLED`, `pdf_path:str|None`, `issues:list`, `log_paths:list`, `engine`, `passes`. Fresh output dir required. No secret env. `pdfcheck.inspect_pdf(pdf_path:Path, output_dir:Path, *, beamer:bool=False) -> dict` with `pages:list` (each physical_page, image_path, sha256, geometry, issues), `page_count`, `status`, `overlay_map`, `limitations`; all pages rendered. Actual nav mapping can use sibling `.nav`.

Parser: `parse_tex(text:str, source_name:str='main.tex') -> dict` keys `units` list (id,kind,raw_tex,source_spans,section_id,section_title,semantic_relations,content_hash), `sections` (id,title,source_unit_ids), `macros`, `preamble`, `issues`; offsets lossless. `load_project(root:Path,main_file:str) -> dict` expands safe includes keeping origin spans, checks dependencies. `safe_extract_zip(data:bytes,destination:Path) -> list[str]`; errors ValueError. `preflight_tex(text:str) -> list[dict]` safety + syntax issues.

Beamer: `render_beamer(parsed:dict,plan:dict,output_dir:Path,reference_root:Path|None=None) -> dict` keys `main_file` ('slides.tex'), `source_map`, `frame_plan`, `layout_plan`, `issues`, `theme_hash`; source unchanged. `check_fidelity(parsed,plan,tex:str) -> dict` must examine output independent of claimed map. `theme_status(reference_root:Path) -> dict` default/fdu availability hashes and dependencies. Layout candidates legal font + semantics; no untracked deletions.
