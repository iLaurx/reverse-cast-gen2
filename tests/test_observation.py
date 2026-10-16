import contextlib
import importlib.util
import io
import json
import pathlib
import tempfile
import unittest
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[1]


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


observer = load('observer', 'Observe-Chromecast.py')
recovery = load('recovery', 'Recover-YouTube.py')


class MemoryRecorder:
    def __init__(self):
        self.events = []

    def emit(self, kind, **fields):
        self.events.append({'kind': kind, **fields})

    def reference(self, value):
        return 'local-reference' if value is not None else None


class ObservationTests(unittest.TestCase):
    def test_signed_url_and_custom_values_are_not_logged(self):
        recorder = MemoryRecorder()
        handler = observer.Observer(recorder)
        handler.receive_message(None, {'type': 'MEDIA_STATUS', 'status': [{
            'media': {'contentId': 'https://cdn.example/SECRET?token=SECRET#SECRET',
                      'customData': {'credential': 'SECRET'}},
            'customData': {'private': 'SECRET'},
            'playerState': 'PLAYING', 'currentTime': 100,
        }]})
        self.assertNotIn('SECRET', json.dumps(recorder.events))
        self.assertEqual(recorder.events[0]['content']['host'], 'cdn.example')

    def test_null_media_and_extended_status_are_retained(self):
        recorder = MemoryRecorder()
        handler = observer.Observer(recorder)
        handler.receive_message(None, {'type': 'MEDIA_STATUS', 'status': [{
            'media': None, 'extendedStatus': {'media': {
                'contentId': 'abcdefghijk', 'duration': 600}},
            'customData': None, 'playerState': 'BUFFERING',
        }]})
        self.assertEqual(recorder.events[0]['kind'], 'media')
        self.assertEqual(recorder.events[0]['duration'], 600)

    def test_unexpected_shape_leaves_a_parse_event(self):
        recorder = MemoryRecorder()
        observer.Observer(recorder).receive_message(None, {
            'type': 'MEDIA_STATUS', 'status': ['unexpected', {'media': 'unexpected'}]})
        self.assertEqual([e['kind'] for e in recorder.events], ['parse_issue', 'parse_issue'])

    def test_freshness_identity_and_position_required_for_success(self):
        event = {'video_id': 'abcdefghijk', 'player_state': 'PLAYING',
                 'position': 507, 'observed_monotonic': 12}
        self.assertTrue(recovery.confirms_playback(event, 'abcdefghijk', 506, 10))
        for changed in ({'observed_monotonic': 9}, {'video_id': 'different00'},
                        {'position': 0}, {'position': 550}, {'player_state': 'BUFFERING'}):
            self.assertFalse(recovery.confirms_playback({**event, **changed}, 'abcdefghijk', 506, 10))

    def test_disconnect_discards_old_playback_candidate(self):
        media = recovery.MediaObserver()
        media.latest = {'player_state': 'PLAYING'}
        media.channel_disconnected()
        self.assertIsNone(media.latest)

    def test_interruption_keeps_recovery_report(self):
        with tempfile.TemporaryDirectory(prefix='test-recovery-', dir=ROOT) as folder:
            output = pathlib.Path(folder) / 'report.json'
            argv = ['recover', '--video-id', 'abcdefghijk', '--output', str(output)]
            with patch('sys.argv', argv), patch.object(recovery, 'recover', side_effect=KeyboardInterrupt), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(recovery.main(), 1)
            report = json.loads(output.read_text(encoding='utf-8'))
            self.assertTrue(report['interrupted'])
            self.assertFalse(report['playback_near_requested_position_observed'])


if __name__ == '__main__':
    unittest.main()
