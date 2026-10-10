
function draw(ctx,t,p) {
 const f=(x,y)=>(p.curvature*x*x+y*y)/2;
 const angle=p.angle,ca=Math.cos(angle),sa=Math.sin(angle);
 const project=(x,y,z)=>[360+53*(ca*x-sa*y),325+21*(sa*x+ca*y)-25*z];
 const line=(a,b,color,width=1)=>{ctx.strokeStyle=color;ctx.lineWidth=width;ctx.beginPath();ctx.moveTo(...a);ctx.lineTo(...b);ctx.stroke();};
 ctx.fillStyle='#f7f9fc';ctx.fillRect(0,0,960,540);
 for(let i=-12;i<=12;i++)for(let j=-12;j<12;j++){
   let x=i/5,y=j/5;
   line(project(x,y,f(x,y)),project(x,y+.2,f(x,y+.2)),'#b5c8e4');
   line(project(y,x,f(y,x)),project(y+.2,x,f(y+.2,x)),'#b5c8e4');
 }
 line(project(-3,0,0),project(3,0,0),'#69819d',2);line(project(0,-3,0),project(0,3,0),'#69819d',2);
 ctx.font='17px sans-serif';ctx.fillStyle='#1d3651';ctx.fillText('x',...project(3,0,0));ctx.fillText('y',...project(0,3,0));
 let x=p.start,y=1.6,previous=project(x,y,f(x,y));const steps=Math.floor(t*36);
 for(let k=0;k<steps;k++){
   x-=p.alpha*p.curvature*x;y-=p.alpha*y;const next=project(x,y,f(x,y));line(previous,next,'#dd7427',3);previous=next;
 }
 const z=f(x,y),xy=project(x,y,z),min=project(0,0,0);
 ctx.fillStyle='#6a56b3';ctx.beginPath();ctx.arc(...min,6,0,7);ctx.fill();
 ctx.fillStyle='#dd7427';ctx.beginPath();ctx.arc(...xy,7,0,7);ctx.fill();
 ctx.font='19px sans-serif';ctx.fillStyle='#203853';ctx.fillText('三维目标曲面与下降轨迹',50,104);
 ctx.fillText('f(x,y) = ('+p.curvature.toFixed(1)+'x² + y²) / 2',595,144);
 ctx.fillText('第 '+steps+' 步 · α = '+p.alpha.toFixed(2),595,190);
 ctx.fillText('x = '+x.toFixed(5)+'   y = '+y.toFixed(5),595,234);
 ctx.fillText('f(x,y) = '+z.toFixed(7),595,278);
 ctx.fillText('∇f = (a·x, y)',595,326);
 ctx.fillText('xₖ₊₁ = xₖ − α∇f(xₖ)',595,365);
 ctx.font='17px sans-serif';ctx.fillText('紫色：极小值点 (0,0,0)',595,405);
 const scenes=[{"id": "S1", "math": "∇f=(a x,y)，a∈[1,2]。", "narration": "绘出 f(x,y)=(a x²+y²)/2 的三维网格曲面及初始点。", "seconds": 5, "title": "认识三维目标曲面", "visual": "绘出 f(x,y)=(a x²+y²)/2 的三维网格曲面及初始点。"}, {"id": "S2", "math": "(x,y)←(x,y)−α(a x,y)。", "narration": "依照负梯度迭代，橙色路径位于目标曲面上。", "seconds": 5, "title": "沿负梯度逐步更新", "visual": "依照负梯度迭代，橙色路径位于目标曲面上。"}, {"id": "S3", "math": "0<α<2/max(a,1) 时二次函数梯度下降收敛。", "narration": "点逐渐接近 (0,0,0)，并显示步数和函数值。", "seconds": 5, "title": "观察函数值下降与收敛", "visual": "点逐渐接近 (0,0,0)，并显示步数和函数值。"}]; let end=0; const duration=scenes.reduce((a,s)=>a+s.seconds,0); const scene=scenes.find(s=>{end+=s.seconds;return t*duration<end;}) || scenes[scenes.length-1];
const actualControls={alpha:p.alpha,start:p.start,curvature:p.curvature,angle:p.angle};
return {controls:actualControls,disabled:{},title:scene.title,caption:scene.narration,metrics:{step:steps,x,y,objective:z,gradient_norm:Math.hypot(p.curvature*x,y)}};
}
