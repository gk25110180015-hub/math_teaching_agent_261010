/* Owned runtime. Model code executes only in a disposable, network-blocked worker. */
"use strict";
const project = JSON.parse(document.getElementById("project").textContent);
const canvas = document.getElementById("scene");
const ctx = canvas.getContext("2d");
const timeSlider = document.getElementById("time");
const statusBox = document.getElementById("status");
const duration = project.story.scenes.reduce((n, s) => n + s.seconds, 0);
const params = Object.fromEntries(project.program.controls.map(c => [c.id, c.value]));
const defaults = {...params}, widgets = new Map();
let mode = 'presentation', effective = {...params};
const version2 = project.program.runtime_version === 2;
let position = 0, playing = false, serial = 0, requests = new Map(), broken = null;
const workerSource = `"use strict";\n${project.program.code}\n;
const surface = new OffscreenCanvas(960, 540);
const context = surface.getContext('2d');
self.onmessage = function(event) {
  const {id,t,p} = event.data;
  try {
    const plotText = [], drawingEvidence = {texts:[],rectangles:[],paints:[],invalid_calls:[]};
    const originals = {};
    let clipped = false; const clipStack = [];
    const numericArguments={fillRect:4,strokeRect:4,clearRect:4,moveTo:2,lineTo:2,rect:4,arc:5,arcTo:5,ellipse:7,bezierCurveTo:6,quadraticCurveTo:4,translate:2,scale:2,rotate:1};
    const paints=['fillText','strokeText','fillRect','strokeRect','fill','stroke'];
    for (const method of new Set(['save','restore','clip',...paints,...Object.keys(numericArguments)])) {
      originals[method] = context[method];
      context[method] = function(...args) {
        if (method==='save') clipStack.push(clipped);
        if (method==='restore' && clipStack.length) clipped=clipStack.pop();
        if (method==='clip') clipped=true;
        const required=numericArguments[method];
        if (required && (args.length<required || args.slice(0,required).some(v=>typeof v!=='number'||!Number.isFinite(v))) && drawingEvidence.invalid_calls.length<12) {
          drawingEvidence.invalid_calls.push({method,arguments:args.slice(0,required).map(v=>String(v).slice(0,80)),reason:'绘图坐标/尺寸必须是有限数值，检查辅助函数实参是否缺失或错位'});
        }
        if (!paints.includes(method)) return originals[method].apply(this,args);
        const color = String(method.startsWith('stroke') ? this.strokeStyle : this.fillStyle);
        const matrix=this.getTransform(), transform=[matrix.a,matrix.b,matrix.c,matrix.d,matrix.e,matrix.f];
        if (method.endsWith('Text') && plotText.length < 80) {
          plotText.push(String(args[0]).slice(0,200));
          const measure=this.measureText(String(args[0]));
          const scale=typeof args[3]==='number' && args[3]>0 ? Math.min(1,args[3]/measure.width) : 1;
          const left=args[1]-measure.actualBoundingBoxLeft*scale,right=args[1]+measure.actualBoundingBoxRight*scale;
          const top=args[2]-measure.actualBoundingBoxAscent,bottom=args[2]+measure.actualBoundingBoxDescent;
          const corners=[[left,top],[right,top],[left,bottom],[right,bottom]].map(([x,y])=>[matrix.a*x+matrix.c*y+matrix.e,matrix.b*x+matrix.d*y+matrix.f]);
          const bounds=[Math.min(...corners.map(c=>c[0])),Math.min(...corners.map(c=>c[1])),Math.max(...corners.map(c=>c[0])),Math.max(...corners.map(c=>c[1]))];
          drawingEvidence.texts.push({text:String(args[0]).slice(0,100),x:args[1],y:args[2],color,transform,bounds,clipped});
        } else if (method.endsWith('Rect') && drawingEvidence.rectangles.length < 24) {
          drawingEvidence.rectangles.push({method,box:args.slice(0,4),color,transform});
        } else if ((method==='fill'||method==='stroke') && drawingEvidence.paints.length < 24) {
          drawingEvidence.paints.push({method,color});
        }
        return originals[method].apply(this,args);
      };
    }
    surface.width = 960; surface.height = 540;
    context.fillStyle = '#f7f9fc'; context.fillRect(0,0,960,540);
    let result;
    try { context.save(); result = draw(context,t,p); context.restore(); }
    finally { for (const method of Object.keys(originals)) context[method] = originals[method]; }
    const bitmap = surface.transferToImageBitmap();
    self.postMessage({id,bitmap,result,plotText,drawingEvidence}, [bitmap]);
  } catch (error) { self.postMessage({id,error:String(error.message || error)}); }
};`;
const workerURL = URL.createObjectURL(new Blob([workerSource], {type: "text/javascript"}));
const worker = new Worker(workerURL);
URL.revokeObjectURL(workerURL);
function fail(message) {
  broken = String(message); playing = false; statusBox.textContent = `动画运行失败：${broken}`;
  worker.terminate();
  for (const value of requests.values()) { clearTimeout(value.timer); value.reject(new Error(broken)); }
  requests.clear();
}
worker.onerror = e => { e.preventDefault(); fail(e.message || "动画代码无法运行"); };
worker.onmessage = e => {
  const item = requests.get(e.data.id);
  if (!item) { if (e.data.bitmap) e.data.bitmap.close(); return; }
  requests.delete(e.data.id); clearTimeout(item.timer);
  if (e.data.error) { item.reject(new Error(e.data.error)); return; }
  item.resolve(e.data);
};
function requestFrame(t, p) {
  if (broken) return Promise.reject(new Error(broken));
  return new Promise((resolve,reject) => {
    const id = ++serial;
    const timer = setTimeout(() => fail("单帧超过 3 秒，请修复代码后重试"), 3000);
    requests.set(id, {resolve,reject,timer}); worker.postMessage({id,t,p});
  });
}
function lines(text, x, y, width, lineHeight, maxLines) {
  let line = "", count = 0;
  const chars = [...text];
  for (let index=0;index<chars.length;index++) {
    const char=chars[index];
    if (ctx.measureText(line + char).width > width) {
      if (count === maxLines-1) { ctx.fillText(line.slice(0,-1)+'…',x,y); return; }
      ctx.fillText(line, x, y); y += lineHeight; line = ""; count++;
    }
    line += char;
  }
  ctx.fillText(line, x, y);
}
function currentScene(t) {
  let end = 0;
  return project.story.scenes.find(s => { end += s.seconds; return t * duration < end; }) || project.story.scenes.at(-1);
}
async function render(t, overrides = {}, options = {}) {
  t = Math.max(0, Math.min(1, t));
  const frameMode = options.mode || (Object.keys(overrides).length ? 'explore' : mode);
  const inputs = {...(frameMode === 'presentation' ? defaults : params), ...overrides};
  const frame = await requestFrame(t, {...inputs, $mode:frameMode});
  const result = frame.result || {};
  if (version2) {
    if (!result.controls || typeof result.title !== 'string' || !result.title.trim() || result.title.length>100 ||
        typeof result.caption !== 'string' || !result.caption.trim() || result.caption.length>120) {
      frame.bitmap.close(); throw new Error('draw 必须返回有效 controls、title（1–100字）和 caption（1–120字）');
    }
    for (const control of project.program.controls) {
      const v=result.controls[control.id], reason=result.disabled?.[control.id];
      if (typeof v !== 'number' || !Number.isFinite(v) || v<control.min-1e-8 || v>control.max+1e-8 ||
          (reason !== undefined && (typeof reason !== 'string' || !reason.trim()))) {
        frame.bitmap.close(); throw new Error(`有效控件值或禁用说明无效：${control.id}`);
      }
      if (frameMode === 'explore' && !reason && Math.abs(v-inputs[control.id])>1e-7) {
        frame.bitmap.close(); throw new Error(`自由探索控件被忽略或被时间轴覆盖：${control.id}，输入 ${inputs[control.id]}，实际 ${v}`);
      }
    }
    effective = {...result.controls};
    for (const [id,w] of widgets) {
      w.input.value=String(effective[id]); w.output.textContent=String(Number(effective[id].toFixed(5)));
      w.input.disabled=Boolean(result.disabled?.[id]); w.reason.textContent=result.disabled?.[id] || '';
    }
  }
  ctx.setTransform(1,0,0,1,0,0); ctx.drawImage(frame.bitmap,0,0); frame.bitmap.close();
  // Hash just the plot area, before captions; a changing subtitle cannot pass animation checks.
  const pixels = ctx.getImageData(0,68,960,367).data;
  let signature = 2166136261;
  for (let i=0;i<pixels.length;i+=4) { signature = Math.imul(signature ^ pixels[i],16777619); signature = Math.imul(signature ^ pixels[i+1],16777619); signature = Math.imul(signature ^ pixels[i+2],16777619); }
  const scene = currentScene(t);
  const title = version2 ? result.title : scene.title;
  const caption = version2 ? result.caption : scene.narration;
  ctx.fillStyle = "#f7f9fc"; ctx.fillRect(0,0,960,68); ctx.fillRect(0,435,960,105);
  ctx.fillStyle = "#18283b"; ctx.font = "bold 25px sans-serif";
  lines(project.story.title,28,34,890,28,1);
  ctx.fillStyle = "#567087"; ctx.font = "16px sans-serif";
  ctx.fillText(`${title} · ${(t*duration).toFixed(1)} / ${duration} 秒`,28,59);
  ctx.fillStyle = "#1d3651"; ctx.font = "19px sans-serif";
  lines(caption,28,460,900,25,3);
  ctx.fillStyle = "#4562d9"; ctx.fillRect(0,534,960*t,6);
  position = t; timeSlider.value = String(t);
  document.getElementById("caption").textContent = caption;
  document.getElementById("mode").textContent = frameMode==='presentation' ? '分镜演示 · 调整参数可进入自由探索' : '自由探索 · 滑杆控制当前参数，可重置返回分镜演示';
  return {metrics: result.metrics || {}, plot_signature: String(signature >>> 0), plot_text:frame.plotText,
          drawing_evidence:frame.drawingEvidence,
          title,caption,controls:version2 ? result.controls : inputs,disabled:result.disabled || {},mode:frameMode,scene_id:scene.id};
}
let rendering = false, queued = null;
async function show(t) {
  queued=t;
  if (rendering) return;
  rendering = true;
  try { while(queued !== null) { const next=queued; queued=null; await render(next); } } catch (e) { fail(e.message); }
  finally { rendering = false; }
}
for (const control of project.program.controls) {
  const label = document.createElement("label");
  const title = document.createElement("span"); title.textContent = control.label;
  const input = document.createElement("input"); input.type="range";
  input.min=control.min; input.max=control.max; input.step=control.step; input.value=control.value;
  input.id=`param-${control.id}`; input.setAttribute("aria-label",control.label);
  const value = document.createElement("output"); value.textContent=control.value;
  const reason = document.createElement('small'); reason.className='control-reason';
  input.oninput = () => { if (version2 && mode==='presentation') Object.assign(params,effective); mode='explore'; params[control.id]=Number(input.value); value.textContent=input.value; playing=false; show(position); };
  widgets.set(control.id,{input,output:value,reason});
  label.append(title,input,value,reason); document.getElementById("controls").append(label);
}
timeSlider.oninput = () => { playing=false; show(Number(timeSlider.value)); };
document.getElementById("play").onclick = async () => {
  if (playing) { playing=false; return; }
  if (position>=1) position=0;
  playing=true; const start=performance.now()-position*duration*1000;
  while(playing && position<1 && !broken) {
    await show(Math.min(1,(performance.now()-start)/(duration*1000)));
    await new Promise(resolve=>setTimeout(resolve,33));
  }
  playing=false;
};
document.getElementById("reset").onclick = () => { playing=false; mode='presentation'; Object.assign(params,defaults); show(0); };
if (version2) {
  // A presentation can lock every control. Exploration must still be reachable.
  const explore = document.createElement('button'); explore.id='explore'; explore.textContent='自由探索';
  explore.onclick = () => { playing=false; if(mode==='presentation')Object.assign(params,effective); mode='explore'; show(position); };
  document.getElementById('reset').before(explore);
}
async function record() {
  playing=false; mode='presentation'; await render(0,{}, {mode:'presentation'});
  const mime = ["video/webm;codecs=vp9","video/webm;codecs=vp8"].find(v=>MediaRecorder.isTypeSupported(v));
  if (!mime) throw new Error("浏览器不支持 WebM 视频编码");
  const stream=canvas.captureStream(24);
  const recorder=new MediaRecorder(stream,{mimeType:mime,videoBitsPerSecond:4000000});
  const chunks=[]; let size=0;
  const completed=new Promise((resolve,reject)=>{
    recorder.ondataavailable=e=>{ chunks.push(e.data); size+=e.data.size; if(size>80*1024*1024){recorder.stop();reject(new Error('视频超过 80MB 限制'));} };
    recorder.onerror=e=>reject(new Error(e.error?.message || "视频编码失败"));
    recorder.onstop=resolve;
  });
  recorder.start(1000); const start=performance.now(); let frames=0;
  try {
    while (performance.now()-start<duration*1000) {
      await render(Math.min(1,(performance.now()-start)/(duration*1000)),{}, {mode:'presentation'}); frames++;
      await new Promise(resolve=>setTimeout(resolve,1000/24));
    }
    await render(1,{}, {mode:'presentation'}); await new Promise(resolve=>setTimeout(resolve,150));
    recorder.stop(); await completed;
  } finally { stream.getTracks().forEach(track=>track.stop()); }
  const blob=new Blob(chunks,{type:mime});
  const video=document.createElement("video"); video.muted=true; video.src=URL.createObjectURL(blob);
  await new Promise((resolve,reject)=>{video.onloadeddata=resolve;video.onerror=()=>reject(new Error('视频解码验证失败'));});
  const dimensions={width:video.videoWidth,height:video.videoHeight}; URL.revokeObjectURL(video.src);
  const data=await new Promise(resolve=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result.split(',')[1]);reader.readAsDataURL(blob);});
  return {data,mime,frames,duration_seconds:duration,recorded_seconds:(performance.now()-start)/1000,...dimensions};
}
window.visualization = {render,record,params,duration,ready:render(0)};
window.visualization.ready.catch(e=>fail(e.message));
