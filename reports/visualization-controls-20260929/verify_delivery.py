"""Verify the recovered task using its actual local web endpoints and controls."""
import io
import json
from pathlib import Path
import time
import zipfile
import httpx
from playwright.sync_api import sync_playwright
from math_agent.service import Service
from math_agent.settings import Settings
from math_agent.util import digest
from math_agent.visualization.render import browser_path

RID='43a4bc7fcb564b7dbd156b482bab5aa7'
PLAN='735b15da3d279fb8e4a3bc17d071f04a7033a478785b8334eb0afe7abeae2249'
ROOT=Path(__file__).resolve().parent
s=Service(Settings())
deadline=time.monotonic()+600
while True:
    run=s.get(RID)
    if run['status'] not in ('QUEUED','BUILDING','LOCAL_REVIEW','REPAIRING'):
        break
    if time.monotonic()>deadline:
        raise TimeoutError('Delivery remains pending')
    time.sleep(2)
assert run['status']=='COMPLETED_WITH_WARNINGS', run.get('error')
assert run['plan']['hash']==run['approval']['hash']==PLAN
report={'status':'PASS','run_id':RID,'run_status':run['status'],'plan_hash':PLAN,'plan_revision':run['plan']['revision'],
        'request_count':run['request_count'],'artifacts':[]}
with httpx.Client(base_url='http://127.0.0.1:8765',trust_env=False,timeout=30) as client:
    assert client.get('/api/health').status_code==200
    assert client.get('/api/session').status_code==200
    for a in run['artifacts']:
        if a['status']=='superseded' or a['metadata'].get('kind')!='visualization' or a['metadata'].get('plan_hash')!=PLAN:continue
        response=client.get('/api/artifacts/'+a['artifact_id']);response.raise_for_status()
        assert digest(response.content)==a['sha256'],a['name']
        report['artifacts'].append({'name':a['name'],'sha256':a['sha256'],'bytes':len(response.content)})
        if a['name']=='source_bundle.zip':
            with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
                assert archive.testzip() is None
                assert archive.read('video.webm').startswith(b'\x1aE\xdf\xa3')
                quality=json.loads(archive.read('quality_report.json'))
                assert quality['code_review']['approved'] and quality['render']['status']=='PASS'
                assert quality['render']['video']['duration_seconds']==78
                assert quality['human_math_review']=='NOT_RUN'
                report['quality']=quality
                assert "explore.textContent='自由探索'" in archive.read('interactive.html').decode('utf-8')
    assert len(report['artifacts'])==11
with sync_playwright() as manager:
    browser=manager.chromium.launch(headless=True,executable_path=browser_path())
    try:
        page=browser.new_page(viewport={'width':1440,'height':1100})
        page.goto('http://127.0.0.1:8765/visualizations?run='+RID)
        page.wait_for_selector('video')
        page.wait_for_function('()=>document.querySelector("video").readyState>=1')
        video=page.locator('video')
        video.evaluate('v=>{v.muted=true;return v.play();}')
        page.wait_for_function('()=>document.querySelector("video").currentTime>.2')
        report['web_video']=video.evaluate('v=>({width:v.videoWidth,height:v.videoHeight,played_seconds:v.currentTime})')
        video.evaluate('v=>v.pause()')
        assert report['web_video']['width']==960 and report['web_video']['height']==540
        page.locator('iframe').scroll_into_view_if_needed()
        frame=next(f for f in page.frames if '/preview' in f.url)
        frame.evaluate('()=>window.visualization.ready')
        assert frame.evaluate('self.origin')=='null'
        def slide(id,value):
            frame.locator('#'+id).evaluate('(e,v)=>{e.value=v;e.dispatchEvent(new Event("input"));}',value)
        slide('time',29/78)
        frame.wait_for_function('()=>document.querySelector("#param-h").disabled')
        frame.locator('#explore').click()
        frame.wait_for_function('()=>!document.querySelector("#param-h").disabled')
        slide('param-h',.3);slide('param-side',-1)
        left=frame.evaluate('()=>window.visualization.render(+document.querySelector("#time").value)')
        assert abs(left['metrics']['h']+.3)<1e-5 and abs(left['metrics']['slope']-1.7)<1e-5
        assert '左' in left['title']
        frame.locator('#reset').click();frame.wait_for_function('()=>document.querySelector("#time").value==="0"')
        slide('time',71/78)
        frame.wait_for_function('()=>document.querySelector("#param-example").value==="1"')
        frame.locator('#explore').click();frame.wait_for_function('()=>!document.querySelector("#param-example").disabled')
        slide('param-example',0);slide('param-x0',1)
        back=frame.evaluate('()=>window.visualization.render(+document.querySelector("#time").value)')
        assert back['metrics']['example']=='x²' and back['metrics']['derivative']==2
        assert not frame.locator('#status').inner_text()
        frame.locator('#scene').screenshot(path=str(ROOT/'delivered-web-canvas.png'))
        page.screenshot(path=str(ROOT/'delivered-web-page.png'))
        report['web_controls']={'status':'PASS','s3_left':left,'s6_switch_back':back,'sandbox_origin':'null'}
    finally:
        browser.close()
(ROOT/'delivery.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({k:report[k] for k in ('status','run_id','run_status','request_count','web_video')},ensure_ascii=False))
