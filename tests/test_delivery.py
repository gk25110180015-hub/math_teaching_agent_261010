"""Actual Windows source delivery regressions, with retained JSON/PDF evidence."""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import hashlib
import json
import os
from pathlib import Path
import shutil
from types import SimpleNamespace
import zipfile

import pytest

from math_agent.compiler import TexCompiler, resolve_xelatex
from math_agent.parsing import safe_extract_zip
from math_agent.pdfcheck import inspect_pdf
from math_agent.pipeline import Pipeline
from math_agent.domain import NewRun
from math_agent.service import Service
from math_agent.settings import Settings

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SYNTHETIC_SECRET = 'SYNTHETIC_DELIVERY_SECRET_MUST_NEVER_EXPORT_20260920'
LECTURE = r'''\documentclass[UTF8,fontset=fandol,11pt]{ctexart}
\usepackage{amsmath,amssymb,amsthm}
\newtheorem{definition}{定义}[section]
\newtheorem{theorem}{定理}[section]
\begin{document}
\section{数列极限}
\begin{definition}若任取 $\varepsilon>0$，存在 $N\in\mathbb N$，使 $n>N$ 时 $|a_n-L|<\varepsilon$，则称 $a_n\to L$。\end{definition}
\begin{theorem}收敛数列的极限唯一。\end{theorem}
\section{基本例题}
证明 $1/n\to0$。\textbf{解：}任取 $\varepsilon>0$，取 $N>1/\varepsilon$，当 $n>N$ 时 $0<1/n<\varepsilon$。
\end{document}
'''


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, data):
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')


def export_fixture(tmp_path: Path) -> Path:
    source = tmp_path / 'fixture_source'
    output = tmp_path / 'fixture_export'
    source.mkdir()
    output.mkdir()
    (source / 'lecture.tex').write_text(LECTURE, encoding='utf-8')
    # These files deliberately live beside the source and must never enter its ZIP.
    (source / '.env').write_text('MATH_AGENT_API_KEY=' + SYNTHETIC_SECRET, encoding='utf-8')
    (source / 'private.sqlite').write_text(SYNTHETIC_SECRET, encoding='utf-8')
    (source / 'provider_response.json').write_text(json.dumps({'token': SYNTHETIC_SECRET}), encoding='utf-8')
    pipeline = Pipeline.__new__(Pipeline)
    pipeline.settings = Settings(workspace=tmp_path/'export-state',model='mock-delivery-fixture')
    service = Service(pipeline.settings)
    pipeline.store = service.store
    pipeline.run = service.create(NewRun(workflow_id='lecture.generate',topic='Synthetic source export fixture'))
    pipeline.model_id = 'gpt6'
    pipeline.export_source(source, 'lecture.tex', output, {'hash': 'synthetic-confirmed-plan-fixture'})
    return output / 'source_bundle.zip'


def existing_or_fixture_bundle(tmp_path: Path) -> tuple[Path, str]:
    existing = PROJECT_ROOT / 'workspace' / 'test-m1-lecture-first'
    matches = sorted(existing.rglob('source_bundle.zip')) if existing.exists() else []
    for path in matches:
        with zipfile.ZipFile(path) as archive:
            if 'lecture.tex' in archive.namelist():
                return path, 'existing_mock_workflow_artifact'
    return export_fixture(tmp_path), 'fresh_synthetic_export_fixture'


@pytest.mark.windows_compile
@pytest.mark.integration
def test_t59_existing_source_bundle_compiles_from_clean_directory(tmp_path):
    if os.name != 'nt' or not resolve_xelatex():
        pytest.skip('Actual Windows XeLaTeX unavailable')
    bundle, origin = existing_or_fixture_bundle(tmp_path)
    extracted = tmp_path / '全新 解压目录 (交付)'
    members = safe_extract_zip(bundle.read_bytes(), extracted)
    assert 'lecture.tex' in members and 'README.md' in members
    assert not any(p.suffix.lower() in {'.env', '.sqlite', '.db'} for p in extracted.rglob('*'))
    before = {p.relative_to(extracted).as_posix(): sha(p) for p in extracted.rglob('*') if p.is_file()}
    result = TexCompiler().compile(extracted, 'lecture.tex', tmp_path / 'clean-build', trusted=True)
    write_json(tmp_path / 'compile_result.json', result)
    assert result['status'] == 'PASS', result
    assert 2 <= result['passes'] <= 4
    pdf = inspect_pdf(Path(result['pdf_path']), tmp_path / 'clean-preview')
    write_json(tmp_path / 'pdf_inspection.json', pdf)
    assert pdf['page_count'] > 0 and len(pdf['pages']) == pdf['page_count']
    assert pdf['visual_review']['status'] == 'NOT_RUN'
    after = {p.relative_to(extracted).as_posix(): sha(p) for p in extracted.rglob('*') if p.is_file()}
    assert before == after, 'Compilation must not mutate extracted editable source.'
    write_json(tmp_path / 'delivery_evidence.json', {
        'test': 'T59', 'status': 'PASS', 'origin': origin, 'bundle_path': str(bundle),
        'bundle_sha256': sha(bundle), 'extracted_files': before,
        'recompiled_pdf_path': result['pdf_path'], 'recompiled_pdf_sha256': result['pdf_sha256'],
        'passes': result['passes'], 'page_count': pdf['page_count'],
        'all_physical_pages_rendered': len(pdf['pages']) == pdf['page_count'],
        'teacher_visual_review': 'NOT_RUN', 'real_api': 'NOT_RUN',
    })


@pytest.mark.windows_compile
@pytest.mark.integration
def test_t49_open_pdf_remains_untouched_while_new_revision_compiles(tmp_path):
    if os.name != 'nt' or not resolve_xelatex():
        pytest.skip('Actual Windows XeLaTeX unavailable')
    src1 = tmp_path / 'source-v1'
    src2 = tmp_path / 'source-v2'
    src1.mkdir()
    (src1 / 'lecture.tex').write_text(LECTURE, encoding='utf-8')
    compiler = TexCompiler()
    first = compiler.compile(src1, 'lecture.tex', tmp_path / 'build-v1', trusted=True)
    write_json(tmp_path / 'compile_v1.json', first)
    assert first['status'] == 'PASS', first
    old_pdf = Path(first['pdf_path'])
    old_hash = sha(old_pdf)
    kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel32.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
        wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    kernel32.CreateFileW.restype = wintypes.HANDLE
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    invalid = ctypes.c_void_p(-1).value
    # Share reads, but deny writes/deletes: reproduces a PDF viewer's restrictive file handle.
    handle = kernel32.CreateFileW(str(old_pdf), 0x80000000, 0x00000001, None, 3, 0x80, None)
    assert handle not in (None, invalid), ctypes.get_last_error()
    write_denied = False
    try:
        try:
            descriptor = os.open(old_pdf, os.O_RDWR)
        except PermissionError:
            write_denied = True
        else:
            os.close(descriptor)
        assert write_denied, 'Fixture must actually hold an exclusive write-denying Windows handle.'
        shutil.copytree(src1, src2)
        text = (src2 / 'lecture.tex').read_text(encoding='utf-8').replace('基本例题', '基本例题（第二版本）')
        (src2 / 'lecture.tex').write_text(text, encoding='utf-8')
        second = compiler.compile(src2, 'lecture.tex', tmp_path / 'build-v2', trusted=True)
        write_json(tmp_path / 'compile_v2.json', second)
        assert second['status'] == 'PASS', second
        assert Path(second['pdf_path']) != old_pdf
        assert sha(old_pdf) == old_hash, 'The open PDF must not be overwritten.'
        assert second['pdf_sha256'] != old_hash
        pdf = inspect_pdf(Path(second['pdf_path']), tmp_path / 'revision-v2-preview')
        write_json(tmp_path / 'pdf_v2_inspection.json', pdf)
        assert len(pdf['pages']) == pdf['page_count'] > 0
    finally:
        kernel32.CloseHandle(handle)
    write_json(tmp_path / 'delivery_evidence.json', {
        'test': 'T49', 'status': 'PASS', 'windows_write_denial_verified': write_denied,
        'old_pdf_path': str(old_pdf), 'old_pdf_sha256_unchanged': sha(old_pdf) == old_hash,
        'new_pdf_path': second['pdf_path'], 'new_pdf_sha256': second['pdf_sha256'],
        'page_count': pdf['page_count'], 'teacher_visual_review': 'NOT_RUN', 'real_api': 'NOT_RUN',
    })


@pytest.mark.security
def test_t55_export_excludes_environment_key_and_private_sidecars(tmp_path, monkeypatch):
    monkeypatch.setenv('MATH_AGENT_API_KEY', SYNTHETIC_SECRET)
    monkeypatch.setenv('MATH_AGENT_LIVE_API_ENABLED', 'false')
    bundle = export_fixture(tmp_path)
    contents = {}
    with zipfile.ZipFile(bundle) as archive:
        for member in archive.infolist():
            data = archive.read(member)
            assert SYNTHETIC_SECRET.encode() not in data
            assert 'MATH_AGENT_API_KEY' not in member.filename
            assert member.filename not in {'.env', 'private.sqlite', 'provider_response.json'}
            contents[member.filename] = {'size_bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
    for sidecar in bundle.parent.glob('*'):
        if sidecar.is_file() and sidecar.suffix != '.zip':
            assert SYNTHETIC_SECRET.encode() not in sidecar.read_bytes()
    assert set(contents) == {'lecture.tex', 'README.md'}
    write_json(tmp_path / 'delivery_evidence.json', {
        'test': 'T55', 'status': 'PASS', 'provider_request_count': 0,
        'synthetic_environment_secret_absent': True, 'private_sidecars_excluded': True,
        'export_members': contents, 'real_api': 'NOT_RUN', 'teacher_visual_review': 'NOT_RUN',
    })
