"""Measured, local layout recovery. Never rewrite the approved mathematical payload."""
from copy import deepcopy
from pathlib import Path
import re

from .beamer import render_beamer, check_fidelity
from .pdfcheck import inspect_pdf
from .util import write_json


STEPS = [
    {'font_size': 'normalsize', 'split_long': False},
    {'font_size': 'small', 'split_long': False},
    {'font_size': 'footnotesize', 'split_long': False},
    *[{'font_size': 'footnotesize', 'split_long': True, 'segment_capacity': capacity}
      for capacity in (400, 260, 160, 80)],
]


def overflow_frames(compiled):
    """Read the final TeX log; frame markers enclose all physical overlays."""
    logs = [Path(p) for p in compiled.get('log_paths', []) if p.endswith('.tex.log')]
    if not logs:
        return set()
    active = None
    affected = set()
    for line in logs[-1].read_text(encoding='utf-8', errors='replace').splitlines():
        match = re.search(r'MATH-AGENT-FRAME-(BEGIN|END) (F\d+)', line)
        if match:
            active = match[2] if match[1] == 'BEGIN' else None
        if active and re.search(r'Overfull \\[hv]box', line):
            affected.add(active)
    return affected


def build_measured_beamer(parsed, plan, output, reference_root, compile_fn, stage, *, title_generator=None):
    # Pipeline.compile carries the current workspace and the immutable storage key.
    # Rebase only this rendering view; persisted parsed.root and approvals stay intact.
    owner = getattr(compile_fn, '__self__', None)
    if owner is not None and hasattr(owner, 'settings') and hasattr(owner, 'run'):
        source_key = owner.run.get('input', {}).get('source_key')
        if source_key:
            from .portable_paths import snapshot_root
            parsed = {**parsed, 'root': str(snapshot_root(owner.settings.workspace, owner.run['id'], source_key))}
    modules = {}
    attempts = []
    inspection = None
    # Each independently affected module advances monotonically through seven states.
    # The bound also permits a geometry-only failure discovered after TeX warnings clear.
    for index in range(1, 25):
        inspection = None
        stage('BUILDING', f'layout.candidate.{index}')
        layout = {'measured': True, 'modules': {key: STEPS[value] for key, value in modules.items()}}
        source = output / f'candidate-{index}'
        rendered = render_beamer(parsed, {**plan, '_layout': layout}, source, reference_root, title_generator=title_generator)
        fidelity = check_fidelity(parsed, {**plan, '_render_scaffold_hash': rendered['render_scaffold_hash']},
                                  (source / 'slides.tex').read_text(encoding='utf-8'))
        write_json(output / f'fidelity-{index}.json', fidelity)
        issues = rendered.get('issues', []) + fidelity.get('issues', [])
        if fidelity['status'] == 'FAIL' or any(i.get('severity') == 'blocking' for i in issues):
            compiled = {'status': 'BLOCKED', 'issues': list(issues), 'pdf_path': None}
        else:
            stage('LOCAL_REVIEW', f'compile.layout.{index}')
            compiled = compile_fn(source, 'slides.tex', output / f'build-{index}')
        frames = {f['frame_id']: f for f in rendered['frame_plan']}
        affected = overflow_frames(compiled)
        footer_risks = set()
        fatal = [i for i in compiled.get('issues', [])
                 if i.get('severity') == 'blocking' and i.get('rule_id') != 'OVERFULL_BOX']
        if compiled['status'] == 'PASS' and compiled.get('pdf_path'):
            pdf = Path(compiled['pdf_path'])
            (pdf.parent / 'frame_ids.txt').write_text('\n'.join(frames), encoding='utf-8')
            stage('GLOBAL_REVIEW', f'layout.geometry.{index}')
            inspection = inspect_pdf(pdf, output / f'pages-{index}', beamer=True)
            write_json(output / f'pdf-inspection-{index}.json', inspection)
            mapping = {p['physical_page']: p['frame_id'] for p in inspection.get('overlay_map', {}).get('pages', [])}
            for issue in inspection.get('issues', []):
                footer_risk = issue.get('rule_id') == 'BODY_REGION_CONTACT' and any(
                    e.get('boundary') == 'footer' for e in issue.get('evidence', []))
                if issue.get('severity') == 'blocking' or footer_risk:
                    fid = mapping.get(issue.get('location', {}).get('physical_page'))
                    if fid:
                        affected.add(fid)
                        if footer_risk:
                            footer_risks.add(fid)
                    elif not footer_risk:
                        fatal.append(issue)
        affected_modules = {frames[f]['module_id'] for f in affected
                            if f in frames and frames[f].get('module_id')}
        record = {'candidate': index, 'layout': deepcopy(layout), 'compile': compiled,
                  'affected_frames': sorted(affected), 'affected_modules': sorted(affected_modules),
                  'footer_risk_frames': sorted(footer_risks),
                  'geometry_status': inspection['status'] if inspection else 'NOT_RUN',
                  'frame_count': len(frames)}
        attempts.append(record)
        write_json(output / 'layout_candidates.json', attempts)
        done = compiled['status'] == 'PASS' and inspection and inspection['status'] != 'FAIL' and not affected
        if done or fatal or not affected_modules or any(not frames.get(f, {}).get('module_id') for f in affected):
            break
        changed = False
        for key in affected_modules:
            step = modules.get(key, 0)
            if step + 1 < len(STEPS):
                modules[key] = step + 1
                changed = True
        if not changed:
            break
    return source, rendered, fidelity, compiled, inspection
