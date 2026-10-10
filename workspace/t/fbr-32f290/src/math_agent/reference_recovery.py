"""Evidence-bound label insertion. The model proposes anchors, never replacement TeX."""
import copy
import json
import re
from pathlib import Path

from pydantic import Field

from .crossrefs import LABEL, reference_registry
from .domain import StrictModel
from .parsing import uncomment
from .util import AgentError, digest, uid, within, write_json


class LabelBinding(StrictModel):
    label: str = Field(min_length=1,max_length=120)
    unit_id: str = Field(min_length=1,max_length=200)
    quote: str = Field(min_length=12,max_length=4000,
        description='Exact unique contiguous quotation from active TeX of this existing unit, including the defining statement.')
    rationale: str = Field(min_length=10,max_length=1500,
        description='Why this quoted mathematical concept is the planned label, not a different or negated concept.')


class LabelProposal(StrictModel):
    bindings: list[LabelBinding] = Field(max_length=100)
    unresolved_labels: list[str] = Field(max_length=100,
        description='Abstain when the existing content does not unambiguously define this label. Never invent content.')


NUMBERED_KINDS={'definition','theorem','example','exercise'}
PREFIX_KINDS={'def':'definition','definition':'definition','thm':'theorem','theorem':'theorem',
    'lem':'theorem','lemma':'theorem','prop':'theorem','cor':'theorem',
    'ex':'example','example':'example','exercise':'exercise'}


def missing_planned_labels(spec,section):
    existing={label for u in section['units'] for label in re.findall(r'\\label\s*\{([^{}]+)\}',uncomment(u['tex']))}
    return [label for label in spec.get('reference_labels',[]) if label not in existing]


def apply_label_proposal(spec,section,plan,proposal):
    """Validate total coverage and unique literal evidence; prepend only inert labels."""
    proposal=LabelProposal.model_validate(proposal).model_dump()
    missing=missing_planned_labels(spec,section)
    registry=reference_registry(plan)
    bindings=proposal['bindings'];labels=[b['label'] for b in bindings]
    unresolved=proposal['unresolved_labels']
    if (len(labels)!=len(set(labels)) or len(unresolved)!=len(set(unresolved))
        or set(labels)&set(unresolved) or set(labels)|set(unresolved)!=set(missing)):
        raise AgentError('LABEL_MAPPING_SCOPE','映射必须精确覆盖本节全部缺失计划标签，不能重复、新增或改动已有标签')
    if unresolved:
        raise AgentError('LABEL_MAPPING_UNRESOLVED','既有正文不能可靠定位计划标签，保留原稿和疑点：'+','.join(unresolved))
    units={u['id']:u for u in section['units']}
    if len(units)!=len(section['units']):
        raise AgentError('LABEL_MAPPING_SCOPE','单元 ID 不唯一，不能自动放置标签')
    for binding in bindings:
        label=binding['label'];unit=units.get(binding['unit_id']);quote=binding['quote']
        expected_kind=PREFIX_KINDS.get(label.split(':',1)[0])
        if (not LABEL.fullmatch(label) or registry.get(label)!=spec['id'] or unit is None
            or expected_kind is None or unit['kind']!=expected_kind or unit['kind'] not in NUMBERED_KINDS):
            raise AgentError('LABEL_MAPPING_SCOPE','标签必须属于本节已批准注册表，并对应受支持的既有编号单元；方程/未知类型须单独审查')
        active=uncomment(unit['tex'])
        if (unit['tex'].count(quote)!=1 or active.count(quote)!=1
            or sum(uncomment(u['tex']).count(quote) for u in section['units'])!=1
            or not re.search(r'[A-Za-z\u3400-\u9fff]',quote)):
            raise AgentError('LABEL_MAPPING_EVIDENCE','映射证据必须是目标单元唯一的、未被注释的精确原文，不能凭模糊或跨单元匹配插入')
    result=copy.deepcopy(section)
    inserted={}
    for unit in result['units']:
        # Preserve approved label order; several distinct labels may share one definition.
        selected=[label for label in missing if any(b['label']==label and b['unit_id']==unit['id'] for b in bindings)]
        if selected:
            prefix=''.join('\\label{'+label+'}' for label in selected)
            unit['tex']=prefix+unit['tex']
            inserted[unit['id']]=prefix
    for before,after in zip(section['units'],result['units']):
        expected={**before,'tex':inserted.get(before['id'],'')+before['tex']}
        if after!=expected:
            raise AgentError('LABEL_MAPPING_SCOPE','除确定性标签前缀外发生内容改变')
    return result,{'schema_version':1,'status':'INSERTED_PENDING_RECHECK','section_id':spec['id'],
        'bindings':bindings,'insertions':inserted,'before_hash':digest(section),'after_hash':digest(result),
        'preserved_fields':['unit IDs/order/kinds/relates_to','all original TeX bytes after inserted prefixes','calculations','calculation_limitations','uncertainties'],
        'limitations':['语义定位来自模型提议；精确引文验证不构成数学证明，必须重新进行单元/引用/数学/模型审阅/编译检查。'],
        'teacher_visual_review':'NOT_RUN'}


def recover_planned_labels(pipeline,spec,section,completed,plan,draft,attempt):
    from .provider import PROMPTS
    context={'section':section,'section_spec':spec,'missing_labels':missing_planned_labels(spec,section),
        'approved_plan':plan,'supported_prefix_kinds':PREFIX_KINDS,
        'instruction':'Map only exact existing definitions. Multiple labels may share a unit. Abstain on ambiguity, negations, equation anchors, or absent content.'}
    identity={'context_hash':digest(context),'preceding_hash':digest(completed),'model':pipeline.settings.model,
        'provider':pipeline.run['input']['provider'],'prompt_hash':digest((PROMPTS/'propose_reference_labels.md').read_bytes()),
        'schema_hash':digest(LabelProposal.model_json_schema()),'implementation_hash':digest(Path(__file__).read_bytes())}
    base=pipeline.root/'label-recovery'/spec['id']/digest(identity)
    cache=base/'cache.json';reused=False
    if cache.is_file():
        try:
            record=json.loads(cache.read_bytes())
            proposal_path=within(pipeline.settings.workspace,record['proposal_key'])
            if record['identity']!=identity or not proposal_path.is_relative_to(base.resolve()):raise ValueError('scope')
            raw=proposal_path.read_bytes()
            if digest(raw)!=record['proposal_hash']:raise ValueError('hash')
            proposal=json.loads(raw);reused=True
        except (OSError,ValueError,KeyError,TypeError):
            raise AgentError('LABEL_RECOVERY_CACHE_INVALID','标签恢复提案缓存路径/哈希失配；证据保留，不静默替换') from None
    else:
        folder=base/('attempt-'+uid()[:12])
        write_json(folder/'before.json',section);write_json(folder/'context.json',context)
        pipeline.stage('REPAIRING','repair.labels.'+spec['id'])
        proposal=pipeline.provider.generate('propose_reference_labels',context,LabelProposal)
        proposal_path=folder/'proposal.json';write_json(proposal_path,proposal)
        # Persist even a semantically rejected mapping for diagnosis, but cache only valid mappings.
    try:
        result,evidence=apply_label_proposal(spec,section,plan,proposal)
    except AgentError as exc:
        write_json(draft/f'label-repair-{attempt}-rejected.json',{'code':exc.code,'message':str(exc),
            'proposal_key':proposal_path.relative_to(pipeline.settings.workspace).as_posix(),'before_hash':digest(section)})
        raise
    evidence.update(identity=identity,proposal_key=proposal_path.relative_to(pipeline.settings.workspace).as_posix(),reused_proposal=reused)
    write_json(draft/f'label-repair-{attempt}-evidence.json',evidence)
    write_json(draft/f'label-repair-{attempt}-candidate.json',result)
    if not reused:
        write_json(proposal_path.parent/'candidate.json',result)
        write_json(proposal_path.parent/'evidence.json',evidence)
        with pipeline.store.transaction() as c:
            pipeline.store.assert_fence(c,pipeline.job)
            write_json(cache,{'identity':identity,'proposal_key':evidence['proposal_key'],
                'proposal_hash':digest(proposal_path.read_bytes()),'status':'UNCHECKED_MAPPING'})
            pipeline.store.event(c,pipeline.run['id'],'labels.proposal_saved',{'section_id':spec['id'],'labels':context['missing_labels'],'status':'UNCHECKED'})
    return result,evidence
