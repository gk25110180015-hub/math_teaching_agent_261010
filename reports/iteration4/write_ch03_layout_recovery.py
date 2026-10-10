"""Read-only audit of the real S05.U22 layout recovery; no API/compile/render."""
import difflib
import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

PROJECT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).parent
WORKSPACE=PROJECT/'workspace/iteration2-live'
RUN='a45be503af594ce8aae0bb1e4c30184b'
BUILD=WORKSPACE/'b'/RUN[:16]
REPAIRED=BUILD/'sS05_bd250159fdc5'


def sha(value):
    if not isinstance(value,bytes):
        value=json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode('utf-8')
    return hashlib.sha256(value).hexdigest()


def evidence(path):
    raw=path.read_bytes()
    return {'path':str(path),'relative_path':path.relative_to(PROJECT).as_posix(),
            'raw_sha256':sha(raw),'bytes':len(raw)}


def load(path):
    return json.loads(path.read_bytes())


def main():
    for name in ('CH03-live-layout-recovery.json','CH03-live-layout-recovery.md'):
        assert not (OUT/name).exists(), 'Refusing to overwrite existing audit'
    conn=sqlite3.connect((WORKSPACE/'agent.db').as_uri()+'?mode=ro',uri=True)
    conn.row_factory=sqlite3.Row
    conn.execute('BEGIN')
    run=dict(conn.execute('SELECT id,status,stage,request_count,updated_at,active_plan_revision FROM runs WHERE id=?',(RUN,)).fetchone())
    step=conn.execute("SELECT rowid,* FROM steps WHERE run_id=? AND step_key='section.S05' ORDER BY created_at DESC,rowid DESC LIMIT 1",(RUN,)).fetchone()
    checkpoint=dict(step) if step else None
    if checkpoint:
        assert sha(checkpoint['output_json'].encode('utf-8'))==checkpoint['output_hash']
        checkpoint['output']=json.loads(checkpoint.pop('output_json'))
    rows=[dict(row) for row in conn.execute("SELECT sequence,type,payload_json,timestamp FROM events WHERE run_id=? AND type IN ('provider.result','provider.routing') ORDER BY sequence",(RUN,))]
    conn.rollback();conn.close()
    for row in rows:row['payload']=json.loads(row.pop('payload_json'))
    state_path=WORKSPACE/'runs'/RUN/'local-repair/S05.json'
    state=load(state_path)
    current=WORKSPACE/state['candidate_key']
    assert sha(current.read_bytes())==state['candidate_hash']
    before=load(REPAIRED/'candidate-normalized.json')
    after=load(REPAIRED/'repair-1.json')['section']
    changed=[u['id'] for u,v in zip(before['units'],after['units']) if u!=v]
    assert len(before['units'])==len(after['units']) and changed==['S05.U22']
    assert {k:v for k,v in before.items() if k!='units'}=={k:v for k,v in after.items() if k!='units'}
    old_unit=next(u for u in before['units'] if u['id']=='S05.U22')
    new_unit=next(u for u in after['units'] if u['id']=='S05.U22')
    assert {k:v for k,v in old_unit.items() if k!='tex'}=={k:v for k,v in new_unit.items() if k!='tex'}
    patch=load(REPAIRED/'repair-1-patch.json')
    patch_record=load(REPAIRED/'repair-1-evidence.json')
    assert sha(patch)==patch_record['patch_hash']
    assert sha(before)==patch_record['source_section_hash'] and sha(after)==patch_record['result_section_hash']
    attempts=[]
    for label,folder,review_name in [
        ('historical_fail',BUILD/'sS05_79367048d571','local-0-review-0.json'),
        ('resumed_fail',REPAIRED,'local-0-review-0.json'),
        ('after_accepted_layout_patch',REPAIRED/'compile-attempt-1','../local-1-review-0.json')]:
        comp=load(folder/'compile.json');source=folder/'source/lecture.tex';pdf=Path(comp['pdf_path'])
        assert sha(pdf.read_bytes())==comp['pdf_sha256']
        review_path=(folder/review_name).resolve();review=load(review_path)
        matching=[row for row in rows if row['payload'].get('output_hash')==sha(review)]
        call_ids={row['payload']['call_id'] for row in matching}
        calls=[row for row in rows if row['payload'].get('call_id') in call_ids]
        attempts.append({'label':label,'directory':str(folder),'source':evidence(source),'compile_report':evidence(folder/'compile.json'),
            'compile':comp,'pdf':evidence(pdf),'logs':[evidence(Path(path)) for path in comp['log_paths']],
            'math_review_file':evidence(review_path),'math_review':review,'math_review_provider_events':calls,
            'source_and_build_tex_equal':source.read_bytes()==(folder/'build/lecture.tex').read_bytes()})
    for name in ('compile-attempt-evidence.json','compile-attempt-1/compile-attempt-evidence.json'):
        for dep in load(REPAIRED/name)['dependencies']:
            assert sha((WORKSPACE/dep['key']).read_bytes())==dep['hash']
    patch_events=[row for row in rows if row['payload'].get('output_hash')==sha(patch)]
    patch_calls={row['payload']['call_id'] for row in patch_events}
    patch_events=[row for row in rows if row['payload'].get('call_id') in patch_calls]
    difference=''.join(difflib.unified_diff(old_unit['tex'].splitlines(keepends=True),new_unit['tex'].splitlines(keepends=True),fromfile='S05.U22 before',tofile='S05.U22 accepted'))
    report={'schema_version':1,'captured_at':datetime.now(timezone.utc).isoformat(),
        'run_snapshot':run,'final_delivery':'NOT_FINAL_ACTIVE_REVIEW_OR_REPAIR',
        'method':{'api_calls':0,'new_compile_runs':0,'pdf_render_runs':0,'agent_visual_review':'NOT_RUN',
            'teacher_math_review':'NOT_RUN','teacher_visual_review':'NOT_RUN','product_mutations':0,'database_mutations':0},
        'compile_evidence_kind':'Existing real Windows trusted_local XeLaTeX, not mock; all logs and PDF hashes independently reread.',
        'attempts':attempts,'layout_mapping':load(REPAIRED/'compile-layout-mapping.json'),
        'patch':{'file':evidence(REPAIRED/'repair-1-patch.json'),'value':patch,'evidence_file':evidence(REPAIRED/'repair-1-evidence.json'),
            'evidence':patch_record,'provider_events':patch_events,'changed_unit_ids_independently_verified':changed,
            'other_units_and_metadata_unchanged':True,'tex_diff':difference},
        'current_local_state_file':evidence(state_path),'current_local_state':state,
        'current_candidate_file':evidence(current),'latest_S05_checkpoint_at_capture':checkpoint,
        'interpretation':['Old math reviews reported no issue but did not inspect PDF layout; old compile FAIL remains valid for its own source.',
            'Accepted patch only splits the final paragraph and displays 9,-1,3,-1,-4 separately; all sign changes, monotonicity, domain and multiple-equilibrium conclusions are retained.',
            'Post-patch review explicitly declined to claim compile/visual success; the separate real two-pass compiler then reported PASS with no issues.',
            'APPLIED_UNCHECKED in immutable patch evidence records the acceptance-time stage; later LocalRecovery CHECKED and compile-attempt-1 PASS supply the later evidence.',
            'This section-level cumulative 17-page PDF is not the frozen final chapter and has not received agent/teacher all-page visual review.']}
    (OUT/'CH03-live-layout-recovery.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    lines=['# CH03 S05.U22 真实布局恢复记录','',f"捕获时间：{report['captured_at']}。任务 `{RUN}`；当前状态 **{run['status']} / {run['stage']}**，累计请求 {run['request_count']}。任务仍在全章审阅/修复链中，**不是最终交付**。",'',
        '本报告只读既有证据，没有发 API、重新编译或渲染 PDF。下列编译均是已经执行的真实 Windows XeLaTeX，不是 mock。Agent 全页目视、教师数学和教师视觉均为 **NOT_RUN**。','',
        '## 三次真实编译证据','',
        '| 阶段 | 编译目录 | 结果 | 两遍耗时 / 页数 | 源码 SHA-256 | PDF SHA-256 |','|---|---|---|---|---|---|']
    for item in attempts:
        folder=Path(item['directory']).relative_to(PROJECT).as_posix()
        lines.append(f"| {item['label']} | [{Path(folder).name}](../../{folder}/compile.json) | {item['compile']['status']} | {item['compile']['elapsed_seconds']} s / {item['compile']['page_count']} | `{item['source']['raw_sha256']}` | `{item['pdf']['raw_sha256']}` |")
    lines+=['','前两次的 `OVERFULL_BOX` 都是 `Overfull \\hbox (0.5104pt too wide) in paragraph at lines 932--933`。源码第 912 行标识 `% UNIT S05.U22`，932 行结束表格公式，933 行是一段连续文字与内联数列。当前映射将完整报错区间唯一定位到 S05.U22，未把上游章节改为修复目标。','',
        '## 接受的修复及保留的数学','',
        '[原始局部补丁](../../workspace/iteration2-live/b/a45be503af594ce8/sS05_bd250159fdc5/repair-1-patch.json) 的 raw SHA 为 `'+sha((REPAIRED/'repair-1-patch.json').read_bytes())+'`。补丁仅替换 S05.U22，将“所得函数连续且非负……”后分段，五个超额需求值改为独立陈列公式；后面仍指出三个开区间各有一个零点。修后源码对应行 933–939。未删除数学内容、缩小字号、提高容差或隐藏警告。','',
        '独立对比候选 JSON：单元总数、顺序、ID、kind、关联题号及非目标单元逐项不变；仅 S05.U22.tex 改变，全部计算请求/限制/疑点元数据不变。当前 LocalRecovery 记录 proposal_calls=1、applied_rounds=1、S05.U22 实际修改=1、rejected_proposals=0，没有清零旧失败。','',
        '题解仍以 E(1)=9>0、E(5)=-4<0 证明存在；额外需求严格递减、供给严格递增使 E 严格递减，才推出唯一。原条件下所给分段线性非负函数仍产生 9,-1,3,-1,-4，前三段连续且端点异号，确实允许多个均衡点。','',
        '## 数学审阅与编译分开判定','']
    for item in attempts:
        review=item['math_review'];ref=item['math_review_file']['relative_path']
        matched=[event['payload'] for event in item['math_review_provider_events'] if 'output_hash' in event['payload']]
        models=', '.join(sorted({event.get('reported_model',event.get('model','UNKNOWN')) for event in matched})) or '未以输出哈希匹配到模型记录'
        lines.append(f"- {item['label']}：[模型原审阅](../../{ref})，raw SHA `{item['math_review_file']['raw_sha256']}`，{len(review['checked_unit_ids'])} 个实际单元，issues={len(review['issues'])}；输出规范化哈希匹配模型：{models}。")
    lines+=['','修后模型说明旧日志不能证明新源码仍溢出，并明确没有编译或检查最终 PDF；它没有冒称排版成功。随后 `compile-attempt-1` 实际运行两遍 XeLaTeX，返回 PASS、issues=[]、17 页。这一编译结果仅解决该版源码的机器可检测问题，不能替代逐页视觉或教师验收。','',
        '补丁证据中的 `APPLIED_UNCHECKED`、math_check=NOT_RUN 是接受补丁时保存的历史阶段，不应覆盖成后验 PASS。后续 CHECKED 状态、局部数学审阅和独立新目录编译结果另行保存。','',
        '[完整 JSON、每个编译报告/四份日志 SHA、模型请求匹配、原补丁与检查点](CH03-live-layout-recovery.json)','',
        '最终冻结后仍需逐条核查 22 项 REQUIRED 与 G01–G08，映射 unit/TeX 行/PDF 物理页，逐页目视并验证源 ZIP 重编译。当前 17 页累计节编译稿不能提前当作最终 PDF。','']
    (OUT/'CH03-live-layout-recovery.md').write_text('\n'.join(lines),encoding='utf-8')
    print(json.dumps({'status':run['status'],'stage':run['stage'],'attempts':[item['compile']['status'] for item in attempts],
        'report':'reports/iteration4/CH03-live-layout-recovery.md','current_candidate_matches_accepted':load(current)==after},ensure_ascii=False))


if __name__=='__main__':main()
