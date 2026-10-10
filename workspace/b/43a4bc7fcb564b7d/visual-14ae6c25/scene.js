function draw(ctx,t,p){
  const W=960,H=540,TAU=Math.PI*2;
  const num=(v,d)=>Number.isFinite(Number(v))?Number(v):d;
  const clamp=(v,a,b)=>Math.max(a,Math.min(b,v));
  const mode=p.$mode==='explore'?'explore':'presentation';
  const inputH=clamp(num(p.h,.5),.02,2), inputX=clamp(num(p.x0,1),-2,2);
  const inputSide=num(p.side,1)<0?-1:1, inputEx=num(p.example,0)>=.5?1:0;
  const sec=clamp(num(t,0),0,1)*78;
  const cuts=[8,22,36,50,64,78];
  let si=0;while(si<5&&sec>=cuts[si])si++;
  const start=si?cuts[si-1]:0,end=cuts[si];
  const local=clamp((sec-start)/(end-start),0,1);
  const disabled={};
  let example,x0,side,mag;
  if(mode==='presentation'){
    example=si===5?1:0;
    x0=si===5?0:1;
    side=inputSide;
    mag=si===2?1-.98*local:inputH;
    disabled.example=si===5?'演示第六镜固定展示绝对值反例':'演示前五镜固定使用平方函数主例';
    disabled.x0=si===5?'演示第六镜固定在绝对值原点 x₀=0':'演示前五镜先固定 x₀=1';
    if(si===2){side=1;disabled.h='本镜步长由时间轴从 1 缩小到 0.02';disabled.side='本镜按方案固定从右侧逼近';}
  }else{
    example=inputEx;x0=inputX;side=inputSide;mag=inputH;
  }
  const isAbs=example===1;
  const f=x=>isAbs?Math.abs(x):x*x;
  const fp=f(x0),h=side*mag,qx=x0+h,fq=f(qx);
  const slope=(fq-fp)/h;
  const derivative=isAbs?(Math.abs(x0)<1e-9?null:(x0>0?1:-1)):2*x0;
  const L=derivative===null?null:(x=>fp+derivative*(x-x0));
  const residual=derivative===null?null:fq-L(qx);
  const error=Math.abs(residual===null?0:residual);
  const ratio=derivative===null?null:error/Math.abs(h);
  const rp=(f(x0+mag)-fp)/mag;
  const lm=(f(x0-mag)-fp)/(-mag);
  const both=si===3||si===5||(si===4&&isAbs&&Math.abs(x0)<1e-9);
  const fmt=v=>v===null?'不存在':Number(v.toFixed(6));
  const safeText=v=>String(v);
  ctx.fillStyle='#f7fafc';ctx.fillRect(0,0,W,H);
  ctx.fillStyle='#18324a';ctx.font='bold 23px sans-serif';ctx.fillText('割线旋转成切线：导数的极限定义',35,42);
  ctx.fillStyle='#5a7286';ctx.font='17px sans-serif';ctx.fillText('h ≠ 0 · 总时长 78 秒',770,42);
  const gx=45,gy=88,gw=570,gh=334,xmin=-4.5,xmax=4.5,ymin=-2.2,ymax=18;
  const X=x=>gx+(x-xmin)*gw/(xmax-xmin),Y=y=>gy+gh-(y-ymin)*gh/(ymax-ymin);
  const clip=fn=>{ctx.save();ctx.beginPath();ctx.rect(gx,gy,gw,gh);ctx.clip();fn();ctx.restore();};
  const seg=(x1,y1,x2,y2,c,w,d)=>clip(()=>{ctx.strokeStyle=c;ctx.lineWidth=w||2;ctx.setLineDash(d||[]);ctx.beginPath();ctx.moveTo(X(x1),Y(y1));ctx.lineTo(X(x2),Y(y2));ctx.stroke();ctx.setLineDash([]);});
  const dot=(x,y,c,r)=>clip(()=>{ctx.fillStyle=c;ctx.beginPath();ctx.arc(X(x),Y(y),r||6,0,TAU);ctx.fill();});
  const txt=(x,y,s,c,fs)=>{ctx.fillStyle=c||'#2f4a5e';ctx.font=(fs||16)+'px sans-serif';ctx.fillText(s,x,y);};
  ctx.fillStyle='#fff';ctx.fillRect(gx,gy,gw,gh);ctx.strokeStyle='#cbdde8';ctx.strokeRect(gx+.5,gy+.5,gw-1,gh-1);
  for(let z=-4;z<=4;z++)seg(z,ymin,z,ymax,'#e7f0f5',1);
  for(let z=0;z<=16;z+=2)seg(xmin,z,xmax,z,'#e7f0f5',1);
  seg(xmin,0,xmax,0,'#385d73',2);seg(0,ymin,0,ymax,'#385d73',2);
  txt(gx+gw-18,Y(0)-8,'x');txt(X(0)+8,gy+17,'y');
  clip(()=>{ctx.strokeStyle='#236fb5';ctx.lineWidth=3;ctx.beginPath();for(let i=0;i<=700;i++){const x=xmin+(xmax-xmin)*i/700,y=f(x);if(i===0)ctx.moveTo(X(x),Y(y));else ctx.lineTo(X(x),Y(y));}ctx.stroke();});
  if(L&&si>=2)seg(xmin,L(xmin),xmax,L(xmax),'#9b55b6',2,[8,6]);
  if(both){
    const selected=side>0?'#168c70':'#d84b4b',other=side>0?'#efb2b2':'#b9dccc';
    seg(x0,fp,x0+mag,f(x0+mag),selected,3);seg(x0,fp,x0-mag,f(x0-mag),other,3);
    dot(x0+mag,f(x0+mag),'#168c70',6);dot(x0-mag,f(x0-mag),'#d84b4b',6);
    txt(clamp(X(x0+mag)+7,gx+5,gx+gw-65),clamp(Y(f(x0+mag))-8,gy+18,gy+gh-8),'Q(+|h|)', '#168c70',14);
    txt(clamp(X(x0-mag)+7,gx+5,gx+gw-65),clamp(Y(f(x0-mag))-8,gy+18,gy+gh-8),'Q(−|h|)', '#b53d3d',14);
  }else{
    const dx=qx-x0,dy=fq-fp,len=Math.sqrt(dx*dx+dy*dy)||1;
    seg(x0-dx*10/len,fp-dy*10/len,x0+dx*10/len,fp+dy*10/len,'#7a4aa8',3);
    seg(x0,fp,qx,fp,'#e58b32',2,[6,5]);seg(qx,fp,qx,fq,'#e58b32',2,[6,5]);
    dot(qx,fq,'#7a4aa8',6);txt(clamp(X(qx)+8,gx+4,gx+gw-28),clamp(Y(fq)-8,gy+20,gy+gh-7),'Q','#5c3480',17);
  }
  if(si===4&&L){seg(qx,L(qx),qx,fq,'#d84b4b',3);dot(qx,L(qx),'#d84b4b',4);txt(clamp(X(qx)+8,gx+5,gx+gw-45),clamp((Y(fq)+Y(L(qx)))/2,gy+20,gy+gh-8),'r(h)','#b53d3d',15);}
  dot(x0,fp,'#f28e2b',7);txt(clamp(X(x0)+8,gx+4,gx+gw-25),clamp(Y(fp)-8,gy+20,gy+gh-7),'P','#a3591a',17);
  txt(56,82,'蓝：曲线','#236fb5');txt(155,82,'橙：增量','#e58b32');
  txt(260,82,both?'绿/红：两侧割线':'紫：割线/切线',both?'#168c70':'#7a4aa8');
  const bx=636,by=88,bw=289,bh=334;ctx.fillStyle='#eef5fa';ctx.fillRect(bx,by,bw,bh);ctx.strokeStyle='#c6d9e5';ctx.strokeRect(bx+.5,by+.5,bw-1,bh-1);
  let title;
  if(si===0)title=isAbs?'绝对值曲线与固定点':'固定点与附近的动点';
  if(si===1)title=isAbs?'绝对值的割线斜率':'用增量构造割线斜率';
  if(si===2)title=derivative===null?((side>0?'从右侧':'从左侧')+'逼近原点：差商恒为 '+(side>0?'1':'−1')):((side>0?'从右侧':'从左侧')+'逼近切线');
  if(si===3)title=isAbs&&Math.abs(x0)<1e-9?'左右斜率不一致：原点不可导':'左右极限必须一致';
  if(si===4)title=derivative===null?'绝对值原点没有切线':(isAbs?'绝对值非原点的局部线性':'切线为何能近似曲线');
  if(si===5)title=isAbs&&Math.abs(x0)<1e-9?'连续的尖点为何不可导':(isAbs?'绝对值函数在非原点可导':'平方函数的可导性与切线');
  ctx.fillStyle='#18324a';ctx.font='bold 18px sans-serif';ctx.fillText('S'+(si+1)+' '+title,bx+14,by+31);ctx.strokeStyle='#c6d9e5';ctx.beginPath();ctx.moveTo(bx+12,by+45);ctx.lineTo(bx+bw-12,by+45);ctx.stroke();
  const rows=[];rows.push('f(x)='+(isAbs?'|x|':'x²')+'，x₀ = '+x0.toFixed(2));rows.push('h = '+(h>0?'+':'−')+Math.abs(h).toFixed(3));
  if(both){rows.push('m(+|h|) = '+rp.toFixed(4));rows.push('m(−|h|) = '+lm.toFixed(4));rows.push('当前选中侧 = '+(side>0?'+':'−'))}else rows.push('m(h) = '+slope.toFixed(4));
  if(isAbs)rows.push(derivative===null?'原点双侧极限不相等':'当前导数 = '+derivative.toFixed(2));else rows.push('m(h)=2x₀+h = '+slope.toFixed(4));
  if(si===4){rows.push('|h| = '+Math.abs(h).toFixed(4));rows.push('r(h) = '+(derivative===null?'不适用':error.toFixed(6)));rows.push('r(h)/|h| = '+(ratio===null?'不适用':ratio.toFixed(6)));}
  ctx.fillStyle='#2f4a5e';ctx.font='17px sans-serif';for(let i=0;i<rows.length;i++)ctx.fillText(rows[i],bx+14,by+74+i*25);
  ctx.strokeStyle='#c6d9e5';ctx.beginPath();ctx.moveTo(bx+12,by+238);ctx.lineTo(bx+bw-12,by+238);ctx.stroke();
  const formulas=isAbs?['m(h)=(|x₀+h|−|x₀|)/h',Math.abs(x0)<1e-9?'h>0→1，h<0→−1':'非原点处斜率为 '+(x0>0?'1':'−1')]:['m(h)=[f(x₀+h)−f(x₀)]/h','[(x₀+h)²−x₀²]/h=2x₀+h','L(x)=x₀²+2x₀(x−x₀)'];
  ctx.fillStyle='#7a4aa8';ctx.font='15px sans-serif';for(let i=0;i<formulas.length;i++)ctx.fillText(formulas[i],bx+14,by+264+i*25);
  let caption;
  if(isAbs&&Math.abs(x0)<1e-9)caption=si===4?'绝对值原点没有唯一切线；左右差商分别为 −1 与 1。':(both?'左、右差商分别为 −1 与 1，双侧导数不存在。':(side>0?'当前为右侧差商 1；原点仍不可导。':'当前为左侧差商 −1；原点仍不可导。'));
  else if(isAbs&&si===4)caption='绝对值在非原点可导；在不跨过原点的局部区间内，切线与函数完全重合，误差为 0。';
  else if(isAbs)caption='当前点不在尖点，绝对值函数在此处可导，导数为 '+(x0>0?'1':'−1')+'。';
  else if(si===0)caption='固定 P=(x₀,x₀²)，取附近点 Q，观察函数曲线与割线。';
  else if(si===1)caption='差商就是割线斜率；平方函数化简为 m(h)=2x₀+h，且 h 始终非零。';
  else if(si===2)caption=derivative===null?'单侧差商虽稳定为 '+(side>0?'1':'−1')+'，但另一侧不同，因此不存在切线。':(side>0?'从右侧':'从左侧')+'缩小 h，差商趋近切线斜率 2x₀；有限动画不取 h=0。';
  else if(si===3)caption=isAbs?'两侧差商分别为 '+lm.toFixed(3)+' 与 '+rp.toFixed(3)+'，在原点不相等。':'同时比较两侧差商；平方函数两侧都趋向同一个有限数 2x₀。';
  else if(si===4)caption='平方函数的切线误差为 h²，误差比 r(h)/|h|=|h| 随步长缩小而趋于 0。';
  else caption=isAbs?'绝对值函数在当前取点可导，切线斜率为 '+(x0>0?'1':'−1')+'。':'平方函数在当前点可导，切线斜率为 2x₀。';
  const controls={h:Number(mag.toFixed(5)),side:side,x0:Number(x0.toFixed(5)),example:example};
  return {metrics:{scene:si+1,elapsedSeconds:Number(sec.toFixed(3)),example:isAbs?'|x|':'x²',x0:Number(x0.toFixed(5)),h:Number(h.toFixed(5)),slope:fmt(slope),rightSlope:fmt(rp),leftSlope:fmt(lm),derivative:fmt(derivative),residual:derivative===null?'不适用':fmt(residual),errorRatio:derivative===null?'不适用':fmt(ratio)},controls:controls,disabled:disabled,title:title,caption:caption};
}