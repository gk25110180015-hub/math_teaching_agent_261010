"""Prepare report-only candidates; never write production source."""
import argparse
import ast
import difflib
import hashlib
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPORTS = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise ValueError('Expected exactly one insertion point: ' + old[:100])
    return text.replace(old, new, 1)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--pipeline-base', type=Path, default=ROOT / 'src/math_agent/pipeline.py')
    args = parser.parse_args()
    base = args.pipeline_base.read_text(encoding='utf-8')
    text = replace_once(base, "        from .feedback_review import feedback_contract\n", "        from .feedback_review import feedback_contract\n        from .uncertainty_review import uncertainty_contract\n")
    text = replace_once(text, "            'feedback_review_contract':feedback_contract(),\n", "            'feedback_review_contract':feedback_contract(),\n            'uncertainty_review_contract':uncertainty_contract(),\n")
    text = replace_once(text, "                math = check_math(generated)\n                issues.extend(math.get('issues', []))\n", """                math = check_math(generated)
                uncertainty_guard=None
                declared_issue_objects=[]
                prior_uncertainty_issues=[]
                uncertainty_migration=[]
                if generated.get('uncertainties'):
                    from .uncertainty_review import (UncertaintyReview, build_uncertainty_context,
                        located_math_issues, prior_same_body_issues)
                    located=located_math_issues(generated,math)
                    declared_issue_objects=[i for i in located if i.get('rule_id')=='DECLARED_MATH_UNCERTAINTY']
                    issues.extend(located)
                    prior_uncertainty_issues,uncertainty_migration=prior_same_body_issues(recovery,generated)
                    uncertainty_guard=UncertaintyReview(self,build_uncertainty_context(plan,generated,
                        [g for _,g in completed],math,issues,self.run['input']['provider']=='mock'))
                else:
                    issues.extend(math.get('issues', []))
""")
    old = """                review = self.review_units(generated['units'], {'plan':plan,'prior_sections':[g for _,g in completed],'tool_checks':math,
                    'reference_recovery':label_recovery,'local_recovery':recovery_context,
                    'scope':{'kind':'section_local','current_section':spec,'pending_sections':[s['id'] for s in plan['sections'] if s['id'] not in {x['id'] for x,_ in completed} and s['id']!=sid]}},draft,f'local-{attempt}')
"""
    new = """                ordinary_context={'plan':plan,'prior_sections':[g for _,g in completed],'tool_checks':math,
                    'reference_recovery':label_recovery,'local_recovery':recovery_context,
                    'scope':{'kind':'section_local','current_section':spec,'pending_sections':[s['id'] for s in plan['sections'] if s['id'] not in {x['id'] for x,_ in completed} and s['id']!=sid]}}
                if uncertainty_guard:
                    review=uncertainty_guard.ordinary_review(
                        lambda frozen: self.review_units(generated['units'],frozen,draft,f'local-{attempt}'),ordinary_context)
                else:
                    review=self.review_units(generated['units'],ordinary_context,draft,f'local-{attempt}')
"""
    text = replace_once(text, old, new)
    old = """                if generated.get('uncertainties'):
                    issues.extend({'severity':'review','message':i} for i in generated['uncertainties'])
                report = {'section_id':sid,'math':math,'llm_review':review, 'issues':issues,
"""
    new = """                uncertainty_report=None
                if uncertainty_guard:
                    uncertainty_report,declared=uncertainty_guard.evaluate()
                    issues=[i for i in issues if not any(i is original for original in declared_issue_objects)]+declared
                    seen={digest(i) for i in issues}
                    issues.extend(i for i in prior_uncertainty_issues if digest(i) not in seen)
                    review_identity={**review_identity,'uncertainty_identity':uncertainty_report['identity_hash'],
                        'uncertainty_assessment_hash':digest(uncertainty_report['assessment'])}
                report = {'section_id':sid,'math':math,'llm_review':review, 'issues':issues,
"""
    text = replace_once(text, old, new)
    text = replace_once(text, "                blocking=recovery.record_review(issues,review_identity,report)\n", """                if uncertainty_report:
                    report['uncertainty_review']=uncertainty_report
                    report['uncertainty_legacy_mapping']=uncertainty_migration
                blocking=recovery.record_review(issues,review_identity,report)
""")
    text = replace_once(text, "                if not blocking:\n                    from .compile_recovery", """                if uncertainty_report and any(i['disposition']=='open_dependency' for i in uncertainty_report['assessment']['items']):
                    raise AgentError('UNCERTAINTY_DEPENDENCY_BLOCKED','声明数学疑点仍缺可核实依据；原疑点、当前正文和显式裁定已保留，普通重试不重新抽取通过')
                if not blocking:
                    from .compile_recovery""")
    ast.parse(text)
    path = REPORTS / 'uncertainty-pipeline.candidate.py'
    path.write_text(text, encoding='utf-8', newline='\n')
    (REPORTS / 'uncertainty-pipeline.patch').write_text(''.join(difflib.unified_diff(base.splitlines(True), text.splitlines(True),
        fromfile='a/src/math_agent/pipeline.py', tofile='b/src/math_agent/pipeline.py')), encoding='utf-8', newline='\n')
    provider = ROOT / 'src/math_agent/provider.py'
    content = replace_once(provider.read_text(encoding='utf-8'), "schema_attempts = 1 if role == 'reviewer_feedback' else", "schema_attempts = 1 if role in ('reviewer_feedback', 'reviewer_uncertainty') else")
    content = replace_once(content, "        elif role == 'reviewer_feedback':\n", "        elif role == 'reviewer_uncertainty':\n            from .uncertainty_review import mock_uncertainty_assessment\n            value = mock_uncertainty_assessment(context)\n        elif role == 'reviewer_feedback':\n")
    ast.parse(content)
    (REPORTS / 'uncertainty-provider.candidate.py').write_text(content, encoding='utf-8', newline='\n')
    fixture_folder=REPORTS/'fixtures/uncertainty_ch03'
    fixture_folder.mkdir(parents=True,exist_ok=True)
    source_fixtures=ROOT/'reports/iteration4/CH03-feedback-receipts-blocked146'
    fixture_names=['2-candidate-becc07d4d97b.json','1-review-1f3161930303.json']
    for name in fixture_names:
        shutil.copyfile(source_fixtures/name,fixture_folder/name)
        assert sha(source_fixtures/name)==sha(fixture_folder/name)
    files=[]
    for source,candidate in [('src/math_agent/uncertainty_review.py','uncertainty_review.candidate.py'),
            ('src/math_agent/prompts/reviewer_uncertainty.md','reviewer_uncertainty.candidate.md'),
            ('src/math_agent/provider.py','uncertainty-provider.candidate.py'),
            ('src/math_agent/pipeline.py','uncertainty-pipeline.candidate.py'),
            ('tests/test_uncertainty_review.py','test_uncertainty_review_candidate.py'),
            *[('tests/fixtures/uncertainty_ch03/'+name,'fixtures/uncertainty_ch03/'+name) for name in fixture_names]]:
        live=ROOT/source
        files.append({'source':source,'candidate':candidate,'baseline_sha256':sha(live) if live.exists() else None,
                      'candidate_sha256':sha(REPORTS/candidate)})
    manifest={'status':'CANDIDATE_NOT_VALIDATED','files':files,'pipeline_patch_base':str(args.pipeline_base),
              'pipeline_patch_base_sha256':sha(args.pipeline_base),'tests':'NOT_RUN','api_calls':0}
    (REPORTS/'uncertainty-review-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(manifest,ensure_ascii=False,indent=2))


if __name__ == '__main__':
    main()
