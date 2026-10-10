from typing import Literal
import math
from pydantic import Field, model_validator
from ..domain import StrictModel


class Scene(StrictModel):
    id: str = Field(pattern=r'^S[0-9]+$')
    title: str = Field(min_length=1, max_length=100)
    visual: str = Field(min_length=1, max_length=1500)
    narration: str = Field(min_length=1, max_length=120)
    math: str = Field(min_length=1, max_length=1000)
    seconds: int = Field(ge=3, le=30)


class Story(StrictModel):
    title: str = Field(min_length=1, max_length=150)
    summary: str = Field(min_length=1, max_length=2000)
    objectives: list[str] = Field(min_length=1, max_length=8)
    scenes: list[Scene] = Field(min_length=2, max_length=8)
    interaction_goals: list[str] = Field(min_length=1, max_length=8)
    math_notes: list[str] = Field(min_length=1, max_length=12)

    @model_validator(mode='after')
    def timeline(self):
        if len({s.id for s in self.scenes}) != len(self.scenes):
            raise ValueError('Scene IDs must be unique')
        if sum(s.seconds for s in self.scenes) > 120:
            raise ValueError('Total video duration must be at most 120 seconds')
        return self


class Candidate(Story):
    id: str = Field(pattern=r'^C[0-9]+$')


class Candidates(StrictModel):
    candidates: list[Candidate] = Field(min_length=3, max_length=4)

    @model_validator(mode='after')
    def unique_ids(self):
        if len({c.id for c in self.candidates}) != len(self.candidates):
            raise ValueError('Candidate IDs must be unique')
        return self


class Option(StrictModel):
    id: str = Field(pattern=r'^[A-Z][A-Z0-9_]{0,30}$')
    label: str = Field(min_length=1, max_length=150)
    effect: str = Field(min_length=1, max_length=1000)


class Question(StrictModel):
    id: str = Field(pattern=r'^Q[A-Za-z0-9_-]{1,40}$')
    prompt: str = Field(min_length=1, max_length=500)
    reason: str = Field(min_length=1, max_length=1000)
    options: list[Option] = Field(min_length=2, max_length=4)

    @model_validator(mode='after')
    def unique_ids(self):
        if len({o.id for o in self.options}) != len(self.options):
            raise ValueError('Option IDs must be unique')
        return self


class Refinement(StrictModel):
    story: Story
    questions: list[Question] = Field(max_length=5)
    changes: list[str] = Field(min_length=1, max_length=12)
    applied_decision_ids: list[str] = Field(min_length=1, max_length=100)

    @model_validator(mode='after')
    def unique_ids(self):
        if len({q.id for q in self.questions}) != len(self.questions):
            raise ValueError('Question IDs must be unique')
        return self


class RefineRequest(StrictModel):
    expected_plan_revision: int
    expected_plan_hash: str
    candidate_id: str | None = None
    answers: dict[str, str] = Field(default_factory=dict, max_length=5)
    suggestion: str = Field(default='', max_length=5000)


class Control(StrictModel):
    id: str = Field(pattern=r'^[a-z][a-z0-9_]{0,30}$')
    label: str = Field(min_length=1, max_length=100)
    min: float
    max: float
    step: float
    value: float

    @model_validator(mode='after')
    def bounded(self):
        if not all(math.isfinite(v) and abs(v) <= 1e6 for v in (self.min, self.max, self.step, self.value)):
            raise ValueError('Control numbers must be finite and bounded')
        if not self.min < self.max or not self.min <= self.value <= self.max or not 0 < self.step <= self.max - self.min:
            raise ValueError('Invalid slider range, default or step')
        return self


class Program(StrictModel):
    runtime_version: Literal[1, 2] = 1
    code: str = Field(min_length=100, max_length=60000)
    controls: list[Control] = Field(min_length=1, max_length=8)
    covered_decision_ids: list[str]
    explanation: str = Field(min_length=1, max_length=4000)
    limitations: list[str] = Field(max_length=12)

    @model_validator(mode='after')
    def code_contract(self):
        import re
        if not re.search(r'function\s+draw\s*\(\s*ctx\s*,\s*t\s*,\s*p\s*\)', self.code):
            raise ValueError('Define function draw(ctx, t, p) using the documented contract')
        if len({c.id for c in self.controls}) != len(self.controls):
            raise ValueError('Control IDs must be unique')
        if {c.id for c in self.controls} & {'timeline', 'time', 'progress', 'pause', 'play'}:
            raise ValueError('Timeline and playback controls are supplied by the host; only generate mathematical or view parameters')
        return self


class CodeReview(StrictModel):
    approved: bool
    issues: list[str] = Field(max_length=15)
    limitations: list[str] = Field(max_length=15)

    @model_validator(mode='after')
    def verdict(self):
        if self.approved and self.issues:
            raise ValueError('Approved code cannot contain unresolved issues')
        if not self.approved and not self.issues:
            raise ValueError('Rejected code needs actionable issues')
        return self


class CodeEdit(StrictModel):
    old: str = Field(min_length=1, max_length=60000)
    new: str = Field(max_length=60000)
    reason: str = Field(min_length=1, max_length=1000)


class ProgramRepair(StrictModel):
    edits: list[CodeEdit] = Field(min_length=1, max_length=24)
    explanation: str = Field(min_length=1, max_length=4000)
    controls: list[Control] | None = Field(default=None, min_length=1, max_length=8)
    covered_decision_ids: list[str] | None = None
    limitations: list[str] | None = Field(default=None, max_length=12)
