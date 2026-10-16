"""Prueba explícita: abre YouTube y reemplaza la cola con un video y posición."""
import argparse
import datetime as dt
import ipaddress
import json
import logging
import pathlib
import re
import threading
import time
from uuid import UUID

import requests
from pychromecast import Chromecast
from pychromecast.controllers import BaseController
from pychromecast.controllers.youtube import TimeoutYouTubeSession
from pychromecast.models import CastInfo, HostServiceInfo

# Shared with the persistent web service.
import sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from app.protocol import MDX, MEDIA, SessionObserver, MediaObserver, confirms_playback


def recover(host, video_id, position, report):
    info = CastInfo({HostServiceInfo(host, 8009)}, UUID(int=0), None, None,
                    host, 8009, 'cast', None)
    cast = Chromecast(info, tries=3, timeout=4, retry_wait=1)
    cast.unregister_handler(cast.media_controller)
    session, media = SessionObserver(), MediaObserver()
    cast.register_handler(session)
    cast.register_handler(media)
    try:
        cast.wait(timeout=15)
        report['previous_app'] = cast.app_id
        cast.start_app('233637DE', timeout=20)
        deadline = time.monotonic() + 15
        while MDX not in cast.socket_client.app_namespaces:
            if time.monotonic() >= deadline:
                raise TimeoutError('YouTube no expuso MDX')
            cast.socket_client.receiver_controller.update_status()
            time.sleep(1)
        cast.socket_client.send_app_message(MDX, {'type': 'getMdxSessionStatus'})
        if not session.ready.wait(10):
            raise TimeoutError('YouTube no entregó sesión MDX')
        report['screen_id_received'] = True
        # Session credentials stay in this process and are not serialized.
        youtube = TimeoutYouTubeSession(session.screen_id, timeout=10)
        requested_at = time.monotonic()
        media.latest = None
        youtube.play_video(video_id, start_time=str(position))
        report['play_request_completed'] = True
        deadline = time.monotonic() + 35
        while time.monotonic() < deadline:
            try:
                cast.socket_client.send_app_message(MEDIA, {'type': 'GET_STATUS'})
            except Exception:
                pass
            current = media.latest
            if (current and current.get('video_id') == video_id
                    and current.get('observed_monotonic', -1) >= requested_at):
                report['last_matching_media'] = {
                    key: current[key] for key in ('video_id', 'player_state', 'position')}
                if confirms_playback(current, video_id, position, requested_at):
                    report['playback_near_requested_position_observed'] = True
                    return
            time.sleep(2)
    finally:
        cast.disconnect(timeout=10)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', default='192.168.1.6')
    parser.add_argument('--video-id', required=True)
    parser.add_argument('--position', type=float, default=0)
    parser.add_argument('--output', type=pathlib.Path, required=True)
    args = parser.parse_args()
    ipaddress.IPv4Address(args.host)
    if not re.fullmatch(r'[A-Za-z0-9_-]{11}', args.video_id) or not 0 <= args.position <= 86400:
        parser.error('Video ID de 11 caracteres y posición 0–86400 segundos')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    logging.getLogger('pychromecast').setLevel(logging.CRITICAL)
    report = {'time_utc': dt.datetime.now(dt.timezone.utc).isoformat(),
              'host': args.host, 'requested_video_id': args.video_id,
              'requested_position': args.position, 'play_request_completed': False,
              'playback_near_requested_position_observed': False}
    with args.output.open('x', encoding='utf-8') as stream:
        try:
            recover(args.host, args.video_id, args.position, report)
        except KeyboardInterrupt:
            report['interrupted'] = True
        except Exception as error:
            report['error_type'] = type(error).__name__
            if isinstance(error, requests.HTTPError) and error.response is not None:
                report['http_status'] = error.response.status_code
        json.dump(report, stream, indent=2, ensure_ascii=False)
        print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report['playback_near_requested_position_observed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())

