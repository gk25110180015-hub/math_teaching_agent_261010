function draw(ctx,t,p){
  var W=960,H=540;
  var mode=p&&p.$mode==='explore'?'explore':'presentation';
  function finite(v,d){return typeof v==='number'&&v===v&&v!==Infinity&&v!==-Infinity?v:d;}
  function clamp(v,a,b){return Math.max(a,Math.min(b,v));}
  var tt=clamp(finite(t,0),0,0.999999);
  var px=clamp(finite(p&&p.x,0),-2,2);
  var pv=clamp(Math.round(finite(p&&p.view,0)),0,1);
  var scene,u,x,view;
  if(mode==='explore'){
    scene=Math.min(2,Math.floor(tt*3));
    u=tt*3-scene;
    x=px;
    view=pv;
  }else{
    var z=tt*3;
    scene=Math.min(2,Math.floor(z));
    u=z-scene;
    if(scene===0){
      x=-2+4*u;
      view=0;
    }else if(scene===1){
      if(u<0.20){x=-2+5*u;}
      else if(u<0.40){x=-1;}
      else if(u<0.62){x=-1+2*(u-0.40)/0.22;}
      else if(u<0.82){x=1;}
      else{x=1-3*(u-0.82)/0.18;}
      x=clamp(x,-2,2);
      view=0;
    }else{
      x=-2+4*u;
      view=u<0.52?0:1;
    }
  }
  x=clamp(x,-2,2);
  var f=function(q){return q*q*q-3*q;};
  var d=function(q){return 3*q*q-3;};
  var fx=f(x),dx=d(x);
  var tol=1e-9;
  var atLeft=Math.abs(x+1)<tol;
  var atRight=Math.abs(x-1)<tol;
  var stationary=atLeft||atRight;
  var trend=dx>tol?'递增':dx<-tol?'递减':'驻点：需看两侧符号';
  var extrema=atLeft?'x=-1：左正右负，局部极大':atRight?'x=1：左负右正，局部极小':'当前点不是驻点';
  var plot={l:55,r:610,top:105,bot:395};
  function X(q){return plot.l+(q+2)/4*(plot.r-plot.l);}
  function Y(q){return 250-f(q)*55;}
  function text(s,x0,y0,size,color,align){
    ctx.fillStyle=color||'#17202a';
    ctx.font=(size||18)+'px sans-serif';
    ctx.textAlign=align||'left';
    ctx.textBaseline='middle';
    ctx.fillText(s,x0,y0);
  }
  function line(x1,y1,x2,y2,color,w){
    ctx.strokeStyle=color||'#53636b';
    ctx.lineWidth=w||2;
    ctx.beginPath();ctx.moveTo(x1,y1);ctx.lineTo(x2,y2);ctx.stroke();
  }
  ctx.clearRect(0,0,W,H);
  ctx.fillStyle='#fbfcf7';ctx.fillRect(0,0,W,H);
  ctx.fillStyle='#eef4ef';ctx.fillRect(35,85,890,335);
  text(view===0?'函数图像视图':'导数符号带视图',650,105,18,'#41615a');
  text('f(x)=x³−3x',650,137,22,'#17202a');
  text('f′(x)=3x²−3',650,166,21,'#17202a');
  text('当前位置 x='+x.toFixed(2)+'，f(x)='+fx.toFixed(2),650,199,18,'#17202a');
  text('f′(x)='+dx.toFixed(2)+'，'+trend,650,226,18,dx>tol?'#13795b':dx<-tol?'#b23a48':'#805500');
  if(stationary)text(extrema,650,253,18,'#805500');
  ctx.save();
  ctx.beginPath();ctx.rect(plot.l,plot.top,plot.r-plot.l,plot.bot-plot.top);ctx.clip();
  if(view===0){
    line(plot.l,250,plot.r,250,'#53636b',1.5);
    line(X(0),plot.top,X(0),plot.bot,'#53636b',1.5);
    for(var k=-2;k<=2;k++){
      line(X(k),246,X(k),254,'#53636b',1);
      text(String(k),X(k),270,15,'#53636b','center');
    }
    ctx.strokeStyle='#176b87';ctx.lineWidth=3;ctx.beginPath();
    for(var i=0;i<=240;i++){
      var q=-2+4*i/240;
      var xx=X(q),yy=Y(q);
      if(i===0)ctx.moveTo(xx,yy);else ctx.lineTo(xx,yy);
    }
    ctx.stroke();
    var xa=X(x),ya=Y(x);
    line(X(-2),Y(x)-dx*(-2-x)*55,X(2),Y(x)-dx*(2-x)*55,'#d26a3a',2);
    ctx.fillStyle='#d22f45';ctx.beginPath();ctx.arc(xa,ya,6,0,Math.PI*2);ctx.fill();
    text('P('+x.toFixed(2)+','+fx.toFixed(2)+')',xa+10,ya-15,16,'#b12a3d');
    if(stationary)text('水平切线',xa+12,ya+20,16,'#805500');
  }else{
    text('[-2,-1)',X(-1)-90,145,18,'#17202a','center');
    text('(-1,1)',X(0),145,18,'#17202a','center');
    text('(1,2]',X(1)+90,145,18,'#17202a','center');
    ctx.fillStyle='#8bd3b5';ctx.fillRect(X(-2),180,X(-1)-X(-2),48);
    ctx.fillStyle='#f3b4b4';ctx.fillRect(X(-1),180,X(1)-X(-1),48);
    ctx.fillStyle='#8bd3b5';ctx.fillRect(X(1),180,X(2)-X(1),48);
    text('＋ 递增',X(-1)-110,204,18,'#155b43','center');
    text('− 递减',X(0),204,18,'#8a2634','center');
    text('＋ 递增',X(1)+105,204,18,'#155b43','center');
    line(X(-2),252,X(2),252,'#53636b',2);
    line(X(-1),244,X(-1),260,'#53636b',2);
    line(X(1),244,X(1),260,'#53636b',2);
    text('-1',X(-1),278,17,'#17202a','center');
    text('1',X(1),278,17,'#17202a','center');
    line(X(x),172,X(x),236,'#805500',2);
    text('当前位置',X(x),158,15,'#805500','center');
  }
  ctx.restore();
  if(view===0){
    var pxx=X(x),pyy=Y(x);
    line(pxx,pyy,pxx,250,'#a24d38',1.5);
    line(pxx,250,pxx+dx*35,250,'#a24d38',2);
  }
  text('切线斜率 = f′(x)',650,290,18,'#17202a');
  text('正：上升；负：下降；零：先检查两侧符号',650,320,17,'#41515b');
  text('位置沿曲线移动，不把导数当作运动速度',650,350,16,'#53636b');
  text('控制：x 选择位置；视图切换图像/符号带',650,380,16,'#53636b');
  var title,caption;
  if(mode==='presentation'){
    if(scene===0){
      title='切线斜率与函数走势';
      caption='切线向上时导数为正，函数递增；切线向下时导数为负，函数递减。';
    }else if(scene===1){
      title='驻点与局部极值';
      caption=atLeft?'x=-1 处切线水平，左侧导数为正、右侧为负，所以是局部极大。':atRight?'x=1 处切线水平，左侧导数为负、右侧为正，所以是局部极小。':'比较驻点两侧导数符号，才能判断局部极值。';
    }else{
      title='用符号表概括增减';
      caption='符号表把曲线分段：正号上升，负号下降，变号处可判断极值。';
    }
  }else{
    title=view===0?'导数符号与函数走势：图像探索':'导数符号带：查看增减区间';
    if(atLeft)caption='x=-1 为驻点，左侧导数为正、右侧为负，因此是局部极大。';
    else if(atRight)caption='x=1 为驻点，左侧导数为负、右侧为正，因此是局部极小。';
    else caption='当前位置 '+x.toFixed(2)+' 处函数'+trend+'；只有导数为零且两侧变号，才能判断极值。';
  }
  return {
    metrics:{x:x,f:fx,derivative:dx,view:view,stationary:stationary?1:0,atLeft:atLeft?1:0,atRight:atRight?1:0},
    controls:{x:x,view:view},
    disabled:{},
    title:title,
    caption:caption
  };
}