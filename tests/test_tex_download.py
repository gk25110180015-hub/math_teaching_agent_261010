"""Registered lecture source downloads, using an isolated mock build only.

The real renderer, ZIP exporter, artifact registry and HTTP endpoint run here.
The compiler is an explicit stub; no model API or teacher acceptance is claimed.
"""
import io
import os
import zipfile

import pytest
from fastapi.testclient import TestClient

from math_agent.pipeline import Pipeline
from math_agent.util import digest, within
from math_agent.web.app import create_app
from test_draft_recovery import OfflineProvider, setup_pipeline


@pytest.fixture
def delivered_lecture(tmp_path, monkeypatch):
    for key in tuple(os.environ):
        if key.startswith('MATH_AGENT_'):
            monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv('MATH_AGENT_LIVE_API_ENABLED', 'false')

    def mock_compile(self, source, entry, build):
        build.mkdir(parents=True, exist_ok=True)
        return {'status': 'PASS', 'issues': [], 'pdf_path': None,
                'fixture': 'MOCK_COMPILER_NO_TEX_PROCESS', 'passes': 0}

    monkeypatch.setattr(Pipeline, 'compile', mock_compile)
    service, pipeline, _ = setup_pipeline(tmp_path / 'isolated', OfflineProvider())
    pipeline.build()
    run = service.get(pipeline.run['id'])
    assert run['status'] == 'AWAITING_USER_REVIEW' and run['reviews'] == []
    assert run['input']['provider'] == 'mock'
    artifacts = {item['name']: item for item in run['artifacts']}
    assert {'lecture.tex', 'source_bundle.zip'} <= set(artifacts)
    with service.store.connect() as connection:
        row = connection.execute('SELECT storage_key FROM artifacts WHERE artifact_id=?',
                                 (artifacts['lecture.tex']['artifact_id'],)).fetchone()
    source = within(pipeline.settings.workspace, row['storage_key'])
    app = create_app(pipeline.settings)
    with TestClient(app, base_url='http://127.0.0.1:8765') as client:
        client.get('/api/session')
        yield client, service, run['id'], artifacts, source


def test_registered_tex_is_an_attachment_and_matches_the_exported_zip(delivered_lecture):
    client, service, rid, artifacts, source = delivered_lecture
    listed = client.get(f'/api/runs/{rid}/artifacts')
    assert listed.status_code == 200
    tex = next(item for item in listed.json() if item['name'] == 'lecture.tex')
    response = client.get('/api/artifacts/' + tex['artifact_id'])
    assert response.status_code == 200
    assert response.headers['content-disposition'] == 'attachment; filename="lecture.tex"'
    assert response.headers['x-content-type-options'] == 'nosniff'
    assert response.headers['cache-control'] == 'no-store'
    assert response.content == source.read_bytes()
    assert digest(response.content) == tex['sha256']
    assert r'\documentclass' in response.text and '实数列按正整数下标排列' in response.text
    bundle = client.get('/api/artifacts/' + artifacts['source_bundle.zip']['artifact_id'])
    assert bundle.status_code == 200
    assert bundle.headers['content-disposition'].startswith('attachment;')
    assert digest(bundle.content) == artifacts['source_bundle.zip']['sha256']
    with zipfile.ZipFile(io.BytesIO(bundle.content)) as exported:
        assert exported.read('lecture.tex') == response.content
        assert 'README.md' in exported.namelist()
    # Downloading either source representation is not human approval.
    after = service.get(rid)
    assert after['status'] == 'AWAITING_USER_REVIEW' and after['reviews'] == []


@pytest.mark.parametrize('fault, status, code', [
    ('changed', 409, 'ARTIFACT_CHANGED'),
    ('missing', 404, 'MISSING_ARTIFACT'),
    ('outside_workspace', 403, 'BAD_ARTIFACT'),
])
def test_invalid_registered_tex_is_not_delivered(delivered_lecture, fault, status, code):
    client, service, rid, artifacts, source = delivered_lecture
    artifact = artifacts['lecture.tex']
    if fault == 'changed':
        source.write_bytes(source.read_bytes() + b'\n% isolated tamper fixture\n')
    elif fault == 'missing':
        source.unlink()
    else:
        outside = service.settings.workspace.parent / 'outside.tex'
        outside.write_bytes(b'ISOLATED_OUTSIDE_WORKSPACE_FIXTURE')
        with service.store.transaction() as connection:
            connection.execute('UPDATE artifacts SET storage_key=?,sha256=? WHERE artifact_id=?',
                               ('../outside.tex', digest(outside.read_bytes()), artifact['artifact_id']))
    response = client.get('/api/artifacts/' + artifact['artifact_id'])
    assert response.status_code == status and response.json()['error']['code'] == code
    assert 'ISOLATED_OUTSIDE_WORKSPACE_FIXTURE' not in response.text
    # The endpoint retains the original record for diagnosis rather than
    # publishing an unregistered replacement or changing the review status.
    assert any(item['artifact_id'] == artifact['artifact_id'] for item in service.get(rid)['artifacts'])
    assert service.get(rid)['reviews'] == []


@pytest.mark.parametrize('fault, code', [
    ('no_session', 'SESSION_REQUIRED'),
    ('foreign_origin', 'ORIGIN_REJECTED'),
    ('foreign_host', 'HOST_REJECTED'),
    ('cross_site', 'CROSS_SITE'),
])
def test_tex_download_uses_the_existing_local_access_boundary(delivered_lecture, fault, code):
    client, _, _, artifacts, _ = delivered_lecture
    headers = {}
    if fault == 'no_session':
        client.cookies.clear()
    elif fault == 'foreign_origin':
        headers['Origin'] = 'https://unrelated.example'
    elif fault == 'foreign_host':
        headers['Host'] = 'unrelated.example'
    else:
        headers['Sec-Fetch-Site'] = 'cross-site'
    response = client.get('/api/artifacts/' + artifacts['lecture.tex']['artifact_id'], headers=headers)
    assert response.status_code == 403 and response.json()['error']['code'] == code
