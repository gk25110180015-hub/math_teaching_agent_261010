from math_agent.pipeline import Pipeline
from math_agent.settings import Settings
from math_agent.util import AgentError
import pytest

class Provider:
    def __init__(self,valid_on_second=True):self.calls=[];self.valid_on_second=valid_on_second
    def generate(self,role,context,schema):
        self.calls.append((role,context.copy()))
        assert role=='reviewer_math'
        return {'checked_unit_ids':['S01-U01'],'limitations':['synthetic scope regression'],
                'issues':[] if len(self.calls)>1 and self.valid_on_second else [{'unit_id':'S02','severity':'blocking','message':'第二节还没有提供','evidence':'只有S01'}]}

def pipeline(tmp_path,provider):
    p=object.__new__(Pipeline);p.settings=Settings(workspace=tmp_path);p.provider=provider
    return p

def test_local_review_rejects_outside_section_id_then_rechecks_scope(tmp_path):
    provider=Provider();p=pipeline(tmp_path,provider)
    result=p.review_units([{'id':'S01-U01','kind':'definition','tex':'已提供的定义。'}],
        {'scope':{'kind':'section_local','current_section':'S01','pending_sections':['S02']}},tmp_path,'local')
    assert result['issues']==[] and len(provider.calls)==2
    assert provider.calls[1][1]['review_validation_feedback']['invalid_issue_unit_ids']==['S02']
    assert len(list(tmp_path.glob('local-review-*.json')))==2

def test_persistent_out_of_scope_review_is_blocked_not_silently_removed(tmp_path):
    provider=Provider(False);p=pipeline(tmp_path,provider)
    with pytest.raises(AgentError) as exc:p.review_units([{'id':'S01-U01','tex':'定义。'}],{'scope':{'kind':'section_local'}},tmp_path,'local')
    assert exc.value.code=='REVIEW_SCOPE_BLOCKED'
    assert len(provider.calls)==3
