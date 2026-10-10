import json
import pytest
from fastapi.testclient import TestClient
from math_agent.domain import NewRun, ConfirmRequest, ExecuteRequest, DecisionsRequest
from math_agent.settings import Settings
from math_agent.service import Service
from math_agent.worker import Worker
from math_agent.util import AgentError, digest
from math_agent.visualization.models import RefineRequest, Program, Control
from math_agent.visualization.service import refine
from math_agent.visualization.document import interactive_html
from math_agent.visualization.render import child_environment
from math_agent.visualization.render import control_probe_values, scene_probe_times
from math_agent.web.app import create_app


def identity(plan):
    return {'expected_plan_revision': plan['revision'], 'expected_plan_hash': plan['hash']}


@pytest.fixture
def flow(tmp_path, monkeypatch):
    from math_agent.visualization import pipeline
    monkeypatch.setattr(pipeline, 'probe_program', lambda *a: {'status': 'PASS', 'scenes': [], 'controls': []})
    settings = Settings(workspace=tmp_path, live_api_enabled=False)
    service = Service(settings)
    worker = Worker(settings)
    rid = service.create(NewRun(workflow_id='visualization.create', topic='导数', trusted_input=True))['id']
    service.propose(rid); worker.tick()
    return service, worker, rid


def ready(flow):
    service, worker, rid = flow
    plan = service.get(rid)['plan']
    refine(service, rid, RefineRequest(**identity(plan), candidate_id=plan['candidates'][0]['id']))
    worker.tick()
    plan = service.get(rid)['plan']
    refine(service, rid, RefineRequest(**identity(plan), answers={q['id']: q['options'][0]['id'] for q in plan['questions']}))
    worker.tick()
    return service.get(rid)['plan']


def test_candidate_questions_refinement_persist_across_restart(flow):
    service, worker, rid = flow
    run = service.get(rid)
    assert run['status'] == 'AWAITING_PLAN_INPUT' and len(run['plan']['candidates']) >= 3
    assert not run['artifacts'] and not run['approval']
    plan = ready(flow)
    restarted = Service(service.settings).get(rid)
    assert restarted['status'] == 'PLAN_READY' and restarted['plan']['hash'] == plan['hash']
    assert len(plan['decisions']) == 2 and not plan['questions'] and plan['refinement_round'] == 2
    assert plan['question_history'][1]['questions']
    assert any('默认求导点为 1' in v for v in plan['story']['math_notes'])


def test_cannot_confirm_candidate_or_pending_model_refinement(flow):
    service, worker, rid = flow
    plan = service.get(rid)['plan']
    with pytest.raises(AgentError, match='选择'):
        service.confirm(rid, ConfirmRequest(**identity(plan), action_id='premature'))
    refine(service, rid, RefineRequest(**identity(plan), candidate_id='C1'))
    plan = service.get(rid)['plan']
    with pytest.raises(AgentError):
        service.confirm(rid, ConfirmRequest(**identity(plan), action_id='pending'))
    assert not service.get(rid)['approval']


def test_old_revision_double_submission_and_invalid_options_rejected(flow):
    service, worker, rid = flow
    plan = service.get(rid)['plan']
    req = RefineRequest(**identity(plan), candidate_id='C1')
    refine(service, rid, req)
    with pytest.raises(AgentError) as error:
        refine(service, rid, req)
    assert error.value.status == 409
    worker.tick(); plan = service.get(rid)['plan']
    with pytest.raises(AgentError):
        refine(service, rid, RefineRequest(**identity(plan), answers={q['id']: 'NOT_AN_OPTION' for q in plan['questions']}))
    with pytest.raises(AgentError):
        refine(service, rid, RefineRequest(**identity(plan), answers={plan['questions'][0]['id']: 'SQUARE'}))


def test_legacy_plan_endpoint_cannot_skip_model_refinement(flow):
    service, _, rid = flow
    with pytest.raises(AgentError) as error:
        service.decisions(rid, DecisionsRequest(expected_plan_revision=1))
    assert error.value.code == 'VISUAL_PLAN_ENDPOINT'


def test_execute_idempotent_and_cancel_blocks_late_refinement(flow):
    service, worker, rid = flow
    plan = ready(flow)
    service.confirm(rid, ConfirmRequest(**identity(plan), action_id='confirmed'))
    req = ExecuteRequest(**identity(plan), idempotency_key='double-click')
    assert service.execute(rid, req)['id'] == service.execute(rid, req)['id']
    service.cancel(rid)
    assert not worker.tick()
    assert service.get(rid)['status'] == 'CANCELLED'


def test_failing_model_retains_decisions_and_retry(flow, monkeypatch):
    service, worker, rid = flow
    plan = service.get(rid)['plan']
    refine(service, rid, RefineRequest(**identity(plan), candidate_id='C2'))
    from math_agent.visualization import mock
    original = mock.generate
    monkeypatch.setattr(mock, 'generate', lambda *a: (_ for _ in ()).throw(AgentError('PROVIDER_UNAVAILABLE','temporary failure')))
    worker.tick()
    failed = service.get(rid)
    assert failed['status'] == 'BLOCKED' and failed['plan']['selected_candidate_id'] == 'C2'
    monkeypatch.setattr(mock, 'generate', original)
    service.retry(rid); worker.tick()
    assert service.get(rid)['plan']['questions']
    assert len(service.get(rid)['plan']['decisions']) == 1


def test_new_ambiguity_requires_another_round(flow, monkeypatch):
    service, worker, rid = flow
    from math_agent.visualization import mock
    original = mock.generate
    def extra_question(role, context, schema):
        result = original(role, context, schema)
        if role == 'visualization_refine' and context['current_plan']['refinement_round'] == 1:
            result['questions'] = [{'id': 'Q-precision', 'prompt': '数值显示几位小数？', 'reason': '误差的可见精度需要选择。',
                                   'options': [{'id': 'FIVE', 'label': '五位', 'effect': '显示五位小数'}, {'id': 'THREE', 'label': '三位', 'effect': '显示三位小数'}]}]
        return schema.model_validate(result).model_dump()
    monkeypatch.setattr(mock, 'generate', extra_question)
    plan = ready(flow)
    assert plan['phase'] == 'questions' and service.get(rid)['status'] == 'AWAITING_PLAN_INPUT'
    with pytest.raises(AgentError):
        service.confirm(rid, ConfirmRequest(**identity(plan), action_id='too-early'))
    refine(service, rid, RefineRequest(**identity(plan), answers={'Q-precision': 'FIVE'})); worker.tick()
    plan = service.get(rid)['plan']
    assert plan['phase'] == 'ready' and len(plan['decisions']) == 3


def test_cancelled_model_response_never_commits_plan(flow, monkeypatch):
    service, worker, rid = flow
    plan = service.get(rid)['plan']
    refine(service, rid, RefineRequest(**identity(plan), candidate_id='C1'))
    from math_agent.visualization import mock
    original = mock.generate
    def cancel_before_return(*args):
        result = original(*args); service.cancel(rid); return result
    monkeypatch.setattr(mock, 'generate', cancel_before_return)
    worker.tick()
    run = service.get(rid)
    assert run['status'] == 'CANCELLED' and run['plan']['pending_refinement']
    assert run['plan']['refinement_round'] == 0


def test_failed_render_keeps_diagnostics_without_publishing_video(flow, monkeypatch):
    service, worker, rid = flow
    plan = ready(flow)
    service.confirm(rid, ConfirmRequest(**identity(plan), action_id='confirmed'))
    service.execute(rid, ExecuteRequest(**identity(plan), idempotency_key='build'))
    from math_agent.visualization import pipeline
    monkeypatch.setattr(pipeline, 'render_video', lambda *a: (_ for _ in ()).throw(AgentError('VISUAL_RENDER_FAILED', 'synthetic renderer failure')))
    worker.tick(); run = service.get(rid)
    assert run['status'] == 'BLOCKED' and run['approval']['hash'] == plan['hash']
    assert any(a['metadata'].get('kind') == 'visualization_draft' for a in run['artifacts'])
    assert not any(a['name'] == 'video.webm' for a in run['artifacts'])


def test_repair_preserves_history_and_retry_starts_from_last_failure(flow, monkeypatch):
    service, worker, rid = flow
    plan = ready(flow)
    service.confirm(rid, ConfirmRequest(**identity(plan), action_id='confirmed'))
    from math_agent.visualization import mock, recovery
    original = mock.generate
    written = []
    def rejecting(role, context, schema):
        if role == 'visualization_writer':
            written.append(context)
            assert [s['id'] for s in context['scene_requirements']] == [s['id'] for s in plan['story']['scenes']]
            assert all(s['visual'] and len(s['sample_times'])==5 for s in context['scene_requirements'])
            program = original(role, context, schema)
            if 'code' in program:
                program['code'] += f'\n// repair attempt {len(written)}'
            else:
                program['edits'][-1]['new'] += f'\n// repair attempt {len(written)}'
            return program
        if role == 'visualization_reviewer':
            assert 'runtime_evidence' in context
            return {'approved': False, 'issues': [f'problem-{len(written)}'], 'limitations': []}
        return original(role, context, schema)
    monkeypatch.setattr(mock, 'generate', rejecting)
    service.execute(rid, ExecuteRequest(**identity(plan), idempotency_key='build'))
    worker.tick()
    assert len(written) == 3
    assert written[-1]['repair_history'] == [{'issues': ['problem-1']}, {'issues': ['problem-2']}]
    saved = recovery.last_failure(service.store, service.settings.workspace, service.get(rid))
    assert saved['previous_program']['code'].endswith('// repair attempt 3')
    service.retry(rid); worker.tick()
    assert len(written) == 6
    assert written[3]['previous_program']['code'].endswith('// repair attempt 3')
    assert written[3]['repair_issues'] == ['problem-3']
    run = service.get(rid)
    assert run['approval']['hash'] == run['plan']['hash'] == plan['hash']
    assert len(recovery.last_failure(service.store, service.settings.workspace, run)['repair_history']) == 6


def test_runtime_control_failure_cannot_be_overridden_by_model_approval(flow, monkeypatch):
    service, worker, rid = flow
    plan = ready(flow)
    service.confirm(rid, ConfirmRequest(**identity(plan), action_id='confirmed'))
    from math_agent.visualization import pipeline
    monkeypatch.setattr(pipeline, 'probe_program', lambda *a: {'status': 'FAIL', 'issues': ['example 未改变画面']})
    def must_not_record(*args):
        pytest.fail('A failed interactive program must not reach video recording')
    monkeypatch.setattr(pipeline, 'render_video', must_not_record)
    service.execute(rid, ExecuteRequest(**identity(plan), idempotency_key='build'))
    worker.tick()
    run = service.get(rid)
    assert run['status'] == 'BLOCKED' and run['error']['code'] == 'VISUAL_QUALITY_BLOCKED'
    assert 'example' in run['error']['message']
    assert any(a['name'] == 'probes-2.json' for a in run['artifacts'])
    assert not any(a['metadata'].get('kind') == 'visualization' for a in run['artifacts'])


def test_legacy_failed_program_recovery_checks_hash_and_plan(flow):
    service, worker, rid = flow
    plan = ready(flow)
    service.confirm(rid, ConfirmRequest(**identity(plan), action_id='confirmed'))
    service.execute(rid, ExecuteRequest(**identity(plan), idempotency_key='build'))
    job = service.store.claim('legacy-fixture')
    from math_agent.visualization import mock, recovery
    program = mock.generate('visualization_writer', {'input': service.get(rid)['input'], 'confirmed_plan': plan}, Program)
    files = {'program-2.json': program, 'issues-2.json': ['example 未生效']}
    for name, value in files.items():
        path = service.settings.workspace/name
        path.write_text(json.dumps(value), encoding='utf-8')
        service.store.publish_artifacts(job, [{'storage_key': name, 'name': name, 'media_type': 'application/json',
            'sha256': digest(path.read_bytes()), 'metadata': {'kind': 'visualization_draft', 'plan_hash': plan['hash']}}])
    run = service.get(rid)
    restored = recovery.last_failure(service.store, service.settings.workspace, run)
    assert restored['previous_program'] == program and restored['repair_issues'] == ['example 未生效']
    (service.settings.workspace/'program-2.json').write_text('{}', encoding='utf-8')
    assert recovery.last_failure(service.store, service.settings.workspace, run) == {}


def test_generated_program_cannot_escape_json_script_or_child_environment(monkeypatch):
    from math_agent.visualization.mock import story, DERIVATIVE
    output = interactive_html(story(False), {'code': DERIVATIVE+'\n// </script><script>attack()</script>', 'controls': [],
        'explanation': '<script>attack()</script>', 'limitations': []}, 'mock')
    assert '</script><script>attack()' not in output
    assert '\\u003c/script' in output
    monkeypatch.setenv('MATH_AGENT_API_KEY', 'secret-sentinel')
    monkeypatch.setenv('MATH_AGENT_DEEPSEEK_API_KEY', 'second-sentinel')
    assert all('API_KEY' not in key for key in child_environment())


@pytest.mark.parametrize('value', [float('nan'), float('inf'), -2, 3])
def test_control_boundaries(value):
    with pytest.raises(ValueError):
        Control(id='x', label='x', min=0., max=2., step=.1, value=value)


def test_control_probe_covers_periodic_angles_and_each_scene():
    assert control_probe_values({'min': -180., 'max': 180., 'step': 1.}) == [-180., 0., 180.]
    assert control_probe_values({'min': 0., 'max': 1., 'step': 1.}) == [0., 1.]
    times = scene_probe_times({'scenes': [{'seconds': 15}, {'seconds': 15}, {'seconds': 18}, {'seconds': 15}, {'seconds': 15}, {'seconds': 12}]})
    assert (48+7.5)/90 in times  # A control used only in scene 4 still gets tested.


def test_metrics_accept_mathematical_states_and_report_precise_invalid_paths():
    from math_agent.visualization.render import finite_metrics, metric_issues
    assert finite_metrics({'stationary':True,'derivative':0,'trend':'驻点','domain':[-2,2]})
    assert not finite_metrics({'slope':float('nan')})
    assert not finite_metrics({})
    assert metric_issues({'state':{'derivative':None}})[0].startswith('metrics.state.derivative')


def test_story_requirements_and_samples_cover_both_stationary_holds():
    from math_agent.visualization.contracts import scene_requirements
    from math_agent.visualization.render import presentation_probe_times, review_evidence
    story={'scenes':[{'id':'S1','seconds':6,'visual':'全图'}, {'id':'S2','seconds':12,'visual':'驻点放大与左右符号'}]}
    requirements=scene_requirements(story)
    assert requirements[1]['start_time']==pytest.approx(1/3)
    times=presentation_probe_times(story)
    assert (6+12*.3)/18 in times and (6+12*.7)/18 in times
    probes=[{'time':t,'values':[{'caption':'切线斜率为正','metrics':{'derivative':2}}]} for t in (0.1,0.5)]
    evidence=review_evidence({'status':'PASS','scenes':[{'drawing_evidence':{'rectangles':[1]}}],
        'controls':[{'id':'x','status':'PASS','probes':probes}]})
    assert len(evidence['controls'][0]['probes'])==2
    assert evidence['scenes'][0]['drawing_evidence']['rectangles']==[1]


def test_unclipped_plot_text_overflow_is_actionable():
    from math_agent.visualization.render import text_overflow_issues
    label={'text':'长侧栏说明','bounds':[650,210,1024,232],'clipped':False}
    sample={'drawing_evidence':{'texts':[label]}}
    assert '长侧栏说明' in text_overflow_issues(sample)[0]
    label['clipped']=True
    assert text_overflow_issues(sample)==[]


def test_generation_context_preserves_confirmed_choices_without_unselected_stories():
    import copy
    from math_agent.visualization.contracts import confirmed_context
    plan={'hash':'approved','story':{'title':'确认的分镜'},'candidates':[{'id':'C2','title':'未选方案'}],
        'decisions':[{'id':'D1','candidate':{'id':'C1','title':'选择的方案','scenes':[1,2]},
                      'answers':[{'option':{'effect':'展示两个驻点'}}]}], 'decision_ids':['D1']}
    original=copy.deepcopy(plan)
    context=confirmed_context(plan)
    assert context['story']==plan['story'] and context['decision_ids']==['D1']
    assert context['decisions'][0]['answers']==plan['decisions'][0]['answers']
    assert context['decisions'][0]['candidate']=={'id':'C1','title':'选择的方案'}
    assert 'candidates' not in context and plan==original


def test_api_guards_and_new_page(flow):
    service, worker, rid = flow
    with TestClient(create_app(service.settings), base_url='http://127.0.0.1:8765') as client:
        csrf = client.get('/api/session').json()['csrf_token']
        client.headers['X-CSRF-Token'] = csrf
        assert client.get('/visualizations').status_code == 200
        assert 'visualizations' in client.get('/').text
        plan = service.get(rid)['plan']
        payload = {**identity(plan), 'candidate_id': 'C1'}
        assert client.post(f'/api/runs/{rid}/visualization/refine', json=payload, headers={'X-CSRF-Token': ''}).status_code == 403
        assert client.post(f'/api/runs/{rid}/visualization/refine', json=payload).status_code == 202
        assert client.post(f'/api/runs/{rid}/visualization/refine', json=payload).status_code == 409
        assert client.get('/api/visualizations/artifacts/not-real/preview').status_code == 404


def test_preview_is_sandboxed_and_hash_checked(flow):
    service, _, rid = flow
    plan=ready(flow)
    service.confirm(rid, ConfirmRequest(**identity(plan), action_id='confirm'))
    service.execute(rid, ExecuteRequest(**identity(plan), idempotency_key='build'))
    job=service.store.claim('test-publisher')
    path=service.settings.workspace/'interactive.html';path.write_text('<html>test</html>',encoding='utf-8')
    service.store.publish_artifacts(job,[{'storage_key':'interactive.html','name':'interactive.html','media_type':'text/html','sha256':digest(path.read_bytes())}])
    aid=service.get(rid)['artifacts'][0]['artifact_id']
    with TestClient(create_app(service.settings),base_url='http://127.0.0.1:8765') as client:
        client.get('/api/session')
        response=client.get(f'/api/visualizations/artifacts/{aid}/preview')
        assert response.status_code==200
        policy=response.headers['Content-Security-Policy']
        assert 'sandbox allow-scripts' in policy and 'allow-same-origin' not in policy and "connect-src 'none'" in policy
        assert 'attachment' in client.get(f'/api/artifacts/{aid}').headers['Content-Disposition']
        path.write_text('<html>changed</html>',encoding='utf-8')
        assert client.get(f'/api/visualizations/artifacts/{aid}/preview').status_code==409
