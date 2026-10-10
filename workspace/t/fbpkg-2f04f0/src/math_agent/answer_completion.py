"""Append-only completion of explicitly missing example/exercise answers.

This module proposes and applies unchecked candidates only. It never calls a
model, normalizes TeX, executes calculations, writes files, or approves content.
The pipeline must retain evidence and repeat all existing checks after applying.
"""
from __future__ import annotations

import copy
import json
import re

from pydantic import Field, model_validator

from .calculation_protocol import calculation_protocol
from .domain import StrictModel
from .parsing import _mask_verbatim, uncomment
from .util import digest

MAX_UNITS = 100
MAX_CALCULATIONS = 100
MAX_CALCULATION_BYTES = 65536
_KINDS = {'definition', 'theorem', 'example', 'solution', 'proof', 'exercise', 'explanation'}
_FORBIDDEN_BODY = re.compile(
    r'\\(?:documentclass|usepackage|RequirePackage|newcommand|renewcommand|providecommand|'
    r'newtheorem|def|gdef|edef|xdef|global|section|subsection|chapter|input|include)(?![A-Za-z@])'
    r'|\\(?:begin|end)\s*\{(?:document|definition|theorem|lemma|proposition|corollary|example|exercise|problem|question)\*?\}'
)


class AnswerCompletionError(ValueError):
    """The candidate cannot be applied without changing unapproved content."""


class CompletedAnswer(StrictModel):
    target_id: str = Field(min_length=1, max_length=500)
    tex: str = Field(min_length=1, max_length=30000)

    @model_validator(mode='after')
    def nonblank(self):
        if not self.target_id.strip() or not self.tex.strip():
            raise ValueError('Answer target and body must be nonblank')
        return self


class AnswerCompletion(StrictModel):
    section_id: str = Field(min_length=1, max_length=500)
    answers: list[CompletedAnswer] = Field(min_length=1, max_length=MAX_UNITS)
    calculations: list[dict] = Field(default_factory=list, max_length=MAX_CALCULATIONS)
    calculation_limitations: list[str] = Field(default_factory=list, max_length=100)
    uncertainties: list[str] = Field(default_factory=list, max_length=100)

    @model_validator(mode='after')
    def bounded_notes(self):
        for note in self.calculation_limitations + self.uncertainties:
            if not note.strip() or len(note) > 5000:
                raise ValueError('New limitation/uncertainty notes must be nonblank and at most 5000 characters')
        return self


def _json_bytes(value) -> bytes:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False).encode('utf-8')
    except (TypeError, ValueError, UnicodeError, RecursionError) as error:
        raise AnswerCompletionError('Completion data must be finite, encodable JSON') from error


def _validate_section(section: dict) -> None:
    if not isinstance(section, dict) or not isinstance(section.get('section_id'), str) or not section['section_id'].strip() or len(section['section_id']) > 500:
        raise AnswerCompletionError('A section with an exact section_id is required')
    units = section.get('units')
    if not isinstance(units, list) or not 1 <= len(units) <= MAX_UNITS:
        raise AnswerCompletionError('Source section must contain 1..100 existing units')
    ids = []
    for unit in units:
        if (not isinstance(unit, dict) or not isinstance(unit.get('id'), str) or not unit['id'].strip() or len(unit['id']) > 500
                or not isinstance(unit.get('kind'), str) or unit['kind'] not in _KINDS or not isinstance(unit.get('tex'), str)
                or not unit['tex'].strip() or len(unit['tex']) > 30000
                or (unit.get('relates_to') is not None and not isinstance(unit['relates_to'], str))):
            raise AnswerCompletionError('Source unit is structurally invalid')
        ids.append(unit['id'])
    if len(ids) != len(set(ids)):
        raise AnswerCompletionError('Source unit IDs must be unique')
    calculations = section.get('calculations', [])
    if not isinstance(calculations, list) or len(calculations) > MAX_CALCULATIONS or not all(isinstance(c, dict) for c in calculations):
        raise AnswerCompletionError('Existing calculations must be a list of at most 100 JSON requests')
    for field in ('uncertainties', 'calculation_limitations'):
        if not isinstance(section.get(field, []), list) or not all(isinstance(note, str) for note in section.get(field, [])):
            raise AnswerCompletionError('Existing notes must remain a list of strings')
    _json_bytes(section)


def missing_answer_targets(section: dict) -> list[str]:
    """Return exact missing example/exercise IDs in original unit order.

    Inline prose is not guessed to be an answer: the application requires a
    distinct solution with an exact relates_to relation.
    """
    _validate_section(section)
    solved = {unit.get('relates_to') for unit in section['units'] if unit['kind'] == 'solution'}
    return [unit['id'] for unit in section['units'] if unit['kind'] in ('example', 'exercise') and unit['id'] not in solved]


def _targets(section: dict, target_ids: list[str] | None) -> list[str]:
    missing = missing_answer_targets(section)
    requested = missing if target_ids is None else target_ids
    if (not isinstance(requested, list) or not requested or not all(isinstance(target, str) for target in requested)
            or len(requested) != len(set(requested)) or not set(requested).issubset(missing)):
        raise AnswerCompletionError('Targets must be unique exact IDs of currently unanswered examples/exercises')
    targets = [target for target in missing if target in requested]
    if len(section['units']) + len(targets) > MAX_UNITS:
        raise AnswerCompletionError('Adding required answers would exceed the 100-unit section limit')
    existing_ids = {unit['id'] for unit in section['units']}
    if any(target + '.answer' in existing_ids for target in targets):
        raise AnswerCompletionError('A deterministic answer ID collides with an existing source unit')
    return targets


def propose_context(section: dict, target_ids: list[str] | None = None) -> dict:
    """Build fresh read-only context for role repair_missing_answers."""
    targets = _targets(section, target_ids)
    by_id = {unit['id']: unit for unit in section['units']}
    return {
        'operation': 'append_missing_answers', 'section_id': section['section_id'],
        'source_section_hash': digest(section), 'existing_section': copy.deepcopy(section),
        'targets': [{'target_id': target, 'answer_unit_id': target + '.answer',
                     'problem': copy.deepcopy(by_id[target])} for target in targets],
        'remaining_unit_slots': MAX_UNITS - len(section['units']),
        'remaining_calculation_slots': MAX_CALCULATIONS - len(section.get('calculations', [])),
        'calculation_protocol': calculation_protocol(),
        'requirements': [
            'Only return solutions for exactly the listed targets; no existing unit may be replaced, removed, or reordered.',
            'Each new calculation.unit_id must equal one listed answer_unit_id; calculation IDs must not collide with existing IDs.',
            'Existing uncertainty/limitation notes remain; new doubts may only be appended. This response is unchecked.',
        ],
    }


def _validate_calculations(section: dict, new: list[dict], answer_ids: set[str]) -> None:
    existing = section.get('calculations', [])
    if len(existing) + len(new) > MAX_CALCULATIONS:
        raise AnswerCompletionError('Appending calculations would exceed the 100-request section limit')
    known_ids = {c.get('id', f'C{index + 1:03d}') for index, c in enumerate(existing)
                 if isinstance(c.get('id', f'C{index + 1:03d}'), str)}
    protocol = calculation_protocol()
    for calculation in new:
        if not isinstance(calculation.get('id'), str) or not calculation['id'].strip() or len(calculation['id']) > 500:
            raise AnswerCompletionError('Each new calculation needs a bounded unique string ID')
        if calculation['id'] in known_ids:
            raise AnswerCompletionError('New calculation ID collides with an existing or new request')
        known_ids.add(calculation['id'])
        if not isinstance(calculation.get('unit_id'), str) or calculation['unit_id'] not in answer_ids:
            raise AnswerCompletionError('New calculations may bind only to the deterministic new answer unit IDs')
        kind = calculation.get('kind')
        if not isinstance(kind, str) or kind not in protocol['request_kinds']:
            raise AnswerCompletionError('Unsupported new calculation kind')
        required = set(protocol['request_common_fields']['required']) | set(protocol['request_kinds'][kind]['required'])
        if set(calculation) != required:
            raise AnswerCompletionError('Calculation fields must match the existing checker protocol exactly')
        if len(_json_bytes(calculation)) > MAX_CALCULATION_BYTES:
            raise AnswerCompletionError('A calculation exceeds the 64 KiB checker input limit')
    # AST validity, variable assumptions, truth and timing remain the original
    # bounded checker's responsibility. No math result is claimed here.


def apply_answer_completion(section: dict, reply: dict | AnswerCompletion,
                            target_ids: list[str] | None = None) -> tuple[dict, dict]:
    """Return a new section and audit data, or raise without mutating either input."""
    targets = _targets(section, target_ids)
    patch = AnswerCompletion.model_validate(reply).model_dump()
    if patch['section_id'] != section['section_id']:
        raise AnswerCompletionError('Completion section_id does not match the source section')
    answers = patch['answers']
    returned_ids = [answer['target_id'] for answer in answers]
    if len(returned_ids) != len(set(returned_ids)) or set(returned_ids) != set(targets):
        raise AnswerCompletionError('Completion must answer every authorized target exactly once, with no extra target')
    by_target = {answer['target_id']: answer for answer in answers}
    for answer in answers:
        if _FORBIDDEN_BODY.search(uncomment(_mask_verbatim(answer['tex']))):
            raise AnswerCompletionError('An answer body cannot add problems/theory or alter document structure')
    answer_ids = {target + '.answer' for target in targets}
    _validate_calculations(section, patch['calculations'], answer_ids)
    result = copy.deepcopy(section)
    added = [{'id': target + '.answer', 'kind': 'solution', 'tex': by_target[target]['tex'], 'relates_to': target}
             for target in targets]
    result['units'].extend(added)
    for field in ('calculations', 'calculation_limitations', 'uncertainties'):
        if patch[field]:
            result.setdefault(field, []).extend(copy.deepcopy(patch[field]))
    evidence = {
        'schema_version': 1, 'operation': 'append_missing_answers', 'status': 'APPLIED_UNCHECKED',
        'source_section_hash': digest(section), 'patch_hash': digest(patch), 'result_section_hash': digest(result),
        'target_ids': targets, 'new_unit_ids': [unit['id'] for unit in added],
        'new_unit_hashes': {unit['id']: digest(unit) for unit in added},
        'original_unit_count': len(section['units']), 'added_unit_count': len(added),
        'original_units_preserved': result['units'][:len(section['units'])] == section['units'],
        'original_calculations_preserved': result.get('calculations', [])[:len(section.get('calculations', []))] == section.get('calculations', []),
        'new_calculation_count': len(patch['calculations']),
        'math_check': 'NOT_RUN', 'normalization': 'NOT_RUN', 'teacher_review': 'NOT_RUN',
    }
    return result, evidence
