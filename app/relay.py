"""YouTube Lounge relay. No LAN sockets, saved history or retained credentials."""
import hashlib
import os
import threading
import time
from collections import OrderedDict

import requests
from casttube import YouTubeSession
from casttube.YouTubeSession import BIND_URL, HEADERS, LOUNGE_TOKEN_URL
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

ORIGIN = os.environ.get('CAST_SITE_ORIGIN', 'https://reverse-cast-web.onrender.com')
api = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
api.add_middleware(CORSMiddleware, allow_origins=[ORIGIN], allow_methods=['POST'], allow_headers=['Content-Type'])
slots = threading.BoundedSemaphore(4)
recent = OrderedDict()
recent_lock = threading.Lock()


class Play(BaseModel):
    model_config = ConfigDict(extra='forbid', hide_input_in_errors=True)
    screen_id: str = Field(min_length=1, max_length=256, pattern=r'^[A-Za-z0-9_-]+$')
    video_id: str = Field(pattern=r'^[A-Za-z0-9_-]{11}$')
    position: float = Field(default=0, ge=0, le=86400, allow_inf_nan=False)


class LoungeSession(YouTubeSession):
    def _do_post(self, url, data=None, params=None, headers=None, session_request=False):
        # CastTube's default has no timeout and may rebind after an error.
        # One explicit request only; do not replay an uncertain media command.
        if url not in (LOUNGE_TOKEN_URL, BIND_URL):
            raise ValueError('Unsupported endpoint')
        response = requests.post(url, data=data, params=params,
                                 headers={**HEADERS, **(headers or {})},
                                 timeout=(5, 10), allow_redirects=False)
        if response.status_code != 200:
            raise ValueError('Upstream rejected request')
        if session_request:
            self._req_count += 1
        self._rid += 1
        return response


@api.exception_handler(RequestValidationError)
async def invalid_body(request, error):
    # FastAPI's default validation response includes the rejected input.
    return JSONResponse({'detail': 'Datos de reproducción inválidos.'}, status_code=422)


@api.middleware('http')
async def guard(request: Request, call_next):
    if request.method == 'POST':
        if request.headers.get('origin') != ORIGIN:
            return JSONResponse({'detail': 'Origen no permitido.'}, status_code=403)
        if request.headers.get('content-type', '').split(';')[0] != 'application/json':
            return JSONResponse({'detail': 'Se requiere JSON.'}, status_code=415)
        # Bound the actual body even when Content-Length is absent or misleading.
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > 2048:
                return JSONResponse({'detail': 'Solicitud demasiado grande.'}, status_code=413)
        request._body = bytes(body)
    response = await call_next(request)
    response.headers['Cache-Control'] = 'no-store'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    return response


@api.get('/health')
def health():
    return {'status': 'ok'}


@api.post('/api/youtube/play')
def play(body: Play):
    # A screen ID is a short-lived control capability, never an account login.
    # Retain only a digest briefly for throttling, never its original value.
    digest = hashlib.sha256(body.screen_id.encode()).digest()
    now = time.monotonic()
    with recent_lock:
        while recent and next(iter(recent.values())) < now - 60:
            recent.popitem(last=False)
        if digest in recent and now - recent[digest] < 3:
            return JSONResponse({'detail': 'Espera unos segundos antes de enviar otra orden.'}, status_code=429)
        if not slots.acquire(blocking=False):
            return JSONResponse({'detail': 'Servicio ocupado. No se envió la orden.'}, status_code=503)
        recent[digest] = now
        recent.move_to_end(digest)
        while len(recent) > 1024:
            recent.popitem(last=False)
    try:
        lounge = LoungeSession(body.screen_id)
        lounge.play_video(body.video_id, start_time=str(body.position))
        return {'message': 'Orden enviada a YouTube. Esperando el estado del Chromecast.'}
    except Exception:
        return JSONResponse({'detail': 'YouTube no confirmó el envío. Revisa la TV antes de repetir.'}, status_code=502)
    finally:
        slots.release()
