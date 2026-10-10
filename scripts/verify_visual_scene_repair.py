"""Opt-in live replay of rejected storyboard code, isolated from the original run."""
import argparse
import json
from pathlib import Path

from math_agent.provider import CompatibleChatProvider
from math_agent.settings import Settings
from math_agent.util import AgentError, write_json
from math_agent.visualization.contracts import scene_requirements, confirmed_context
from math_agent.visualization.document import interactive_html
from math_agent.visualization.models import Program, CodeReview
from math_agent.visualization.generation import generate_program
from math_agent.visualization.render import probe_program, review_evidence, render_video


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live', action='store_true', required=True)
    parser.add_argument('--diagnostics', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--resume', action='store_true')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=args.resume)
    read = lambda name: json.loads((args.diagnostics/name).read_text(encoding='utf-8'))
    plan = read('plan.json')
    attempts = sorted(int(p.stem.split('-')[1]) for p in args.diagnostics.glob('program-*.json'))
    latest = attempts[-1]
    history = [{'issues':read(f'issues-{n}.json')} for n in attempts]
    context = {'confirmed_plan':confirmed_context(plan), 'runtime_contract_version':2,
        'scene_requirements':scene_requirements(plan['story']),
        'previous_program':read(f'program-{latest}.json'), 'repair_issues':history[-1]['issues'],
        'repair_history':history, 'runtime_evidence':review_evidence(read(f'probes-{latest}.json'))}
    settings = Settings(llm_read_timeout_seconds=600, llm_total_timeout_seconds=900)
    metadata = args.output/'provider-metadata.json'
    records = json.loads(metadata.read_text(encoding='utf-8')) if args.resume and metadata.exists() else []
    def record(value):
        records.append(value)
        write_json(args.output/'provider-metadata.json', records)
    provider = CompatibleChatProvider(settings, record=record, failure_dir=args.output/'provider-failures',
        preferred_model=plan.get('model_id','gpt6'), allow_fallback=False)
    def generate(role, payload, schema):
        try:
            return provider.generate(role, payload, schema)
        except AgentError as error:
            write_json(args.output/'verification.json',{'status':'INCOMPLETE','role':role,
                'code':error.code,'message':error.message,'human_review':'NOT_RUN'})
            raise
    for attempt in range(3):
        saved = args.output/f'program-{attempt}.json'
        issues_path = args.output/f'issues-{attempt}.json'
        saved_issues = json.loads(issues_path.read_text(encoding='utf-8')) if args.resume and issues_path.exists() else []
        if args.resume and saved.exists() and saved_issues:
            history.append({'issues':saved_issues})
            context.update(previous_program=json.loads(saved.read_text(encoding='utf-8')),
                repair_issues=history[-1]['issues'],repair_history=history,
                runtime_evidence=review_evidence(json.loads((args.output/f'probes-{attempt}.json').read_text(encoding='utf-8'))))
            continue
        print(f'writer attempt {attempt + 1}', flush=True)
        program = json.loads(saved.read_text(encoding='utf-8')) if args.resume and saved.exists() else generate_program(
            generate, context, settings.max_schema_repair_attempts,
            record=lambda revision, patch: write_json(args.output/f'patch-{attempt}-{revision}.json',patch))
        write_json(args.output/f'program-{attempt}.json', program)
        project = {'story':plan['story'], 'program':program, 'provider':'live','plan_hash':plan['hash']}
        write_json(args.output/'project.json',project)
        write_json(args.output/'plan.json',plan)
        (args.output/'scene.js').write_text(program['code'],encoding='utf-8')
        (args.output/'interactive.html').write_text(interactive_html(plan['story'],program,'live'),encoding='utf-8')
        probes = probe_program(args.output)
        write_json(args.output/f'probes-{attempt}.json',probes)
        evidence = review_evidence(probes)
        print(f'browser {probes["status"]}; reviewing', flush=True)
        review = generate('visualization_reviewer', {'confirmed_plan':confirmed_context(plan),'program':program,
            'scene_requirements':context['scene_requirements'],'runtime_evidence':evidence,'repair_history':history}, CodeReview)
        write_json(args.output/f'review-{attempt}.json',review)
        issues = list(probes.get('issues',[])) + review['issues']
        if probes['status']!='PASS' and not probes.get('issues'):
            issues.append(probes.get('error','Browser probe failed'))
        if set(program['covered_decision_ids']) != set(plan['decision_ids']):
            issues.append('Decision coverage differs from confirmed plan')
        if program['runtime_version'] != 2:
            issues.append('Expected runtime_version=2')
        write_json(args.output/f'issues-{attempt}.json',issues)
        if not issues:
            print('recording verified presentation',flush=True)
            try:
                rendered = render_video(args.output,sum(s['seconds'] for s in plan['story']['scenes']))
            except AgentError as error:
                issues.append(error.message)
                write_json(issues_path,issues)
            else:
                write_json(args.output/'verification.json',{'status':'PASS','source_diagnostics':str(args.diagnostics),
                    'attempts':attempt+1,'review':review,'render':rendered,'human_review':'NOT_RUN'})
                print('PASS: '+str(args.output),flush=True)
                return
        history.append({'issues':issues})
        context.update(previous_program=program,repair_issues=issues,repair_history=history,runtime_evidence=evidence)
        print(f'{len(issues)} repair issues',flush=True)
    write_json(args.output/'verification.json',{'status':'FAIL','issues':history[-1]['issues']})
    raise SystemExit(1)


if __name__ == '__main__':
    main()
