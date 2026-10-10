"""Apply bounded, unchecked replacements without asking a model to rewrite a section."""
from __future__ import annotations

import copy
import re
from collections.abc import Collection

from pydantic import Field, model_validator

from .answer_completion import MAX_CALCULATION_BYTES, MAX_CALCULATIONS, AnswerCompletionError, _json_bytes, _validate_section
from .calculation_protocol import calculation_protocol
from .domain import StrictModel
from .parsing import _mask_verbatim, uncomment
from .util import digest

_GLOBAL_TEX = re.compile(
    r'\\(?:documentclass|usepackage|RequirePackage|newcommand|renewcommand|providecommand|'
    r'newtheorem|def|gdef|edef|xdef|global|section|subsection|chapter|input|include)(?![A-Za-z@])'
    r'|\\(?:begin|end)\s*\{document\}'
)


class LocalPatchError(ValueError):
    """A local patch exceeds its explicit body/calculation/append-only scope."""


class LocalReplacement(StrictModel):
    unit_id: str = Field(min_length=1, max_length=500)
    tex: str = Field(min_length=1, max_length=30000)

    @model_validator(mode='after')
    def nonblank(self):
        if not self.unit_id.strip() or not self.tex.strip():
            raise ValueError('Replacement unit_id and tex must be nonblank')
        return self


class LocalPatch(StrictModel):
    section_id: str = Field(min_length=1, max_length=500)
    replacements: list[LocalReplacement] = Field(min_length=1, max_length=100)
    calculation_updates: list[dict] = Field(default_factory=list, max_length=MAX_CALCULATIONS)
    calculation_additions: list[dict] = Field(default_factory=list, max_length=MAX_CALCULATIONS)
    uncertainties_append: list[str] = Field(default_factory=list, max_length=100)
    calculation_limitations_append: list[str] = Field(default_factory=list, max_length=100)

    @model_validator(mode='after')
    def bounded_notes(self):
        for note in self.uncertainties_append + self.calculation_limitations_append:
            if not note.strip() or len(note) > 5000:
                raise ValueError('Appended notes must be nonblank and at most 5000 characters')
        return self


def _bytes(value):
    try:
        return _json_bytes(value)
    except AnswerCompletionError as error:
        raise LocalPatchError(str(error)) from error


def _allowed(section, allowed_ids):
    try:
        _validate_section(section)
    except AnswerCompletionError as error:
        raise LocalPatchError(str(error)) from error
    if (not isinstance(allowed_ids, Collection) or isinstance(allowed_ids, (str, bytes, dict))
            or not allowed_ids or not all(isinstance(unit_id, str) for unit_id in allowed_ids)
            or len(allowed_ids) != len(set(allowed_ids))):
        raise LocalPatchError('Allowed IDs must be a nonempty collection of unique unit IDs')
    ids = [unit['id'] for unit in section['units']]
    if not set(allowed_ids).issubset(ids):
        raise LocalPatchError('Allowed IDs must identify existing units in this section')
    return [unit_id for unit_id in ids if unit_id in allowed_ids]


def _request(calculation, allowed):
    for field in ('id', 'unit_id'):
        if not isinstance(calculation.get(field), str) or not calculation[field].strip() or len(calculation[field]) > 500:
            raise LocalPatchError('Each calculation needs bounded string id and unit_id')
    if calculation['unit_id'] not in allowed:
        raise LocalPatchError('Calculations may bind only to authorized target units')
    protocol = calculation_protocol()
    kind = calculation.get('kind')
    if not isinstance(kind, str) or kind not in protocol['request_kinds']:
        raise LocalPatchError('Unsupported calculation kind')
    required = set(protocol['request_common_fields']['required']) | set(protocol['request_kinds'][kind]['required'])
    if set(calculation) != required:
        raise LocalPatchError('Calculation fields must match the existing checker protocol exactly')
    if len(_bytes(calculation)) > MAX_CALCULATION_BYTES:
        raise LocalPatchError('Calculation exceeds the 64 KiB checker request budget')


def _apply_calculations(section, patch, allowed):
    original = section.get('calculations', [])
    effective_ids = []
    explicit = {}
    for index, calculation in enumerate(original):
        request_id = calculation.get('id', f'C{index + 1:03d}')
        if not isinstance(request_id, str) or not request_id.strip() or request_id in effective_ids:
            raise LocalPatchError('Existing calculation IDs are invalid or ambiguous')
        effective_ids.append(request_id)
        if 'id' in calculation:
            explicit[request_id] = index
    if len(original) + len(patch['calculation_additions']) > MAX_CALCULATIONS:
        raise LocalPatchError('Appending calculations would exceed the 100-request section limit')
    result = copy.deepcopy(original)
    updated = set()
    # Unknown pre-existing metadata must not disappear from an updated request.
    # The patch itself cannot introduce metadata or claim checker results.
    protocol = calculation_protocol()
    protocol_keys = set(protocol['request_common_fields']['required'])
    for kind in protocol['request_kinds'].values():
        protocol_keys.update(kind['required'])
    for request in patch['calculation_updates']:
        _request(request, allowed)
        request_id = request['id']
        if request_id not in explicit or request_id in updated:
            raise LocalPatchError('Update IDs must each identify one existing explicit calculation ID')
        index = explicit[request_id]
        if original[index].get('unit_id') != request['unit_id']:
            raise LocalPatchError('A calculation update cannot change its original unit binding')
        metadata = {key: copy.deepcopy(value) for key, value in original[index].items() if key not in protocol_keys}
        result[index] = copy.deepcopy(request) | metadata
        if len(_bytes(result[index])) > MAX_CALCULATION_BYTES:
            raise LocalPatchError('Updated calculation with retained metadata exceeds the request budget')
        updated.add(request_id)
    known_ids = set(effective_ids)
    for request in patch['calculation_additions']:
        _request(request, allowed)
        if request['id'] in known_ids:
            raise LocalPatchError('Added calculation ID collides with an existing or new request')
        known_ids.add(request['id'])
        result.append(copy.deepcopy(request))
    return result


def apply_local_patch(section: dict, allowed_ids: Collection[str],
                      reply: dict | LocalPatch) -> tuple[dict, dict]:
    """Return a new unchecked section and evidence; never mutate inputs or run a model.

    All original unit fields except authorized tex values remain byte-for-byte
    equal in the JSON data. Existing calculations cannot be removed or reordered.
    TeX normalization, the bounded checker, model review and compile remain caller
    responsibilities. Invalid full-section responses are rejected, not sanitized.
    """
    allowed = _allowed(section, allowed_ids)
    patch = LocalPatch.model_validate(reply).model_dump()
    if patch['section_id'] != section['section_id']:
        raise LocalPatchError('Patch section_id differs from the source section')
    returned = [item['unit_id'] for item in patch['replacements']]
    if len(returned) != len(set(returned)) or set(returned) != set(allowed):
        raise LocalPatchError('Replacements must cover each authorized target exactly once and no other unit')
    by_id = {item['unit_id']: item['tex'] for item in patch['replacements']}
    for body in by_id.values():
        if _GLOBAL_TEX.search(uncomment(_mask_verbatim(body))):
            raise LocalPatchError('Local replacement cannot alter global document structure or read files')
    calculations = _apply_calculations(section, patch, set(allowed))
    result = copy.deepcopy(section)
    for unit in result['units']:
        if unit['id'] in by_id:
            unit['tex'] = by_id[unit['id']]
    if 'calculations' in section or calculations:
        result['calculations'] = calculations
    for source, destination in (('uncertainties_append', 'uncertainties'),
                                ('calculation_limitations_append', 'calculation_limitations')):
        if patch[source]:
            result.setdefault(destination, []).extend(copy.deepcopy(patch[source]))
    _bytes(result)
    evidence = {
        'schema_version': 1, 'operation': 'strict_local_patch', 'status': 'APPLIED_UNCHECKED',
        'source_section_hash': digest(section), 'patch_hash': digest(patch), 'result_section_hash': digest(result),
        'allowed_unit_ids': allowed,
        'changed_unit_ids': [before['id'] for before, after in zip(section['units'], result['units']) if before != after],
        'unit_order_preserved': [unit['id'] for unit in section['units']] == [unit['id'] for unit in result['units']],
        'unit_identity_and_metadata_preserved': all(
            {key: value for key, value in before.items() if key != 'tex'} == {key: value for key, value in after.items() if key != 'tex'}
            for before, after in zip(section['units'], result['units'])),
        'non_target_units_preserved': all(before == after for before, after in zip(section['units'], result['units']) if before['id'] not in allowed),
        'original_calculation_count': len(section.get('calculations', [])),
        'calculation_updates': [item['id'] for item in patch['calculation_updates']],
        'calculation_additions': [item['id'] for item in patch['calculation_additions']],
        'non_target_calculations_preserved': all(before == after for before, after in zip(section.get('calculations', []), calculations)
                                                if before.get('unit_id') not in allowed),
        'old_uncertainties_preserved': result.get('uncertainties', [])[:len(section.get('uncertainties', []))] == section.get('uncertainties', []),
        'old_calculation_limitations_preserved': result.get('calculation_limitations', [])[:len(section.get('calculation_limitations', []))] == section.get('calculation_limitations', []),
        'normalization': 'NOT_RUN', 'math_check': 'NOT_RUN', 'teacher_review': 'NOT_RUN',
    }
    return result, evidence
