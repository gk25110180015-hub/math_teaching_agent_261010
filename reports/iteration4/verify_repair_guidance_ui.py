"""Real Edge DOM with localhost static assets and synthetic API responses only."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading
import traceback
from urllib.parse import urlparse
import uuid

from playwright.sync_api import sync_playwright, expect
from run_final_deployed_e2e import source_hashes

ROOT=Path(__file__).resolve().parents[2]
REPORTS=Path(__file__).resolve().parent
CANDIDATE=REPORTS/'app-repair-guidance.candidate.js'
stamp=datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:6]
output=REPORTS/'repair-guidance-ui-validation'/stamp
output.mkdir(parents=True,exist_ok=False)
fixture=REPORTS/'final-deployed-e2e/20260922-043328-aa8704/20260922-123516/receipt-before.json'
run=deepcopy(json.loads(fixture.read_bytes()))
run.update(id='synthetic-guidance-run',status='BLOCKED',stage='review.section.S03',
    error={'code':'SYNTHETIC_REPAIR_SCOPE','message':'本地界面测试，不是数学裁定'},
    artifacts=[],reviews=[],jobs=[],partial_checkpoints=[],quality_report=None,feedback_review=None,
    repair_guidance_context=None)
run['budget']['can_increase']=False
context={'section_id':'S03','candidate_hash':'a'*64,'units':[
    {'id':'S03.U04','kind':'proof','tex_excerpt':'当前证明需要补充一个独立依据。'},
    {'id':'S03.U05','kind':'example','tex_excerpt':'这是应当保留的另一例题。'}]}
run_url='/api/runs/'+run['id']
calls=[];errors=[];checks=[];external=[]
failure_modes=['409','abort','503','202']
before=source_hashes()
result={'status':'RUNNING','real_edge':'EXECUTED','api':'MOCK_ROUTED_IN_BROWSER','model':'NOT_RUN',
    'real_api':'NOT_RUN','windows_compile':'NOT_RUN','teacher_review':'NOT_RUN','checks':checks,
    'candidate_sha256':hashlib.sha256(CANDIDATE.read_bytes()).hexdigest(),
    'fixture_sha256':hashlib.sha256(fixture.read_bytes()).hexdigest()}

class Assets(BaseHTTPRequestHandler):
    def do_GET(self):
        items={'/':(ROOT/'src/math_agent/web/static/index.html','text/html; charset=utf-8'),
            '/static/app.js':(CANDIDATE,'application/javascript; charset=utf-8'),
            '/static/style.css':(ROOT/'src/math_agent/web/static/style.css','text/css; charset=utf-8')}
        entry=items.get(urlparse(self.path).path)
        if entry is None:
            self.send_response(404);self.end_headers();return
        data=entry[0].read_bytes();self.send_response(200)
        self.send_header('Content-Type',entry[1]);self.send_header('Content-Length',str(len(data)))
        self.end_headers();self.wfile.write(data)
    def log_message(self,*args):pass

server=ThreadingHTTPServer(('127.0.0.1',0),Assets)
threading.Thread(target=server.serve_forever,daemon=True).start()
base=f'http://127.0.0.1:{server.server_port}'

def respond(route,value,status=200):
    route.fulfill(status=status,content_type='application/json',body=json.dumps(value,ensure_ascii=False))

def route_api(route):
    request=route.request;url=urlparse(request.url);path=url.path
    if url.hostname!='127.0.0.1':external.append(request.url);route.abort();return
    if not path.startswith('/api/'):
        route.continue_();return
    if request.method=='POST':
        data=request.post_data_json;calls.append({'path':path,'payload':data})
        if path!=run_url+'/repair-guidance':respond(route,{'error':{'message':'Unexpected POST'}},500);return
        mode=failure_modes[len(calls)-1]
        if mode=='abort':route.abort('failed');return
        if mode!='202':respond(route,{'error':{'message':'合成接口失败：草稿必须保留。'}},int(mode));return
        run.update(status='QUEUED',repair_guidance_context=None,jobs=[{'id':'original-job','kind':'build','status':'queued'}])
        respond(route,{'id':'original-job','status':'queued'},202);return
    if path=='/api/session':respond(route,{'csrf_token':'synthetic-local-token'})
    elif path=='/api/capabilities':respond(route,{'worker':{'alive':True},'templates':{},'settings':{'models':[]}})
    elif path=='/api/health':respond(route,{'worker':{'alive':True}})
    elif path=='/api/runs':respond(route,[run])
    elif path==run_url:respond(route,run)
    elif path==run_url+'/events':respond(route,[])
    else:respond(route,{'error':{'message':'Unknown synthetic GET'}},404)

browser=None
try:
    executable=next((p for p in [Path('C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'),
        Path('C:/Program Files/Microsoft/Edge/Application/msedge.exe')] if p.is_file()),None)
    if executable is None:raise RuntimeError('Microsoft Edge not available; no skip or PASS claim')
    with sync_playwright() as manager:
        browser=manager.chromium.launch(headless=True,executable_path=str(executable))
        browser_context=browser.new_context(viewport={'width':1440,'height':1100},locale='zh-CN')
        browser_context.tracing.start(screenshots=True,snapshots=True,sources=True)
        page=browser_context.new_page();page.on('pageerror',lambda error:errors.append(str(error)))
        page.route('**/*',route_api)
        page.add_init_script("localStorage.setItem('math-agent-run','synthetic-guidance-run')")
        try:
            page.goto(base)
            expect(page.locator('[data-testid=run-status]')).to_have_attribute('data-status','BLOCKED')
            expect(page.locator('#repair-guidance-panel')).to_have_count(0)
            checks.append('Absent context hides guidance form')
            run['repair_guidance_context']=deepcopy(context)
            page.evaluate('() => refreshRun()')
            expect(page.locator('#repair-guidance-panel')).to_be_visible()
            expect(page.locator('#repair-guidance-unit')).to_have_value('')
            expect(page.locator('#repair-guidance-instructions')).to_have_value('')
            expect(page.locator('#repair-guidance-panel')).to_contain_text('不是教师批准')
            assert not calls
            checks.append('Context-only fingerprint change renders an empty, explicit-selection form with no automatic POST')
            page.locator('#repair-guidance-unit').select_option('S03.U04')
            expect(page.locator('#repair-guidance-excerpt')).to_have_text(context['units'][0]['tex_excerpt'])
            draft='请仅补充本单元缺失依据，保持已批准教学范围与其他单元内容不变。'
            field=page.locator('#repair-guidance-instructions');field.fill(draft)
            with page.expect_response(lambda response: response.url.endswith(run_url)):
                page.wait_for_timeout(1700)
            expect(field).to_have_value(draft)
            page.evaluate('() => refreshRun(true)')
            expect(page.locator('#repair-guidance-instructions')).to_have_value(draft)
            expect(page.locator('#repair-guidance-unit')).to_have_value('S03.U04')
            assert not calls
            checks.append('Actual timer and forced render preserve selected unit and draft without submitting')
            run['repair_guidance_context']['candidate_hash']='b'*64
            page.evaluate('() => refreshRun()')
            expect(page.locator('#repair-guidance-instructions')).to_have_value('')
            expect(page.locator('#repair-guidance-unit')).to_have_value('')
            run['repair_guidance_context']=deepcopy(context)
            page.evaluate('() => refreshRun()')
            expect(page.locator('#repair-guidance-instructions')).to_have_value(draft)
            checks.append('Changed candidate does not inherit old selection or instructions; old same-body draft stays recoverable')
            page.locator('#submit-repair-guidance').click()
            expect(page.locator('#notice')).to_contain_text('合成接口失败')
            expect(page.locator('#submit-repair-guidance')).to_be_enabled()
            expect(page.locator('#repair-guidance-instructions')).to_have_value(draft)
            assert len(calls)==1
            first=calls[0]['payload']
            assert first=={'expected_plan_revision':run['plan']['revision'],'expected_plan_hash':run['plan']['hash'],
                'action_id':first['action_id'],'section_id':'S03','expected_candidate_hash':'a'*64,
                'unit_ids':['S03.U04'],'instructions':draft,'source':'user'}
            assert uuid.UUID(first['action_id']).version==4
            checks.append('409 retains draft and exact approved plan/body/single-unit request binding')
            page.locator('#submit-repair-guidance').click()
            expect(page.locator('#notice')).to_contain_text('Failed to fetch')
            expect(page.locator('#submit-repair-guidance')).to_be_enabled()
            expect(page.locator('#repair-guidance-instructions')).to_have_value(draft)
            assert len(calls)==2 and calls[1]['payload']==first
            checks.append('Same-content retry after HTTP failure reuses action ID; network failure retains draft without automatic retry')
            edited=draft+' 请优先说明命题的使用条件与非循环的论证过程。'
            page.locator('#repair-guidance-instructions').fill(edited)
            page.locator('#submit-repair-guidance').click()
            expect(page.locator('#notice')).to_contain_text('合成接口失败')
            expect(page.locator('#submit-repair-guidance')).to_be_enabled()
            assert len(calls)==3 and calls[2]['payload']['action_id']!=first['action_id']
            expect(page.locator('#repair-guidance-instructions')).to_have_value(edited)
            page.screenshot(path=str(output/'guidance-error-retained.png'),full_page=True)
            checks.append('Editing instructions creates a new action ID and 503 preserves the revised draft')
            run['status']='FAILED';page.evaluate('() => refreshRun()')
            expect(page.locator('#repair-guidance-panel')).to_be_visible()
            expect(page.locator('#repair-guidance-instructions')).to_have_value(edited)
            page.locator('#submit-repair-guidance').click()
            expect(page.locator('[data-testid=run-status]')).to_have_attribute('data-status','QUEUED')
            expect(page.locator('#repair-guidance-panel')).to_have_count(0)
            assert len(calls)==4 and calls[3]['payload']==calls[2]['payload']
            assert page.evaluate('() => Object.keys(state.repairGuidance).length')==1  # untouched b-body empty draft
            run.update(status='BLOCKED',jobs=[],repair_guidance_context=deepcopy(context))
            page.evaluate('() => refreshRun()')
            expect(page.locator('#repair-guidance-instructions')).to_have_value('')
            expect(page.locator('#repair-guidance-unit')).to_have_value('')
            checks.append('FAILED also supports guidance; successful 202 reuses the action ID and clears only its own draft')
            run['workflow_id']='beamer.from_tex';page.evaluate('() => refreshRun(true)')
            expect(page.locator('#repair-guidance-panel')).to_have_count(0)
            assert all(call['path']==run_url+'/repair-guidance' for call in calls)
            assert not external and not errors
            checks.append('Other workflow hides guidance, no teacher-review endpoint or external service was called')
            result['status']='PASS'
        finally:
            page.screenshot(path=str(output/'final.png'),full_page=True)
            browser_context.tracing.stop(path=str(output/'trace.zip'))
            browser.close()
except Exception as error:
    result.update(status='FAIL',error={'type':type(error).__name__,'message':str(error),'traceback':traceback.format_exc()})
finally:
    server.shutdown();server.server_close()
    result.update(source_and_tests_unchanged=before==source_hashes(),posts=calls,console_errors=errors,
                  external_requests=external,finished_at=datetime.now(timezone.utc).isoformat())
    if not result['source_and_tests_unchanged']:result['status']='FAIL'
    (output/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'status':result['status'],'checks':len(checks),'output':str(output),
        'source_and_tests_unchanged':result['source_and_tests_unchanged']},ensure_ascii=False))
raise SystemExit(0 if result['status']=='PASS' else 1)
