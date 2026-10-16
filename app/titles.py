"""Optional titles: native metadata first, bounded background oEmbed fallback."""
import json
import threading
import time
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor

import requests

from app.validation import VIDEO


def clean_title(value):
    if not isinstance(value, str):
        return None
    return ' '.join(value.split())[:300] or None


def fetch_title(video_id):
    if not isinstance(video_id, str) or not VIDEO.fullmatch(video_id):
        return None
    # Only a canonical video ID reaches this fixed endpoint. No cookies or redirects.
    with requests.Session() as session:
        session.trust_env = False
        with session.get('https://www.youtube.com/oembed', params={
            'url': f'https://www.youtube.com/watch?v={video_id}', 'format': 'json'},
            timeout=(2, 3), allow_redirects=False, stream=True) as response:
            if response.status_code != 200:
                return None
            body = bytearray()
            for chunk in response.iter_content(4096):
                body.extend(chunk)
                if len(body) > 32768:
                    return None
            data = json.loads(body)
            return clean_title(data.get('title')) if isinstance(data, dict) else None


class TitleResolver:
    def __init__(self, fetcher=fetch_title):
        self.fetcher = fetcher
        self.lock = threading.Lock()
        self.cache = OrderedDict()
        self.pending = set()
        self.closed = False
        self.worker = ThreadPoolExecutor(max_workers=1, thread_name_prefix='video-title')

    def get(self, video_id, native=None):
        if not isinstance(video_id, str) or not VIDEO.fullmatch(video_id):
            return None
        native = clean_title(native)
        with self.lock:
            if native:
                self._remember(video_id, native)
                return native
            cached = self.cache.get(video_id)
            if cached and cached[1] > time.monotonic():
                self.cache.move_to_end(video_id)
                return cached[0]
            if not self.closed and video_id not in self.pending and len(self.pending) < 8:
                self.pending.add(video_id)
                self.worker.submit(self._resolve, video_id)
        return None

    def _remember(self, video_id, title):
        self.cache[video_id] = (title, time.monotonic() + (21600 if title else 300))
        self.cache.move_to_end(video_id)
        while len(self.cache) > 256:
            self.cache.popitem(last=False)

    def _resolve(self, video_id):
        try:
            title = clean_title(self.fetcher(video_id))
        except Exception:
            title = None  # Optional lookup failure must never affect Cast or leak URLs.
        with self.lock:
            # Native metadata may have arrived while the HTTP request was pending.
            existing = self.cache.get(video_id)
            if not existing or not existing[0] or existing[1] <= time.monotonic():
                self._remember(video_id, title)
            self.pending.discard(video_id)

    def close(self):
        with self.lock:
            self.closed = True
        self.worker.shutdown(wait=True, cancel_futures=True)
