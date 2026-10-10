"""Read-only Edge inspection of the recovered task; no teacher review requests."""
import json
import hashlib
from pathlib import Path

from playwright.sync_api import sync_playwright, expect
from math_agent.util import write_json, now

rid='e53fd34585fb4bc9af2a85fd994d610a'
folder=Path(__file__).resolve().parent/'production-ui5'
folder.mkdir(exist_ok=False)
report={'started_at':now(),'run_id':rid,'status':'RUNNING','human_review_posts':0}
try:
    with sync_playwright() as manager:
        browser=manager.chromium.launch(headless=True,executable_path=r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe')
        context=browser.new_context(base_url='http://127.0.0.1:8765',viewport={'width':1440,'height':1000},locale='zh-CN')
        page=context.new_page()
        errors=[];mutations=[]
        page.on('pageerror',lambda error: errors.append(str(error)))
        page.on('request',lambda req:mutations.append({'method':req.method,'url':req.url}) if req.method not in ('GET','HEAD','OPTIONS') else None)
        page.add_init_script("localStorage.setItem('math-agent-run',"+json.dumps(rid)+");")
        page.goto('http://127.0.0.1:8765',wait_until='networkidle')
        expect(page.locator('[data-testid=run-status]')).to_have_attribute('data-status','AWAITING_USER_REVIEW',timeout=30000)
        assert page.locator('.error-panel').count()==0
        assert page.locator('#confirm-plan').count()==0
        assert page.locator('.page-review').count()==209
        report['preview_count']=page.locator('.page-review').count()
        delivery=json.loads((folder.parent/'production-recovery.json').read_text(encoding='utf-8'))
        report['downloads']=[]
        for name in ['slides.pdf','slides.tex','source_bundle.zip','quality_report.json','presentation_adaptations.json']:
            expected=[item for item in delivery['downloads'] if item['name']==name]
            assert len(expected)==1,(name,expected)
            artifact=expected[0]
            link=page.locator('a.artifact-link[data-artifact-id="'+artifact['artifact_id']+'"]')
            assert link.count()==1,(name,link.count())
            expect(link.locator('strong')).to_have_text(name)
            response=page.request.get(link.get_attribute('href'))
            assert response.status==200
            assert hashlib.sha256(response.body()).hexdigest()==artifact['sha256']
            report['downloads'].append({'name':name,'artifact_id':artifact['artifact_id'],'hash_verified':True})
        page.screenshot(path=str(folder/'recovered-task.png'),full_page=False)
        report['loaded_preview_pages']=[]
        for index in [19,131,139,207]:
            panel=page.locator('.page-review').nth(index)
            panel.scroll_into_view_if_needed()
            panel.locator('summary').first.click()
            preview=panel.locator('img')
            expect(preview).to_be_visible()
            page.wait_for_function('(id) => { const img=document.querySelector(`[data-page-id="${id}"] img`); return img && img.complete && img.naturalWidth > 0; }',arg=panel.get_attribute('data-page-id'))
            panel.screenshot(path=str(folder/f'preview-{index+1}.png'))
            report['loaded_preview_pages'].append(index+1)
        assert not errors and not mutations,(errors,mutations)
        report.update(status='PASS',page_errors=errors,mutating_requests=mutations)
        browser.close()
except Exception as exc:
    report.update(status='FAIL',error=str(exc))
    raise
finally:
    report['finished_at']=now()
    write_json(folder/'report.json',report)
    print(json.dumps(report,ensure_ascii=False))
