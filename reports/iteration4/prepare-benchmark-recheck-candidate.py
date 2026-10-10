"""Stage benchmark version selection without modifying deployed source."""
import difflib
import hashlib
import json
from pathlib import Path

root = Path(__file__).resolve().parents[2]
source = root / 'src/math_agent/benchmark.py'
before = source.read_text(encoding='utf-8')
helper = '''
def approved_checkpoint_metrics(settings, run, rows):
    """Read the same approved checkpoint identity/SHA as Pipeline, without jobs or writes."""
    from .pipeline import Pipeline
    plan=run.get('plan') or {}; approval=run.get('approval') or {}
    history=[{k:row[k] for k in ('checkpoint_rowid','step_key','input_hash','output_hash','created_at')}
             for row in rows]
    evidence={'status':'NO_CURRENT_APPROVED_PLAN','history':history,'selected':[],
        'order':'created_at DESC,rowid DESC','errors':[],
        'freshness':'Latest verified approved body; does not itself rerun checks or approve delivery.'}
    unhashed={key:value for key,value in plan.items() if key!='hash'}
    if (not plan.get('hash') or digest(unhashed)!=plan['hash'] or approval.get('hash')!=plan['hash']
            or approval.get('revision')!=plan.get('revision')
            or approval.get('input_hash')!=run.get('input_hash')):
        return {},evidence
    # Do not invoke Pipeline.__init__: it initializes budgets, directories and providers.
    reader=object.__new__(Pipeline)
    reader.settings=settings;reader.run=run
    reader.model_id=run['input'].get('model_id','gpt6')
    reader.root=settings.workspace/'runs'/run['id']
    reader.build_root=settings.workspace/'b'/run['id'][:16]
    grouped={};metadata={row['checkpoint_rowid']:entry for row,entry in zip(rows,history)}
    for row in rows:grouped.setdefault(row['step_key'],[]).append(row)
    sections={};prefix=[]
    evidence['status']='VERIFIED_APPROVED_CHECKPOINTS'
    for spec in plan.get('sections',[]):
        expected=reader._section_check_identity(plan,spec)
        expected_input=reader._section_input_hash(plan,spec,prefix)
        selected=None
        for row in grouped.get('section.'+spec['id'],[]):
            entry=metadata[row['checkpoint_rowid']]
            try:
                declared_output=json.loads(row['output_json'])
                if not isinstance(declared_output,dict) or digest(declared_output)!=row['output_hash']:
                    raise ValueError('Checkpoint output SHA mismatch')
                declared=declared_output.get('check_identity')
                entry['check_identity']=declared
                entry['output_hash_check']='PASS'
                matches_prefix=row['input_hash']==expected_input
                if declared is not None and declared!=expected:
                    entry['selection']='OTHER_PLAN_SPEC_OR_MODEL';continue
                if declared is None and not matches_prefix and not reader._legacy_checkpoint_proven(row,plan):
                    entry['selection']='UNPROVEN_LEGACY_IDENTITY';continue
                saved=reader._validate_section_checkpoint(row,spec,plan)
                entry.update(selection='SELECTED',source_key=saved['source_key'],
                    source_hash=saved['source_hash'],input_matches_current_prefix=matches_prefix)
                selected=(row,saved)
                break
            except (AgentError,OSError,ValueError,KeyError,TypeError) as exc:
                entry['selection']='INVALID_NO_OLDER_FALLBACK'
                evidence['status']='BLOCKED_INVALID_CHECKPOINT'
                evidence['errors'].append({'section_id':spec['id'],'checkpoint_rowid':row['checkpoint_rowid'],
                    'code':getattr(exc,'code','SECTION_CHECKPOINT_INVALID'),'message':scrub(str(exc))})
                return sections,evidence
        if selected is None:
            evidence['status']='PARTIAL_APPROVED_CHECKPOINTS';break
        row,saved=selected
        sections['section.'+spec['id']]=saved
        evidence['selected'].append(metadata[row['checkpoint_rowid']])
        prefix.append((spec,saved['generated']))
    return sections,evidence


'''
anchor='class BenchmarkRunner:\n'
assert before.count(anchor)==1
after=before.replace(anchor,helper+anchor)
old='''        with self.service.store.connect() as c:
            rows=[dict(r) for r in c.execute('SELECT * FROM artifacts WHERE run_id=? AND revision=? ORDER BY created_at', (run['id'],run['active_plan_revision'] or 0))]
            step_rows=c.execute("SELECT step_key,output_json FROM steps WHERE run_id=? AND step_key LIKE 'section.%' ORDER BY created_at", (run['id'],)).fetchall()
        verified=[]; documents={}
        for row in rows:
            path=within(self.settings.workspace,row['storage_key'])
            valid=path.is_file() and digest(path.read_bytes())==row['sha256']
            verified.append({'artifact_id':row['artifact_id'],'name':row['name'],'path':str(path),'sha256':row['sha256'],'hash_check':'PASS' if valid else 'FAIL'})
            if valid and row['name'] in ('quality_report.json','decision_coverage.json','pdf_inspection.json'):
                documents[row['name']]=json.loads(path.read_text(encoding='utf-8'))
        sections={key:json.loads(value) for key,value in step_rows}
'''
new='''        with self.service.store.connect() as c:
            rows=[dict(r) for r in c.execute('SELECT rowid AS artifact_rowid,* FROM artifacts WHERE run_id=? ORDER BY created_at DESC,rowid DESC', (run['id'],))]
            step_rows=[dict(r) for r in c.execute("SELECT rowid AS checkpoint_rowid,* FROM steps WHERE run_id=? AND step_key LIKE 'section.%' ORDER BY created_at DESC,rowid DESC", (run['id'],))]
        sections,checkpoint_selection=approved_checkpoint_metrics(self.settings,run,step_rows)
        approved=checkpoint_selection['status']!='NO_CURRENT_APPROVED_PLAN'
        verified=[]; documents={}; selected_names=set()
        for row in rows:
            path=within(self.settings.workspace,row['storage_key'])
            valid=path.is_file() and digest(path.read_bytes())==row['sha256']
            current=approved and row['revision']==run['active_plan_revision'] and row['status']!='superseded'
            selected=current and row['name'] not in selected_names
            if selected:selected_names.add(row['name'])
            verified.append({'artifact_id':row['artifact_id'],'name':row['name'],'path':str(path),
                'sha256':row['sha256'],'hash_check':'PASS' if valid else 'FAIL',
                'revision':row['revision'],'status':row['status'],'created_at':row['created_at'],
                'artifact_rowid':row['artifact_rowid'],'current_revision_active':current,'selected_for_current':selected})
            if selected and valid and row['name'] in ('quality_report.json','decision_coverage.json','pdf_inspection.json'):
                documents[row['name']]=json.loads(path.read_text(encoding='utf-8'))
'''
assert after.count(old)==1
after=after.replace(old,new)
old="            'plan_reference_context':plan.get('reference_context'), 'artifacts':verified}"
new="""            'plan_reference_context':plan.get('reference_context'), 'artifacts':verified,
            'checkpoint_selection':checkpoint_selection,
            'artifact_selection':{'order':'created_at DESC,rowid DESC','history_includes_all_revisions':True,
                'current_artifact_ids':[a['artifact_id'] for a in verified if a['selected_for_current']],
                'rule':'Current approved revision, non-superseded, latest per name; invalid newest never falls back.'}}"""
assert after.count(old)==1
after=after.replace(old,new)
folder=root/'reports/iteration4/待合并'
candidate=folder/'benchmark-recheck-current.py'
assert not candidate.exists()
candidate.write_text(after,encoding='utf-8')
sha=lambda raw:hashlib.sha256(raw).hexdigest()
manifest={'scope':'STAGED_NOT_DEPLOYED','files':[{'source':'src/math_agent/benchmark.py',
    'candidate':candidate.name,'baseline_sha256':sha(source.read_bytes()),'candidate_sha256':sha(candidate.read_bytes())}],
    'production_mutations':0,'tests':'tests/test_benchmark_recheck_versions.py',
    'limits':'Read-only analysis does not refresh checks, alter task budgets, claim API execution or teacher review.'}
(folder/'benchmark-recheck-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
(folder/'benchmark-recheck-current.patch').write_text(''.join(difflib.unified_diff(before.splitlines(True),after.splitlines(True),fromfile='a/src/math_agent/benchmark.py',tofile='b/src/math_agent/benchmark.py')),encoding='utf-8')
compile(after,str(candidate),'exec')
print(json.dumps(manifest,ensure_ascii=False))
