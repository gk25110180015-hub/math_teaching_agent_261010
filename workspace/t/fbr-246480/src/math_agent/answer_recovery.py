"""Persist append-only answer proposals; a cached proposal is never a checked section."""
import json
from pathlib import Path

from .answer_completion import AnswerCompletion, AnswerCompletionError, apply_answer_completion, propose_context
from .util import AgentError, digest, uid, within, write_json


def recover_missing_answers(pipeline, spec, section, completed, plan, draft, attempt):
    from .provider import PROMPTS
    from . import answer_completion
    try:
        context = {**propose_context(section), 'approved_plan': plan,
                   'section_spec': spec, 'prior_sections': [g for _, g in completed]}
    except AnswerCompletionError:
        write_json(draft/f'answer-repair-{attempt}-preflight-blocked.json',
                   {'section_id': spec['id'], 'source_hash': digest(section),
                    'reason': 'Missing targets, source structure, ID collision or bounded capacity rejected',
                    'model_called': False})
        raise AgentError('ANSWER_COMPLETION_BLOCKED', '原稿结构、答案ID或容量不允许安全补答案；未调用模型，原稿保留') from None
    identity = {'context_hash': digest(context), 'model': pipeline.settings.model,
                'provider': pipeline.run['input']['provider'],
                'prompt_hash': digest((PROMPTS/'repair_missing_answers.md').read_bytes()),
                'schema_hash': digest(AnswerCompletion.model_json_schema()),
                'implementation_hash': digest(Path(answer_completion.__file__).read_bytes())}
    base = pipeline.root/'answer-recovery'/spec['id']/digest(identity)
    cache = base/'cache.json'
    reused = False
    if cache.is_file():
        try:
            record = json.loads(cache.read_bytes())
            path = within(pipeline.settings.workspace, record['proposal_key'])
            if record['identity'] != identity or not path.is_relative_to(base.resolve()):
                raise ValueError('identity')
            raw = path.read_bytes()
            if digest(raw) != record['proposal_hash']:
                raise ValueError('hash')
            proposal = json.loads(raw)
            reused = True
        except (OSError, ValueError, KeyError, TypeError):
            raise AgentError('ANSWER_RECOVERY_CACHE_INVALID', '补答案缓存身份或哈希失配；保留原证据，不静默重写') from None
    else:
        folder = base/('attempt-'+uid()[:12])
        write_json(folder/'before.json', section)
        write_json(folder/'context.json', context)
        pipeline.stage('REPAIRING', 'repair.answers.'+spec['id'])
        proposal = pipeline.provider.generate('repair_missing_answers', context, AnswerCompletion)
        path = folder/'proposal.json'
        write_json(path, proposal)
    try:
        result, evidence = apply_answer_completion(section, proposal)
    except (AnswerCompletionError, ValueError) as exc:
        write_json(draft/f'answer-repair-{attempt}-rejected.json',
                   {'proposal_key': path.relative_to(pipeline.settings.workspace).as_posix(),
                    'source_hash': digest(section), 'error_type': type(exc).__name__})
        raise AgentError('ANSWER_COMPLETION_BLOCKED', '补答案候选超出绑定范围或格式不合法；原题和候选均保留') from None
    evidence.update(identity=identity, proposal_key=path.relative_to(pipeline.settings.workspace).as_posix(),
                    reused_proposal=reused)
    write_json(draft/f'answer-repair-{attempt}-evidence.json', evidence)
    write_json(draft/f'answer-repair-{attempt}-candidate.json', result)
    if not reused:
        write_json(path.parent/'candidate.json', result)
        write_json(path.parent/'evidence.json', evidence)
        with pipeline.store.transaction() as connection:
            pipeline.store.assert_fence(connection, pipeline.job)
            write_json(cache, {'identity': identity, 'proposal_key': evidence['proposal_key'],
                              'proposal_hash': digest(path.read_bytes()), 'status': 'UNCHECKED_ANSWERS'})
            pipeline.store.event(connection, pipeline.run['id'], 'answers.proposal_saved',
                                 {'section_id': spec['id'], 'target_ids': evidence['target_ids'], 'status': 'UNCHECKED'})
    return result, evidence
