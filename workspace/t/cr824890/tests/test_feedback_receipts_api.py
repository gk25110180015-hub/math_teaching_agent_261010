"""Current feedback receipt projection through real local API; synthetic evidence only."""
import copy
import json

import pytest

from math_agent.util import digest, now, uid
from test_automatic_recheck_api import case, request_recheck

pytestmark = pytest.mark.unit


def start(case, feedback='1. 夹逼计算训练。\n2. 抵消反例。\n3. 模型单位。'):
    client, service, pipeline, plan = case
    response = request_recheck(client, pipeline, plan, feedback=feedback)
    assert response.status_code == 202
    return response.json(), feedback


def receipt(case, job, feedback, **changes):
    _, _, _, plan = case
    value = {'schema_version': 1, 'job_id': job['id'], 'plan_hash': plan['hash'],
        'plan_revision': plan['revision'], 'feedback_hash': digest(feedback),
        'identity_hash': '1'*64, 'status': 'reviewed',
        'items': [{'id': 'F1', 'status': 'supported_improvement', 'reason': '离线合成证据：练习需要补充。',
            'repair_unit_ids': ['S01.U01'],
            'unit_ids': ['S01.U01'], 'unit_evidence': [{'unit_id': 'S01.U01', 'quote': '合成题面', 'kind': 'worked_example'}],
            'objective_evidence': [{'section_id': 'S01', 'field': 'objectives', 'quote': plan['sections'][0]['objectives'][0]}],
            'repair_instruction': '离线测试修订说明，不是教师意见。'}],
        'limitations': ['合成回执仅验证 API 展示与归属隔离，不是实际模型评估。'],
        'evidence_key': 'runs/offline/feedback-review/receipt.json', 'evidence_sha256': '2'*64,
        'teacher_review': 'NOT_RUN', 'mock': True}
    value['items'] += [{**copy.deepcopy(value['items'][0]), 'id': ident} for ident in ('F2','F3')]
    value.update(changes)
    return value


def add_event(case, value):
    _, service, pipeline, _ = case
    with service.store.transaction() as connection:
        service.store.event(connection, pipeline.run['id'], 'feedback.reviewed', value)


def get_receipt(case):
    client, _, pipeline, _ = case
    response = client.get('/api/runs/' + pipeline.run['id'])
    assert response.status_code == 200, response.text
    return response.json()['feedback_review']


def test_no_feedback_preserves_legacy_detail_with_additive_null_field(case):
    assert get_receipt(case) is None
    start(case, feedback='')
    assert get_receipt(case) is None


def test_current_feedback_without_receipt_is_explicitly_pending(case):
    job, feedback = start(case)
    result = get_receipt(case)
    assert result['status'] == 'pending' and result['items'] == []
    assert result['job_id'] == job['id'] and result['feedback_hash'] == digest(feedback)


@pytest.mark.parametrize('status', ['satisfied', 'supported_improvement', 'rejected_not_supported', 'out_of_scope', 'unresolved'])
def test_valid_current_receipt_states_are_readable_without_approval_or_budget_mutation(case, status):
    _, service, pipeline, _ = case
    job, feedback = start(case)
    data = receipt(case, job, feedback)
    data['items'][0]['status'] = status
    if status != 'supported_improvement': data['items'][0]['repair_unit_ids'] = []
    data['status'] = 'unresolved' if status == 'unresolved' else 'reviewed'
    add_event(case, data)
    before = service.store.get_run(pipeline.run['id'])
    with service.store.connect() as connection:
        events_before = [dict(row) for row in connection.execute('SELECT * FROM events ORDER BY sequence')]
    result = get_receipt(case)
    assert result['items'] == data['items'] and result['teacher_review'] == 'NOT_RUN'
    assert result['status'] == data['status'] and result['mock'] is True
    assert service.store.get_run(pipeline.run['id']) == before
    assert before['reviews'] == []
    with service.store.connect() as connection:
        assert [dict(row) for row in connection.execute('SELECT * FROM events ORDER BY sequence')] == events_before


@pytest.mark.parametrize('fault', ['job_id', 'plan_hash', 'plan_revision'])
def test_receipt_for_other_job_or_plan_is_not_current(case, fault):
    job, feedback = start(case)
    data = receipt(case, job, feedback)
    data[fault] = 999 if fault == 'plan_revision' else 'other'
    add_event(case, data)
    result = get_receipt(case)
    assert result['status'] == 'pending' and result['items'] == []


@pytest.mark.parametrize('fault', ['feedback_hash', 'schema_version', 'teacher_review', 'item_status',
    'duplicate_id', 'missing_item', 'unit_type', 'objective_scope', 'objective_type', 'items_type', 'empty_reviewed', 'mock_type', 'unknown_field', 'repair_scope', 'repair_status'])
def test_latest_invalid_receipt_never_falls_back_to_old_success(case, fault):
    job, feedback = start(case)
    valid = receipt(case, job, feedback)
    valid['items'][0]['status'] = 'satisfied'
    valid['items'][0]['repair_unit_ids'] = []
    add_event(case, valid)
    data = copy.deepcopy(valid)
    if fault == 'feedback_hash': data['feedback_hash'] = '0'*64
    elif fault == 'schema_version': data['schema_version'] = 2
    elif fault == 'teacher_review': data['teacher_review'] = 'APPROVED'
    elif fault == 'item_status': data['items'][0]['status'] = 'teacher_pass'
    elif fault == 'duplicate_id': data['items'].append(copy.deepcopy(data['items'][0]))
    elif fault == 'missing_item': data['items'].pop(1)
    elif fault == 'unit_type': data['items'][0]['unit_ids'] = [None]
    elif fault == 'objective_scope': data['items'][0]['objective_evidence'][0]['section_id'] = 'S99'
    elif fault == 'objective_type': data['items'][0]['objective_evidence'][0]['section_id'] = []
    elif fault == 'items_type': data['items'] = {'F1': 'satisfied'}
    elif fault == 'empty_reviewed': data['items'] = []
    elif fault == 'mock_type': data['mock'] = 'false'
    elif fault == 'unknown_field': data['teacher_approved'] = True
    elif fault == 'repair_scope': data['items'][1]['repair_unit_ids'] = ['not-evidenced']
    elif fault == 'repair_status': data['items'][0]['repair_unit_ids'] = ['S01.U01']
    add_event(case, data)
    result = get_receipt(case)
    assert result['status'] == 'invalid' and result['items'] == []


def test_latest_malformed_json_receipt_is_invalid_without_api_500_or_old_success(case):
    _, service, pipeline, _ = case
    job, feedback = start(case)
    add_event(case, receipt(case, job, feedback))
    with service.store.transaction() as connection:
        service.store.event(connection, pipeline.run['id'], 'feedback.reviewed', {})
        connection.execute("UPDATE events SET payload_json='{' WHERE sequence=(SELECT MAX(sequence) FROM events)")
    result = get_receipt(case)
    assert result['status'] == 'invalid' and result['items'] == []


def test_recovered_answer_unit_id_is_a_valid_receipt_target(case):
    job, feedback = start(case)
    data = receipt(case, job, feedback)
    data['items'][0]['unit_ids'] = ['S02.U18.answer']
    data['items'][0]['repair_unit_ids'] = ['S02.U18.answer']
    data['items'][0]['unit_evidence'][0]['unit_id'] = 'S02.U18.answer'
    add_event(case, data)
    result = get_receipt(case)
    assert result['status'] == 'reviewed'
    assert result['items'][0]['unit_ids'] == ['S02.U18.answer']


def test_approved_delivery_constraint_can_support_a_feedback_receipt(case):
    job, feedback = start(case)
    data = receipt(case, job, feedback)
    data['items'][0]['objective_evidence'] = [{'section_id':None, 'field':'lecture.answers_location', 'quote':'end'}]
    add_event(case, data)
    result = get_receipt(case)
    assert result['status'] == 'reviewed'
    assert result['items'][0]['objective_evidence'][0]['field'] == 'lecture.answers_location'


def test_out_of_scope_item_can_have_no_unit_target_with_scope_evidence(case):
    job, feedback = start(case)
    data = receipt(case, job, feedback)
    data['items'][0].update(status='out_of_scope', unit_ids=[], repair_unit_ids=[], unit_evidence=[], repair_instruction=None,
        objective_evidence=[{'section_id':None,'field':'lecture.answers_location','quote':'end'}])
    add_event(case, data)
    result = get_receipt(case)
    assert result['status'] == 'reviewed' and result['items'][0]['unit_ids'] == []


def test_later_empty_feedback_retracts_old_receipt_and_keeps_history(case):
    client, service, pipeline, plan = case
    job, feedback = start(case)
    add_event(case, receipt(case, job, feedback))
    assert get_receipt(case)['status'] == 'reviewed'
    with service.store.transaction() as connection:
        connection.execute("UPDATE jobs SET status='done' WHERE id=?", (job['id'],))
        connection.execute("UPDATE runs SET status='AWAITING_USER_REVIEW' WHERE id=?", (pipeline.run['id'],))
    new = request_recheck(client, pipeline, plan, idempotency_key='empty-new-action', feedback='')
    assert new.status_code == 202
    assert get_receipt(case) is None
    with service.store.connect() as connection:
        assert connection.execute("SELECT count(*) FROM events WHERE type='feedback.reviewed'").fetchone()[0] == 1


def test_newer_build_with_same_timestamp_does_not_use_previous_job_receipt(case):
    _, service, pipeline, _ = case
    job, feedback = start(case)
    add_event(case, receipt(case, job, feedback))
    with service.store.transaction() as connection:
        stamp = connection.execute('SELECT created_at FROM jobs WHERE id=?', (job['id'],)).fetchone()[0]
        connection.execute("INSERT INTO jobs(id,run_id,kind,build_key,status,created_at) VALUES(?,?,?,?,?,?)",
                           (uid(), pipeline.run['id'], 'build', uid(), 'queued', stamp))
    assert get_receipt(case) is None


def test_beamer_does_not_display_lecture_feedback_receipts(case):
    _, service, pipeline, _ = case
    job, feedback = start(case)
    add_event(case, receipt(case, job, feedback))
    with service.store.transaction() as connection:
        connection.execute("UPDATE runs SET workflow_id='beamer.from_tex' WHERE id=?", (pipeline.run['id'],))
    assert get_receipt(case) is None


@pytest.mark.parametrize('status', ['invalid', 'transport_pending'])
def test_unfinished_receipts_do_not_advertise_successful_items(case, status):
    job, feedback = start(case)
    data = receipt(case, job, feedback, status=status)
    for item in data['items']:
        item.update(status='unresolved', unit_ids=[], repair_unit_ids=[], unit_evidence=[], objective_evidence=[], repair_instruction=None)
    add_event(case, data)
    result = get_receipt(case)
    assert result['status'] == status and all(item['status']=='unresolved' for item in result['items'])
    data['items'] = receipt(case, job, feedback)['items']
    add_event(case, data)
    assert get_receipt(case)['status'] == 'invalid'
