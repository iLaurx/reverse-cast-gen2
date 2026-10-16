import threading
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from app.cast import CastObserver
from app.titles import TitleResolver, fetch_title

VIDEO = 'abcdefghijk'
OTHER = 'different00'

class TitleTests(unittest.TestCase):
    def test_native_title_never_needs_network(self):
        fetcher = Mock()
        resolver = TitleResolver(fetcher)
        try:
            self.assertEqual(resolver.get(VIDEO, '  Un título\ncon espacios  '), 'Un título con espacios')
            self.assertEqual(resolver.get(VIDEO), 'Un título con espacios')
            fetcher.assert_not_called()
        finally:
            resolver.close()

    def test_pending_lookup_does_not_block_and_is_deduplicated(self):
        entered, release = threading.Event(), threading.Event()
        calls = []
        def fetcher(video):
            calls.append(video)
            entered.set()
            release.wait(2)
            return 'Título de YouTube'
        resolver = TitleResolver(fetcher)
        try:
            self.assertIsNone(resolver.get(VIDEO))
            self.assertTrue(entered.wait(1))
            # The worker remains blocked while both reads return immediately.
            self.assertIsNone(resolver.get(VIDEO))
            self.assertIsNone(resolver.get(VIDEO))
        finally:
            release.set()
            resolver.close()
        self.assertEqual(resolver.get(VIDEO), 'Título de YouTube')
        self.assertEqual(calls, [VIDEO])
        self.assertIsNone(resolver.get(OTHER))  # Never reuse a different video's title.

    def test_failures_are_cached_and_do_not_escape(self):
        fetcher = Mock(side_effect=TimeoutError('PRIVATE'))
        resolver = TitleResolver(fetcher)
        self.assertIsNone(resolver.get(VIDEO))
        resolver.close()
        self.assertIsNone(resolver.get(VIDEO))
        self.assertIn(VIDEO, resolver.cache)
        self.assertEqual(fetcher.call_count, 1)

    def test_native_metadata_wins_over_pending_web_lookup(self):
        release = threading.Event()
        resolver = TitleResolver(lambda _: (release.wait(2), 'Web title')[1])
        try:
            resolver.get(VIDEO)
            self.assertEqual(resolver.get(VIDEO, 'Título del Chromecast'), 'Título del Chromecast')
        finally:
            release.set()
            resolver.close()
        self.assertEqual(resolver.get(VIDEO), 'Título del Chromecast')

    def test_invalid_id_never_fetches(self):
        fetcher = Mock()
        resolver = TitleResolver(fetcher)
        try:
            self.assertIsNone(resolver.get('https://example.org/private'))
            self.assertIsNone(fetch_title('https://example.org/private'))
            fetcher.assert_not_called()
        finally:
            resolver.close()

    def test_cast_title_is_not_retained_for_another_video(self):
        observer = CastObserver()
        observer.new_cast_status(SimpleNamespace(app_id='233637DE', display_name='YouTube',
                                                  session_id='session', transport_id='transport'))
        def receive(video, metadata):
            observer.receive_message(None, {'type':'MEDIA_STATUS','status':[
                {'media':{'contentId':video,'metadata':metadata},'playerState':'PLAYING'}]})
        receive(VIDEO, {'title':'Nombre real'})
        self.assertEqual(observer.snapshot()['media']['title'], 'Nombre real')
        receive(OTHER, None)
        self.assertIsNone(observer.snapshot()['media']['title'])

if __name__ == '__main__':
    unittest.main()
