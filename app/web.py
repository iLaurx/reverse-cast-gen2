"""Local web API. Launch through python -m app; one worker only."""
import os
import secrets
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field
from app.cast import CastAdapter
from app.service import Service, ServiceError
from app.store import Store

ROOT = Path(__file__).resolve().parents[1]

class Command(BaseModel):
    model_config = ConfigDict(extra='forbid')
    url: str = Field(default='', max_length=2048)
    position: float | None = Field(default=None, ge=0, le=86400, allow_inf_nan=False)
    host: str = Field(default='', max_length=15)
    checkpoint_id: int | None = Field(default=None, gt=0)
    content_confirmed: bool = False
    video_id: str | None = Field(default=None, max_length=11)

def create_app(service=None, token=None, allowed_hosts=None):
    token = token if token is not None else os.environ.get('CAST_WEB_TOKEN')
    allowed_hosts = set(allowed_hosts or os.environ.get('CAST_WEB_HOSTS', '127.0.0.1,localhost').split(','))
    @asynccontextmanager
    async def lifespan(app):
        owned = service is None
        store = Store(ROOT / 'data' / 'history.sqlite3') if owned else None
        app.state.service = Service(store, CastAdapter) if owned else service
        app.state.service.start()
        try:
            yield
        finally:
            app.state.service.close()
            if store:
                store.close()
    api = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)

    @api.middleware('http')
    async def guard(request: Request, call_next):
        try:
            hostname = urlsplit('http://' + request.headers.get('host', '')).hostname
            if hostname not in allowed_hosts:
                return JSONResponse({'detail': 'Dirección de acceso no permitida.'}, status_code=403)
            origin = request.headers.get('origin')
            if origin and origin != f'{request.url.scheme}://{request.headers.get("host")}':
                return JSONResponse({'detail': 'Origen no permitido.'}, status_code=403)
            client = request.client.host if request.client else ''
            if client not in ('127.0.0.1','::1','testclient') and not token:
                return JSONResponse({'detail': 'Configura una clave antes de acceder desde la red local.'}, status_code=403)
            if request.url.path.startswith('/api/'):
                if token and not secrets.compare_digest(request.headers.get('x-cast-key', ''), token):
                    return JSONResponse({'detail': 'Introduce la clave de acceso.'}, status_code=401)
                if request.method == 'POST' and request.headers.get('content-type', '').split(';')[0] != 'application/json':
                    return JSONResponse({'detail': 'Se requiere JSON.'}, status_code=415)
                if int(request.headers.get('content-length', '0')) > 4096:
                    return JSONResponse({'detail': 'Solicitud demasiado grande.'}, status_code=413)
            response = await call_next(request)
            response.headers.update({'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff',
                'Referrer-Policy': 'no-referrer', 'X-Frame-Options': 'DENY',
                'Content-Security-Policy': "default-src 'self'; style-src 'self'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'"})
            return response
        except ValueError:
            return JSONResponse({'detail': 'Solicitud inválida.'}, status_code=400)

    @api.get('/api/state')
    def state(request: Request):
        return request.app.state.service.status()

    @api.post('/api/{action}')
    def command(action: str, body: Command, request: Request):
        try:
            return request.app.state.service.execute(action, body.model_dump())
        except ValueError as error:
            return JSONResponse({'detail': str(error)}, status_code=400)
        except ServiceError as error:
            return JSONResponse({'detail': str(error)}, status_code=409)

    @api.get('/')
    def index():
        return FileResponse(ROOT / 'app/static/index.html')
    api.mount('/static', StaticFiles(directory=ROOT / 'app/static'), name='static')
    return api
