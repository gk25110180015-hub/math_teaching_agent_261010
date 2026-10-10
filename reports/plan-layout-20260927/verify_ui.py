"""Read-only verification of the deployed, rebuilt original task in Edge."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright, expect
from math_agent.util import digest, now, write_json

folder=Path(__file__).resolve().parent
delivery=json.loads((folder/'production.json').read_text(encoding='utf-8'))
assert delivery['status']=='PASS'
output=folder/'production-ui';output.mkdir(exist_ok=False)
report={'started_at':now(),'status':'RUNNING','human_review_posts':0}
try:
    with sync_playwright() as manager:
        browser=manager.chromium.launch(headless=True,executable_path=r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe')
        context=browser.new_context(base_url='http://127.0.0.1:8765',viewport={'width':1440,'height':1000},locale='zh-CN')
        page=context.new_page();errors=[];mutations=[]
        page.on('pageerror',lambda error:errors.append(str(error)))
        page.on('request',lambda req:mutations.append(req.method+' '+req.url) if req.method not in ('GET','HEAD','OPTIONS') else None)
        page.add_init_script("localStorage.setItem('math-agent-run',"+json.dumps(delivery['run_id'])+");")
        page.goto('/',wait_until='networkidle')
        expect(page.locator('[data-testid=run-status]')).to_have_attribute('data-status','AWAITING_USER_REVIEW')
        expect(page.locator('.section-list > li')).to_have_count(4)
        expect(page.locator('.section-list')).not_to_contain_text('导数的概念与计算')
        expect(page.locator('#omission-summary')).to_contain_text('U0001、U0002')
        assert page.locator('.error-panel').count()==page.locator('#confirm-plan').count()==0
        expect(page.locator('.page-review')).to_have_count(178)
        page.locator('.section-list').screenshot(path=str(output/'effective-plan.png'))
        verified=[]
        for name in ('slides.pdf','slides.tex','source_bundle.zip','quality_report.json'):
            artifact=next(a for a in delivery['downloads'] if a['name']==name)
            link=page.locator('a[data-artifact-id="'+artifact['artifact_id']+'"]')
            expect(link).to_have_count(1)
            response=page.request.get(link.get_attribute('href'))
            assert response.status==200 and digest(response.body())==artifact['sha256']
            verified.append(name)
        for number in (3,6,12,46):
            panel=page.locator('.page-review').nth(number-1)
            panel.locator('summary').first.click();expect(panel.locator('img')).to_be_visible()
            page.wait_for_function('(id)=>{const img=document.querySelector(`[data-page-id="${id}"] img`);return img && img.complete && img.naturalWidth>0;}',arg=panel.get_attribute('data-page-id'))
            panel.screenshot(path=str(output/f'page-{number}.png'))
        assert not errors and not mutations,(errors,mutations)
        report.update(status='PASS',preview_count=178,visible_sections=4,downloads=verified,
                      loaded_previews=[3,6,12,46],page_errors=errors,mutating_requests=mutations)
        browser.close()
except Exception as exc:
    report.update(status='FAIL',error=str(exc));raise
finally:
    report['finished_at']=now();write_json(output/'report.json',report)
    print(json.dumps(report,ensure_ascii=False))
