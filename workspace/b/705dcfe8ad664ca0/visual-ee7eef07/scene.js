function draw(ctx,t,p){
  var W=960,H=540,mode=p&&p.$mode==='explore'?'explore':'presentation';
  var D={eta:{min:.1,max:6,step:.1,value:1.5},x0:{min:-6,max:6,step:.1,value:5},y0:{min:-6,max:6,step:.1,value:4},arrows:{min:0,max:1,step:1,value:1},contours:{min:0,max:1,step:1,value:1},func:{min:0,max:1,step:1,value:0}};
  function get(id){var v=Number(p&&p[id]);return isFinite(v)?Math.max(D[id].min,Math.min(D[id].max,v)):D[id].value}
  var eta=get('eta'),x0=get('x0'),y0=get('y0'),ar=get('arrows')>=.5,co=get('contours')>=.5,fn=get('func')>=.5;
  var scene=0,local=t;
  if(mode==='presentation'){
    var s=t*39;
    if(s<8){scene=0;local=s/8;eta=1.5;x0=5;y0=4}
    else if(s<17){scene=1;local=(s-8)/9;eta=1.5;x0=5;y0=4}
    else if(s<29){scene=2;local=(s-17)/12;eta=1.5;x0=5;y0=4}
    else{scene=3;local=(s-29)/10;x0=5;y0=4}
    ar=true;co=true;
  }
  var a=fn?.18:.08,b=.18;
  function f(x,y){return a*x*x+b*y*y}
  function gx(x){return 2*a*x} function gy(y){return 2*b*y}
  function makePath(e,n){var q=[],x=x0,y=y0;q.push([x,y,f(x,y)]);for(var k=0;k<n;k++){x=x-e*gx(x);y=y-e*gy(y);q.push([x,y,f(x,y)])}return q}
  var steps=mode==='presentation'?(scene<2?0:scene===2?Math.floor(local*18):Math.floor(local*18)):Math.floor(t*18);
  var cases=[],selected=0;
  if(scene===3&&mode==='presentation'){
    cases=[makePath(.3,Math.floor(local*18)),makePath(1.5,Math.floor(local*18)),makePath(5.5,Math.floor(local*18))];
    selected=local<.34?0:local<.67?1:2;eta=[.3,1.5,5.5][selected];
  }else{cases=[makePath(eta,steps)]}
  var main=cases[selected]||cases[0],R=6,Z=Math.max(1,f(6,6));
  for(var ci=0;ci<cases.length;ci++)for(var qi=0;qi<cases[ci].length;qi++){R=Math.max(R,Math.abs(cases[ci][qi][0]),Math.abs(cases[ci][qi][1]));Z=Math.max(Z,cases[ci][qi][2])}
  function P(x,y,z){return [350+37*(x-y)/R,285+18*(x+y)/R-105*z/Z]}
  function line(x1,y1,x2,y2,c,w){ctx.strokeStyle=c;ctx.lineWidth=w||1.5;ctx.beginPath();ctx.moveTo(x1,y1);ctx.lineTo(x2,y2);ctx.stroke()}
  function text(s,x,y,n,c){ctx.fillStyle=c||'#26364a';ctx.font=(n||17)+'px sans-serif';ctx.fillText(s,x,y)}
  function arrow(x1,y1,x2,y2,c){line(x1,y1,x2,y2,c,2.5);var q=Math.atan2(y2-y1,x2-x1),l=8;line(x2,y2,x2-l*Math.cos(q-.5),y2-l*Math.sin(q-.5),c,2);line(x2,y2,x2-l*Math.cos(q+.5),y2-l*Math.sin(q+.5),c,2)}
  ctx.fillStyle='#f7f9fc';ctx.fillRect(0,0,W,H);ctx.save();ctx.beginPath();ctx.rect(35,85,890,335);ctx.clip();
  text('z=f(x,y) 的透视投影',50,108,18,'#38506b');
  for(var i=-6;i<=6;i++){var last=null;for(var j=-6;j<=6;j++){var pp=P(i,j,f(i,j));if(last)line(last[0],last[1],pp[0],pp[1],'#b8d5df',1);last=pp}}
  for(var j=-6;j<=6;j++){var last2=null;for(var i=-6;i<=6;i++){var pp2=P(i,j,f(i,j));if(last2)line(last2[0],last2[1],pp2[0],pp2[1],'#b8d5df',1);last2=pp2}}
  var org=P(0,0,0);ctx.fillStyle='#176b58';ctx.beginPath();ctx.arc(org[0],org[1],5,0,Math.PI*2);ctx.fill();text('最优点 (0,0)',org[0]+8,org[1]-8,16,'#176b58');
  if(co){for(var lev=1;lev<=5;lev++){var c=lev;ctx.beginPath();for(var u=0;u<=Math.PI*2+.01;u+=.1){var xx=Math.sqrt(c/a)*Math.cos(u),yy=Math.sqrt(c/b)*Math.sin(u),qq=P(xx,yy,0);if(u===0)ctx.moveTo(qq[0],qq[1]);else ctx.lineTo(qq[0],qq[1])}ctx.strokeStyle='#d4a34e';ctx.lineWidth=1;ctx.stroke()}}
  if(scene===1){var tc=main[main.length-1],tx=tc[0],ty=tc[1],tz=f(tx,ty);for(var qx=-1.5;qx<=1.5;qx+=.5){var ppA=P(tx+qx,ty-1.5,tz+gx(tx)*qx+gy(ty)*-1.5),ppB=P(tx+qx,ty+1.5,tz+gx(tx)*qx+gy(ty)*1.5);line(ppA[0],ppA[1],ppB[0],ppB[1],'#9b78c5',1)}for(var qy=-1.5;qy<=1.5;qy+=.5){var ppC=P(tx-1.5,ty+qy,tz+gx(tx)*-1.5+gy(ty)*qy),ppD=P(tx+1.5,ty+qy,tz+gx(tx)*1.5+gy(ty)*qy);line(ppC[0],ppC[1],ppD[0],ppD[1],'#9b78c5',1)}text('局部切平面 z≈f+∇f·Δθ',70,132,16,'#76549d')}
  for(var cc=0;cc<cases.length;cc++){var pa=cases[cc],col=cases.length>1?['#3778c2','#e37b35','#c34e72'][cc]:'#2878bd';ctx.beginPath();for(var k=0;k<pa.length;k++){var q=P(pa[k][0],pa[k][1],pa[k][2]);if(k===0)ctx.moveTo(q[0],q[1]);else ctx.lineTo(q[0],q[1])}ctx.strokeStyle=col;ctx.lineWidth=cc===selected?3.5:2;ctx.stroke();for(var m=0;m<pa.length;m+=Math.max(1,Math.floor(pa.length/9))){var zq=P(pa[m][0],pa[m][1],pa[m][2]);ctx.fillStyle=col;ctx.beginPath();ctx.arc(zq[0],zq[1],3,0,Math.PI*2);ctx.fill()}}
  var cur=main[main.length-1],cp=P(cur[0],cur[1],cur[2]);ctx.fillStyle='#e34d4d';ctx.beginPath();ctx.arc(cp[0],cp[1],6,0,Math.PI*2);ctx.fill();text('当前点',cp[0]+8,cp[1]-8,16,'#b23b3b');
  if(ar){var sc=35/R,ux=cur[0]+gx(cur[0])/Math.max(.01,sc),uy=cur[1]+gy(cur[1])/Math.max(.01,sc),dx=cur[0]-gx(cur[0])/Math.max(.01,sc),dy=cur[1]-gy(cur[1])/Math.max(.01,sc),up=P(ux,uy,cur[2]),dn=P(dx,dy,cur[2]);arrow(cp[0],cp[1],up[0],up[1],'#d94a4a');arrow(cp[0],cp[1],dn[0],dn[1],'#238b68');text('∇f',up[0]+5,up[1],16,'#b23b3b');text('−∇f',dn[0]+5,dn[1],16,'#167452')}
  if(scene===3){var bx=675,by=120,bw=220,bh=145;ctx.strokeStyle='#9aaabd';ctx.strokeRect(bx,by,bw,bh);text('函数值序列 f(θₖ)',bx+10,by+22,17,'#38506b');var maxF=1;for(var zc=0;zc<cases.length;zc++)for(var zz=0;zz<cases[zc].length;zz++)maxF=Math.max(maxF,cases[zc][zz][2]);for(var zc=0;zc<cases.length;zc++){var pp=cases[zc];ctx.beginPath();for(var zi=0;zi<pp.length;zi++){var X=bx+10+zi*200/18,Y=by+125-105*pp[zi][2]/maxF;if(zi===0)ctx.moveTo(X,Y);else ctx.lineTo(X,Y)}ctx.strokeStyle=['#3778c2','#e37b35','#c34e72'][zc];ctx.lineWidth=zc===selected?3:1.5;ctx.stroke()}text('蓝 η=.3  橙 η=1.5  紫 η=5.5',bx+10,by+142,14,'#526579')}
  ctx.restore();
  var xv=cur[0],yv=cur[1],fv=f(xv,yv),gxx=gx(xv),gyy=gy(yv),gn=Math.sqrt(gxx*gxx+gyy*gyy),nextx=xv-eta*gxx,nexty=yv-eta*gyy,df=f(nextx,nexty)-fv;
  text('当前点 ('+xv.toFixed(2)+', '+yv.toFixed(2)+')   f='+fv.toFixed(3)+'   ||∇f||='+gn.toFixed(3),55,395,17,'#26364a');
  text('η='+eta.toFixed(2)+'   Δf(下一步)='+df.toFixed(3)+'   稳定边界 η<5.56',55,418,16,df<=0?'#237653':'#b23b3b');
  var title,caption;
  if(scene===0){title='目标函数变成三维曲面';caption='把待最小化的函数看成一座山谷，最低处就是最优解。'}
  else if(scene===1){title='梯度与最陡上升方向';caption='梯度指向上升最快方向；切平面给出局部线性近似，下降应沿负梯度。'}
  else if(scene===2){title='真实迭代轨迹';caption='每一步都把当前位置代入真实梯度，轨迹由递推公式生成，而不是预设直线。'}
  else{title='收敛与学习率对比';caption=eta===5.5?'η=5.5 接近稳定边界，轨迹交替振荡；函数值序列仍由真实更新计算。':'比较 η=0.3、1.5、5.5 的真实轨迹与函数值序列。'}
  if(mode==='explore'){title=fn?'各向同性二次碗面中的梯度下降':'各向异性二次碗面中的梯度下降';caption=eta>=5.56?'当前学习率达到或超过稳定边界，目标值可能上升或发散。':'当前轨迹由真实更新 θₖ₊₁=θₖ−η∇f(θₖ) 生成。'}
  return {metrics:{x:xv,y:yv,f:fv,gradient_norm:gn,step_count:main.length-1,delta_f_next:df,stable_boundary:2/(2*b),formula:fn?'f=0.18x²+0.18y²':'f=0.08x²+0.18y²'},controls:{eta:eta,x0:x0,y0:y0,arrows:ar?1:0,contours:co?1:0,func:fn?1:0},disabled:{},title:title,caption:caption};
}