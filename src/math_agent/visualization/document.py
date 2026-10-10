"""Export a self-contained interactive lesson; no remote assets or model HTML."""
import html
import json
from pathlib import Path

CSP = "default-src 'none'; script-src 'unsafe-inline'; worker-src blob:; style-src 'unsafe-inline'; img-src data: blob:; media-src blob:; connect-src 'none'; base-uri 'none'; form-action 'none'"


def interactive_html(story, program, provider):
    data = json.dumps({'story': story, 'program': program}, ensure_ascii=False).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
    runtime = Path(__file__).with_name('player.js').read_text(encoding='utf-8')
    note = 'MOCK 离线示例 · ' if provider == 'mock' else ''
    return f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="{html.escape(CSP, quote=True)}">
<title>{html.escape(story['title'])}</title>
<style>body{{font:16px system-ui,sans-serif;margin:0;padding:20px;background:#edf1f7;color:#18283b}}main{{max-width:1040px;margin:auto}}canvas{{width:100%;background:#f7f9fc;border-radius:12px;box-shadow:0 8px 35px #1c36511a}}button{{padding:9px 20px;border:1px solid #bdcbe5;border-radius:7px;background:white;color:#213d8f;cursor:pointer}}.toolbar{{display:flex;gap:12px;align-items:center;margin:16px 0}}#time{{flex:1}}#controls{{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:14px}}label{{display:grid;grid-template-columns:1fr 2fr 50px;gap:8px;align-items:center;background:white;padding:14px;border-radius:8px}}#caption{{min-height:45px;line-height:1.7}}small{{color:#607189}}#status{{color:#a12c2c}}input{{min-width:0}}</style></head>
<body><style>.control-reason{{grid-column:1/-1}}.control-reason:empty{{display:none}}#mode{{color:#456087;font-size:14px}}</style><main><p><small>{note}调整参数，观察数学过程 · 无声动画与中文字幕 · 待教师复核</small></p>
<canvas id="scene" width="960" height="540" aria-label="数学概念动画"></canvas>
<div class="toolbar"><button id="play">播放 / 暂停</button><button id="reset">重置分镜演示</button><input id="time" aria-label="动画进度" type="range" min="0" max="1" step="0.001" value="0"></div>
<p id="caption"></p><p id="mode"></p><div id="controls"></div><p id="status" role="alert"></p>
<details><summary>数学说明与适用范围</summary><p>{html.escape(program['explanation'])}</p><ul>{''.join('<li>'+html.escape(v)+'</li>' for v in story['math_notes']+program['limitations'])}</ul></details>
</main><script type="application/json" id="project">{data}</script><script>{runtime}</script></body></html>'''
