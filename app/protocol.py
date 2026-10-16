import threading
import time
from pychromecast.controllers import BaseController

MDX = 'urn:x-cast:com.google.youtube.mdx'
MEDIA = 'urn:x-cast:com.google.cast.media'


class SessionObserver(BaseController):
    def __init__(self):
        super().__init__(MDX)
        self.screen_id = None
        self.ready = threading.Event()

    def receive_message(self, message, data):
        if data.get('type') == 'mdxSessionStatus':
            self.screen_id = (data.get('data') or {}).get('screenId')
            if self.screen_id:
                self.ready.set()
        return False


class MediaObserver(BaseController):
    def __init__(self):
        super().__init__(MEDIA)
        self.latest = None

    def receive_message(self, message, data):
        if data.get('type') == 'MEDIA_STATUS':
            statuses = data.get('status') or []
            if not isinstance(statuses, list) or not statuses:
                self.latest = None
                return False
            for status in statuses:
                if not isinstance(status, dict):
                    continue
                extended = status.get('extendedStatus') or {}
                extended = extended if isinstance(extended, dict) else {}
                media = status.get('media') or extended.get('media') or {}
                if not isinstance(media, dict):
                    continue
                self.latest = {'video_id': media.get('contentId'),
                               'player_state': status.get('playerState'),
                               'position': status.get('currentTime'),
                               'observed_monotonic': time.monotonic()}
        return False

    def channel_disconnected(self):
        self.latest = None


def confirms_playback(current, video_id, position, requested_at):
    if not current or current.get('observed_monotonic', -1) < requested_at:
        return False
    actual = current.get('position')
    return (current.get('video_id') == video_id
            and current.get('player_state') == 'PLAYING'
            and isinstance(actual, (int, float))
            and position - 3 <= actual <= position + max(
                0, current['observed_monotonic'] - requested_at) + 5)



