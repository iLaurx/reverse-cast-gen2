"""A single Cast connection, passive controllers and explicit commands."""
import threading
import time
from uuid import UUID
from pychromecast import Chromecast
from pychromecast.models import CastInfo, HostServiceInfo
from pychromecast.controllers.youtube import TimeoutYouTubeSession
from app.protocol import MDX, MEDIA, SessionObserver
from pychromecast.controllers import BaseController
from app.validation import VIDEO
from app.titles import clean_title


def number(value):
    import math
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0 else None


class CastObserver(BaseController):
    def __init__(self):
        super().__init__(MEDIA)
        self.lock = threading.RLock()
        self.connection = 'CONNECTING'
        self.receiver = None
        self.media = None
        self.session = None
        self.generation = 0
        self.error_at = 0

    def new_connection_status(self, status):
        with self.lock:
            self.connection = status.status
            if self.connection != 'CONNECTED':
                self.receiver = self.media = self.session = None
                self.generation += 1

    def new_cast_status(self, status):
        with self.lock:
            identity = (status.app_id, status.session_id, status.transport_id)
            if identity != self.session:
                self.media = None
                self.generation += 1
            self.session = identity
            self.receiver = dict(app_id=status.app_id, app_name=status.display_name,
                                 observed_monotonic=time.monotonic())
            if status.app_id != '233637DE':
                self.media = None

    def channel_disconnected(self):
        with self.lock:
            self.media = None
            self.generation += 1

    def receive_message(self, message, data):
        with self.lock:
            if data.get('type') in ('LOAD_FAILED', 'LOAD_CANCELLED', 'INVALID_REQUEST'):
                self.error_at = time.monotonic()
            if data.get('type') != 'MEDIA_STATUS':
                return False
            self.media = None  # Never merge retained fields into a fresh observation.
            statuses = data.get('status')
            if not isinstance(statuses, list) or not self.receiver or self.receiver['app_id'] != '233637DE':
                return False
            for status in statuses[:1]:
                if not isinstance(status, dict):
                    continue
                extended = status.get('extendedStatus')
                extended = extended if isinstance(extended, dict) else {}
                media = status.get('media') or extended.get('media')
                if not isinstance(media, dict):
                    continue
                video = media.get('contentId')
                video = video if isinstance(video, str) and VIDEO.fullmatch(video) else None
                commands = status.get('supportedMediaCommands')
                metadata = media.get('metadata')
                title = clean_title(metadata.get('title')) if isinstance(metadata, dict) else None
                self.media = dict(video_id=video, position=number(status.get('currentTime')),
                                  title=title,
                                  duration=number(media.get('duration')),
                                  player_state=status.get('playerState') if status.get('playerState') in ('PLAYING','PAUSED','IDLE','BUFFERING') else 'UNKNOWN',
                                  observed_monotonic=time.monotonic(),
                                  commands=commands if isinstance(commands, int) else 0,
                                  media_session_id=status.get('mediaSessionId'),
                                  ad_detected=any(status.get(k) is not None for k in ('breakStatus','adBreakStatus')) or media.get('isPlayingAd') is True,
                                  generation=self.generation)
        return False

    def snapshot(self):
        with self.lock:
            return dict(connection=self.connection,
                        receiver=dict(self.receiver) if self.receiver else None,
                        media=dict(self.media) if self.media else None,
                        generation=self.generation, error_at=self.error_at)


class CastAdapter:
    def __init__(self, host):
        self.observer = CastObserver()
        info = CastInfo({HostServiceInfo(host, 8009)}, UUID(int=0), None, None, host, 8009, 'cast', None)
        self.cast = Chromecast(info, tries=None, timeout=4, retry_wait=2)
        self.cast.unregister_handler(self.cast.media_controller)
        self.mdx = SessionObserver()
        self.cast.register_handler(self.observer)
        self.cast.register_status_listener(self.observer)
        self.cast.register_connection_listener(self.observer)
        self.cast.register_handler(self.mdx)
        self.cast.start()

    def snapshot(self):
        return self.observer.snapshot()

    def poll(self):
        self.cast.socket_client.receiver_controller.update_status()
        if MEDIA in self.cast.socket_client.app_namespaces:
            self.cast.socket_client.send_app_message(MEDIA, {'type': 'GET_STATUS'})

    def play(self, video, position):
        self.cast.start_app('233637DE', timeout=20)
        deadline = time.monotonic() + 15
        while MDX not in self.cast.socket_client.app_namespaces:
            if time.monotonic() >= deadline:
                raise TimeoutError()
            self.cast.socket_client.receiver_controller.update_status()
            time.sleep(.5)
        # A new MDX response and short-lived Lounge session for every explicit play.
        self.mdx.screen_id = None
        self.mdx.ready.clear()
        self.cast.socket_client.send_app_message(MDX, {'type': 'getMdxSessionStatus'})
        if not self.mdx.ready.wait(10):
            raise TimeoutError()
        screen = self.mdx.screen_id
        try:
            current = self.snapshot()
            if current['connection'] != 'CONNECTED' or not current['receiver'] or current['receiver']['app_id'] != '233637DE':
                raise RuntimeError('La sesión cambió durante el inicio de YouTube.')
            TimeoutYouTubeSession(screen, timeout=10).play_video(video, start_time=str(position))
        finally:
            self.mdx.screen_id = None
            self.mdx.ready.clear()

    def control(self, action, media):
        self.cast.socket_client.send_app_message(MEDIA, {
            'type': 'PAUSE' if action == 'pause' else 'PLAY',
            'mediaSessionId': media['media_session_id']}, inc_session_id=True)

    def seek(self, media, position):
        current = self.snapshot()
        latest = current.get('media') or {}
        if (current['connection'] != 'CONNECTED' or not current.get('receiver')
                or current['receiver']['app_id'] != '233637DE'
                or latest.get('generation') != media.get('generation')
                or latest.get('video_id') != media.get('video_id')
                or latest.get('media_session_id') != media.get('media_session_id')
                or latest.get('ad_detected') or not latest.get('commands', 0) & 2):
            raise RuntimeError('La sesión ya no permite buscar la posición.')
        self.cast.socket_client.send_app_message(MEDIA, {
            'type':'SEEK', 'mediaSessionId':media['media_session_id'],
            'currentTime':position, 'resumeState':'PLAYBACK_START'}, inc_session_id=True)

    def close(self):
        self.mdx.screen_id = None
        self.cast.disconnect(timeout=10)
