var XA=-3,XB=3,YA=-2,YB=2,HZ=0.22,JMIN=2,JMAXV=22.5,ZMAX=(JMAXV-JMIN)*HZ;
var C_TEXT='#1f3350',C_GRAY='#7d8ea6',C_ORANGE='#e07b1f',C_BLUE='#2f6fd0',C_PURPLE='#7b3fbf',C_RED='#cf3a2e',C_GREEN='#2f9e5f',C_AMBER='#b8860b',C_DB='#2a4a7a';
var HEAT=[[0,[126,170,222]],[0.28,[104,178,214]],[0.52,[236,208,124]],[0.76,[232,152,96]],[1,[206,94,86]]];
var DEF_ALPHA=0.20;
function clampv(v,a,b){return v<a?a:(v>b?b:v);}
function numv(v,d,a,b){var x=(typeof v==='number'&&isFinite(v))?v:d;return clampv(x,a,b);}
function Jf(x,y){return 0.5*x*x+2*y*y-x-2*y+3;}
function gradf(x,y){return [x-1,4*y-2];}
function smooth(u){u=clampv(u,0,1);return u*u*(3-2*u);}
function fd(v,d){if(!isFinite(v))return '-';if(Math.abs(v)>=1e5)return v.toExponential(1);return v.toFixed(d===undefined?2:d);}
function txt(ctx,s,x,y,size,color,bold,align){ctx.font=(bold?'bold ':'')+size+'px sans-serif';ctx.fillStyle=color;ctx.textAlign=align||'left';ctx.textBaseline='alphabetic';ctx.fillText(s,x,y);}
function heat(h){h=clampv(h,0,1);for(var i=0;i<HEAT.length-1;i++){var p=HEAT[i],q=HEAT[i+1];if(h<=q[0]){var f=(h-p[0])/(q[0]-p[0]);var r=Math.round(p[1][0]+f*(q[1][0]-p[1][0]));var g2=Math.round(p[1][1]+f*(q[1][1]-p[1][1]));var b2=Math.round(p[1][2]+f*(q[1][2]-p[1][2]));return 'rgb('+r+','+g2+','+b2+')';}}return 'rgb(206,94,86)';}
function projFn(az,el){var a=az*Math.PI/180,e=el*Math.PI/180;var ca=Math.cos(a),sa=Math.sin(a),ce=Math.cos(e),se=Math.sin(e);return function(x,y,z){var u=x*ca-y*sa,v=x*sa+y*ca;return {u:u,s:-(z*ce+v*se),d:v*ce-z*se};};}
function fitView(az,el,sample,rect,pad){var pr=projFn(az,el);var umin=1e9,umax=-1e9,smin=1e9,smax=-1e9;for(var i=0;i<sample.length;i++){var p=sample[i];var q=pr(p[0],p[1],p[2]);if(!isFinite(q.u)||!isFinite(q.s))continue;if(q.u<umin)umin=q.u;if(q.u>umax)umax=q.u;if(q.s<smin)smin=q.s;if(q.s>smax)smax=q.s;}if(umin>umax){umin=-1;umax=1;smin=-1;smax=1;}var du=Math.max(umax-umin,1e-6),ds=Math.max(smax-smin,1e-6);var S=Math.min(rect.w/du,rect.h/ds)*(pad||0.9);var ox=rect.x+rect.w/2-(umin+umax)/2*S;var oy=rect.y+rect.h/2-(smin+smax)/2*S;return {S:S,ox:ox,oy:oy,sp:function(x,y,z){var q2=pr(x,y,z);return {x:ox+q2.u*S,y:oy+q2.s*S,d:q2.d};}};}
function buildGrid(N){var g=[];for(var i=0;i<=N;i++){var x=XA+(XB-XA)*i/N;var row=[];for(var j=0;j<=N;j++){var y=YA+(YB-YA)*j/N;row.push([x,y,Jf(x,y)]);}g.push(row);}return g;}
function surfaceSample(g){var out=[];for(var i=0;i<g.length;i++){for(var j=0;j<g[i].length;j++){var p=g[i][j];out.push([p[0],p[1],(p[2]-JMIN)*HZ]);}}return out;}
function drawSurface(ctx,view,g,revealN,alpha){var N=g.length-1;var quads=[];var i,j;for(i=0;i<N&&i<revealN;i++){for(j=0;j<N;j++){var a=g[i][j],b=g[i+1][j],c=g[i+1][j+1],d=g[i][j+1];var pa=view.sp(a[0],a[1],(a[2]-JMIN)*HZ);var pb=view.sp(b[0],b[1],(b[2]-JMIN)*HZ);var pc=view.sp(c[0],c[1],(c[2]-JMIN)*HZ);var pd=view.sp(d[0],d[1],(d[2]-JMIN)*HZ);quads.push({a:pa,b:pb,c:pc,d:pd,dep:(pa.d+pb.d+pc.d+pd.d)/4,J:(a[2]+b[2]+c[2]+d[2])/4});}}quads.sort(function(A,B){return B.dep-A.dep;});ctx.globalAlpha=alpha;ctx.lineWidth=0.8;ctx.strokeStyle='rgba(255,255,255,0.5)';for(var q=0;q<quads.length;q++){var Q=quads[q];var hh=Math.sqrt(clampv((Q.J-JMIN)/(JMAXV-JMIN),0,1));ctx.fillStyle=heat(hh);ctx.beginPath();ctx.moveTo(Q.a.x,Q.a.y);ctx.lineTo(Q.b.x,Q.b.y);ctx.lineTo(Q.c.x,Q.c.y);ctx.lineTo(Q.d.x,Q.d.y);ctx.closePath();ctx.fill();ctx.stroke();}ctx.globalAlpha=1;}
function drawBaseGrid(ctx,view){ctx.strokeStyle='rgba(150,168,196,0.45)';ctx.lineWidth=1;var i;for(i=0;i<=12;i++){var x=XA+(XB-XA)*i/12;var p1=view.sp(x,YA,0),p2=view.sp(x,YB,0);ctx.beginPath();ctx.moveTo(p1.x,p1.y);ctx.lineTo(p2.x,p2.y);ctx.stroke();}for(i=0;i<=8;i++){var y=YA+(YB-YA)*i/8;var p3=view.sp(XA,y,0),p4=view.sp(XB,y,0);ctx.beginPath();ctx.moveTo(p3.x,p3.y);ctx.lineTo(p4.x,p4.y);ctx.stroke();}}
function drawAxisLabels(ctx,view){var p1=view.sp(XB+0.45,0,0);txt(ctx,'θ₁',p1.x,p1.y,18,C_TEXT,true,'left');var p2=view.sp(0,YB+0.55,0);txt(ctx,'θ₂',p2.x,p2.y,18,C_TEXT,true,'left');var p3=view.sp(XA-0.35,YA-0.35,ZMAX*0.95);txt(ctx,'J',p3.x,p3.y,18,C_TEXT,true,'center');}
function dot(ctx,x,y,r,fill,stroke){if(!isFinite(x)||!isFinite(y))return;ctx.beginPath();ctx.arc(x,y,r,0,Math.PI*2);ctx.fillStyle=fill;ctx.fill();if(stroke){ctx.strokeStyle=stroke;ctx.lineWidth=1.8;ctx.stroke();}}
function cross(ctx,x,y,r,color){if(!isFinite(x)||!isFinite(y))return;ctx.strokeStyle=color;ctx.lineWidth=3;ctx.beginPath();ctx.moveTo(x-r,y);ctx.lineTo(x+r,y);ctx.moveTo(x,y-r);ctx.lineTo(x,y+r);ctx.stroke();}
function dashLine(ctx,x1,y1,x2,y2,color,lw){if(!isFinite(x1)||!isFinite(y1)||!isFinite(x2)||!isFinite(y2))return;if(Math.abs(x1)>9000||Math.abs(x2)>9000||Math.abs(y1)>9000||Math.abs(y2)>9000)return;ctx.save();ctx.setLineDash([5,5]);ctx.strokeStyle=color;ctx.lineWidth=lw;ctx.beginPath();ctx.moveTo(x1,y1);ctx.lineTo(x2,y2);ctx.stroke();ctx.restore();}
function arrow(ctx,x1,y1,x2,y2,color,lw,hs){if(!isFinite(x1)||!isFinite(y1)||!isFinite(x2)||!isFinite(y2))return;if(Math.abs(x1)>9000||Math.abs(x2)>9000||Math.abs(y1)>9000||Math.abs(y2)>9000)return;var dx=x2-x1,dy=y2-y1;var L=Math.sqrt(dx*dx+dy*dy);if(L<1e-6)return;ctx.strokeStyle=color;ctx.lineWidth=lw;ctx.lineCap='round';ctx.beginPath();ctx.moveTo(x1,y1);ctx.lineTo(x2,y2);ctx.stroke();var ux=dx/L,uy=dy/L;var h2=Math.min(hs,L*0.7);ctx.beginPath();ctx.moveTo(x2,y2);ctx.lineTo(x2-ux*h2+uy*h2*0.6,y2-uy*h2-ux*h2*0.6);ctx.lineTo(x2-ux*h2-uy*h2*0.6,y2-uy*h2+ux*h2*0.6);ctx.closePath();ctx.fillStyle=color;ctx.fill();}
function traj(x0,y0,al,K){var pts=[[x0,y0]];var x=x0,y=y0;var f1=Math.abs(1-al),f2=Math.abs(1-4*al);var e1=x0-1,e2=y0-0.5;var act1=Math.abs(e1)>1e-7,act2=Math.abs(e2)>1e-7;var eff=0;if(act1)eff=Math.max(eff,f1);if(act2)eff=Math.max(eff,f2);var status;if(eff>1+1e-9)status='diverged';else if(eff>1-1e-9)status='critical';else status='converged';for(var k=1;k<=K;k++){var nx=x-al*(x-1),ny=y-al*(4*y-2);if(!isFinite(nx)||!isFinite(ny)){status='diverged';break;}x=nx;y=ny;pts.push([x,y]);if(Math.abs(x)>1e4||Math.abs(y)>1e4){status='diverged';break;}}if(status!=='diverged'){var lp=pts[pts.length-1];var g0=Math.sqrt(e1*e1+e2*e2);var g1=Math.sqrt((lp[0]-1)*(lp[0]-1)+(lp[1]-0.5)*(lp[1]-0.5));if(g0>1e-9&&g1>1e4*g0)status='diverged';}return {pts:pts,status:status,f1:f1,f2:f2,eff:eff,act1:act1,act2:act2};}
function statusText(s){if(s==='diverged')return '发散：误差被逐步放大';if(s==='critical')return '临界：误差不衰减';return '收敛：误差逐步衰减';}
function statusColor(s){if(s==='diverged')return C_RED;if(s==='critical')return C_AMBER;return C_GREEN;}
function drawPath(ctx,view,pts,n,color,lw,dots){var i;ctx.strokeStyle=color;ctx.lineWidth=lw;ctx.lineJoin='round';ctx.lineCap='round';ctx.beginPath();var started=false;for(i=0;i<n&&i<pts.length;i++){var q=pts[i];if(Math.abs(q[0])>25||Math.abs(q[1])>25){started=false;continue;}var s=view.sp(q[0],q[1],(Jf(q[0],q[1])-JMIN)*HZ);if(!isFinite(s.x)||!isFinite(s.y)){started=false;continue;}if(!started){ctx.moveTo(s.x,s.y);started=true;}else ctx.lineTo(s.x,s.y);}ctx.stroke();if(dots){for(i=0;i<n&&i<pts.length;i++){var q2=pts[i];if(Math.abs(q2[0])>25||Math.abs(q2[1])>25)continue;var s2=view.sp(q2[0],q2[1],(Jf(q2[0],q2[1])-JMIN)*HZ);if(!isFinite(s2.x)||!isFinite(s2.y))continue;var rr=(i%5===0)?4.5:2.6;dot(ctx,s2.x,s2.y,rr,(i===0)?C_RED:color,(i%5===0)?'#ffffff':null);}}}
function drawContours(ctx,view,levels){for(var i=0;i<levels.length;i++){var d=levels[i]-2;if(d<=0)continue;var a=Math.sqrt(2*d),b=Math.sqrt(d/2);ctx.beginPath();var seg=72;for(var k=0;k<=seg;k++){var th=k/seg*Math.PI*2;var x=1+a*Math.cos(th),y=0.5+b*Math.sin(th);var s=view.sp(x,y,0);if(k===0)ctx.moveTo(s.x,s.y);else ctx.lineTo(s.x,s.y);}ctx.closePath();ctx.fillStyle='rgba(110,165,225,0.07)';ctx.fill();ctx.strokeStyle='rgba(60,110,180,0.75)';ctx.lineWidth=2;ctx.stroke();}}
function gradArrowParam(ctx,view,x,y,scale,color,lw){var g=gradf(x,y);var gn=Math.sqrt(g[0]*g[0]+g[1]*g[1]);if(!(gn>1e-6))return 0;var L=clampv(0.10*gn,0.05,0.70)*scale;var p1=view.sp(x,y,0),p2=view.sp(x-g[0]/gn*L,y-g[1]/gn*L,0);arrow(ctx,p1.x,p1.y,p2.x,p2.y,color,lw,7);return gn;}
function factorChip(ctx,show,f1,f4){var x=740,y=86,w=186,h=50;if(show){ctx.fillStyle='rgba(255,255,255,0.95)';ctx.strokeStyle='#cfdcee';ctx.lineWidth=1;ctx.beginPath();ctx.rect(x,y,w,h);ctx.fill();ctx.stroke();txt(ctx,'|1−α| = '+fd(f1,2),x+10,y+20,16,C_BLUE,false);txt(ctx,'|1−4α| = '+fd(f4,2),x+10,y+41,16,C_PURPLE,false);}else{ctx.fillStyle='rgba(255,255,255,0.7)';ctx.strokeStyle='#e2e9f3';ctx.lineWidth=1;ctx.beginPath();ctx.rect(x,y,w,h);ctx.fill();ctx.stroke();txt(ctx,'误差因子已隐藏',x+10,y+31,15,C_GRAY,false);}}
function drawLossChart(ctx,rect,pts,showN,logScale,status){
  var vals=[];var i;
  for(i=0;i<pts.length;i++)vals.push(Jf(pts[i][0],pts[i][1]));
  var N=vals.length-1;
  var shown=Math.max(0,Math.min(showN-1,N));
  var padL=58,padR=18,padT=42,padB=42;
  var X0c=rect.x+padL,X1c=rect.x+rect.w-padR;
  var Y0c=rect.y+rect.h-padB,Y1c=rect.y+padT;
  ctx.fillStyle='#ffffff';ctx.fillRect(rect.x,rect.y,rect.w,rect.h);
  ctx.strokeStyle='#dbe4f0';ctx.lineWidth=1;ctx.strokeRect(rect.x+0.5,rect.y+0.5,rect.w-1,rect.h-1);
  txt(ctx,'损失 J(θₖ) 随步数 k 下降',rect.x+14,rect.y+26,18,C_TEXT,true);
  txt(ctx,statusText(status),X1c,rect.y+26,15,statusColor(status),false,'right');
  var mapY,ymin,ymax;
  if(logScale){
    var lo=0,hi=-1e9;
    for(i=0;i<=shown;i++){var w0=clampv(vals[i]-2,1e-12,1e6);var lv=Math.log10(w0);if(lv<lo)lo=lv;if(lv>hi)hi=lv;}
    if(hi<-1e8)hi=0;
    if(hi<lo+1)hi=lo+1;
    ymin=lo;ymax=hi;
    mapY=function(vv){var w=clampv(vv-2,1e-12,1e6);return Y0c-(Math.log10(w)-lo)/(hi-lo)*(Y0c-Y1c);};
  }else{
    var vmax=2.6;
    for(i=0;i<=shown;i++){var v2=vals[i];if(isFinite(v2)&&v2>vmax)vmax=v2;}
    ymax=Math.min(vmax*1.06,40);if(ymax<3.4)ymax=3.4;ymin=2;
    mapY=function(vv){var w=clampv(vv,ymin,ymax);return Y0c-(w-ymin)/(ymax-ymin)*(Y0c-Y1c);};
  }
  var mapX=function(k2){return N>0?X0c+(k2/N)*(X1c-X0c):X0c;};
  ctx.strokeStyle='#e6edf6';ctx.lineWidth=1;
  for(i=1;i<=4;i++){var yy=Y0c+(Y1c-Y0c)*i/5;ctx.beginPath();ctx.moveTo(X0c,yy);ctx.lineTo(X1c,yy);ctx.stroke();}
  ctx.strokeStyle='#9fb0c8';ctx.lineWidth=1.6;
  ctx.beginPath();ctx.moveTo(X0c,Y1c);ctx.lineTo(X0c,Y0c);ctx.lineTo(X1c,Y0c);ctx.stroke();
  txt(ctx,'k',(X0c+X1c)/2,Y0c+32,17,C_TEXT,false,'center');
  txt(ctx,logScale?'log₁₀(J−2)':'J(θₖ)',X0c-8,Y1c-10,15,C_TEXT,false,'right');
  var ticks=[0,Math.round(N/2),N];
  for(i=0;i<ticks.length;i++)txt(ctx,''+ticks[i],mapX(ticks[i]),Y0c+20,15,C_GRAY,false,'center');
  if(logScale){txt(ctx,fd(ymax,1),X0c-8,Y1c+4,15,C_GRAY,false,'right');txt(ctx,fd(ymin,1),X0c-8,Y0c+6,15,C_GRAY,false,'right');}
  else{txt(ctx,fd(ymax,1),X0c-8,Y1c+4,15,C_GRAY,false,'right');txt(ctx,'2',X0c-8,Y0c+6,15,C_GRAY,false,'right');ctx.save();ctx.setLineDash([6,6]);ctx.strokeStyle='rgba(123,63,191,0.8)';ctx.lineWidth=1.6;ctx.beginPath();ctx.moveTo(X0c,Y0c);ctx.lineTo(X1c,Y0c);ctx.stroke();ctx.restore();txt(ctx,'J(θ*)=2',X1c,Y0c-8,15,C_PURPLE,false,'right');}
  var col=(status==='diverged')?C_RED:C_ORANGE;
  ctx.strokeStyle=col;ctx.lineWidth=2.6;ctx.lineJoin='round';
  ctx.beginPath();var st=false;
  for(i=0;i<=shown;i++){var vv=vals[i];if(!isFinite(vv)){st=false;continue;}var px=mapX(i),py=mapY(vv);if(!isFinite(px)||!isFinite(py)){st=false;continue;}if(!st){ctx.moveTo(px,py);st=true;}else ctx.lineTo(px,py);}
  ctx.stroke();
  for(i=0;i<=shown;i++){var vv2=vals[i];if(!isFinite(vv2))continue;var px2=mapX(i),py2=mapY(vv2);if(!isFinite(px2)||!isFinite(py2))continue;dot(ctx,px2,py2,3.2,col,null);}
}
function draw(ctx,t,p){
  p=p||{};
  var alphaU=numv(p.alpha,0.20,0.01,0.60);
  var K=Math.round(numv(p.steps,40,0,100));
  var x0=numv(p.theta1_0,-2.2,-3,3);
  var y0=numv(p.theta2_0,1.6,-2,2);
  var elevC=numv(p.elev,30,5,90);
  var azimC=numv(p.azim,-35,-180,180);
  var showEig=numv(p.show_eig,1,0,1)>=0.5;
  var logScale=numv(p.log_scale,0,0,1)>=0.5;
  var durs=[15,15,18,15,15,12],TOTAL=90;
  var sec=clampv(t*TOTAL,0,TOTAL-1e-6);
  var si=0,local=0,acc=0,ii;
  for(ii=0;ii<durs.length;ii++){if(ii===durs.length-1||sec<acc+durs[ii]){si=ii;local=(sec-acc)/durs[ii];break;}acc+=durs[ii];}
  local=clampv(local,0,1);
  var dElev=elevC-30,dAz=azimC+35;
  var alpha=alphaU;
  if(si===5&&Math.abs(alphaU-DEF_ALPHA)<1e-9){var ramp=DEF_ALPHA+0.35*Math.min(1,local/0.70);if(ramp>alpha)alpha=clampv(ramp,0.01,0.60);}
  var tr=traj(x0,y0,alpha,K);
  var f1=tr.f1,f4=tr.f2,fmax=tr.eff;
  var status=tr.status;
  var shownTotal=0;
  var i,j,k;
  ctx.save();
  ctx.fillStyle='#f6f9fd';ctx.fillRect(0,0,960,540);
  ctx.textAlign='left';ctx.textBaseline='alphabetic';
  if(si===0){
    var az1=-35+dAz,el1=clampv(30+dElev,4,90);
    var g1=buildGrid(24);
    var sm1=surfaceSample(g1);
    sm1.push([XA,YA,0],[XB,YA,0],[XA,YB,0],[XB,YB,0]);
    var v1=fitView(az1,el1,sm1,{x:352,y:92,w:380,h:318},0.92);
    ctx.save();ctx.beginPath();ctx.rect(348,86,388,330);ctx.clip();
    drawBaseGrid(ctx,v1);
    var rev1=Math.max(1,Math.ceil(24*Math.min(1,local/0.32)));
    drawSurface(ctx,v1,g1,rev1,1);
    drawAxisLabels(ctx,v1);
    var qm=v1.sp(1,0.5,0);
    cross(ctx,qm.x,qm.y,10,C_PURPLE);
    txt(ctx,'θ*',qm.x+16,qm.y-12,18,C_PURPLE,true,'left');
    var zb1=(Jf(x0,y0)-JMIN)*HZ;
    var sA=v1.sp(x0,y0,zb1),sB=v1.sp(x0,y0,0);
    dashLine(ctx,sA.x,sA.y,sB.x,sB.y,'rgba(190,70,55,0.85)',1.6);
    dot(ctx,sA.x,sA.y,7,C_RED,'#ffffff');
    txt(ctx,'P₀',sA.x+16,sA.y-10,18,C_RED,true,'left');
    ctx.restore();
    txt(ctx,'把损失想成地形',45,114,22,C_TEXT,true);
    txt(ctx,'参数 θ₁、θ₂ 是地图坐标，',45,152,17,C_TEXT);
    txt(ctx,'损失 J(θ) 是海拔高度，',45,178,17,C_TEXT);
    txt(ctx,'J = 0.5θ₁² + 2θ₂² − θ₁ − 2θ₂ + 3',45,214,17,C_DB);
    txt(ctx,'A = diag(1,4)，b = (1,2)ᵀ，c = 3',45,240,17,C_DB);
    txt(ctx,'θ* = (1, 0.5)，J(θ*) = 2',45,266,17,C_PURPLE);
    txt(ctx,'函数固定：无曲率比与函数切换',45,296,17,C_GRAY);
    txt(ctx,'低处偏蓝，高处偏暖',45,322,17,C_GRAY);
    txt(ctx,'红点：初值 P₀',760,158,16,C_TEXT);
    txt(ctx,'紫十字：最低点',760,182,16,C_TEXT);
    txt(ctx,'颜色：高度分层',760,206,16,C_TEXT);
    txt(ctx,'25×25 网格',760,230,16,C_GRAY);
  }else if(si===1){
    var az2=-32+dAz,el2=clampv(32+dElev,4,90);
    var g2=buildGrid(20);
    var sm2=surfaceSample(g2);
    sm2.push([XA,YA,0],[XB,YA,0],[XA,YB,0],[XB,YB,0]);
    var v2b=fitView(az2,el2,sm2,{x:345,y:92,w:390,h:318},0.92);
    var zb2=(Jf(x0,y0)-JMIN)*HZ;
    var anchor=v2b.sp(x0,y0,zb2);
    var ZK=1.5,CXZ=600,CYZ=250;
    var v2={sp:function(x,y,z){var q=v2b.sp(x,y,z);return {x:CXZ+(q.x-anchor.x)*ZK,y:CYZ+(q.y-anchor.y)*ZK,d:q.d};}};
    ctx.save();ctx.beginPath();ctx.rect(330,86,406,330);ctx.clip();
    drawBaseGrid(ctx,v2);
    drawSurface(ctx,v2,g2,20,0.8);
    var gx0=x0-1,gy0=4*y0-2;
    var gn0=Math.sqrt(gx0*gx0+gy0*gy0);
    var x1=x0-alpha*gx0,y1=y0-alpha*gy0;
    var zb3=(Jf(x1,y1)-JMIN)*HZ;
    var bp0=v2.sp(x0,y0,0),bp1=v2.sp(x1,y1,0);
    var sp0=v2.sp(x0,y0,zb2),sp1=v2.sp(x1,y1,zb3);
    dashLine(ctx,sp0.x,sp0.y,bp0.x,bp0.y,'rgba(120,140,170,0.9)',1.4);
    dashLine(ctx,sp1.x,sp1.y,bp1.x,bp1.y,'rgba(120,140,170,0.9)',1.4);
    arrow(ctx,bp0.x,bp0.y,bp1.x,bp1.y,C_BLUE,3,12);
    arrow(ctx,sp0.x,sp0.y,sp1.x,sp1.y,'#1f57b8',3,12);
    dot(ctx,sp0.x,sp0.y,7,C_RED,'#ffffff');
    dot(ctx,sp1.x,sp1.y,7,C_GREEN,'#ffffff');
    txt(ctx,'P₀',sp0.x+14,sp0.y-10,18,C_RED,true,'left');
    txt(ctx,'P₁',sp1.x+14,sp1.y-10,18,C_GREEN,true,'left');
    ctx.restore();
    txt(ctx,'一步到底走多远',45,114,22,C_TEXT,true);
    txt(ctx,'θₖ₊₁ = θₖ − α∇J(θₖ)',45,154,19,C_DB);
    txt(ctx,'∇J(θ) = (θ₁−1, 4θ₂−2)',45,184,17,C_DB);
    txt(ctx,'α = '+fd(alpha,2),45,216,17,C_TEXT);
    txt(ctx,'∇J(θ₀) = ('+fd(gx0,2)+', '+fd(gy0,2)+')',45,242,17,C_TEXT);
    txt(ctx,'‖∇J(θ₀)‖ = '+fd(gn0,3),45,268,17,C_TEXT);
    txt(ctx,'平面位移 α‖∇J‖ = '+fd(alpha*gn0,3),45,294,17,C_ORANGE);
    txt(ctx,'初值 P₀ = ('+fd(x0,2)+', '+fd(y0,2)+')',45,320,17,C_GRAY);
    txt(ctx,'蓝箭头：−α∇J 的实际位移',45,356,17,C_BLUE);
    txt(ctx,'α < 2/λmax = 0.5 时收敛',45,382,17,statusColor(status));
    txt(ctx,'一步：θ₀→θ₁',760,170,16,C_TEXT);
    txt(ctx,'α 越大，位移越大',760,196,16,C_TEXT);
    txt(ctx,'新点 P₁ 在曲面上',760,222,16,C_GRAY);
  }else if(si===2){
    var az3=-35+dAz,el3=clampv(30+dElev,4,90);
    var g3=buildGrid(24);
    var sm3=surfaceSample(g3);
    sm3.push([XA,YA,0],[XB,YA,0],[XA,YB,0],[XB,YB,0]);
    var v3=fitView(az3,el3,sm3,{x:352,y:92,w:376,h:318},0.92);
    ctx.save();ctx.beginPath();ctx.rect(348,86,384,330);ctx.clip();
    drawBaseGrid(ctx,v3);
    drawSurface(ctx,v3,g3,24,1);
    drawAxisLabels(ctx,v3);
    var total3=tr.pts.length;
    var rv=smooth(clampv(local/0.80,0,1));
    var show3=Math.max(1,Math.min(total3,Math.ceil(rv*total3)));
    shownTotal=show3-1;
    var isDiv=(status==='diverged');
    var cTraj=isDiv?C_RED:C_ORANGE;
    for(k=0;k<show3;k+=5){var q3=tr.pts[k];if(Math.abs(q3[0])>20||Math.abs(q3[1])>20)continue;var u3=v3.sp(q3[0],q3[1],(Jf(q3[0],q3[1])-JMIN)*HZ);var w3=v3.sp(q3[0],q3[1],0);dashLine(ctx,u3.x,u3.y,w3.x,w3.y,'rgba(150,125,190,0.6)',1.2);}
    drawPath(ctx,v3,tr.pts,show3,cTraj,3.2,true);
    for(k=0;k+1<show3;k+=4){var qa=tr.pts[k],qb=tr.pts[k+1];if(Math.abs(qa[0])>20||Math.abs(qa[1])>20||Math.abs(qb[0])>20||Math.abs(qb[1])>20)continue;var sa=v3.sp(qa[0],qa[1],(Jf(qa[0],qa[1])-JMIN)*HZ);var sb=v3.sp(qb[0],qb[1],(Jf(qb[0],qb[1])-JMIN)*HZ);var dx=sb.x-sa.x,dy=sb.y-sa.y,L=Math.sqrt(dx*dx+dy*dy);if(L>3){var ux=dx/L,uy=dy/L;var len=Math.min(L*2.0,40);arrow(ctx,sa.x,sa.y,sa.x+ux*len,sa.y+uy*len,C_BLUE,2.4,8);}}
    ctx.restore();
    var qk=tr.pts[Math.min(show3-1,tr.pts.length-1)];
    var gnk=Math.sqrt((qk[0]-1)*(qk[0]-1)+(4*qk[1]-2)*(4*qk[1]-2));
    txt(ctx,'真实的下降轨迹',45,114,22,C_TEXT,true);
    txt(ctx,'θₖ₊₁ = θₖ − α∇J(θₖ)',45,152,19,C_DB);
    txt(ctx,'α = '+fd(alpha,2)+'，K = '+K,45,184,17,C_TEXT);
    txt(ctx,'已显示 '+(show3-1)+' 步',45,210,17,C_TEXT);
    txt(ctx,'J(θₖ) = '+fd(Jf(qk[0],qk[1]),2),45,236,17,C_TEXT);
    txt(ctx,'‖∇J(θₖ)‖ = '+fd(gnk,2),45,262,17,C_TEXT);
    txt(ctx,'max|1−αλ| = '+fd(fmax,2),45,294,17,statusColor(status));
    txt(ctx,statusText(status),45,320,17,statusColor(status));
    txt(ctx,'橙色：真实折线',760,170,16,C_ORANGE);
    txt(ctx,'蓝箭头：负梯度',760,196,16,C_BLUE);
    txt(ctx,'梯度变小，步长变短',760,224,16,C_TEXT);
  }else if(si===3){
    var u4=smooth(clampv(local/0.45,0,1));
    var az4=-35+dAz;
    var el4=clampv(30+58*u4+dElev,4,90);
    var LEV=[2.4,3.2,4.4,6.2,8.8,12.4];
    var dmax=LEV[LEV.length-1]-2;
    var amax=Math.sqrt(2*dmax),bmax=Math.sqrt(dmax/2);
    var sm4=[];
    for(k=0;k<=40;k++){var th=k/40*Math.PI*2;sm4.push([1+amax*Math.cos(th),0.5+bmax*Math.sin(th),0]);}
    var g4=buildGrid(12);
    var s4b=surfaceSample(g4);
    for(k=0;k<s4b.length;k++)sm4.push(s4b[k]);
    for(k=0;k<tr.pts.length;k++){var tp=tr.pts[k];if(Math.abs(tp[0])<12&&Math.abs(tp[1])<12)sm4.push([tp[0],tp[1],0]);}
    var v4=fitView(az4,el4,sm4,{x:352,y:92,w:376,h:318},0.92);
    ctx.save();ctx.beginPath();ctx.rect(348,86,384,330);ctx.clip();
    drawContours(ctx,v4,LEV);
    var sAlpha=1-u4;
    if(sAlpha>0.02)drawSurface(ctx,v4,g4,12,sAlpha);
    var show4=Math.min(tr.pts.length,K+1);
    shownTotal=show4-1;
    var isDiv4=(status==='diverged');
    drawPath(ctx,v4,tr.pts,show4,isDiv4?C_RED:C_ORANGE,3.2,false);
    if(u4>0.30){
      ctx.globalAlpha=clampv((u4-0.30)/0.40,0,1);
      var stp=Math.max(1,Math.floor(show4/12));
      for(k=0;k<show4;k+=stp){var q4=tr.pts[k];if(Math.abs(q4[0])>12||Math.abs(q4[1])>12)continue;gradArrowParam(ctx,v4,q4[0],q4[1],1,C_BLUE,2.4);}
      ctx.globalAlpha=1;
    }
    var qc4=v4.sp(1,0.5,0);
    dot(ctx,qc4.x,qc4.y,6,C_PURPLE,'#ffffff');
    if(showEig){
      var e1a=v4.sp(-3.5,0.5,0),e1b=v4.sp(5.5,0.5,0);
      var e2a=v4.sp(1,-2.5,0),e2b=v4.sp(1,3.5,0);
      ctx.save();ctx.setLineDash([8,6]);ctx.strokeStyle=C_PURPLE;ctx.lineWidth=2.2;
      ctx.beginPath();ctx.moveTo(e1a.x,e1a.y);ctx.lineTo(e1b.x,e1b.y);ctx.stroke();
      ctx.beginPath();ctx.moveTo(e2a.x,e2a.y);ctx.lineTo(e2b.x,e2b.y);ctx.stroke();
      ctx.restore();
      txt(ctx,'θ₁ 方向 λ₁=1',e1b.x+6,e1b.y+4,15,C_PURPLE);
      txt(ctx,'θ₂ 方向 λ₂=4',e2b.x+6,e2b.y-6,15,C_PURPLE);
    }
    ctx.restore();
    var stLine;
    if(fmax>1+1e-9)stLine=' > 1：发散';else if(fmax>1-1e-9)stLine=' = 1：不衰减';else stLine=' < 1：收敛';
    var noteEig='';
    if(!tr.act1)noteEig='θ₁ 方向误差为 0，不参与判定';
    else if(!tr.act2)noteEig='θ₂ 方向误差为 0，不参与判定';
    txt(ctx,'俯视：等高线与特征方向',45,114,22,C_TEXT,true);
    txt(ctx,'等高线 短轴:长轴 = 1:2',45,150,16,C_GRAY);
    txt(ctx,'|1−α| = '+fd(f1,2)+'（λ₁=1）',45,182,16,C_BLUE);
    txt(ctx,'|1−4α| = '+fd(f4,2)+'（λ₂=4）',45,208,16,C_PURPLE);
    txt(ctx,'控制因子 = '+fd(fmax,2)+stLine,45,240,16,statusColor(status));
    txt(ctx,'负梯度与等高线处处垂直',45,272,16,C_TEXT);
    txt(ctx,showEig?'特征方向：已显示':'特征方向：已隐藏',45,298,16,C_GRAY);
    txt(ctx,noteEig,45,324,15,C_AMBER);
    txt(ctx,'橙色：轨迹投影',760,170,16,C_ORANGE);
    txt(ctx,'蓝箭头：−∇J 方向',760,196,16,C_BLUE);
    txt(ctx,'箭头越长，梯度越大',760,222,16,C_TEXT);
  }else if(si===4){
    var az5=-35+dAz,el5=clampv(30+dElev,4,90);
    var g5=buildGrid(20);
    var sm5=surfaceSample(g5);
    sm5.push([XA,YA,0],[XB,YA,0],[XA,YB,0],[XB,YB,0]);
    var v5=fitView(az5,el5,sm5,{x:40,y:148,w:400,h:232},0.92);
    ctx.save();ctx.beginPath();ctx.rect(38,146,404,236);ctx.clip();
    drawBaseGrid(ctx,v5);
    drawSurface(ctx,v5,g5,20,1);
    var show5=Math.min(tr.pts.length,K+1);
    shownTotal=show5-1;
    drawPath(ctx,v5,tr.pts,show5,status==='diverged'?C_RED:C_ORANGE,3.0,true);
    var qc5=v5.sp(1,0.5,0);
    cross(ctx,qc5.x,qc5.y,8,C_PURPLE);
    ctx.restore();
    txt(ctx,'损失随步数下降',45,110,21,C_TEXT,true);
    txt(ctx,'α = '+fd(alpha,2)+'，K = '+K+'，已显示 '+(show5-1)+' 步',45,396,16,C_TEXT);
    var qk5=tr.pts[show5-1];
    txt(ctx,'J(θₖ) = '+fd(Jf(qk5[0],qk5[1]),3),45,418,16,C_TEXT);
    drawLossChart(ctx,{x:495,y:148,w:430,h:232},tr.pts,K+1,logScale,status);
    txt(ctx,'纵轴：'+(logScale?'对数刻度':'线性刻度')+'（整数开关切换）',495,396,16,C_GRAY);
    txt(ctx,'橙色曲线逐步贴近 J(θ*)=2',495,418,16,C_GRAY);
  }else{
    var LEV6=[2.4,3.2,4.4,6.2,8.8,12.4];
    var dmax6=LEV6[LEV6.length-1]-2;
    var amax6=Math.sqrt(2*dmax6),bmax6=Math.sqrt(dmax6/2);
    var sm6=[];
    for(k=0;k<=40;k++){var th6=k/40*Math.PI*2;sm6.push([1+amax6*Math.cos(th6),0.5+bmax6*Math.sin(th6),0]);}
    sm6.push([x0,y0,0]);
    var el6=clampv(88+dElev,4,90);
    var az6=-35+dAz;
    var v6=fitView(az6,el6,sm6,{x:40,y:148,w:400,h:232},0.92);
    ctx.save();ctx.beginPath();ctx.rect(38,146,404,236);ctx.clip();
    drawContours(ctx,v6,LEV6);
    var show6=Math.min(tr.pts.length,61);
    shownTotal=show6-1;
    drawPath(ctx,v6,tr.pts,show6,status==='diverged'?C_RED:C_ORANGE,3.2,true);
    var c6=v6.sp(1,0.5,0);
    cross(ctx,c6.x,c6.y,8,C_PURPLE);
    if(status==='diverged'){
      ctx.fillStyle='rgba(207,58,46,0.14)';ctx.fillRect(110,286,260,46);
      txt(ctx,'发散',128,318,26,C_RED,true);
      txt(ctx,'|1−4α| = '+fd(f4,2)+' > 1',200,318,18,C_RED,true);
    }else if(status==='critical'){
      ctx.fillStyle='rgba(184,134,11,0.16)';ctx.fillRect(85,286,290,46);
      txt(ctx,'临界：误差不衰减',105,318,20,C_AMBER,true);
    }
    ctx.restore();
    var qk6=tr.pts[show6-1];
    txt(ctx,'越过阈值：临界与发散',45,110,21,C_TEXT,true);
    txt(ctx,'α = '+fd(alpha,2),310,110,21,(status==='diverged')?C_RED:(status==='critical'?C_AMBER:C_GREEN),true);
    txt(ctx,'θₖ₊₁ = θₖ − α∇J(θₖ)',45,396,16,C_DB);
    txt(ctx,'|1−4α| = '+fd(f4,2),45,418,16,(status==='converged')?C_TEXT:(status==='critical'?C_AMBER:C_RED));
    txt(ctx,'J(θₖ) = '+fd(Jf(qk6[0],qk6[1]),3),250,418,16,C_TEXT);
    drawLossChart(ctx,{x:495,y:148,w:430,h:232},tr.pts,show6,logScale,status);
    if(status==='diverged'){
      txt(ctx,'发散：|1−4α| = '+fd(f4,2)+' > 1',495,396,16,C_RED);
      txt(ctx,'轨迹飞出画面，损失上升',495,418,16,C_RED);
    }else if(status==='critical'){
      txt(ctx,'临界：|1−4α| = 1，误差不衰减',495,396,16,C_AMBER);
      txt(ctx,'振幅不变，不收敛到 θ*',495,418,16,C_AMBER);
    }else{
      txt(ctx,'安全区：0 < α < 0.5',495,396,16,C_GREEN);
      txt(ctx,'α > 0.5 时轨迹变红并飞出画面',495,418,16,C_GRAY);
    }
  }
  factorChip(ctx,showEig,f1,f4);
  ctx.restore();
  var lastP=tr.pts[tr.pts.length-1];
  var xf=clampv(lastP[0],-1e4,1e4);
  var yf=clampv(lastP[1],-1e4,1e4);
  var Jfin=clampv(Jf(xf,yf),-1e12,1e12);
  if(!isFinite(Jfin))Jfin=0;
  return {metrics:{
    scene:si+1,
    time_sec:Math.round(sec*100)/100,
    alpha:Math.round(alpha*1000)/1000,
    steps_K:K,
    steps_shown:shownTotal,
    theta1_final:Math.round(xf*1e4)/1e4,
    theta2_final:Math.round(yf*1e4)/1e4,
    J_final:Math.round(Jfin*1e4)/1e4,
    factor_theta1:Math.round(f1*1e4)/1e4,
    factor_theta2:Math.round(f4*1e4)/1e4,
    max_factor:Math.round(fmax*1e4)/1e4,
    status:status,
    theta_star_J:2
  }};
}