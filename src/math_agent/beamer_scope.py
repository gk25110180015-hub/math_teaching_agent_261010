"""Project the retained source scope without losing the reversible source inventory."""
from copy import deepcopy


def retained_sections(sections, units, omitted, additions=()):
    by_id = {u['id']: u for u in units}
    added = {a.get('insertion_location') for a in additions}
    result = []
    for section in sections:
        ids = [uid for uid in section.get('source_unit_ids', []) if uid not in omitted
               and (uid not in by_id or (by_id[uid]['kind'] != 'presentation_scaffold'
                    and by_id[uid].get('source_visibility') != 'inactive'))]
        if ids or section['id'] in added:
            result.append({**deepcopy(section), 'source_unit_ids': ids})
    return result


def refresh_beamer_scope(plan, parsed):
    # source_sections is an inventory, not a second executable content plan.
    inventory = deepcopy(plan.get('source_sections', parsed['sections']))
    titles = {s['id']: s['title'] for s in plan.get('sections', [])}
    for section in inventory:
        section['title'] = titles.get(section['id'], section['title'])
    omitted = {uid for item in plan.get('omissions', [])
               for uid in item.get('unit_ids', [item.get('unit_id')])}
    plan['source_sections'] = inventory
    plan['sections'] = retained_sections(inventory, parsed['units'], omitted, plan.get('additions', []))
    retained = {s['id'] for s in plan['sections']}
    plan['empty_sections'] = [{'id': s['id'], 'title': s['title'],
                              'reason': '本节没有保留正文或获准新增内容，不生成目录项或章节页'}
                             for s in inventory if s['id'] not in retained]
