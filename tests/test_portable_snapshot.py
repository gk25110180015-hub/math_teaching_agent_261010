"""Copied workspaces keep signed history and resolve files in the copied tree."""
import copy
from io import BytesIO
from pathlib import Path
import shutil
import sqlite3
import zipfile

import pytest

from math_agent.beamer_layout import build_measured_beamer
from math_agent.domain import ConfirmRequest, ExecuteRequest, NewRun
from math_agent.partial_delivery import checkpoint_items, download_checkpoint
from math_agent.service import Service
from math_agent.settings import Settings
from math_agent.util import canonical, digest


@pytest.fixture
def setup(tmp_path):
    service = Service(Settings(workspace=tmp_path / 'old', api_key='', deepseek_api_key='', live_api_enabled=False))
    run = service.create(NewRun(workflow_id='lecture.generate', topic='Partial snapshot', trusted_input=True))
    rid = run['id']
    with service.store.transaction() as connection:
        service.store.save_plan(connection, rid, {'title': 'Partial snapshot', 'provider': 'mock',
            'sections': [{'id': 'S01', 'title': 'One'}], 'questions': [], 'unresolved_blocking_questions': []})
    plan = service.store.get_run(rid)['plan']
    service.confirm(rid, ConfirmRequest(expected_plan_revision=plan['revision'], expected_plan_hash=plan['hash'], action_id='fixture'))
    service.execute(rid, ExecuteRequest(expected_plan_revision=plan['revision'], expected_plan_hash=plan['hash'], idempotency_key='fixture'))
    job = service.store.claim('portable-fixture')
    draft = service.settings.workspace / 'b' / rid[:16] / 'sS01_fixture'
    source = draft / 'source' / 'lecture.tex'
    source.parent.mkdir(parents=True)
    source.write_bytes(b'Portable partial source fixture')
    pdf = draft / 'build' / 'lecture.pdf'
    pdf.parent.mkdir()
    pdf.write_bytes(b'%PDF-1.4\nSynthetic hash fixture; not a compiled PDF.\n')
    checkpoint = {'generated': {'section_id': 'S01', 'units': []},
        'source_key': source.relative_to(service.settings.workspace).as_posix(), 'source_hash': digest(source.read_bytes()),
        'report': {'compile': {'status': 'PASS', 'pdf_path': str(pdf), 'pdf_sha256': digest(pdf.read_bytes())}}}
    service.store.checkpoint(job, 'section.S01', 'fixture-input', checkpoint)
    service.store.finish(job, 'BLOCKED', 'fixture', {'code': 'FIXTURE', 'message': 'Offline fixture'})
    return None, service, rid, job, checkpoint, source, pdf


def copied_service(service, destination):
    shutil.copytree(service.settings.workspace, destination, ignore=shutil.ignore_patterns('agent.db*'))
    with service.store.connect() as source, sqlite3.connect(destination / 'agent.db') as target:
        source.backup(target)
    return Service(service.settings.model_copy(update={'workspace': destination}))


def test_partial_pdf_after_move_preserves_records_and_downloads_verified_bytes(setup, tmp_path):
    _, service, rid, _, _, _, pdf = setup
    before = service.store.get_run(rid)
    original = checkpoint_items(service.store, service.settings.workspace, rid, include_bytes=True)
    moved = copied_service(service, tmp_path / 'moved')
    pdf.unlink()  # The original location cannot satisfy the download.
    after = checkpoint_items(moved.store, moved.settings.workspace, rid, include_bytes=True)
    assert after == original
    for item in after[0]['downloads']:
        assert download_checkpoint(moved.store, moved.settings.workspace, rid, item['id'])['_body'] == item['_body']
    assert moved.store.get_run(rid) == before


@pytest.mark.parametrize('fault', ['other_run', 'other_section', 'traversal', 'changed_pdf'])
def test_moved_partial_pdf_rejects_foreign_path_and_changed_bytes(setup, tmp_path, fault):
    _, service, rid, _, checkpoint, _, _ = setup
    moved = copied_service(service, tmp_path / 'moved')
    altered = copy.deepcopy(checkpoint)
    recorded = Path(altered['report']['compile']['pdf_path'])
    if fault == 'other_run':
        altered['report']['compile']['pdf_path'] = str(recorded).replace(rid[:16], 'f' * 16)
    elif fault == 'other_section':
        altered['report']['compile']['pdf_path'] = str(recorded).replace('sS01_fixture', 'sS02_fixture')
    elif fault == 'traversal':
        altered['report']['compile']['pdf_path'] = str(recorded.parent / '..' / 'build' / recorded.name)
    else:
        target = moved.settings.workspace / Path(checkpoint['source_key']).parent.parent / 'build' / 'lecture.pdf'
        target.write_bytes(b'%PDF-tampered')
    with moved.store.transaction() as connection:
        connection.execute('UPDATE steps SET output_json=?,output_hash=? WHERE run_id=?',
                           (canonical(altered), digest(altered), rid))
    item = checkpoint_items(moved.store, moved.settings.workspace, rid)[0]
    assert item['status'] == 'PARTIAL_UNAVAILABLE' and item['downloads'] == []


def test_beamer_move_reads_copied_image_without_mutating_input_or_approval(tmp_path):
    service = Service(Settings(workspace=tmp_path / 'old', api_key='', deepseek_api_key='', live_api_enabled=False))
    run = service.create(NewRun(workflow_id='beamer.from_tex', topic='Portable image', trusted_input=True))
    archive = BytesIO()
    with zipfile.ZipFile(archive, 'w') as bundle:
        bundle.writestr('main.tex', r'\begin{document}\section{Image}\includegraphics{figure.png}\end{document}')
        bundle.writestr('figure.png', b'OFFLINE_IMAGE_COPY_FIXTURE')
    service.attachments(run['id'], 'source.zip', archive.getvalue(), main_file='main.tex')
    saved = service.store.get_run(run['id'])
    with service.store.transaction() as connection:
        service.store.save_plan(connection, run['id'], {'title': 'Portable image', 'provider': 'mock',
            'theme': 'default', 'sections': saved['input']['parsed']['sections'], 'omissions': [],
            'additions': [], 'questions': [], 'unresolved_blocking_questions': []})
    plan = service.store.get_run(run['id'])['plan']
    service.confirm(run['id'], ConfirmRequest(expected_plan_revision=plan['revision'],
                    expected_plan_hash=plan['hash'], action_id='portable-fixture'))
    before = service.store.get_run(run['id'])
    moved = copied_service(service, tmp_path / 'moved')
    (Path(before['input']['parsed']['root']) / 'figure.png').unlink()

    class StopAfterRendering(Exception):
        pass

    class CompileOwner:
        settings = moved.settings
        run = moved.store.get_run(before['id'])

        def compile(self, *args):
            raise StopAfterRendering

    owner = CompileOwner()
    output = tmp_path / 'rendered'
    with pytest.raises(StopAfterRendering):
        build_measured_beamer(owner.run['input']['parsed'], plan, output, tmp_path / 'refs',
                              owner.compile, lambda *args: None)
    assert (output / 'candidate-1' / 'figure.png').read_bytes() == b'OFFLINE_IMAGE_COPY_FIXTURE'
    assert owner.run == before == moved.store.get_run(before['id'])
    assert digest(owner.run['input']) == before['input_hash']

    owner.run = copy.deepcopy(before)
    owner.run['input']['source_key'] = owner.run['input']['source_key'].replace(before['id'], 'f' * 32)
    with pytest.raises(ValueError, match='Snapshot does not belong'):
        build_measured_beamer(owner.run['input']['parsed'], plan, tmp_path / 'bad-render', tmp_path / 'refs',
                              owner.compile, lambda *args: None)


def test_bundled_reference_root_is_preferred_and_explicit_setting_wins(tmp_path, monkeypatch):
    import math_agent.settings as settings_module
    monkeypatch.setattr(settings_module, 'PROJECT_ROOT', tmp_path)
    monkeypatch.delenv('MATH_AGENT_REFERENCE_ROOT', raising=False)
    assert Settings().reference_root == tmp_path.parent
    (tmp_path / 'reference_data').mkdir()
    assert Settings().reference_root == tmp_path / 'reference_data'
    assert Settings(reference_root=tmp_path / 'explicit').reference_root == tmp_path / 'explicit'
