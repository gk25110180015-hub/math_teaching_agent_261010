"""Explicit offline fixtures for derivative and gradient-descent demonstrations."""
import copy
import json
from ..util import AgentError


DERIVATIVE = r'''
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
'''

GRADIENT = r'''
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
 return {metrics:{step:steps,x,y,objective:z,gradient_norm:Math.hypot(p.curvature*x,y)}};
}
'''


def is_gradient(topic):
    if any(s in topic.lower() for s in ('梯度', 'gradient')):
        return True
    if any(s in topic.lower() for s in ('导数', 'derivative')):
        return False
    raise AgentError('MOCK_CONCEPT_UNAVAILABLE', 'MOCK 仅提供导数和梯度下降示例；其他概念请选择真实 API')


def story(gradient, title=None):
    if gradient:
        titles=['认识三维目标曲面','沿负梯度逐步更新','观察函数值下降与收敛']
        visuals=['绘出 f(x,y)=(a x²+y²)/2 的三维网格曲面及初始点。', '依照负梯度迭代，橙色路径位于目标曲面上。', '点逐渐接近 (0,0,0)，并显示步数和函数值。']
        maths=['∇f=(a x,y)，a∈[1,2]。','(x,y)←(x,y)−α(a x,y)。','0<α<2/max(a,1) 时二次函数梯度下降收敛。']
    else:
        titles=['函数曲线与两个点','割线逐渐逼近切线','差商数值收敛到导数']
        visuals=['画出 f(x)=x²、P、Q 及割线和切线。','h 从初始间隔指数减小，两点靠近、橙色割线趋向紫色切线。','同步呈现差商、解析导数与绝对误差。']
        maths=['割线斜率=[f(x₀+h)−f(x₀)]/h。','h>0 趋于零，不取零避免除零。','f(x)=x² 时差商=2x₀+h，导数=2x₀。']
    return {'title': title or ('梯度下降：在曲面上寻找极小值' if gradient else '导数：从割线走向切线'),
            'summary':'MOCK 离线教学演示；真实 API 会依据任意概念编写方案及代码。',
            'objectives': titles, 'scenes':[{'id':f'S{i+1}', 'title':titles[i], 'visual':visuals[i],
                'narration':visuals[i], 'math':maths[i], 'seconds':5} for i in range(3)],
            'interaction_goals':['调节步长、初始点、曲面曲率和三维视角'] if gradient else ['调节求导点、初始间隔以及示例函数'],
            'math_notes':maths}


def generate(role, context, schema):
    gradient = is_gradient(context['input']['topic'])
    if role == 'visualization_candidates':
        titles = ['三维曲面与下降轨迹', '步长如何影响收敛', '初始点和曲率的影响'] if gradient else ['割线逼近切线', '差商误差与收敛', '改变求导点，观察局部变化']
        value={'candidates':[dict(story(gradient, title), id=f'C{i+1}') for i,title in enumerate(titles)]}
    elif role == 'visualization_refine':
        plan=context['current_plan']; current=copy.deepcopy(plan['story'])
        questions=[]
        if plan['refinement_round']==0:
            choices=[('Q-step','选择哪种步长演示？','步长影响迭代速度。', [('SMALL','较小步长 0.1','默认步长为 0.1'),('FAST','较快步长 0.4','默认步长为 0.4')]),
                     ('Q-surface','目标曲面选哪一种？','曲率影响不同方向的收敛。',[('ROUND','旋转对称抛物面','曲率 a=1'),('ELLIPSE','椭圆抛物面','曲率 a=2')])] if gradient else [
                     ('Q-function','使用哪个示例函数？','不同曲线有不同导数。',[('SQUARE','f(x)=x²','使用 f(x)=x² 与导数 2x'),('SIN','f(x)=sin(x)','使用正弦函数与导数 cos(x)')]),
                     ('Q-point','从哪个求导点开始？','求导点决定局部斜率。',[('ONE','x₀=1','默认求导点为 1'),('ZERO','x₀=0','默认求导点为 0')])]
            questions=[{'id':qid,'prompt':prompt,'reason':reason,'options':[{'id':oid,'label':label,'effect':effect} for oid,label,effect in options]} for qid,prompt,reason,options in choices]
        for decision in plan['decisions']:
            for answer in decision['answers']:
                effect=answer['option']['effect']
                if effect not in current['math_notes']:current['math_notes'].append(effect)
                if answer['option']['id']=='SIN':
                    for scene in current['scenes']:
                        for key in ('visual','narration','math'):
                            scene[key]=scene[key].replace('f(x)=x²','f(x)=sin(x)').replace('差商=2x₀+h，导数=2x₀','差商趋于 cos(x₀)')
        value={'story':current,'questions':questions,'changes':['已将本轮选择写入方案；请核对数学说明与分镜。'], 'applied_decision_ids':plan['decision_ids']}
    elif role == 'visualization_writer':
        if context.get('repair_format') == 'anchored_edits':
            code = context['previous_program']['code']
            anchor = code[-120:]
            return schema.model_validate({'edits':[{'old':anchor,'new':anchor,'reason':'MOCK 保留原示例代码；不代表真实数学修复'}],
                'explanation':'MOCK 局部修复契约演示。'}).model_dump()
        plan=context['confirmed_plan']; ids=[a['option']['id'] for d in plan['decisions'] for a in d['answers']]
        def control(id,label,min,max,step,value):return dict(id=id,label=label,min=float(min),max=float(max),step=float(step),value=float(value))
        controls=[control('alpha','学习率 α',.03,.9,.01,.4 if 'FAST' in ids else .1), control('start','初始 x',.5,2.2,.1,2),
                  control('curvature','曲率 a',1,2,.1,2 if 'ELLIPSE' in ids else 1), control('angle','三维视角',-.8,1.4,.05,.6)] if gradient else [
                  control('x0','求导点 x₀',-1.5,1.5,.1,0 if 'ZERO' in ids else 1),control('hstart','初始间隔 h',.2,1.5,.1,1),
                  control('curve','函数：0 为平方，1 为正弦',0,1,1,1 if 'SIN' in ids else 0)]
        code = GRADIENT if gradient else DERIVATIVE
        # Offline fixtures exercise the same v2 state/caption protocol as live code.
        scenes = json.dumps(plan['story']['scenes'], ensure_ascii=False)
        state = ('const scenes='+scenes+'; let end=0; const duration=scenes.reduce((a,s)=>a+s.seconds,0); '
                 'const scene=scenes.find(s=>{end+=s.seconds;return t*duration<end;}) || scenes[scenes.length-1];\n')
        state += 'const actualControls={' + ','.join(c['id']+':p.'+c['id'] for c in controls) + '};\n'
        code = code.replace('return {metrics:', state+'return {controls:actualControls,disabled:{},title:scene.title,caption:scene.narration,metrics:')
        value={'runtime_version':2,'code':code,'controls':controls,'covered_decision_ids':plan['decision_ids'],
               'explanation':'MOCK 示例：数值随动画时间和参数即时重算。','limitations':['此代码来自离线测试样例，未经真实模型或教师审阅。']}
    else:
        value={'approved':True,'issues':[],'limitations':['MOCK 不构成真实数学审核；待教师复核。']}
    return schema.model_validate(value).model_dump()
