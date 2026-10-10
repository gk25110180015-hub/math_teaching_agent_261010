
function draw(ctx,t,p) {
 const cubic=p.curve>0.5, f=x=>cubic?Math.sin(x):x*x, df=x=>cubic?Math.cos(x):2*x;
 const x=p.x0, h=p.hstart*Math.pow(0.001,Math.max(0,(t-.2)/.8));
 const slope=(f(x+h)-f(x))/h, exact=df(x);
 const X=x=>290+x*88, Y=y=>365-y*48;
 const line=(a,b,c,d,color,w=2)=>{ctx.strokeStyle=color;ctx.lineWidth=w;ctx.beginPath();ctx.moveTo(a,b);ctx.lineTo(c,d);ctx.stroke();};
 const point=(x,y,color)=>{ctx.fillStyle=color;ctx.beginPath();ctx.arc(X(x),Y(y),6,0,7);ctx.fill();};
 ctx.fillStyle='#f7f9fc';ctx.fillRect(0,0,960,540);
 for(let i=-2;i<=3;i++)line(X(i),95,X(i),410,'#e1e7ef',1);
 line(55,Y(0),555,Y(0),'#91a0b3');line(X(0),90,X(0),413,'#91a0b3');
 ctx.strokeStyle='#4664d8';ctx.lineWidth=3;ctx.beginPath();
 for(let i=0;i<=200;i++){const q=-2.5+i/40;const px=X(q),py=Y(f(q));i?ctx.lineTo(px,py):ctx.moveTo(px,py);}ctx.stroke();
 const a=x-.95,b=x+1.5;
 line(X(a),Y(f(x)+exact*(a-x)),X(b),Y(f(x)+exact*(b-x)),'#7e61b8',3);
 line(X(a),Y(f(x)+slope*(a-x)),X(b),Y(f(x)+slope*(b-x)),'#db742a',3);
 point(x,f(x),'#4664d8');point(x+h,f(x+h),'#db742a');
 ctx.font='18px sans-serif';ctx.fillStyle='#213750';ctx.fillText(cubic?'f(x) = sin(x)':'f(x) = x²',65,103);
 ctx.fillText('x',540,Y(0)-10);ctx.fillText('f(x)',X(0)+9,92);
 ctx.fillText('P',X(x)-18,Y(f(x))-12);ctx.fillText('Q',X(x+h)+10,Y(f(x+h))-10);
 ctx.font='21px sans-serif';ctx.fillText('差商 → 导数',610,125);
 ctx.font='18px sans-serif';ctx.fillText('h = '+h.toFixed(5),610,169);
 ctx.fillStyle='#db742a';ctx.fillText('割线斜率 = '+slope.toFixed(5),610,207);
 ctx.fillStyle='#7e61b8';ctx.fillText('切线斜率 = '+exact.toFixed(5),610,245);
 ctx.fillStyle='#213750';ctx.fillText('|误差| = '+Math.abs(slope-exact).toFixed(5),610,283);
 ctx.fillText('[f(x₀+h) − f(x₀)] / h',610,335);
 line(615,391,615+Math.min(260,Math.abs(slope-exact)*160),391,'#db742a',9);
 return {metrics:{h,slope,derivative:exact,error:Math.abs(slope-exact),x0:x}};
}
