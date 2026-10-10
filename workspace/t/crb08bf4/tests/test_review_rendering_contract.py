from math_agent.pipeline import Pipeline
from math_agent.settings import Settings


def test_review_knows_only_separate_linked_exercise_answers_move_to_end(tmp_path):
    calls = []
    class Provider:
        def generate(self, role, context, schema):
            calls.append(context)
            return {'issues': [], 'checked_unit_ids': [u['id'] for u in context['units']], 'limitations': []}
    pipeline = object.__new__(Pipeline)
    pipeline.settings = Settings(workspace=tmp_path)
    pipeline.provider = Provider()
    units = [
        {'id': 'Q1', 'kind': 'exercise', 'tex': '题目和不应内嵌的答案'},
        {'id': 'A1', 'kind': 'solution', 'tex': '独立解答', 'relates_to': 'Q1'},
        {'id': 'E1', 'kind': 'example', 'tex': '例题'},
        {'id': 'EA', 'kind': 'solution', 'tex': '例题解答', 'relates_to': 'E1'},
        {'id': 'BAD', 'kind': 'solution', 'tex': '悬空解答', 'relates_to': 'UNKNOWN'}]
    for location in ('end', 'section'):
        pipeline.review_units(units, {'plan': {'lecture': {'answers_location': location}}}, tmp_path, location)
    assert calls[0]['rendering_contract']['relocated_solution_ids'] == ['A1']
    assert calls[1]['rendering_contract']['relocated_solution_ids'] == []
    assert 'NOT relocated' in calls[0]['rendering_contract']['instruction']
    assert calls[0]['units'] == units
