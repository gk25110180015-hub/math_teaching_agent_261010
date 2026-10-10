"""Real browser regressions for generated-code/host interaction, without API calls."""
import json
from pathlib import Path
import pytest
from playwright.sync_api import sync_playwright
from math_agent.visualization.document import interactive_html
from math_agent.visualization.render import browser_path, run_renderer

pytestmark = pytest.mark.e2e

# Small independent mathematical fixture. Model output can choose a scene in video,
# but changing a slider must switch to manual state and update the actual narration.
CODE = r'''
function draw(ctx,t,p) {
 const explore=p.$mode==='explore', last=t>=.8;
 const example=explore?p.example:(last?1:0);
 const x0=example?0:p.x0;
 const mag=explore?p.h:1-.98*t, side=explore?p.side:1;
 const h=side*mag, slope=example?side:2*x0+h;
 const controls={example,x0,h:mag,side};
 const title=(side<0?'从左侧':'从右侧')+'逼近：'+(example?'绝对值':'平方函数');
 const caption=example?'左右斜率分别为负一和正一，原点不可导。':'平方函数差商为 2x0+h，导数为 2x0。';
 ctx.fillStyle='#284a75';ctx.beginPath();ctx.arc(250+x0*30+h*70,180+example*60,15,0,7);ctx.fill();
 ctx.font='20px sans-serif';ctx.fillText('m(h)='+slope.toFixed(4),600,200);
 return {metrics:{h,slope,x0,example},controls,disabled:!explore&&last?{x0:'绝对值反例固定在原点',example:'分镜指定的反例',h:'分镜步长',side:'分镜方向'}:example?{x0:'绝对值反例固定在原点'}:{},title,caption};
}
'''


def project(code=CODE):
    controls = [{'id': id, 'label': id, 'min': lo, 'max': hi, 'step': step, 'value': val}
                for id, lo, hi, step, val in [('h',.02,2,.01,1),('side',-1,1,2,1),('example',0,1,1,0),('x0',-2,2,.1,1)]]
    return {'story': {'title': '导数交互回归', 'math_notes': [], 'scenes': [
        {'id': 'S1', 'title': '固定原字幕：右侧', 'narration': '固定原字幕：平方函数', 'seconds': 5},
        {'id': 'S2', 'title': '不可导反例', 'narration': '原点不可导', 'seconds': 5}]},
        'program': {'runtime_version': 2, 'code': code, 'controls': controls, 'explanation': '测试', 'limitations': []}}


def write_project(directory, data):
    (directory/'project.json').write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
    document = interactive_html(data['story'], data['program'], 'mock')
    (directory/'interactive.html').write_text(document, encoding='utf-8')
    return document


def test_actual_rejected_derivative_detects_unused_example(tmp_path):
    data = json.loads((Path(__file__).parents[1]/'fixtures/visualization_derivative_rejected.json').read_text(encoding='utf-8'))
    write_project(tmp_path, data)
    result = run_renderer(tmp_path, probe_only=True)
    assert result['status'] == 'FAIL'
    assert any(c['id']=='example' and c['status']=='FAIL' for c in result['controls'])
    assert 'example' in result['error']
    assert not (tmp_path/'video.webm').exists()


@pytest.mark.parametrize('broken', ['ignored', 'overridden'])
def test_control_failures_are_collected_before_recording(tmp_path, broken):
    code = CODE.replace('const example=explore?p.example:(last?1:0);', 'const example=last?1:0;').replace('const controls={example,x0,h:mag,side};', 'const controls={example:p.example,x0,h:mag,side};') if broken=='ignored' else CODE.replace('const mag=explore?p.h:1-.98*t', 'const mag=1-.98*t')
    data = project(code)
    write_project(tmp_path, data)
    result = run_renderer(tmp_path, probe_only=True)
    assert result['status'] == 'FAIL'
    expected = 'example' if broken=='ignored' else 'h'
    assert expected in result['error']
    assert result['controls'] and result['scenes']
    assert not (tmp_path/'video.webm').exists()


def test_actual_text_bounds_detect_sidebar_overflow(tmp_path):
    code=CODE.replace("ctx.fillText('m(h)='+slope.toFixed(4),600,200);", "ctx.fillText('m(h)='+slope.toFixed(4),950,200);")
    write_project(tmp_path,project(code))
    result=run_renderer(tmp_path,probe_only=True)
    assert result['status']=='FAIL'
    assert any('文字超出画布' in issue for issue in result['issues'])
    assert not (tmp_path/'video.webm').exists()


def test_canvas_silent_noop_is_detected_before_recording(tmp_path):
    code=CODE.replace("ctx.font='20px sans-serif';", "ctx.fillRect(80,300,120,'#00ff00');ctx.font='20px sans-serif';")
    write_project(tmp_path,project(code))
    result=run_renderer(tmp_path,probe_only=True)
    assert result['status']=='FAIL'
    assert any('无效 Canvas' in issue and 'fillRect' in issue for issue in result['issues'])
    assert not (tmp_path/'video.webm').exists()


def test_derivative_stationary_zoom_signs_and_tangent_pixels(tmp_path):
    data=json.loads((Path(__file__).parents[1]/'fixtures/visualization_derivative_signs.json').read_text(encoding='utf-8'))
    document=write_project(tmp_path,data)
    with sync_playwright() as manager:
        browser=manager.chromium.launch(headless=True,executable_path=browser_path())
        try:
            page=browser.new_page()
            page.route('**/*',lambda route:route.fulfill(content_type='text/html',body=document))
            page.goto('https://visualization.invalid/')
            page.evaluate('()=>window.visualization.ready')
            for x in (-2,-1,-.95,1,2):
                sample=page.evaluate('(x)=>window.visualization.render(.5,{x,view:0},{mode:"explore"})',x)
                state=sample['metrics'];view=state['viewport']
                assert state['f']==pytest.approx(x**3-3*x)
                assert state['derivative']==pytest.approx(3*x*x-3)
                assert view['xmin']<=x<=view['xmax'] and view['ymin']<=state['f']<=view['ymax']
                if abs(x)==1:
                    assert state['stationary'] and state['focus']==x
                    assert state['interval']=='驻点/区间边界'
                    assert view['xmax']-view['xmin']<4
                    colors={r['color'] for r in sample['drawing_evidence']['rectangles'] if r['box'][1]>300}
                    assert {'#b9e5cf','#f4c4c4'}<=colors
                    y=395-(state['f']-view['ymin'])/(view['ymax']-view['ymin'])*290
                    # Check actual pixels, so an opaque band painted later cannot hide the tangent.
                    visible=page.evaluate('''y=>{
                        const c=document.querySelector('#scene').getContext('2d');
                        return [100,180,480,560].every(x=>{
                            const pixels=c.getImageData(x,Math.round(y)-2,1,5).data;
                            for(let i=0;i<pixels.length;i+=4) if(Math.abs(pixels[i]-210)<12&&Math.abs(pixels[i+1]-106)<12&&Math.abs(pixels[i+2]-58)<12)return true;
                            return false;
                        });
                    }''',y)
                    assert visible, 'Both stationary horizontal tangents must remain visible above sign bands'
                else:
                    assert not state['stationary']
                    assert '极大' not in sample['caption'] and '极小' not in sample['caption']
        finally:
            browser.close()


def test_manual_state_captions_disabled_controls_and_reset(tmp_path):
    document = write_project(tmp_path, project())
    with sync_playwright() as manager:
        browser = manager.chromium.launch(headless=True, executable_path=browser_path())
        try:
            page = browser.new_page()
            page.route('**/*', lambda route: route.fulfill(content_type='text/html', body=document))
            page.goto('https://visualization.invalid/')
            page.evaluate('()=>window.visualization.ready')
            first = page.evaluate('()=>window.visualization.render(.4)')
            assert first['controls']['h'] == pytest.approx(.608)
            assert any(item['text'].startswith('m(h)=') and item['x']==600 for item in first['drawing_evidence']['texts'])
            assert first['drawing_evidence']['paints']
            page.locator('#param-side').evaluate('(e)=>{e.value=-1;e.dispatchEvent(new Event("input"));}')
            page.wait_for_function('()=>document.querySelector("#caption").textContent.includes("平方") && document.querySelector("#mode").textContent.includes("自由探索")')
            result = page.evaluate('()=>window.visualization.render(.4)')
            assert '左侧' in result['title'] and result['metrics']['h']<0
            page.locator('#param-h').evaluate('(e)=>{for(const n of [.2,.8,1.3]){e.value=n;e.dispatchEvent(new Event("input"));}}')
            page.wait_for_function('()=>document.querySelector("#param-h").value==="1.3" && document.querySelector("#param-h").nextElementSibling.textContent==="1.3"')
            result = page.evaluate('()=>window.visualization.render(.4)')
            assert result['metrics']['h'] == pytest.approx(-1.3)
            assert result['metrics']['slope'] == pytest.approx(2*result['metrics']['x0']-1.3)
            page.locator('#param-example').evaluate('(e)=>{e.value=1;e.dispatchEvent(new Event("input"));}')
            page.wait_for_function('()=>document.querySelector("#param-x0").disabled')
            assert '原点不可导' in page.locator('#caption').inner_text()
            assert page.locator('#param-x0').input_value() == '0'
            assert '固定在原点' in page.locator('.control-reason').last.inner_text()
            result = page.evaluate('()=>window.visualization.render(.95,{example:0,x0:1,h:.3,side:-1})')
            assert result['metrics']['example']==0 and '平方' in result['caption']
            assert result['metrics']['slope'] == pytest.approx(1.7)
            page.locator('#reset').click()
            page.wait_for_function('()=>document.querySelector("#mode").textContent.startsWith("分镜演示")')
            result = page.evaluate('()=>window.visualization.render(0)')
            assert result['mode']=='presentation' and result['metrics']['h']==1
            assert result['controls']['example']==0 and not page.locator('#param-x0').is_disabled()
            page.evaluate('()=>window.visualization.render(.95)')
            assert page.locator('#param-example').is_disabled()
            assert page.locator('#param-h').is_disabled()
            page.locator('#explore').click()
            page.wait_for_function('()=>!document.querySelector("#param-example").disabled')
            page.locator('#param-example').evaluate('(e)=>{e.value=0;e.dispatchEvent(new Event("input"));}')
            page.wait_for_function('()=>!document.querySelector("#param-x0").disabled')
            result = page.evaluate('()=>window.visualization.render(.95)')
            assert result['controls']['example']==0 and '平方' in result['caption']
        finally:
            browser.close()
