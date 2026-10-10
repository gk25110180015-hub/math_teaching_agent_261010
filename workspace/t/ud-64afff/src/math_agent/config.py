"""Validated local policy defaults, separate from secrets in environment variables."""
from pathlib import Path
from typing import Literal
import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator


class Budget(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    soft:int=Field(ge=20,le=1000)
    hard:int=Field(ge=20,le=1200)
    @model_validator(mode='after')
    def order(self):
        if self.soft>self.hard:raise ValueError('soft budget cannot exceed hard budget')
        return self


class TextBudgets(BaseModel):
    model_config=ConfigDict(extra='forbid')
    calibration_status:Literal['uncalibrated','measured']='uncalibrated'
    large:Budget=Budget(soft=100,hard=160)
    normalsize:Budget=Budget(soft=180,hard=260)
    small:Budget=Budget(soft=240,hard=330)
    footnotesize:Budget=Budget(soft=300,hard=400)


def text_budgets(path:Path|None=None):
    path=path or Path(__file__).resolve().parents[2]/'configs'/'defaults.yaml'
    raw=yaml.safe_load(path.read_text(encoding='utf-8'))
    beamer=raw['beamer']
    if beamer['allowed_text_sizes']!=['footnotesize','small','normalsize','large']:
        raise ValueError('Cannot weaken the four permitted font sizes')
    if beamer['summary_frames'] is not False:
        raise ValueError('Summary frames require explicit per-plan authorization')
    if beamer['solution_prefixes']!=[r'\textbf{解：}',r'\textbf{证明：}']:
        raise ValueError('TeX prefixes must have exactly one leading backslash')
    return TextBudgets.model_validate(beamer['text_budget'])
