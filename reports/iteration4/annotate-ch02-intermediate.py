"""Attach independent agent text-review findings to the preserved audit snapshot."""
import hashlib
import json
from pathlib import Path
import re

root = Path(__file__).resolve().parents[2]
path = root / 'reports/iteration4/CH02-intermediate-semantic.json'
data = json.loads(path.read_bytes())
assert data['semantic_assessment'] == 'PENDING_AGENT_READ'
source = Path(data['sections'][-1]['source_path'])
source_raw = source.read_bytes()
assert hashlib.sha256(source_raw).hexdigest() == data['sections'][-1]['source_sha256']
text = source_raw.decode('utf-8')
lines = {match[1]: text.count('\n', 0, match.start()) + 1
         for match in re.finditer(r'^% UNIT (\S+)', text, re.M)}
all_units = {u['id']: u for s in data['sections'] for u in s['generated']['units']}
assert len(all_units) == len(lines) == 82
relations = []
for section in data['sections']:
    units = section['generated']['units']
    for question in units:
        if question['kind'] in ('example', 'exercise'):
            answers = [u['id'] for u in units if u['kind'] == 'solution' and u.get('relates_to') == question['id']]
            assert len(answers) == 1
            relations.append({'question_id': question['id'], 'kind': question['kind'], 'solution_ids': answers})
baseline = json.loads((root / 'reports/iteration2/lecture_semantic_baselines.json').read_bytes())
ch = next(c for c in baseline['chapters'] if c['id'] == 'CH02')
original = Path(ch['source']['path'])
assert hashlib.sha256(original.read_bytes()).hexdigest() == ch['source']['sha256']
data.update(semantic_assessment='INTERMEDIATE_AGENT_TEXT_REVIEW_COMPLETED_NOT_FINAL',
    final_pass_claim=False, reviewed_all_unit_ids=list(all_units),
    combined_source={'path': str(source), 'sha256': hashlib.sha256(source_raw).hexdigest(),
                     'unit_lines': lines, 'observed_compile_status': 'PASS',
                     'observed_cumulative_pages': 17, 'new_compile_or_pdf_visual_review': 'NOT_RUN'},
    original_source={**ch['source'], 'sha256_reverified_for_this_audit': True},
    answer_relation_audit={'examples': 8, 'exercises': 10, 'solutions': 18,
        'all_questions_have_exactly_one_related_solution': True, 'relations': relations,
        'student_navigation_issue': 'S05.U18 incorrectly previews only this section before all-chapter answers'},
    known_findings=[
        {'id': 'LOG_SERIES_START', 'status': 'CORRECTED_IN_CAPTURED_VERSION', 'unit_ids': ['S03.U13', 'S03.U14'],
         'evidence': 'Problem and solution both start at n=2, explicitly require ln(n)>0.'},
        {'id': 'S0_UNDEFINED', 'status': 'CORRECTED_IN_CAPTURED_VERSION', 'unit_ids': ['S04.U07'],
         'evidence': 'The even-partial-sum difference is now quantified m>=2. No S0 definition is needed; subsequent odd/even remainder cases cover n>=1.'},
        {'id': 'OVERESCAPED_TEX', 'status': 'NO_REPEAT_IN_CAPTURED_UNITS',
         'unit_ids': [f'S04.U{i:02}' for i in range(7,14)],
         'evidence': 'All seven previously overescaped units read correctly; no double-backslash-command matches across 82 units. This is a text check, not new visual acceptance.'},
        {'id': 'ABSOLUTE_CONVERGENCE_PROOF', 'status': 'CORRECT_TEXT_ROUTE', 'unit_ids': ['S05.U05'],
         'evidence': 'Comparison proves sum(a_n+|a_n|) converges first; only then subtracts sum|a_n|. Triangle inequality follows from finite sums and limits, not circular Cauchy reasoning.'},
        {'id': 'REMAINDER_THRESHOLD', 'status': 'CONSISTENT_STRONG_HYPOTHESES', 'unit_ids': ['S04.U02','S04.U04','S04.U07','S04.U12','S05.U20'],
         'evidence': 'S04 assumes nonincrease from n=1, so remainder <= b_(n+1) for every n>=1 is valid. n=999 is minimal for the given sufficient bound, not an unjustified claim about exact error. S05 geometric bound yields n=4 with explicit scope.'}],
    recheck_feedback=[
        {'id':'CH02-INTERMEDIATE-R01','classification':'ANSWER_NAVIGATION_CONTRADICTION',
         'severity':'review','unit_ids':['S05.U18'], 'source_lines':[787,792],
         'approved_basis':'lecture.answers_location=end; lecture.exercises=with_answers; G08 answer-to-question clarity',
         'quoted_text':'以下答案与本节三道练习依次对应。',
         'finding':'Rendered source immediately starts the entire chapter answer block with S01.U09, not the three S05 answers.',
         'request':'Change only S05.U18 to neutral guidance matching all-chapter numbered answer backlinks; preserve question/solution content and end placement.'},
        {'id':'CH02-INTERMEDIATE-R02','classification':'METHOD_APPLICATION_TRAINING_GAP',
         'severity':'teaching_review_not_math_error','unit_ids':['S03.U14','S03.U16'],
         'approved_basis':'S03 objectives: master comparison/limit comparison/integral-test conditions and select appropriate tests.',
         'finding':'Limit comparison has a correct theorem/proof at U07-U08, but all S03/S05 worked example and exercise solutions use direct comparison; no worked limit-comparison application appears.',
         'request':'Review whether to append a short alternative solution to S03.U14(1), retaining the existing correct proof: b_n=1/n^2>0, a_n>0, a_n/b_n->3 in (0,infinity), hence convergence. Do not label direct comparison incorrect.'}],
    source_baseline_scope_differences=[
        {'criterion':'CH02-T01','source_baseline_status':'PARTIAL_TEXT_SCOPE',
         'units':['S03.U09','S03.U10','S05.U20'],
         'observation':'General negative ratios and zero-leading-coefficient degeneracy are absent throughout S05; current a>0,r>=0 theorem is explicitly restricted and correct.',
         'approved_plan_assessment':'S03 is positive-series reference scope; no explicit promise of all-real-r geometric classification. Keep broader original baseline gap separate; do not require expansion through recheck.'},
        {'criterion':'CH02-P01','source_baseline_status':'PARTIAL_TEXT_SCOPE',
         'units':['S01.U08','S01.U09'],
         'observation':'The question only asks S3=3/4 and which sequence controls convergence. It does not ask or provide complete telescoping Sn=1-1/(n+1).',
         'approved_plan_assessment':'S01 basic finite-sum/calculation objective has correct examples. Additional telescoping training is optional benchmark enrichment, not a wrong answer.'}],
    optional_style_suggestions=[
        {'units':['S01.U03','S01.U04','S01.U05'],'suggestion':'Reduce repeated definition/theorem/by-definition proof if a future authored revision permits it; currently mathematically correct.'},
        {'units':['S04.U07','S04.U13'],'suggestion':'Two correct remainder proofs repeat the same argument; future teaching edit may shorten repetition without weakening the key proof.'},
        {'units':['S03.U14'],'suggestion':'Optionally explain the integral-test shift from lower endpoint 1 to 2 explicitly; the tail application is mathematically valid and finite changes were already proved.'}],
    limitations=['Text review of an active GLOBAL_REVIEW checkpoint, not a completed chapter grade.',
        'No new model API, symbolic test, Windows compilation, PDF rendering, or teacher review in this audit.',
        'A legitimate alternative proof is not an error solely because it differs from the original reference.',
        'No percentage of mathematical correctness or final 16/16 score is assigned.'])
evidence = {
 'CH02-D01':(['S01.U01','S01.U02','S01.U03'],'OBSERVED_TEXT','Series/terms/finite partial sums and finite-limit convergence are distinguished.'),
 'CH02-T01':(['S03.U09','S03.U10'],'PARTIAL_SOURCE_SCOPE','Positive/nonnegative ratio version only; correct within explicitly stated scope.'),
 'CH02-P01':(['S01.U07','S01.U08','S01.U09','S03.U10'],'PARTIAL_SOURCE_SCOPE','Finite geometric sums present; complete telescoping derivation absent but not demanded by the actual exercise.'),
 'CH02-T02':(['S02.U02','S02.U03','S02.U07'],'OBSERVED_TEXT','Necessary condition, proof and harmonic counterexample.'),
 'CH02-T03':(['S02.U08','S02.U09','S02.U10','S02.U11','S02.U12','S02.U13','S02.U14'],'OBSERVED_TEXT','Convergent linear combinations, finite changes, remainder and divergent-sum caveat are justified.'),
 'CH02-P02':(['S02.U07'],'OBSERVED_TEXT','Finite binary blocks give H_(2^m)>=1+m/2.'),
 'CH02-T04':(['S03.U01','S03.U03','S03.U04'],'OBSERVED_TEXT','Nonnegative terms and bounded partial sums are used correctly.'),
 'CH02-T05':(['S03.U05','S03.U06','S03.U14','S03.U16'],'OBSERVED_TEXT','Comparison directions and finite-prefix handling are correct.'),
 'CH02-T06':(['S03.U09','S03.U10'],'OBSERVED_TEXT','All real p cases covered; elementary finite-integral proof for p>1 is valid.'),
 'CH02-T07':(['S03.U07','S03.U08','S03.U11','S03.U12','S03.U14'],'OBSERVED_THEORY_APPLICATION_GAP','Correct conditions/proofs for both tests; limit-comparison worked application remains missing.'),
 'CH02-D02':(['S04.U06','S05.U02','S05.U03'],'OBSERVED_TEXT','Absolute/conditional meanings and both conditions are explicit.'),
 'CH02-T08':(['S05.U04','S05.U05'],'OBSERVED_TEXT','Comparison and valid subtraction establish absolute-implies-convergent.'),
 'CH02-T09':(['S04.U02','S04.U04','S04.U07'],'OBSERVED_TEXT','Uses stronger from-start monotonicity, valid <= remainder bound and sign statement.'),
 'CH02-P03':(['S04.U03','S04.U07'],'OBSERVED_TEXT','Even/odd subsequences converge to the same limit; no undefined S0.'),
 'CH02-E01':(['S04.U06','S04.U11','S04.U12','S05.U11','S05.U19','S05.U20','S05.U21'],'OBSERVED_TEXT','Classification and integer truncation estimates have condition checks and matched solutions.'),
 'CH02-X01':(['S01.U09','S02.U18.answer','S02.U19.answer','S02.U20.answer','S03.U16','S04.U11','S04.U12','S05.U18','S05.U19','S05.U20','S05.U21'],'ANSWERS_PRESENT_NAVIGATION_REVIEW','Every exercise has a correct associated solution; S05.U18 misleading all-chapter placement needs review.')}
data['original_16_item_intermediate_map'] = []
for criterion in ch['checklist']:
    if criterion['scope'] != 'REQUIRED':
        continue
    ids, status, note = evidence[criterion['id']]
    data['original_16_item_intermediate_map'].append({
        'id': criterion['id'], 'title': criterion['title'], 'original_scope': 'REQUIRED',
        'intermediate_status': status, 'note': note,
        'evidence': [{'unit_id': uid, 'source_line': lines[uid]} for uid in ids],
        'final_criterion_verdict': 'NOT_ASSESSED_FINAL_VERSION_PENDING'})
assert len(data['original_16_item_intermediate_map']) == 16
path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({'report': str(path), 'read_units': len(all_units), 'criteria':16,
    'feedback':len(data['recheck_feedback']), 'final_verdict':'NOT_ASSESSED'}, ensure_ascii=False))
