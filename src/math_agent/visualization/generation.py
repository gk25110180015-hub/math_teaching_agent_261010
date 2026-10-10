"""Bind local model edits to the rejected source; keep unrelated code byte-for-byte."""
from ..util import AgentError
from .models import Program, ProgramRepair


def apply_repair(previous, proposal):
    proposal = ProgramRepair.model_validate(proposal).model_dump()
    code = previous['code']
    spans = []
    for index, edit in enumerate(proposal['edits']):
        if code.count(edit['old']) != 1:
            raise ValueError(f'edits[{index}].old 必须在 previous_program.code 中逐字唯一命中；请附带足够上下文')
        if edit['old'] == code:
            raise ValueError('不可用整段 code 作为替换锚点；请按具体问题提交局部修改')
        start = code.index(edit['old'])
        spans.append((start, start+len(edit['old']), edit['new']))
    spans.sort()
    if any(left[1] > right[0] for left, right in zip(spans, spans[1:])):
        raise ValueError('edits 的原文区间不能重叠；同一处的修改请合并为一个 edit')
    if sum(end-start for start,end,_ in spans) > len(code)*.8:
        raise ValueError('局部修复替换范围超过原代码的 80%；请缩小到与当前问题直接相关的片段')
    for start, end, replacement in reversed(spans):
        code = code[:start] + replacement + code[end:]
    result = {**previous, 'code':code, 'runtime_version':2,
              **{k:v for k,v in proposal.items() if k != 'edits' and v is not None}}
    return Program.model_validate(result).model_dump()


def generate_program(generate, context, repair_attempts=2, record=lambda *args: None):
    previous = context.get('previous_program')
    if not previous or previous.get('runtime_version') != 2:
        return generate('visualization_writer', context, Program)
    context = {**context, 'repair_format':'anchored_edits',
        'edit_contract':'所有 old 都相对同一个 previous_program.code；逐字唯一、不重叠。未改动部分由宿主原样保留。'}
    for attempt in range(repair_attempts + 1):
        proposal = generate('visualization_writer', context, ProgramRepair)
        record(attempt, proposal)
        try:
            return apply_repair(previous, proposal)
        except ValueError as error:
            if attempt == repair_attempts:
                raise AgentError('VISUAL_PATCH_BLOCKED', '可视化局部修复未能绑定原稿：' + str(error)) from error
            context = {**context, 'previous_repair':proposal, 'patch_validation_feedback':[str(error)]}
