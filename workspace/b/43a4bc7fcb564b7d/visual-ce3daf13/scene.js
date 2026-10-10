function draw(ctx,t,p){
  const W=960,H=540,TAU=Math.PI*2;
  const num=(v,d)=>Number.isFinite(Number(v))?Number(v):d;
  const clamp=(v,a,b)=>Math.max(a,Math.min(b,v));
  const mode=p.$mode==='explore'?'explore':'presentation';
  const inH=clamp(num(p.h,.5),.02,2),inX=clamp(num(p.x0,1),-2,2),inSide=num(p.side,1)<0?-1:1,inEx=num(p.example,0)>=.5?1:0;
  const sec=clamp(num(t,0),0,1)*78;
  const cuts=[8,22,36,50,64,78];
  let si=0;while(si<5&&sec>=cuts[si])si++;
  const a=si?cuts[si-1]:0,b=cuts[si],u=clamp((sec-a)/(b-a),0,1);
  const disabled={};
  let ex=inEx,x0=inX,side=inSide,mag=inH;
  if(mode==='presentation'){
    ex=si===5?1:0;x0=si===5?0:1;
    disabled.example=si===5?'演示固定展示绝对值原点反例':'演示主线固定使用平方函数';
    disabled.x0=si===5?'演示固定在绝对值原点':'演示前五镜固定 x₀=1';
    if(si===2||si===3){
      mag=1-.98*u;
      disabled.h='本镜步长由时间轴从 1 缩小至 0.02';
      if(si===2){side=1;disabled.side='本镜按方案从右侧逼近';}
    }
  }
  const abs=ex===1;
  const f=x=>abs?Math.abs(x):x*x;
  const fp=f(x0),h=side*mag,qx=x0+h,fq=f(qx),slope=(fq-fp)/h;
  let der;
  if(abs)der=Math.abs(x0)<1e-9?null:(x0>0?1:-1);else der=2*x0;
  const L=der===null?null:(x=>fp+der*(x-x0));
  const residual=der===null?null:fq-L(qx),err=der===null?null:Math.abs(residual),ratio=der===null?null:err/mag;
  const rp=(f(x0+mag)-fp)/mag,lm=(f(x0-mag)-fp)/(-mag);
  const origin=abs&&Math.abs(x0)<1e-9;
  const crosses=abs&&x0*(x0+h)<=0&&Math.abs(x0)>1e-9;
  const both=si===3||(si===5&&abs)||(si===4&&origin);
  const fmt=v=>v===null?'不存在':Number(v.toFixed(6));
  const text=(x,y,s,c,fs)=>{ctx.fillStyle=c||'#29485d';ctx.font=(fs||16)+'px sans-serif';ctx.fillText(String(s),x,y);};
  const plot={x:45,y:88,w:570,h:334,x0:-4.5,x1:4.5,y0:-2.2,y1:18};
  const X=x=>plot.x+(x-plot.x0)*plot.w/(plot.x1-plot.x0);
  const Y=y=>plot.y+plot.h-(y-plot.y0)*plot.h/(plot.y1-plot.y0);
  const clip=fn=>{ctx.save();ctx.beginPath();ctx.rect(plot.x,plot.y,plot.w,plot.h);ctx.clip();fn();ctx.restore();};
  const line=(x1,y1,x2,y2,c,w,d)=>clip(()=>{ctx.strokeStyle=c;ctx.lineWidth=w||2;ctx.setLineDash(d||[]);ctx.beginPath();ctx.moveTo(X(x1),Y(y1));ctx.lineTo(X(x2),Y(y2));ctx.stroke();ctx.setLineDash([]);});
  const dot=(x,y,c,r)=>clip(()=>{ctx.fillStyle=c;ctx.beginPath();ctx.arc(X(x),Y(y),r||6,0,TAU);ctx.fill();});
  ctx.fillStyle='#f7fafc';ctx.fillRect(0,0,W,H);
  ctx.fillStyle='#18324a';ctx.font='bold 23px sans-serif';ctx.fillText('割线旋转成切线：导数的极限定义',35,42);
  text(760,42,'h ≠ 0 · 总时长 78 秒','#5a7286',17);
  ctx.fillStyle='#fff';ctx.fillRect(plot.x,plot.y,plot.w,plot.h);ctx.strokeStyle='#cbdde8';ctx.strokeRect(plot.x+.5,plot.y+.5,plot.w-1,plot.h-1);
  for(let z=-4;z<=4;z++)line(z,plot.y0,z,plot.y1,'#e7f0f5',1);
  for(let z=0;z<=16;z+=2)line(plot.x0,z,plot.x1,z,'#e7f0f5',1);
  line(plot.x0,0,plot.x1,0,'#385d73',2);line(0,plot.y0,0,plot.y1,'#385d73',2);
  text(590,Y(0)-8,'x');text(X(0)+8,105,'y');
  clip(()=>{ctx.strokeStyle='#236fb5';ctx.lineWidth=3;ctx.beginPath();for(let i=0;i<=700;i++){const x=plot.x0+(plot.x1-plot.x0)*i/700,y=f(x);if(i===0)ctx.moveTo(X(x),Y(y));else ctx.lineTo(X(x),Y(y));}ctx.stroke();});
  if(L&&si>=2)line(plot.x0,L(plot.x0),plot.x1,L(plot.x1),'#9b55b6',2,[8,6]);
  const drawSec=(sgn,col)=>{const xx=x0+sgn*mag,yy=f(xx);line(x0,fp,xx,yy,col,3);dot(xx,yy,col,6);text(clamp(X(xx)+7,plot.x+5,plot.x+plot.w-105),clamp(Y(yy)-8,plot.y+20,plot.y+plot.h-8),sgn>0?'Q(+|h|)':'Q(−|h|)',col,14);};
  if(both){drawSec(1,side>0?'#168c70':'#d84b4b');drawSec(-1,side<0?'#168c70':'#d84b4b');}
  else{
    const dx=qx-x0,dy=fq-fp,len=Math.sqrt(dx*dx+dy*dy)||1;
    line(x0-dx*10/len,fp-dy*10/len,x0+dx*10/len,fp+dy*10/len,'#7a4aa8',3);
    line(x0,fp,qx,fp,'#e58b32',2,[6,5]);line(qx,fp,qx,fq,'#e58b32',2,[6,5]);dot(qx,fq,'#7a4aa8',6);text(clamp(X(qx)+8,plot.x+5,plot.x+plot.w-30),clamp(Y(fq)-8,plot.y+20,plot.y+plot.h-7),'Q','#5c3480',17);
  }
  if(si===4&&L){line(qx,L(qx),qx,fq,'#d84b4b',3);dot(qx,L(qx),'#d84b4b',4);text(clamp(X(qx)+8,plot.x+5,plot.x+plot.w-45),clamp((Y(fq)+Y(L(qx)))/2,plot.y+20,plot.y+plot.h-8),'r(h)','#b53d3d',15);}
  dot(x0,fp,'#f28e2b',7);text(clamp(X(x0)+8,plot.x+4,plot.x+plot.w-25),clamp(Y(fp)-8,plot.y+20,plot.y+plot.h-7),'P','#a3591a',17);
  text(56,82,'蓝：曲线','#236fb5');text(155,82,'橙：增量','#e58b32');text(260,82,both?'绿/红：两侧割线':'紫：割线/切线',both?'#168c70':'#7a4aa8');
  const bx=636,by=88,bw=289,bh=334;ctx.fillStyle='#eef5fa';ctx.fillRect(bx,by,bw,bh);ctx.strokeStyle='#c6d9e5';ctx.strokeRect(bx+.5,by+.5,bw-1,bh-1);
  let title;
  if(si===0)title=abs?'绝对值曲线与固定点':'固定点与附近的动点';
  if(si===1)title=abs?'绝对值的割线斜率':'用增量构造割线斜率';
  if(si===2)title=der===null?((side>0?'从右侧':'从左侧')+'逼近原点：差商恒为 '+(side>0?'1':'−1')):((side>0?'从右侧':'从左侧')+'逼近切线');
  if(si===3)title=origin?'左右斜率不一致：原点不可导':(abs?'绝对值在当前点的左右极限':'左右极限必须一致');
  if(si===4)title=der===null?'绝对值原点没有切线':(abs?'绝对值的局部线性':'切线为何能近似曲线');
  if(si===5)title=origin?'连续的尖点为何不可导':(abs?'绝对值函数在当前点可导':'平方函数的可导性与切线');
  ctx.fillStyle='#18324a';ctx.font='bold 18px sans-serif';ctx.fillText('S'+(si+1)+' '+title,bx+14,by+31);ctx.strokeStyle='#c6d9e5';ctx.beginPath();ctx.moveTo(bx+12,by+45);ctx.lineTo(bx+bw-12,by+45);ctx.stroke();
  const rows=['f(x)='+(abs?'|x|':'x²')+'，x₀ = '+x0.toFixed(2),'h = '+(h>0?'+':'−')+Math.abs(h).toFixed(3)];
  if(both){rows.push('m(+|h|) = '+rp.toFixed(4),'m(−|h|) = '+lm.toFixed(4),'当前选中侧 = '+(side>0?'+':'−'));}
  else rows.push('m(h) = '+slope.toFixed(4));
  rows.push(der===null?'原点双侧极限不相等':'当前导数 = '+der.toFixed(2));
  if(si===4){rows.push('|h| = '+mag.toFixed(4),'r(h) = '+(der===null?'不适用':err.toFixed(6)),'r(h)/|h| = '+(der===null?'不适用':ratio.toFixed(6)));}
  ctx.fillStyle='#2f4a5e';ctx.font='17px sans-serif';for(let i=0;i<rows.length;i++)ctx.fillText(rows[i],bx+14,by+74+i*25);
  ctx.strokeStyle='#c6d9e5';ctx.beginPath();ctx.moveTo(bx+12,by+238);ctx.lineTo(bx+bw-12,by+238);ctx.stroke();
  const formulas=abs?['m(h)=(|x₀+h|−|x₀|)/h',origin?'h>0→1，h<0→−1':'非原点处导数为 '+(x0>0?'1':'−1')]:['m(h)=[f(x₀+h)−f(x₀)]/h','[(x₀+h)²−x₀²]/h=2x₀+h','L(x)=x₀²+2x₀(x−x₀)'];
  ctx.fillStyle='#7a4aa8';ctx.font='15px sans-serif';for(let i=0;i<formulas.length;i++)ctx.fillText(formulas[i],bx+14,by+264+i*25);
  let caption;
  if(si===0)caption=(abs?'固定绝对值函数上的':'固定平方函数上的')+'点 P，取附近点 Q，观察割线。';
  else if(si===1)caption=abs?'差商是绝对值函数的割线斜率，h 始终非零。':'差商就是割线斜率；平方函数化简为 m(h)=2x₀+h。';
  else if(si===2)caption=der===null?((side>0?'右侧':'左侧')+'差商恒为 '+(side>0?'1':'−1')+'，原点没有切线。'):((side>0?'从右侧':'从左侧')+'缩小 h，差商趋近当前切线斜率；有限动画不取 h=0。');
  else if(si===3)caption=abs?(origin?'同时比较左右差商；原点两侧极限分别为 −1 与 1。':'绝对值在当前非原点可导；左右差商趋向同一个值 '+(x0>0?'1':'−1')+'。'):'同时比较两侧差商；平方函数都趋向同一个有限数 2x₀。';
  else if(si===4)caption=der===null?'原点不可导，不能定义唯一切线或局部线性误差。':(abs?(crosses?'当前步长跨过原点，误差不为零；局部线性结论需限制在同一分支内。':'当前点位于绝对值的单一线性分支，误差为 0。'):'平方函数的切线误差为 h²，误差比 r(h)/|h|=|h| 随步长缩小而趋于 0。');
  else caption=origin?'绝对值函数在原点连续，但左右差商不相等，导数不存在。':(abs?'绝对值函数在当前非尖点可导，切线斜率为 '+(x0>0?'1':'−1')+'。':'平方函数在当前点可导，切线斜率为 2x₀。');
  const controls={h:Number(mag.toFixed(5)),side:side,x0:Number(x0.toFixed(5)),example:ex};
  return {metrics:{scene:si+1,elapsedSeconds:Number(sec.toFixed(3)),example:abs?'|x|':'x²',x0:Number(x0.toFixed(5)),h:Number(h.toFixed(5)),slope:fmt(slope),rightSlope:fmt(rp),leftSlope:fmt(lm),derivative:fmt(der),residual:der===null?'不适用':fmt(residual),errorRatio:der===null?'不适用':fmt(ratio)},controls:controls,disabled:disabled,title:title,caption:caption};
}