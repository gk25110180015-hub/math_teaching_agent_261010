"""Actual browser, worker, WebM encoding and sandboxed interactive preview."""
import json
from pathlib import Path
import pytest
from test_browser_workflows import local_services, browser_page, expect

pytestmark = pytest.mark.e2e


@pytest.mark.parametrize('topic', ['导数', '梯度下降算法'])
def test_visualization_full_browser_flow(browser_page, local_services, topic):
    page = browser_page
    page.get_by_role('link', name='数学概念 → 视频与交互页面').click()
    page.locator('#visual-topic').fill(topic)
    page.locator('#visual-provider').select_option('mock')
    page.locator('#visual-trust').check()
    page.locator('#visual-create').click()
    page.locator('#visual-candidate-form').wait_for(timeout=30000)
    # Arbitrary candidate choice; custom suggestions are intentionally left empty.
    page.locator('input[name=candidate]').first.check()
    expect(page.locator('#visual-suggestion')).to_be_visible()
    page.locator('#visual-choose').click()
    page.locator('#visual-refine-form fieldset').first.wait_for(timeout=30000)
    for field in page.locator('#visual-refine-form fieldset').all():
        field.locator('input[type=radio]').first.check()
    page.locator('#visual-refine').click()
    page.locator('#visual-confirm').wait_for(timeout=30000)
    page.reload()
    page.locator('#visual-confirm').wait_for(timeout=10000)
    page.locator('#visual-confirm').click()
    expect(page.locator('[data-testid=visual-status]')).to_have_attribute('data-status','COMPLETED_WITH_WARNINGS',timeout=150000)
    video = page.locator('video')
    expect(video).to_be_visible()
    page.wait_for_function('()=>document.querySelector("video").readyState >= 1')
    assert video.evaluate('(v)=>v.videoWidth') == 960
    video.evaluate('(v)=>v.play()')
    page.wait_for_function('()=>document.querySelector("video").currentTime > 0.2')
    video.evaluate('(v)=>v.pause()')
    page.locator('iframe[title="数学概念交互页面"]').scroll_into_view_if_needed()
    iframe=page.frame_locator('iframe[title="数学概念交互页面"]')
    iframe.locator('#scene').wait_for()
    frame=next(f for f in page.frames if '/preview' in f.url)
    frame.evaluate('()=>window.visualization.ready')
    assert frame.evaluate('self.origin') == 'null'
    start=frame.evaluate('()=>window.visualization.render(.65)')
    control=iframe.locator('#controls input').first
    control.evaluate('(e)=>{e.value=e.max;e.dispatchEvent(new Event("input",{bubbles:true}));}')
    page.wait_for_timeout(300)
    after=frame.evaluate('()=>window.visualization.render(.65)')
    assert start['plot_signature'] != after['plot_signature']
    if topic == '导数':
        metrics = after['metrics']
        assert metrics['slope'] == pytest.approx(2*metrics['x0'] + metrics['h'], rel=1e-7)
        assert metrics['error'] == pytest.approx(metrics['h'], rel=1e-7)
    else:
        metrics = after['metrics']; n = metrics['step']
        assert metrics['x'] == pytest.approx(2*(1-.9)**n, abs=1e-12)
        assert metrics['objective'] == pytest.approx((metrics['x']**2+metrics['y']**2)/2)
    assert iframe.locator('#status').inner_text() == ''
    iframe.locator('#scene').screenshot(path=str(local_services[1] / ('gradient.png' if '梯度' in topic else 'derivative.png')))
    with page.expect_download() as download:
        page.get_by_role('link',name='source_bundle.zip',exact=True).click()
    artifact=local_services[1] / ('gradient.zip' if '梯度' in topic else 'derivative.zip')
    download.value.save_as(artifact)
    import zipfile
    with zipfile.ZipFile(artifact) as archive:
        assert {'video.webm','interactive.html','scene.js','project.json','plan.json'}.issubset(archive.namelist())
        quality=json.loads(archive.read('quality_report.json'))
        assert quality['render']['status']=='PASS' and quality['render']['video']['frames']>100
        samples=quality['render']['samples']
        metric='objective' if '梯度' in topic else 'error'
        assert samples[-1]['metrics'][metric] < samples[0]['metrics'][metric] / 100
    page.get_by_role('link',name='返回讲义与课件').click()
    page.locator('#new-run-form').wait_for()
