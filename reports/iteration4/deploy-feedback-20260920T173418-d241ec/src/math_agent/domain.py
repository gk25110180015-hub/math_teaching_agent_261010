from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)


class NewRun(StrictModel):
    workflow_id: Literal['lecture.generate', 'beamer.from_tex']
    topic: str = Field(default='', max_length=500)
    difficulty: str = Field(default='经济学本科一年级微积分', min_length=1, max_length=500)
    provider: Literal['mock', 'live'] = 'mock'
    model_id: Literal['gpt6', 'deepseek-flash', 'deepseek-v4-pro'] = 'gpt6'
    trusted_input: bool = False
    theme: Literal['default', 'fduclassroom'] = 'default'
    use_reference_bibliography: bool = False


class Selection(StrictModel):
    question_id: str
    question_revision: int
    selected_option_ids: list[str]
    custom_input: str = Field(default='', max_length=5000)


class Addition(StrictModel):
    new_content: str = Field(min_length=1, max_length=20000)
    insertion_location: str = Field(min_length=1, max_length=100)
    priority: Literal['必须', '有空间再加入'] = '必须'


class DecisionsRequest(StrictModel):
    expected_plan_revision: int
    decisions: list[Selection] = Field(default_factory=list)
    omitted_unit_ids: list[str] | None = None
    additions: list[Addition] | None = None


class ConfirmRequest(StrictModel):
    expected_plan_revision: int
    expected_plan_hash: str
    action_id: str = Field(min_length=1, max_length=128)


class RevisePlanRequest(StrictModel):
    expected_plan_revision: int
    title: str | None = Field(default=None, min_length=1, max_length=500)
    section_titles: dict[str, str] = Field(default_factory=dict)
    section_order: list[str] | None = None


class ExecuteRequest(StrictModel):
    expected_plan_revision: int
    expected_plan_hash: str
    idempotency_key: str = Field(min_length=1, max_length=128)


class ReviewRequest(StrictModel):
    artifact_id: str
    sha256: str
    verdict: Literal['pass', 'issue']
    note: str = Field(default='', max_length=5000)


class SectionSpec(StrictModel):
    id: str = Field(pattern=r'^S[0-9]+$')
    title: str = Field(min_length=1, max_length=200)
    objectives: list[str]
    required_kinds: list[Literal['definition', 'theorem', 'example', 'solution', 'proof', 'exercise']]
    prerequisites: list[Annotated[str,Field(pattern=r'^S[0-9]+$')]] = Field(default_factory=list,
        description='Only IDs of sections earlier in this plan. First section uses []. Put natural-language knowledge prerequisites in the top-level prerequisites field.')
    reference_labels: list[Annotated[str,Field(pattern=r'^[A-Za-z][A-Za-z0-9:._-]{0,119}$')]] = Field(default_factory=list, max_length=100,
        description='Declarations of NEW labels defined in this section, globally unique; not a list of labels referenced from other sections. Do not redeclare earlier labels or reserved sec:Sxx labels. Empty is allowed.')


class LectureProposal(StrictModel):
    title: str
    objectives: list[str]
    prerequisites: list[str]
    sections: list[SectionSpec] = Field(min_length=2, max_length=20)
    symbols: dict[str, str]
    exclusions: list[str]

    @model_validator(mode='after')
    def ordered_dependencies(self):
        seen=set();labels={'sec:'+s.id for s in self.sections}
        for section in self.sections:
            if section.id in seen:
                raise ValueError('Section IDs must be unique')
            if not set(section.prerequisites).issubset(seen):
                raise ValueError('Each section prerequisite must name an earlier section ID; first section prerequisites must be empty')
            seen.add(section.id)
            for label in section.reference_labels:
                if label in labels or label.startswith('sec:'):
                    raise ValueError('reference_labels declares new definitions only; labels must be globally unique and cannot use reserved sec: prefix')
                labels.add(label)
        return self


class WrittenUnit(StrictModel):
    id: str
    kind: Literal['definition', 'theorem', 'example', 'solution', 'proof', 'exercise', 'explanation']
    tex: str = Field(min_length=1, max_length=30000)
    relates_to: str | None = None


class WrittenSection(StrictModel):
    section_id: str
    units: list[WrittenUnit] = Field(min_length=1, max_length=100)
    calculations: list[dict] = Field(default_factory=list)
    calculation_limitations: list[str] = Field(default_factory=list,description='Coverage limitations of symbolic tools, not unresolved mathematical doubts. Empty calculations are not a symbolic PASS.')
    uncertainties: list[str] = Field(default_factory=list)


class MathIssue(StrictModel):
    unit_id: str
    severity: Literal['blocking', 'review', 'warning']
    message: str
    evidence: str


class MathReview(StrictModel):
    issues: list[MathIssue]
    checked_unit_ids: list[str]
    limitations: list[str]


QUALITY_DIMENSIONS = ('content', 'math', 'fidelity', 'compile', 'layout', 'policy', 'security')
