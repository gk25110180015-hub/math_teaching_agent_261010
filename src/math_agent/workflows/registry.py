from dataclasses import dataclass
from typing import Protocol, Any
from ..domain import NewRun
from ..util import AgentError


class WorkflowPlugin(Protocol):
    workflow_id: str
    version: int
    input_schema: Any
    def validate_input(self,input,context): ...
    def propose_plan(self,input,context): ...
    def validate_plan(self,plan,decisions): ...
    def build_next_step(self,snapshot,checkpoint): ...
    def review_local(self,step_artifacts,context): ...
    def review_global(self,all_artifacts,context): ...
    def export(self,accepted_revision): ...


@dataclass(frozen=True)
class BuiltinWorkflow:
    workflow_id: str
    version: int = 1
    input_schema: Any = NewRun

    def validate_input(self,input,context=None):
        data=self.input_schema.model_validate(input)
        if data.workflow_id!=self.workflow_id:raise AgentError('WORKFLOW_MISMATCH','输入业务类型不符')
        return data

    def propose_plan(self,input,context):
        return context.plan()

    def validate_plan(self,plan,decisions):
        return {'status':'PASS' if not plan.get('unresolved_blocking_questions') and plan['workflow_id']==self.workflow_id else 'FAIL'}

    def build_next_step(self,snapshot,checkpoint):
        return checkpoint.build()

    def review_local(self,step_artifacts,context):
        return step_artifacts.get('report',{'status':'NOT_RUN'})

    def review_global(self,all_artifacts,context):
        return all_artifacts.get('quality_report',{'status':'NOT_RUN'})

    def export(self,accepted_revision):
        return accepted_revision.get('artifacts',[])


REGISTRY={p.workflow_id:p for p in (BuiltinWorkflow('lecture.generate'),BuiltinWorkflow('beamer.from_tex'),BuiltinWorkflow('visualization.create'))}


def workflow(workflow_id):
    try:return REGISTRY[workflow_id]
    except KeyError:raise AgentError('UNKNOWN_WORKFLOW','未注册的工作流') from None
