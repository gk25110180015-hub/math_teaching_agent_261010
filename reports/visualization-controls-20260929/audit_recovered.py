"""Read-only browser audit of the user's recovered derivative lesson."""
import json
import math
from pathlib import Path
import sys
from playwright.sync_api import sync_playwright
from math_agent.visualization.render import browser_path

ROOT = Path(__file__).resolve().parent


def audit(directory):
    project = json.loads((directory/'project.json').read_text(encoding='utf-8'))
    story = project['story']
    total = sum(s['seconds'] for s in story['scenes'])
    elapsed = 0; times=[]
    for scene in story['scenes']:
        times.append((elapsed+scene['seconds']/2)/total)
        elapsed += scene['seconds']
    report={'status':'PASS','directory':str(directory),'cases':[],'issues':[]}
    with sync_playwright() as manager:
        browser=manager.chromium.launch(headless=True,executable_path=browser_path())
        try:
            page=browser.new_page(viewport={'width':1100,'height':1050})
            page.goto((directory/'interactive.html').as_uri())
            page.evaluate('()=>window.visualization.ready')
            # The two one-sided secants should approach together in S4 playback.
            s4_start=sum(s['seconds'] for s in story['scenes'][:3])
            s4_len=story['scenes'][3]['seconds']
            start=page.evaluate('t=>window.visualization.render(t,{}, {mode:"presentation"})',(s4_start+.1*s4_len)/total)
            end=page.evaluate('t=>window.visualization.render(t,{}, {mode:"presentation"})',(s4_start+.9*s4_len)/total)
            assert abs(end['metrics']['h'])<abs(start['metrics']['h']), 'S4 playback must shrink the two-sided step'
            for index,t in enumerate(times):
                baseline=page.evaluate('t=>window.visualization.render(t,{}, {mode:"presentation"})',t)
                assert baseline['controls']['example'] == (1 if index==5 else 0)
                for example in (0,1):
                    for x0 in (-2,0,1,2):
                        for side in (-1,1):
                            for h in (.02,.5,1,2):
                                params={'example':example,'x0':x0,'side':side,'h':h}
                                frame=page.evaluate('([t,p])=>window.visualization.render(t,p,{mode:"explore"})',[t,params])
                                m=frame['metrics']; c=frame['controls']; x=c['x0']; actual_h=side*h
                                f=abs if example else lambda x:x*x
                                slope=(f(x+actual_h)-f(x))/actual_h
                                case={'scene':index+1,'params':params,'actual':c,'metrics':m,'title':frame['title'],'caption':frame['caption']}
                                report['cases'].append(case)
                                assert c['example']==example and abs(m['h']-actual_h)<1e-5, case
                                assert abs(m['slope']-slope)<2e-5, case
                                if example and abs(x)<1e-8:
                                    assert isinstance(m['derivative'],str), case
                                else:
                                    expected=(1 if x>0 else -1) if example else 2*x
                                    assert abs(m['derivative']-expected)<2e-5, case
                                for key,dx in [('rightSlope',h),('leftSlope',-h)]:
                                    if key in m:
                                        assert abs(m[key]-(f(x+dx)-f(x))/dx)<2e-5,case
                                if not example and 'residual' in m:
                                    assert abs(m['residual']-h*h)<2e-5,case
                                if index==2 and not example:
                                    assert ('左' if side<0 else '右') in frame['title'],case
                                if example and abs(x)>1e-8 and any('m(h)=|h|/h' in v.replace(' ','') for v in frame['plot_text']):
                                    report['issues'].append({'scene':index+1,'params':params,'error':'非原点错误显示 m(h)=|h|/h'})
                                if not example and any(v in frame['title'] for v in ('尖点','不可导')):
                                    report['issues'].append({'scene':index+1,'params':params,'error':'平方函数仍显示不可导标题'})
                                if example and index==4 and isinstance(m.get('residual'),(float,int)) and abs(m['residual'])>.001:
                                    caption=frame['caption']
                                    if not any(v in caption for v in ('跨过','跨越','跨越了')) or '在不跨过' in caption:
                                        report['issues'].append({'scene':index+1,'params':params,'error':'跨尖点有误差时字幕未说明当前情况','caption':caption})
                                if example and index==3 and abs(x)>1e-8 and '在尖点两侧极限不相等' in frame['caption']:
                                    report['issues'].append({'scene':index+1,'params':params,'error':'非原点误用尖点字幕','caption':frame['caption']})
                                if example and index==4 and isinstance(m.get('residual'),(float,int)) and abs(m['residual'])<1e-7 and '误差不为零' in frame['caption']:
                                    report['issues'].append({'scene':index+1,'params':params,'error':'到达原点但未跨越，零误差被说成非零','caption':frame['caption']})
            for name,t,params in [('left',times[2],{'example':0,'x0':1,'side':-1,'h':.5}),
                                  ('corner',times[-1],{'example':1,'x0':0,'side':-1,'h':.5}),
                                  ('switch-back',times[-1],{'example':0,'x0':1,'side':1,'h':.5})]:
                page.evaluate('([t,p])=>window.visualization.render(t,p,{mode:"explore"})',[t,params])
                page.locator('#scene').screenshot(path=str(ROOT/f'recovered-{name}.png'))
            report['status']='FAIL' if report['issues'] else 'PASS'
        except Exception as error:
            report['status']='FAIL';report['error']=str(error)
        finally:
            browser.close()
    path=ROOT/'recovered-audit.json'
    path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'status':report['status'],'cases':len(report['cases']),'issues':len(report['issues']),'error':report.get('error')},ensure_ascii=False))
    return report


if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    result=audit(Path(sys.argv[1]).resolve())
    sys.exit(result['status']!='PASS')
