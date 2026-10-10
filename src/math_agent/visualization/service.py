"""Short transactions; model work is queued, including each plan revision."""
from ..util import AgentError, canonical, digest, now, uid

WORKFLOW = 'visualization.create'


def refine(service, run_id, req):
    with service.store.transaction() as c:
        run, plan = service._check_expected(c, run_id, req.expected_plan_revision, req.expected_plan_hash)
        if run['workflow_id'] != WORKFLOW:
            raise AgentError('WORKFLOW_MISMATCH', '此接口仅用于概念可视化')
        if run['status'] not in ('AWAITING_PLAN_INPUT', 'PLAN_READY', 'PLAN_CONFIRMED'):
            raise AgentError('PLAN_IN_USE', '等待当前步骤结束后再修改计划', 409)
        if not req.candidate_id and not req.answers and not req.suggestion.strip():
            raise AgentError('EMPTY_DECISION', '请选择方案、回答问题或填写建议')
        decision = {'id': uid(), 'actor': service.actor, 'timestamp': now(),
                    'suggestion': req.suggestion.strip(), 'answers': []}
        if plan['phase'] == 'candidates':
            candidate = next((v for v in plan['candidates'] if v['id'] == req.candidate_id), None)
            if not candidate:
                raise AgentError('CANDIDATE_REQUIRED', '请选择一个当前候选方案')
            plan['selected_candidate_id'] = candidate['id']
            plan['story'] = {k: v for k, v in candidate.items() if k != 'id'}
            decision['candidate'] = candidate
        elif req.candidate_id:
            raise AgentError('CANDIDATE_LOCKED', '已选定候选方向；可用建议修改内容，或新建任务选择另一方向')
        questions = {q['id']: q for q in plan.get('questions', [])}
        if not set(req.answers).issubset(questions):
            raise AgentError('QUESTION_CONFLICT', '问题已经更新，请刷新', 409)
        if questions and set(req.answers) != set(questions) and not req.suggestion.strip():
            raise AgentError('UNANSWERED_QUESTIONS', '请回答本轮全部问题，或提交自定义建议交由模型重新规划')
        for qid, oid in req.answers.items():
            option = next((o for o in questions[qid]['options'] if o['id'] == oid), None)
            if not option:
                raise AgentError('INVALID_OPTION', '选择不属于当前问题')
            decision['answers'].append({'question': questions[qid], 'option': option})
        plan.setdefault('decisions', []).append(decision)
        plan.setdefault('decision_ids', []).append(decision['id'])
        plan['pending_refinement'] = decision['id']
        plan['unresolved_blocking_questions'] = ['MODEL_REFINEMENT_PENDING']
        c.execute('INSERT INTO decisions VALUES(?,?,?,?,?,?,?)',
                  (decision['id'], run_id, 'visualization.refine', plan['revision'], canonical(decision), service.actor, now()))
        saved = service.store.save_plan(c, run_id, plan)
        return service._enqueue(c, service.store.row(c, run_id), 'plan', digest([run_id, 'visualization.refine', saved['hash']]))
