"""Monitor Cast de lectura: estado, transiciones y disponibilidad del dispositivo."""
import argparse
import datetime as dt
import hashlib
import ipaddress
import json
import logging
import pathlib
import re
import secrets
import threading
import time
import urllib.parse
import urllib.request
from uuid import UUID

from pychromecast import Chromecast
from pychromecast.controllers import BaseController
from pychromecast.models import CastInfo, HostServiceInfo

MEDIA = 'urn:x-cast:com.google.cast.media'


class Recorder:
    def __init__(self, output):
        output.parent.mkdir(parents=True, exist_ok=True)
        self.stream = output.open('x', encoding='utf-8')
        self.lock = threading.Lock()
        self.salt = secrets.token_bytes(16)
        self.started = time.monotonic()
        self.count = 0

    def reference(self, value):
        if value is None:
            return None
        return hashlib.sha256(self.salt + str(value).encode()).hexdigest()[:12]

    def emit(self, kind, **fields):
        event = {'time_utc': dt.datetime.now(dt.timezone.utc).isoformat(),
                 'elapsed_s': round(time.monotonic() - self.started, 3),
                 'kind': kind, **fields}
        with self.lock:
            self.stream.write(json.dumps(event, ensure_ascii=False) + '\n')
            self.stream.flush()
            self.count += 1


def content_identity(value):
    if not isinstance(value, str):
        return None
    if re.fullmatch(r'[A-Za-z0-9_-]{11}', value):
        return {'youtube_video_id_candidate': value}
    parsed = urllib.parse.urlsplit(value)
    if parsed.hostname in ('youtube.com', 'www.youtube.com', 'm.youtube.com'):
        video = urllib.parse.parse_qs(parsed.query).get('v', [None])[0]
        if not video or not re.fullmatch(r'[A-Za-z0-9_-]{11}', video):
            video = None
        return {'host': parsed.hostname, 'youtube_video_id_candidate': video}
    if parsed.hostname == 'youtu.be':
        video = parsed.path.strip('/')
        return {'host': parsed.hostname, 'youtube_video_id_candidate':
                video if re.fullmatch(r'[A-Za-z0-9_-]{11}', video) else None}
    # Do not retain signed URLs, paths, query strings or fragments.
    return {'scheme': parsed.scheme or None, 'host': parsed.hostname,
            'opaque_content_id_present': bool(value)}


class Observer(BaseController):
    def __init__(self, recorder):
        super().__init__(MEDIA)
        self.rec = recorder

    def new_connection_status(self, status):
        self.rec.emit('connection', status=status.status)

    def new_cast_status(self, status):
        self.rec.emit('receiver', app_id=status.app_id, app_name=status.display_name,
                      session_ref=self.rec.reference(status.session_id),
                      transport_ref=self.rec.reference(status.transport_id),
                      namespaces=status.namespaces, volume=status.volume_level,
                      muted=status.volume_muted, active_input=status.is_active_input,
                      standby=status.is_stand_by)

    def receive_message(self, message, data):
        if data.get('type') in ('LOAD_FAILED', 'LOAD_CANCELLED', 'INVALID_REQUEST'):
            self.rec.emit('media_error', message_type=data['type'], reason=data.get('reason'))
        if data.get('type') != 'MEDIA_STATUS':
            return False
        statuses = data.get('status') or []
        if not isinstance(statuses, list):
            self.rec.emit('parse_issue', reason='status-not-array')
            return False
        if not statuses:
            self.rec.emit('media_empty')
        for status in statuses:
            if not isinstance(status, dict):
                self.rec.emit('parse_issue', reason='status-item-not-object')
                continue
            extended = status.get('extendedStatus') or {}
            extended = extended if isinstance(extended, dict) else {}
            media = status.get('media') or extended.get('media') or {}
            if not isinstance(media, dict):
                self.rec.emit('parse_issue', reason='media-not-object')
                continue
            event = {key: status.get(key) for key in (
                'playerState', 'idleReason', 'currentTime', 'playbackRate',
                'supportedMediaCommands')}
            event['media_session_ref'] = self.rec.reference(status.get('mediaSessionId'))
            event['content'] = content_identity(media.get('contentId'))
            event['duration'] = media.get('duration')
            event['content_type'] = media.get('contentType')
            event['stream_type'] = media.get('streamType')
            event['custom_data_keys'] = sorted(media['customData']) if isinstance(media.get('customData'), dict) else []
            event['status_custom_data_keys'] = sorted(status['customData']) if isinstance(status.get('customData'), dict) else []
            event['status_keys'] = sorted(status.keys())
            ad = status.get('breakStatus') or status.get('adBreakStatus')
            if isinstance(ad, dict):
                event['ad_break'] = {key: ad.get(key) for key in (
                    'currentBreakTime', 'currentBreakClipTime', 'whenSkippable')}
                event['ad_break']['break_id_present'] = bool(ad.get('breakId'))
            else:
                event['ad_break'] = None
            self.rec.emit('media', **event)
        return False


def device_status(opener, host):
    with opener.open(f'http://{host}:8008/setup/eureka_info', timeout=3) as response:
        body = response.read(1024 * 1024 + 1)
        if len(body) > 1024 * 1024:
            raise ValueError('Respuesta demasiado grande')
        info = json.loads(body)
    return {key: info.get(key) for key in (
        'uptime', 'build_version', 'cast_build_revision', 'connected', 'signal_level')}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', default='192.168.1.6')
    parser.add_argument('--duration', type=int, default=60)
    parser.add_argument('--interval', type=float, default=2)
    parser.add_argument('--output', type=pathlib.Path, required=True)
    args = parser.parse_args()
    ipaddress.IPv4Address(args.host)
    if not 1 <= args.duration <= 1800 or not 1 <= args.interval <= 30:
        parser.error('Duración 1–1800 s; intervalo 1–30 s')
    logging.getLogger('pychromecast').setLevel(logging.CRITICAL)
    recorder = Recorder(args.output)
    recorder.emit('start', host=args.host, duration_s=args.duration,
                  interval_s=args.interval, mode='read-only-status-queries')
    # Direct host selection; zero UUID is a local placeholder, not a device identity.
    info = CastInfo({HostServiceInfo(args.host, 8009)}, UUID(int=0), None,
                    None, args.host, 8009, 'cast', None)
    cast = Chromecast(info, tries=None, timeout=4, retry_wait=1)
    # Only our observer handles media; the standard controller's automatic
    # channel_connected/update_status path has an implicit app-launch fallback.
    cast.unregister_handler(cast.media_controller)
    observer = Observer(recorder)
    cast.register_status_listener(observer)
    cast.register_connection_listener(observer)
    cast.register_handler(observer)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    cast.start()
    deadline = time.monotonic() + args.duration
    next_device = 0
    try:
        while time.monotonic() < deadline:
            try:
                cast.socket_client.receiver_controller.update_status()
                if MEDIA in cast.socket_client.app_namespaces:
                    # Bypass BaseController's app-launch fallback. If the app
                    # changes concurrently, send_app_message refuses the request.
                    cast.socket_client.send_app_message(MEDIA, {'type': 'GET_STATUS'})
            except Exception as error:
                recorder.emit('query_unavailable', error_type=type(error).__name__)
            if time.monotonic() >= next_device:
                try:
                    recorder.emit('device', **device_status(opener, args.host))
                except Exception as error:
                    recorder.emit('device_unavailable', error_type=type(error).__name__)
                next_device = time.monotonic() + 5
            time.sleep(min(args.interval, max(0, deadline - time.monotonic())))
    except KeyboardInterrupt:
        recorder.emit('interrupted')
    finally:
        recorder.emit('observer_stopping')
        cast.disconnect(timeout=10)
        recorder.emit('end')
        recorder.stream.close()
    print(json.dumps({'output': str(args.output.resolve()), 'events': recorder.count}))


if __name__ == '__main__':
    main()
