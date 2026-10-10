"""A closed plan registry permits pending forward references only in local prefixes."""
import re
from .parsing import uncomment
from .util import AgentError

LABEL = re.compile(r'^[A-Za-z][A-Za-z0-9:._-]{0,119}$')


def reference_registry(plan):
    registry = {}
    for section in plan['sections']:
        for label in ['sec:'+section['id'], *section.get('reference_labels', [])]:
            if not LABEL.fullmatch(label) or label in registry:
                raise AgentError('REFERENCE_REGISTRY', '计划交叉引用标签非法或重复：'+label)
            registry[label] = section['id']
    return registry


def inspect_section_references(spec, generated, completed, plan):
    registry = reference_registry(plan)
    previous = {'sec:'+s['id'] for s, _ in completed}
    previous.update(label for _,g in completed for u in g['units']
                    for label in re.findall(r'\\label\s*\{([^{}]+)\}', uncomment(u['tex'])))
    labels, refs, issues = [], [], []
    for unit in generated['units']:
        text = uncomment(unit['tex'])
        labels.extend(re.findall(r'\\label\s*\{([^{}]+)\}', text))
        refs.extend(re.findall(r'\\(?:ref|eqref|pageref|autoref|nameref)\*?\s*\{([^{}]+)\}', text))
    for label in labels:
        if not LABEL.fullmatch(label) or labels.count(label)>1 or label in previous or label.startswith('sec:'):
            issues.append({'rule_id':'DUPLICATE_OR_INVALID_LABEL','severity':'blocking','message':'重复、非法或保留标签：'+label})
        elif label in registry and registry[label] != spec['id']:
            issues.append({'rule_id':'LABEL_WRONG_SECTION','severity':'blocking','message':'标签出现在未规划的章节：'+label})
    for label in spec.get('reference_labels', []):
        if label not in labels:
            issues.append({'rule_id':'PLANNED_LABEL_MISSING','severity':'blocking','message':'本节缺少计划标签：'+label})
    defined = previous | set(labels) | {'sec:'+spec['id']}
    future_sections = {s['id'] for s in plan['sections']} - {s['id'] for s,_ in completed} - {spec['id']}
    pending = {label for label in refs if label not in defined and registry.get(label) in future_sections}
    for label in set(refs)-defined-pending:
        issues.append({'rule_id':'UNREGISTERED_REFERENCE','severity':'blocking','message':'未知引用，不能假定未来会定义：'+label})
    return {'issues':issues,'pending_labels':sorted(pending),'defined_labels':sorted(defined)}


def local_reference_gate(result, pending_labels):
    if result['status']=='PASS':
        return {'status':'PASS','pending_labels':[]}
    pending_labels=set(pending_labels)
    blockers=[x for x in result.get('issues',[]) if x.get('severity')=='blocking']
    found=set()
    if result.get('page_count',0)<1 or result.get('passes',0)<2 or not blockers:
        return {'status':'FAIL','pending_labels':[]}
    for issue in blockers:
        if issue.get('rule_id')!='UNRESOLVED_REFERENCE':
            return {'status':'FAIL','pending_labels':[]}
        message=issue.get('message','')
        match=re.search(r"Reference `([^']+)'[^\n]* undefined",message)
        if match and match.group(1) in pending_labels:
            found.add(match.group(1))
        elif 'There were undefined references' not in message:
            return {'status':'FAIL','pending_labels':[]}
    if not found or found!=pending_labels:
        return {'status':'FAIL','pending_labels':[]}
    return {'status':'PENDING_FULL_REFERENCE_CHECK','pending_labels':sorted(found),
            'evidence':'Only labels registered in later approved sections; original compiler FAIL retained. Full build must resolve all labels.'}
