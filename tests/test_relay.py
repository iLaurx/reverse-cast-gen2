import unittest
from unittest.mock import patch, Mock
from fastapi.testclient import TestClient
from app import relay


class RelayTests(unittest.TestCase):
    def setUp(self):
        relay.recent.clear()
        self.client = TestClient(relay.api)
        self.headers = {'origin': relay.ORIGIN}
        self.body = {'screen_id': 'simulated-screen', 'video_id': 'abcdefghijk', 'position': 90}

    def test_origin_json_size_and_validation_hide_capabilities(self):
        self.assertEqual(self.client.post('/api/youtube/play', json=self.body).status_code, 403)
        self.assertEqual(self.client.post('/api/youtube/play', headers=self.headers, content='x').status_code, 415)
        self.assertEqual(self.client.post('/api/youtube/play', headers={**self.headers, 'content-type': 'application/json'}, content='x' * 2049).status_code, 413)
        bad = {**self.body, 'screen_id': 'PRIVATE.invalid'}
        result = self.client.post('/api/youtube/play', headers=self.headers, json=bad)
        self.assertEqual(result.status_code, 422)
        self.assertNotIn('PRIVATE', result.text)

    @patch('app.relay.LoungeSession')
    def test_one_explicit_play_with_position_and_throttle(self, factory):
        result = self.client.post('/api/youtube/play', headers=self.headers, json=self.body)
        self.assertEqual(result.status_code, 200)
        factory.return_value.play_video.assert_called_once_with('abcdefghijk', start_time='90.0')
        self.assertNotIn('simulated-screen', result.text)
        self.assertEqual(result.headers['access-control-allow-origin'], relay.ORIGIN)
        self.assertEqual(self.client.post('/api/youtube/play', headers=self.headers, json=self.body).status_code, 429)
        self.assertEqual(factory.call_count, 1)

    @patch('app.relay.LoungeSession')
    def test_upstream_error_is_redacted_and_never_retried(self, factory):
        factory.return_value.play_video.side_effect = RuntimeError('PRIVATE-session-token')
        result = self.client.post('/api/youtube/play', headers=self.headers, json=self.body)
        self.assertEqual(result.status_code, 502)
        self.assertNotIn('PRIVATE', result.text)
        self.assertEqual(factory.return_value.play_video.call_count, 1)

    @patch('app.relay.requests.post')
    def test_upstream_urls_timeouts_and_redirects(self, post):
        post.return_value = Mock(status_code=200)
        session = relay.LoungeSession('simulated-screen')
        session._do_post(relay.BIND_URL)
        self.assertEqual(post.call_args.kwargs['timeout'], (5, 10))
        self.assertFalse(post.call_args.kwargs['allow_redirects'])
        with self.assertRaises(ValueError):
            session._do_post('http://192.168.1.6/')
        self.assertEqual(post.call_count, 1)

    def test_health_and_browser_preflight(self):
        self.assertEqual(self.client.get('/health').status_code, 200)
        response = self.client.options('/api/youtube/play', headers={**self.headers, 'access-control-request-method': 'POST', 'access-control-request-headers': 'content-type'})
        self.assertEqual(response.status_code, 200)


if __name__ == '__main__':
    unittest.main()
