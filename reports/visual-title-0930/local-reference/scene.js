function draw(ctx,t,p){
  var W=960,H=540;
  function num(v,d){return typeof v==='number'&&isFinite(v)?v:d;}
  function lim(v,a,b){return Math.max(a,Math.min(b,v));}
  function txt(s,x,y,z,c,a){ctx.font=(z||18)+'px sans-serif';ctx.fillStyle=c||'#1e2b30';ctx.textAlign=a||'left';ctx.textBaseline='middle';ctx.fillText(String(s),x,y);}
  function ln(x1,y1,x2,y2,c,w){ctx.strokeStyle=c||'#52636b';ctx.lineWidth=w||2;ctx.beginPath();ctx.moveTo(x1,y1);ctx.lineTo(x2,y2);ctx.stroke();}
  function rect(x,y,w,h,c){if(isFinite(x)&&isFinite(y)&&isFinite(w)&&isFinite(h)&&w>=0&&h>=0){ctx.fillStyle=c;ctx.fillRect(x,y,w,h);}}
  function f(q){return q*q*q-3*q;}
  function d(q){return 3*q*q-3;}
  var mode=p&&p.$mode==='explore'?'explore':'presentation';
  var tt=lim(num(t,0),0,0.999999999);
  var xin=lim(num(p&&p.x,0),-2,2);
  var vin=lim(Math.round(num(p&&p.view,0)),0,1);
  var scene=Math.min(2,Math.floor(tt*3));
  var u=tt*3-scene;
  var x=xin,view=vin,focus=0,hold=false;
  if(mode==='presentation'){
    if(scene===0){x=-2+4*u;view=0;}
    if(scene===1){
      view=0;
      if(u<0.20){x=-1.65+0.65*u/0.20;focus=-1;}
      else if(u<0.38){x=-1;focus=-1;hold=true;}
      else if(u<0.50){x=-1+2*(u-0.38)/0.12;focus=x<0?-1:1;}
      else if(u<0.68){x=1;focus=1;hold=true;}
      else{x=1-0.65*(u-0.68)/0.32;focus=1;}
    }
    if(scene===2){x=-2+4*u;view=u>=0.55?1:0;}
  }
  x=lim(x,-2,2);
  if(scene!==2)view=0;
  var fx=f(x),dx=d(x);
  var atL=Math.abs(x+1)<1e-9,atR=Math.abs(x-1)<1e-9;
  var stationary=atL||atR;
  if(mode==='explore') focus=atL?-1:atR?1:0;
  var sg=dx>1e-8?1:dx<-1e-8?-1:0;
  var interval=atL||atR?'驻点/区间边界':x<-1?'[-2,-1)':x<1?'(-1,1)':'(1,2]';
  var xmin=-2,xmax=2,ymin=-2.5,ymax=2.5;
  var zoomActive=scene===1&&((mode==='explore'&&stationary)||hold);
  if(zoomActive){
    var cen=focus===-1?-1:1;
    xmin=Math.max(-2,cen-0.72);xmax=Math.min(2,cen+0.72);
    ymin=Infinity;ymax=-Infinity;
    for(var k=0;k<=80;k++){var q=xmin+(xmax-xmin)*k/80;var z=f(q);ymin=Math.min(ymin,z);ymax=Math.max(ymax,z);}
    ymin-=0.34;ymax+=0.34;
  }
  var plot={l:55,r:610,top:105,bot:395};
  function X(q){return plot.l+(q-xmin)/(xmax-xmin)*(plot.r-plot.l);}
  function Y(y){return plot.bot-(y-ymin)/(ymax-ymin)*(plot.bot-plot.top);}
  ctx.clearRect(0,0,W,H);rect(0,0,W,H,'#fbfcf7');rect(35,85,890,335,'#eef4ef');
  var st=scene===0?'S1 当前位置与切线':scene===1?'S2 放大驻点':'S3 符号表总结';
  txt(st,625,101,19,'#41615a');txt('f(x)=x³−3x',625,132,21);txt('f′(x)=3x²−3',625,162,20);
  txt('x='+x.toFixed(2)+'，f='+fx.toFixed(2),625,192,17);
  txt('f′(x)='+dx.toFixed(2),625,220,17,sg>0?'#13795b':sg<0?'#b23a48':'#805500');
  txt(sg>0?'切线斜率为正':sg<0?'切线斜率为负':'切线水平',625,247,17,sg>0?'#13795b':sg<0?'#b23a48':'#805500');
  txt('符号区间：'+interval,625,274,16);
  if(atL)txt('x=-1：左正右负，局部极大',625,301,16,'#805500');
  else if(atR)txt('x=1：左负右正，局部极小',625,301,16,'#805500');
  else txt(sg>0?'该区间函数递增':sg<0?'该区间函数递减':'驻点：需比较两侧',625,301,16,sg>0?'#13795b':sg<0?'#b23a48':'#805500');
  ctx.save();ctx.beginPath();ctx.rect(plot.l,plot.top,plot.r-plot.l,plot.bot-plot.top);ctx.clip();
  if(zoomActive){
    txt('放大视窗',plot.l+8,plot.top+17,15,'#52636b');
    var bandY=plot.bot-42,bandH=38,xf=lim(X(focus),plot.l,plot.r);
    rect(plot.l,bandY,Math.max(0,xf-plot.l),bandH,focus===-1?'#b9e5cf':'#f4c4c4');
    rect(xf,bandY,Math.max(0,plot.r-xf),bandH,focus===-1?'#f4c4c4':'#b9e5cf');
    txt(focus===-1?'+':'−',plot.l+(xf-plot.l)/2,bandY+19,20,focus===-1?'#176b4b':'#9d3040','center');
    txt(focus===-1?'−':'+',xf+(plot.r-xf)/2,bandY+19,20,focus===-1?'#9d3040':'#176b4b','center');
    txt('左侧',plot.l+(xf-plot.l)/2,bandY-13,14,'#52636b','center');txt('右侧',xf+(plot.r-xf)/2,bandY-13,14,'#52636b','center');
  }
  if(scene===2&&view===1){
    var by=220,bh=120,a=lim(X(-1),plot.l,plot.r),b=lim(X(1),plot.l,plot.r);
    rect(plot.l,by,Math.max(0,a-plot.l),bh,'#b9e5cf');rect(a,by,Math.max(0,b-a),bh,'#f4c4c4');rect(b,by,Math.max(0,plot.r-b),bh,'#b9e5cf');
    txt('＋ 递增',plot.l+(a-plot.l)/2,by+25,17,'#176b4b','center');txt('− 递减',(a+b)/2,by+25,17,'#9d3040','center');txt('＋ 递增',b+(plot.r-b)/2,by+25,17,'#176b4b','center');
    txt('[-2,-1)',plot.l+(a-plot.l)/2,by-17,15,'#52636b','center');txt('(-1,1)',(a+b)/2,by-17,15,'#52636b','center');txt('(1,2]',b+(plot.r-b)/2,by-17,15,'#52636b','center');
    ln(plot.l,by+78,plot.r,by+78,'#52636b',2);ln(X(x),by+68,X(x),by+88,'#805500',2);txt('当前位置',lim(X(x),plot.l+35,plot.r-35),by+101,14,'#805500','center');
  }
  var yzero=Y(0),xzero=X(0);
  if(yzero>=plot.top&&yzero<=plot.bot)ln(plot.l,yzero,plot.r,yzero,'#52636b',1.4);
  if(xzero>=plot.l&&xzero<=plot.r)ln(xzero,plot.top,xzero,plot.bot,'#52636b',1.4);
  ctx.strokeStyle='#176b87';ctx.lineWidth=3;ctx.beginPath();
  for(var i=0;i<=360;i++){var q1=xmin+(xmax-xmin)*i/360;var yy=Y(f(q1));if(i===0)ctx.moveTo(X(q1),yy);else ctx.lineTo(X(q1),yy);}ctx.stroke();
  ctx.strokeStyle='#d26a3a';ctx.lineWidth=2;ctx.beginPath();ctx.moveTo(X(xmin),Y(fx+dx*(xmin-x)));ctx.lineTo(X(xmax),Y(fx+dx*(xmax-x)));ctx.stroke();
  var px=X(x),py=Y(fx);ctx.fillStyle='#d22f45';ctx.beginPath();ctx.arc(px,py,6,0,Math.PI*2);ctx.fill();
  txt('P('+x.toFixed(2)+','+fx.toFixed(2)+')',lim(px+10,plot.l+5,plot.r-105),lim(py-16,plot.top+15,plot.bot-15),15,'#b12a3d');
  if(stationary)txt('水平切线',lim(px+12,plot.l+5,plot.r-80),lim(py+20,plot.top+18,plot.bot-15),15,'#805500');
  ctx.restore();
  txt(view===0?'图像视图':'符号带视图',625,337,17,'#41615a');txt('正号对应递增，负号对应递减',625,365,15,'#52636b');txt('导数为零还需比较两侧',625,391,15,'#52636b');
  var title,caption;
  if(mode==='presentation'){
    title=scene===0?'切线斜率与函数走势':scene===1?'驻点与局部极值':'用符号表概括增减';
    caption=scene===0?(sg>0?'切线斜率为正，该符号区间递增。':sg<0?'切线斜率为负，该符号区间递减。':'切线水平，继续比较两侧符号。'):scene===1?(atL?'x=-1 左正右负，是局部极大。':atR?'x=1 左负右正，是局部极小。':zoomActive?'放大驻点附近，比较左右导数符号。':'正在移动取点，观察驻点附近的变化。'):'[-2,2] 内先增、后减、再增；由两侧变号判定极值。';
  }else{
    title=view===0?'图像探索：导数符号与走势':'符号带探索：增减区间';
    caption=atL?'当前恰为 x=-1：左正右负，是局部极大。':atR?'当前恰为 x=1：左负右正，是局部极小。':sg>0?'当前切线斜率为正，位于递增区间。':sg<0?'当前切线斜率为负，位于递减区间。':'当前为驻点；仅凭导数为零不能断定极值。';
  }
  return {metrics:{x:x,f:fx,derivative:dx,scene:scene,view:view,stationary:stationary,atLeft:atL,atRight:atR,focus:focus,interval:interval,viewport:{xmin:xmin,xmax:xmax,ymin:ymin,ymax:ymax}},controls:{x:x,view:view},disabled:scene!==2?{view:'符号带可在 S3 总结镜头切换'}:{},title:title,caption:caption};
}