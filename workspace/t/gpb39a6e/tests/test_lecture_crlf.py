"""Offline pipeline source byte tests; no API or compiler acceptance claimed."""
import pytest

from math_agent.pipeline import Pipeline
from test_draft_recovery import OfflineProvider, setup_pipeline


@pytest.mark.unit
@pytest.mark.parametrize('mode',['local','final'])
def test_lecture_source_preserves_rendered_crlf_exactly(tmp_path,monkeypatch,mode):
    import math_agent.pipeline as module
    provider=OfflineProvider()
    _,pipeline,plan=setup_pipeline(tmp_path,provider)
    rendered='before\r\n\\newcommand{\\macro}[1]{line\r\n#1}\r\nafter\n'
    monkeypatch.setattr(module,'render_lecture',lambda *args:rendered)
    observed=[]
    class StopAfterWrite(Exception):pass
    def compile(self,source,entry,build):
        observed.append((source/entry).read_bytes())
        if mode=='final':raise StopAfterWrite()
        build.mkdir()
        return {'status':'PASS','issues':[],'passes':2,'page_count':1,'pdf_path':None,'fixture':'OFFLINE_FAKE_COMPILER'}
    monkeypatch.setattr(Pipeline,'compile',compile)
    if mode=='final':
        monkeypatch.setattr(Pipeline,'lecture',lambda *args:([],[]))
        with pytest.raises(StopAfterWrite):pipeline.build()
    else:
        pipeline.lecture(plan)
    assert observed==[rendered.encode('utf-8')]
    assert b'\r\r\n' not in observed[0]
