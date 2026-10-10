"""Compiler regression fixtures; actual Windows tests are explicitly marked."""
from pathlib import Path
import os
import shutil
import threading
import time
import subprocess
import json
import hashlib
import pytest

from math_agent.compiler import TexCompiler, safe_child_env, resolve_xelatex, parse_log
from math_agent.pdfcheck import inspect_pdf, parse_overlay_map


def source(tmp_path, text):
    root = tmp_path / '中文 源码 (1)'
    root.mkdir()
    (root / 'main.tex').write_text(text, encoding='utf-8')
    return root


@pytest.mark.security
def test_t55_subprocess_env_excludes_all_secrets(tmp_path, monkeypatch):
    monkeypatch.setenv('MATH_AGENT_API_KEY', 'synthetic-secret-do-not-export')
    monkeypatch.setenv('OPENAI_API_KEY', 'another-synthetic-secret')
    monkeypatch.setenv('TEXINPUTS', 'C:/Users/private//;')
    env = safe_child_env(Path('D:/texlive/2024/bin/windows/xelatex.exe'), tmp_path)
    assert not any('KEY' in k or 'TOKEN' in k or 'SECRET' in k for k in env)
    assert 'private' not in str(env)
    assert env['openin_any'] == 'p' and env['openout_any'] == 'p'


@pytest.mark.security
def test_t53_never_resolve_input_directory_fake_compiler(tmp_path, monkeypatch):
    fake = tmp_path / ('xelatex.exe' if os.name == 'nt' else 'xelatex')
    fake.write_text('not a real compiler')
    monkeypatch.chdir(tmp_path)
    resolved = resolve_xelatex(None, forbidden_roots=[tmp_path])
    assert resolved is None or resolved != fake


@pytest.mark.security
def test_t48_stale_pdf_never_reused(tmp_path):
    src = source(tmp_path, r'\documentclass{article}\begin{document}x\end{document}')
    build = tmp_path / 'old-build'
    build.mkdir()
    (build / 'main.pdf').write_bytes(b'%PDF-old')
    result = TexCompiler().compile(src, 'main.tex', build, trusted=True)
    assert result['status'] == 'BLOCKED'
    assert result['pdf_path'] is None
    assert any(x['rule_id'] == 'STALE_BUILD_DIRECTORY' for x in result['issues'])
    assert (build / 'main.pdf').read_bytes() == b'%PDF-old'


@pytest.mark.security
def test_t52_input_reads_and_writes_blocked(tmp_path):
    src = source(tmp_path, r'\documentclass{article}\openin1=C:/private.txt\begin{document}x\end{document}')
    result = TexCompiler().compile(src, 'main.tex', tmp_path / 'build', trusted=True)
    assert result['status'] == 'BLOCKED'
    assert result['pdf_path'] is None


@pytest.mark.security
def test_native_trust_confirmation_required(tmp_path):
    src = source(tmp_path, r'\documentclass{article}\begin{document}x\end{document}')
    result = TexCompiler().compile(src, 'main.tex', tmp_path / 'build', trusted=False)
    assert result['status'] == 'BLOCKED'
    assert result['passes'] == 0


@pytest.mark.security
def test_harmless_readme_is_allowed_but_not_tex_executed(tmp_path):
    from math_agent.compiler import _preflight
    src = source(tmp_path, r'\documentclass{article}\begin{document}x\end{document}')
    (src / 'README.md').write_text('Run XeLaTeX twice. No API key required.', encoding='utf-8')
    assert not _preflight(src.resolve(), (src / 'main.tex').resolve())
    (src / 'README.md').write_text(r'\openin1=../outside.txt', encoding='utf-8')
    assert any(x['rule_id']=='UNSAFE_TEX_COMMAND' for x in _preflight(src.resolve(), (src/'main.tex').resolve()))


@pytest.mark.unit
def test_nav_mapping_all_overlays(tmp_path):
    nav = tmp_path / 'slides.nav'
    nav.write_text(r'\headcommand {\slideentry {1}{0}{1}{1/3}{}{0}}' '\n' r'\headcommand {\slideentry {2}{0}{1}{4/4}{}{0}}')
    result = parse_overlay_map(nav, 4)
    assert result['status'] == 'PASS'
    assert result['frames'][0]['physical_pages'] == [1, 2, 3]
    assert result['pages'][1]['overlay_index'] == 2
    assert parse_overlay_map(nav, 5)['status'] == 'FAIL'


@pytest.mark.unit
def test_fatal_condition_and_vrb_error_keep_exact_source_location():
    log = r'''Overfull \hbox (1.0pt too wide) in paragraph at lines 3--5
./slides.tex:589: Incomplete \iffalse; all text was ignored after line 8.
./slides.vrb:20: LaTeX Error: Environment proofdetail undefined.
'''
    issues = parse_log(log)
    conditional = next(i for i in issues if i['rule_id']=='INCOMPLETE_CONDITIONAL')
    environment = next(i for i in issues if i['rule_id']=='LATEX_ERROR')
    assert conditional['severity']=='blocking' and conditional['location']['source_line']==589
    assert environment['severity']=='blocking' and environment['location']['file']=='./slides.vrb'
    assert environment['location']['source_line']==20


@pytest.mark.unit
def test_layout_probe_requires_matching_template_fingerprint(tmp_path, monkeypatch):
    import math_agent.pdfcheck as module
    project = tmp_path / 'isolated-project'
    (project / 'reference_index').mkdir(parents=True)
    module_path = project / 'src' / 'math_agent' / 'pdfcheck.py'
    monkeypatch.setattr(module, '__file__', str(module_path))
    build = tmp_path / 'probe-build'
    build.mkdir()
    style = build / 'workflow_style.tex'
    style.write_text('original controlled style', encoding='utf-8')
    engine = {'path':'C:/trusted/xelatex.exe','version':'Synthetic engine A'}
    (build/'.math-agent-engine.json').write_text(json.dumps(engine))
    profile = {'theme':'default','measurement':{'status':'measured_probe'}, 'engine':engine,
        'template_fingerprints':{'workflow_style.tex':hashlib.sha256(style.read_bytes()).hexdigest()}}
    (project/'reference_index'/'layout_probe_profiles.json').write_text(json.dumps({'profiles':{'default':profile}}))
    assert module._load_layout_profile(build/'slides.pdf') == profile
    (build/'.math-agent-engine.json').write_text(json.dumps({**engine,'version':'Synthetic engine B'}))
    assert module._load_layout_profile(build/'slides.pdf') is None
    (build/'.math-agent-engine.json').write_text(json.dumps(engine))
    style.write_text('modified template - old geometry is stale', encoding='utf-8')
    assert module._load_layout_profile(build/'slides.pdf') is None


@pytest.mark.unit
def test_pgf_translation_requires_same_frame_visible_glyph_evidence():
    from math_agent.pdfcheck import match_pgf_hidden_character
    hidden={'text':'x','fontname':'AAAAAA+CMR10','size':10,'x0':2028,'top':-1950,'x1':2033,'bottom':-1940}
    visible={'text':'x','fontname':'BBBBBB+CMR10','size':10,'x0':28,'top':50,'x1':33,'bottom':60}
    source={'physical_page':1,'frame_id':'F001','nav_verified':True,'width':453,'height':255,'character_index':12}
    peer={'physical_page':2,'overlay_index':2,'frame_id':'F001','width':453,'height':255,'char':visible,'character_index':12}
    match=match_pgf_hidden_character(hidden,source,[peer])
    assert match and match['visible_physical_page']==2 and match['original_bbox_pt']==[2028,-1950,2033,-1940]
    assert match_pgf_hidden_character(hidden,source,[]) is None
    assert match_pgf_hidden_character(hidden,source,[{**peer,'frame_id':'F002'}]) is None
    assert match_pgf_hidden_character(hidden,source,[{**peer,'char':{**visible,'text':'y'}}]) is None
    assert match_pgf_hidden_character(hidden,source,[{**peer,'char':{**visible,'x0':29}}]) is None
    assert match_pgf_hidden_character(hidden,{**source,'nav_verified':False},[peer]) is None
    assert match_pgf_hidden_character({**hidden,'x0':500,'x1':505},source,[peer]) is None


@pytest.mark.windows_compile
def test_t27_t34_compile_chinese_path_and_all_overlay_pages(tmp_path):
    if os.name != 'nt' or not resolve_xelatex():
        pytest.skip('Actual Windows XeLaTeX unavailable')
    src = source(tmp_path, r'''\documentclass[10pt,aspectratio=169,fontset=fandol]{ctexbeamer}
\setbeamertemplate{navigation symbols}{}
\begin{document}
\section{数列极限}
\begin{frame}{数列极限的定义}
\begin{block}{例题}\normalsize 证明 $a_n=1/n$ 收敛于零。\end{block}
\pause {\normalsize\textbf{证明：}任取 $\varepsilon>0$，取 $N>1/\varepsilon$。当 $n>N$，有 $|a_n|<\varepsilon$。}
\end{frame}
\end{document}''')
    (src / 'main.tex').rename(src / '讲义 (第一章).tex')
    result = TexCompiler(timeout=120).compile(src, '讲义 (第一章).tex', tmp_path / '新 构建 (2)', trusted=True)
    (tmp_path/'compile_result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    assert result['status'] == 'PASS', result
    assert 2 <= result['passes'] <= 4
    pdf = inspect_pdf(Path(result['pdf_path']), tmp_path / '预览', beamer=True)
    assert pdf['page_count'] == 2
    assert len(pdf['pages']) == 2 and all(Path(p['image_path']).is_file() for p in pdf['pages'])
    assert pdf['overlay_map']['status'] == 'PASS'
    assert pdf['overlay_map']['pages'][1]['overlay_index'] == 2
    assert pdf['visual_review']['status'] == 'NOT_RUN'
    assert pdf['status'] == 'PASS', 'PGF-hidden first-overlay solution must not be reported as visible clipping.'
    assert pdf['pages'][0]['geometry']['pgf_hidden_character_count'] > 0
    assert pdf['pages'][0]['overlay_hidden_objects'][0]['visible_physical_page'] == 2


@pytest.mark.unit
def test_tex_auxiliary_disappearing_during_size_scan_is_not_compile_failure():
    from math_agent.compiler import bounded_directory_size
    class VanishingAux:
        def is_file(self): return True
        def stat(self): raise FileNotFoundError('TeX atomically renamed temporary auxiliary')
    class PresentAux:
        def is_file(self): return True
        def stat(self):
            from types import SimpleNamespace
            return SimpleNamespace(st_size=17)
    class Folder:
        def rglob(self, pattern): return iter([VanishingAux(),PresentAux()])
    assert bounded_directory_size(Folder()) == 17


@pytest.mark.windows_compile
def test_t17_cancel_actual_tex_infinite_loop(tmp_path):
    if os.name != 'nt' or not resolve_xelatex():
        pytest.skip('Actual Windows XeLaTeX unavailable')
    src = source(tmp_path, r'\documentclass{article}\begin{document}\loop\iftrue\repeat\end{document}')
    from math_agent.mathcheck import math_child_environment
    unrelated = subprocess.Popen([os.sys.executable, '-c', 'import time; time.sleep(30)'],
        env=math_child_environment(), creationflags=subprocess.CREATE_NO_WINDOW)
    started = time.monotonic()
    try:
        result = TexCompiler(timeout=20).compile(src, 'main.tex', tmp_path / 'cancel-build', trusted=True,
            cancel_check=lambda: time.monotonic() - started > 2)
        assert result['status'] == 'CANCELLED', result
        assert result['pdf_path'] is None and time.monotonic() - started < 12
        assert unrelated.poll() is None, '取消编译不得终止其他 Python 进程'
    finally:
        unrelated.terminate()
        unrelated.wait(timeout=5)


@pytest.mark.windows_compile
def test_t48_actual_failed_compile_keeps_diagnostics(tmp_path):
    if os.name != 'nt' or not resolve_xelatex():
        pytest.skip('Actual Windows XeLaTeX unavailable')
    src = source(tmp_path, r'\documentclass{article}\begin{document}\DefinitelyUndefinedCommand\end{document}')
    result = TexCompiler().compile(src, 'main.tex', tmp_path / 'bad-build', trusted=True)
    assert result['status'] == 'FAIL'
    assert result['pdf_path'] is None
    assert result['log_paths'] and all(Path(p).exists() for p in result['log_paths'])
    assert any(i['rule_id'] == 'UNDEFINED_CONTROL_SEQUENCE' for i in result['issues'])


@pytest.mark.windows_compile
def test_t47_middle_overlay_is_rendered_and_overflow_is_blocked(tmp_path):
    if os.name != 'nt' or not resolve_xelatex():
        pytest.skip('Actual Windows XeLaTeX unavailable')
    src = source(tmp_path, r'''\documentclass[10pt,aspectratio=169]{beamer}
\begin{document}\begin{frame}{Overlay geometry}
Visible on every overlay.
\only<2>{\par\vspace*{25cm}\par MIDDLE OVERFLOW}
\only<3>{Final overlay fits.}
\end{frame}\end{document}''')
    result = TexCompiler().compile(src, 'main.tex', tmp_path / 'middle-build', trusted=True)
    assert result['status'] == 'FAIL' and result['pdf_path'], result
    assert any(i['rule_id'] == 'OVERFULL_BOX' for i in result['issues'])
    pdf = inspect_pdf(Path(result['pdf_path']), tmp_path / 'middle-pages', beamer=True)
    assert pdf['page_count'] == 3 and len(pdf['pages']) == 3
    assert pdf['pages'][1]['overlay_index'] == 2
    assert all(Path(p['image_path']).exists() for p in pdf['pages'])
    assert any(i['severity'] == 'blocking' for i in pdf['pages'][1]['issues'])


@pytest.mark.windows_compile
@pytest.mark.security
def test_t52_actual_openout_restriction_probe(tmp_path):
    engine = resolve_xelatex()
    if os.name != 'nt' or not engine:
        pytest.skip('Actual Windows XeLaTeX unavailable')
    build = tmp_path / 'probe'
    build.mkdir()
    (build / '.tmp').mkdir()
    (build / 'probe.tex').write_text(r'\documentclass{article}\begin{document}\newwrite\f\immediate\openout\f=../escape.txt\immediate\write\f{PROBE}\end{document}')
    proc = subprocess.run([str(engine), '-interaction=nonstopmode', '-halt-on-error', '-no-shell-escape', 'probe.tex'],
        cwd=build, env=safe_child_env(engine, build), capture_output=True, timeout=25,
        creationflags=subprocess.CREATE_NO_WINDOW)
    text = proc.stdout.decode('utf-8', 'replace')
    (build / 'probe.stdout.log').write_text(text, encoding='utf-8')
    assert not (tmp_path / 'escape.txt').exists()
    assert proc.returncode != 0 and ('openout_any' in text or 'Not writing' in text or "can't write" in text), text
