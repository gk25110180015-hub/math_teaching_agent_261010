"""The confirmed storyboard, expanded into executable time windows for every pass."""


def confirmed_context(plan):
    """Unchosen alternatives must not compete with the approved storyboard."""
    context = {k: v for k, v in plan.items() if k not in ('candidates', 'questions', 'question_history')}
    context['decisions'] = [
        {**{k: v for k, v in decision.items() if k != 'candidate'},
         **({'candidate': {k: v for k, v in decision['candidate'].items() if k in ('id', 'title')}}
            if decision.get('candidate') else {})}
        for decision in plan.get('decisions', [])]
    return context


def scene_requirements(story):
    total = sum(scene['seconds'] for scene in story['scenes'])
    elapsed = 0
    result = []
    for scene in story['scenes']:
        result.append({**scene, 'start_time': elapsed / total,
            'end_time': (elapsed + scene['seconds']) / total,
            'sample_times': [(elapsed + scene['seconds'] * fraction) / total
                             for fraction in (.1, .3, .5, .7, .9)]})
        elapsed += scene['seconds']
    return result
