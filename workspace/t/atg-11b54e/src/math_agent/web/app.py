import hmac
import json
import secrets
import time
from pathlib import Path
from urllib.parse import urlparse
from fastapi import FastAPI, Request, UploadFile, File, Form
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from ..domain import NewRun, DecisionsRequest, ConfirmRequest, ExecuteRequest, RecheckRequest, ReviewRequest, RevisePlanRequest
from ..budget import BudgetIncrease
from ..service import Service
from ..settings import Settings, PROJECT_ROOT
from ..util import AgentError, within, digest


def create_app(settings: Settings | None=None):
    settings=settings or Settings()
    service=Service(settings)
    app=FastAPI(title='数学教学 Agent',docs_url=None,redoc_url=None)
    app.state.service=service
    static=Path(__file__).parent/'static'
    app.mount('/static',StaticFiles(directory=static),name='static')

    @app.exception_handler(AgentError)
    async def agent_error(request,exc):
        return JSONResponse({'error':{'code':exc.code,'message':exc.message}},status_code=exc.status)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request,exc):
        return JSONResponse({'error':{'code':'VALIDATION','message':'请求字段、类型或取值无效'},'details':[{'loc':list(e['loc']),'type':e['type']} for e in exc.errors()]},status_code=422)

    @app.middleware('http')
    async def local_boundary(request:Request,call_next):
        host=request.headers.get('host','')
        host_name=host.split(':')[0].lower()
        if host_name not in ('127.0.0.1','localhost'):
            return JSONResponse({'error':{'code':'HOST_REJECTED','message':'仅允许本机回环访问'}},status_code=403)
        origin=request.headers.get('origin')
        if origin and origin != str(request.base_url).rstrip('/'):
            return JSONResponse({'error':{'code':'ORIGIN_REJECTED','message':'拒绝跨源访问'}},status_code=403)
        if request.headers.get('sec-fetch-site')=='cross-site':
            return JSONResponse({'error':{'code':'CROSS_SITE','message':'拒绝跨站访问'}},status_code=403)
        if request.method not in ('GET','HEAD','OPTIONS'):
            cookie=request.cookies.get('math_agent_session','')
            csrf=request.headers.get('x-csrf-token','')
            if not cookie or not csrf or not hmac.compare_digest(cookie,csrf):
                return JSONResponse({'error':{'code':'CSRF','message':'会话过期，请刷新页面'}},status_code=403)
        if request.url.path.startswith('/api/') and request.url.path not in ('/api/session','/api/health','/api/capabilities') and not request.cookies.get('math_agent_session'):
            return JSONResponse({'error':{'code':'SESSION_REQUIRED','message':'请先打开本地界面'}},status_code=403)
        response=await call_next(request)
        response.headers['X-Content-Type-Options']='nosniff'
        response.headers['Cross-Origin-Resource-Policy']='same-origin'
        response.headers['Referrer-Policy']='no-referrer'
        response.headers['Content-Security-Policy']="default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; frame-src 'self'; object-src 'self'; frame-ancestors 'self'; base-uri 'none'"
        response.headers['Cache-Control']='no-store'
        return response

    @app.get('/')
    def index():
        return FileResponse(static/'index.html')

    @app.get('/api/session')
    def session(request:Request):
        token=request.cookies.get('math_agent_session') or secrets.token_urlsafe(32)
        response=JSONResponse({'csrf_token':token})
        response.set_cookie('math_agent_session',token,httponly=True,samesite='strict',max_age=86400*30)
        return response

    @app.get('/api/health')
    def health():
        with service.store.connect() as c:
            row=c.execute('SELECT MAX(timestamp) FROM worker_heartbeats').fetchone()
        last=row[0] if row else None
        return {'status':'ok','worker':{'alive':bool(last and time.time()-last<20),'last_heartbeat':last},'schema_version':1}

    @app.get('/api/capabilities')
    def capabilities():
        from ..beamer import theme_status
        from ..compiler import resolve_xelatex
        engine=resolve_xelatex(settings.xelatex_path,forbidden_roots=[settings.workspace])
        tested={'text':'untested','vision':'untested','tools':'untested','json_schema':'untested','streaming':'untested'}
        capabilities_file=PROJECT_ROOT/'reports'/'capabilities.json'
        if capabilities_file.is_file():
            try:
                saved=json.loads(capabilities_file.read_text(encoding='utf-8'))
                if saved.get('model')==settings.model and saved.get('base_url')==settings.api_base_url:
                    tested.update({k:saved[k] for k in tested if k in saved})
                    tested['tested_at']=saved.get('timestamp')
            except (OSError,ValueError):pass
        public_settings=settings.public()
        models=[]
        for profile in public_settings.get('models',[]):
            tested_profile={key:'untested' for key in ('text','vision','tools','json_schema','streaming')}
            path=PROJECT_ROOT/'reports'/'model-capabilities'/(profile['id']+'.json')
            if path.is_file():
                try:
                    saved=json.loads(path.read_text(encoding='utf-8'))
                    if saved.get('model')==profile['model'] and saved.get('base_url')==profile['base_url']:
                        tested_profile.update({key:saved[key] for key in tested_profile if key in saved})
                        tested_profile['tested_at']=saved.get('timestamp')
                except (OSError,ValueError,TypeError):pass
            models.append({**profile,'capabilities':tested_profile})
        public_settings['models']=models
        return {'settings':public_settings,'models':models,'templates':theme_status(settings.reference_root),
                'reference_manuscript':{'available':(settings.reference_root/'大学数学（一）(1).tex').is_file(),'name':'大学数学（一）(1).tex'},
                'compiler':{'available':engine is not None,'mode':settings.compile_mode,'isolated':False},
                'model':tested,'worker':health()['worker']}

    @app.get('/api/runs')
    def list_runs(): return service.list_runs()

    @app.post('/api/runs',status_code=201)
    def create(data:NewRun): return service.create(data)

    @app.get('/api/runs/{run_id}')
    def get(run_id:str): return service.get(run_id)

    @app.get('/api/runs/{run_id}/budget')
    def get_budget(run_id:str): return service.get_budget(run_id)

    @app.post('/api/runs/{run_id}/budget')
    def increase_budget(run_id:str,data:BudgetIncrease): return service.increase_budget(run_id,data)

    @app.get('/api/runs/{run_id}/partials')
    def partials(run_id:str): return service.partial_checkpoints(run_id)

    @app.get('/api/runs/{run_id}/partials/{token}')
    def partial_download(run_id:str,token:str):
        artifact=service.partial_download(run_id,token)
        return Response(artifact['_body'],media_type=artifact['media_type'],headers={
            'Content-Disposition':'attachment; filename="'+artifact['name']+'"',
            'X-Content-SHA256':artifact['sha256'], 'X-Math-Agent-Status':'PARTIAL'})

    @app.post('/api/runs/{run_id}/attachments')
    async def attach(run_id:str,file:UploadFile=File(...),main_file:str|None=Form(None)):
        data=await file.read(50*1024*1024+1)
        return service.attachments(run_id,file.filename or 'source.tex',data,main_file)

    @app.post('/api/runs/{run_id}/plan',status_code=202)
    def plan(run_id:str): return service.propose(run_id)

    @app.get('/api/runs/{run_id}/plan')
    def get_plan(run_id:str): return service.store.get_run(run_id)['plan']

    @app.post('/api/runs/{run_id}/decisions')
    def decisions(run_id:str,data:DecisionsRequest): return service.decisions(run_id,data)

    @app.post('/api/runs/{run_id}/plan/confirm')
    def confirm(run_id:str,data:ConfirmRequest): return service.confirm(run_id,data)

    @app.post('/api/runs/{run_id}/plan/revise')
    def revise(run_id:str,data:RevisePlanRequest): return service.revise(run_id,data)

    @app.post('/api/runs/{run_id}/execute',status_code=202)
    def execute(run_id:str,data:ExecuteRequest): return service.execute(run_id,data)

    @app.post('/api/runs/{run_id}/recheck',status_code=202)
    def recheck(run_id:str,data:RecheckRequest): return service.recheck(run_id,data)

    @app.post('/api/runs/{run_id}/retry',status_code=202)
    def retry(run_id:str): return service.retry(run_id)

    @app.post('/api/runs/{run_id}/cancel')
    def cancel(run_id:str): return service.cancel(run_id)

    @app.post('/api/runs/{run_id}/reviews')
    def review(run_id:str,data:ReviewRequest): return service.review(run_id,data)

    @app.get('/api/runs/{run_id}/events')
    def events(run_id:str,after:int=0):
        with service.store.connect() as c:
            service.store.row(c,run_id)
            return [{**dict(r),'payload':json.loads(r['payload_json'])} for r in c.execute('SELECT * FROM events WHERE run_id=? AND sequence>? ORDER BY sequence LIMIT 500',(run_id,after))]

    @app.get('/api/runs/{run_id}/artifacts')
    def artifacts(run_id:str):
        service.store.get_run(run_id)
        return service.store.artifacts(run_id)

    @app.get('/api/artifacts/{artifact_id}')
    def artifact(artifact_id:str):
        with service.store.connect() as c:
            row=c.execute('SELECT * FROM artifacts WHERE artifact_id=?',(artifact_id,)).fetchone()
        if row is None:
            raise AgentError('NOT_FOUND','产物不存在',404)
        try: path=within(settings.workspace,row['storage_key'])
        except ValueError: raise AgentError('BAD_ARTIFACT','产物路径校验失败',403) from None
        if not path.is_file(): raise AgentError('MISSING_ARTIFACT','产物文件缺失；数据库记录已保留',404)
        if digest(path.read_bytes())!=row['sha256']:
            raise AgentError('ARTIFACT_CHANGED','产物与保存的哈希不一致；停止交付并保留诊断',409)
        name=''.join(ch for ch in row['name'] if ch.isprintable() and ch not in '/\\')
        inline=row['media_type'] in ('application/pdf','image/png','application/json')
        return FileResponse(path,media_type=row['media_type'],filename=name,content_disposition_type='inline' if inline else 'attachment')

    return app
