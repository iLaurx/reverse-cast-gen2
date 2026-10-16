import pathlib
import tempfile
import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from fastapi.testclient import TestClient
from app.validation import youtube_url, position, host
from app.store import Store
from app.titles import TitleResolver
from app.cast import CastObserver, CastAdapter
from app.service import Service, ServiceError
from app.web import create_app

VIDEO = 'abcdefghijk'

class URLTests(unittest.TestCase):
    def test_common_links_and_times(self):
        for url in (f'https://youtube.com/watch?v={VIDEO}', f'https://youtu.be/{VIDEO}',
                    f'm.youtube.com/watch?v={VIDEO}&list=ignored', f'https://www.youtube.com/shorts/{VIDEO}',
                    f'https://youtube.com/live/{VIDEO}', f'https://youtube.com/embed/{VIDEO}'):
            with self.subTest(url=url):
                self.assertEqual(youtube_url(url), (VIDEO, 0))
        self.assertEqual(youtube_url(f'https://youtu.be/{VIDEO}?t=1h2m3s')[1], 3723)
        self.assertEqual(youtube_url(f'https://youtube.com/watch?v={VIDEO}&start=506')[1], 506)

    def test_reject_arbitrary_domains_malformed_ids_credentials(self):
        for url in ('https://youtube.com.evil/watch?v='+VIDEO, 'file:///etc/passwd',
                    'https://youtube.com@evil.test/watch?v='+VIDEO,
                    'https://evil@youtube.com/watch?v='+VIDEO,
                    'https://youtube.com:8080/watch?v='+VIDEO,
                    'https://youtu.be/short', 'https://youtu.be/'+VIDEO+'/extra',
                    'https://youtube.com/watch?v='+VIDEO+'&v='+VIDEO,
                    'https://youtube.com/watch?v='+VIDEO+'%0a',
                    'https://youtu.be/'+VIDEO+'?t=nan', 'https://youtu.be/'+VIDEO+'?t=999999'):
            with self.subTest(url=url), self.assertRaises(ValueError):
                youtube_url(url)

    def test_numeric_and_private_ip_validation(self):
        for value in ('nan', 'inf', -1, 86401, True):
            with self.subTest(value=value), self.assertRaises(ValueError): position(value)
        self.assertEqual(host('192.168.1.6'), '192.168.1.6')
        for value in ('127.0.0.1', '8.8.8.8', '169.254.1.1', '224.0.0.1', 'not-an-ip'):
            with self.subTest(value=value), self.assertRaises(ValueError): host(value)

class FakeAdapter:
    def __init__(self, host='192.168.1.6'):
        self.data = {'connection':'CONNECTED', 'receiver':None, 'media':None, 'generation':1, 'error_at':0}
        self.video = VIDEO
        self.position = 120
        self.state = 'PLAYING'
        self.mode = 'normal'
        self.closed = False
        self.plays = []
        self.poll()
    def poll(self):
        if self.mode == 'error': raise TimeoutError('SECRET')
        if self.mode == 'stale': return
        now = time.monotonic()
        self.data['receiver'] = {'app_id':'233637DE', 'app_name':'YouTube', 'observed_monotonic':now}
        self.data['media'] = {'video_id':self.video, 'position':self.position, 'duration':600,
                              'player_state':self.state, 'commands':1, 'media_session_id':9,
                              'ad_detected':self.mode=='ad', 'observed_monotonic':now}
    def snapshot(self):
        return {**self.data, 'media':dict(self.data['media']) if self.data['media'] else None}
    def play(self, video, position):
        self.plays.append((video, position))
        if self.mode != 'wrong': self.video, self.position = video, position
    def control(self, action, media): self.state = 'PAUSED' if action == 'pause' else 'PLAYING'
    def close(self): self.closed = True

class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(dir=pathlib.Path(__file__).resolve().parents[1])
        self.path = pathlib.Path(self.folder.name) / 'history.db'
        self.store = Store(self.path)
        self.service = Service(self.store, FakeAdapter, confirmation_timeout=.2, confirmation_stability=0, title_resolver=TitleResolver(fetcher=lambda _: None))
        self.adapter = FakeAdapter()
        self.service.adapter = self.adapter
    def tearDown(self):
        self.service.close(); self.store.close(); self.folder.cleanup()
    def save(self):
        media = self.adapter.snapshot()['media']
        return self.service.execute('save', {'content_confirmed':True, 'video_id':media['video_id'], 'position':media['position']})
    def test_history_and_host_survive_restart(self):
        self.save()
        self.store.set_host('192.168.1.7')
        other = Store(self.path)
        try:
            self.assertEqual(other.checkpoint()['position'],120)
            self.assertEqual(other.history()[0]['video_id'], VIDEO)
            self.assertEqual(other.get_host(), '192.168.1.7')
        finally: other.close()
    def test_uncertain_ads_zero_disconnect_backdrop_never_erase_point(self):
        self.save(); original = self.store.checkpoint()
        for mode in ('ad', 'stale', 'error'):
            self.adapter.mode=mode
            if mode == 'stale': self.adapter.data['media']['observed_monotonic'] -= 30
            elif mode == 'ad': self.adapter.poll()
            try: self.service.execute('play', {'url':f'https://youtu.be/{VIDEO}', 'position':0})
            except ServiceError: pass
            self.assertEqual(self.store.checkpoint(), original)
        for raw in ({'connection':'DISCONNECTED','receiver':None,'media':None},
                    {'connection':'CONNECTED','receiver':{'app_id':'E8C28D3C','app_name':'Backdrop','observed_monotonic':time.monotonic()},'media':None}):
            self.adapter.data=raw
            self.assertTrue(self.service.status()['stale'])
            self.assertEqual(self.store.checkpoint(), original)
        self.assertEqual(len(self.adapter.plays),3)  # No automatic play from state reads.
    def test_save_requires_recent_nonzero_main_content_confirmation(self):
        with self.assertRaises(ServiceError): self.service.execute('save', {})
        self.adapter.position=0;self.adapter.poll()
        with self.assertRaises(ServiceError): self.save()
        self.adapter.position=100;self.adapter.mode='ad';self.adapter.poll()
        with self.assertRaises(ServiceError): self.save()
        self.adapter.mode='normal';self.adapter.poll()
        self.adapter.data['media']['observed_monotonic'] -= 20
        with self.assertRaises(ServiceError): self.save()
        self.assertIsNone(self.store.checkpoint())
    def test_confirmed_recovery_uses_persisted_point(self):
        self.save();self.adapter.position=0
        result=self.service.execute('recover', {})
        self.assertTrue(result['confirmed'])
        self.assertEqual(self.adapter.plays, [(VIDEO,120)])
        self.assertEqual(self.store.checkpoint()['position'],120)
    def test_stale_wrong_video_ad_and_error_do_not_confirm(self):
        self.save()
        for mode in ('stale','wrong','ad','error'):
            self.adapter=FakeAdapter();self.service.adapter=self.adapter
            self.adapter.video='different00';self.adapter.poll();self.adapter.mode=mode
            if mode == 'stale': self.adapter.data['media']['observed_monotonic'] -= 30
            with self.subTest(mode=mode):
                try: self.assertFalse(self.service.execute('recover', {})['confirmed'])
                except ServiceError: self.assertEqual(mode, 'error')
            self.assertEqual(self.store.checkpoint()['position'], 120)
    def test_pause_resume_require_capability_and_fresh_response(self):
        self.assertTrue(self.service.execute('pause', {})['confirmed'])
        self.assertEqual(self.adapter.state, 'PAUSED')
        self.assertTrue(self.service.execute('resume', {})['confirmed'])
        self.adapter.data['media']['commands']=0
        with self.assertRaises(ServiceError): self.service.execute('pause', {})
    def test_save_binds_displayed_point_and_rejects_large_changes(self):
        self.service.execute('save', {'content_confirmed':True,'video_id':VIDEO,'position':118})
        self.assertEqual(self.store.checkpoint()['position'],118)
        with self.assertRaises(ServiceError):
            self.service.execute('save', {'content_confirmed':True,'video_id':VIDEO,'position':10})
        self.assertEqual(self.store.checkpoint()['position'],118)

    def test_same_video_at_wrong_position_uses_one_supported_seek(self):
        self.adapter.mode='stale'
        self.adapter.data['media']['commands']=3
        # Make each poll fresh while setPlaylist intentionally retains the old time.
        self.adapter.play=Mock()
        def poll():
            self.adapter.data['media']['observed_monotonic']=time.monotonic()
            self.adapter.data['receiver']['observed_monotonic']=time.monotonic()
        self.adapter.poll=poll
        def seek(media, position):
            self.adapter.data['media']['position']=position
        self.adapter.seek=Mock(side_effect=seek)
        self.service.timeout=1.4
        self.assertTrue(self.service.execute('play', {'url':'https://youtu.be/'+VIDEO,'position':506})['confirmed'])
        self.adapter.seek.assert_called_once()
        self.assertEqual(self.adapter.data['media']['position'],506)

    def test_transient_position_is_not_success_when_stability_required(self):
        self.service.stability=.12
        self.service.timeout=.25
        self.adapter.play=Mock()
        samples=[]
        def poll():
            now=time.monotonic()
            samples.append(now)
            self.adapter.data['receiver']['observed_monotonic']=now
            self.adapter.data['media']['observed_monotonic']=now
            self.adapter.data['media']['position']=506 if len(samples)==1 else 1800
        self.adapter.poll=poll
        self.assertFalse(self.service.execute('play',{'url':'https://youtu.be/'+VIDEO,'position':506})['confirmed'])

    def test_multiple_fresh_positions_confirm_sustained_playback(self):
        self.service.stability=.12
        self.service.timeout=.4
        self.assertTrue(self.service.execute('play',{'url':'https://youtu.be/'+VIDEO,'position':506})['confirmed'])

    def test_serialization_rejects_overlapping_commands(self):
        with self.service.operation:
            with self.assertRaises(ServiceError): self.service.execute('play', {'url':'https://youtu.be/'+VIDEO})
        self.assertFalse(self.adapter.plays)
    def test_host_switch_closes_old_connection_without_playing(self):
        self.save()
        self.service.execute('host', {'host':'192.168.1.7'})
        self.assertTrue(self.adapter.closed)
        self.assertIsNone(self.service.adapter)
        self.assertEqual(self.store.get_host(), '192.168.1.7')
        self.assertIsNotNone(self.store.checkpoint())
    def test_poll_worker_single_connection_and_clean_shutdown(self):
        factory=Mock(return_value=FakeAdapter())
        service=Service(self.store, factory)
        service.start()
        for _ in range(100):
            if service.adapter: break
            time.sleep(.001)
        service.close()
        self.assertEqual(factory.call_count,1)
        self.assertFalse(service.thread.is_alive())
        self.assertTrue(factory.return_value.closed)
    def test_library_error_is_redacted(self):
        self.adapter.mode='error'
        with self.assertRaises(ServiceError) as error: self.service.execute('pause', {})
        self.assertNotIn('SECRET',str(error.exception))

class ObserverTests(unittest.TestCase):
    def test_empty_partial_ad_and_application_change(self):
        observer=CastObserver()
        observer.new_cast_status(SimpleNamespace(app_id='233637DE',display_name='YouTube',session_id='private',transport_id='private'))
        observer.receive_message(None, {'type':'MEDIA_STATUS','status':[{'currentTime':120,'playerState':'PLAYING','media':{'contentId':VIDEO},'breakStatus':{}}]})
        self.assertTrue(observer.snapshot()['media']['ad_detected'])
        observer.receive_message(None, {'type':'MEDIA_STATUS','status':[{'currentTime':0}]})
        self.assertIsNone(observer.snapshot()['media'])
        observer.new_cast_status(SimpleNamespace(app_id='E8C28D3C',display_name='Backdrop',session_id='other',transport_id='other'))
        self.assertIsNone(observer.snapshot()['media'])
    def test_poll_only_queries_existing_channel(self):
        adapter=object.__new__(CastAdapter);adapter.cast=Mock()
        adapter.cast.socket_client.app_namespaces=[]
        adapter.poll()
        adapter.cast.socket_client.send_app_message.assert_not_called()
        adapter.cast.start_app.assert_not_called()
        adapter.cast.socket_client.app_namespaces=['urn:x-cast:com.google.cast.media']
        adapter.poll()
        adapter.cast.socket_client.send_app_message.assert_called_once_with('urn:x-cast:com.google.cast.media',{'type':'GET_STATUS'})

class APITests(unittest.TestCase):
    def setUp(self):
        self.service=Mock()
        self.service.status.return_value={'connection':'CONNECTED'}
        self.service.execute.return_value={'confirmed':True}
    def test_auth_origin_host_and_json_guards(self):
        with TestClient(create_app(self.service,token='test-key')) as client:
            self.assertEqual(client.get('/api/state',headers={'host':'localhost'}).status_code,401)
            headers={'host':'localhost','x-cast-key':'test-key'}
            self.assertEqual(client.get('/api/state',headers=headers).status_code,200)
            self.assertEqual(client.get('/api/state',headers={**headers,'origin':'https://evil.test'}).status_code,403)
            self.assertEqual(client.get('/api/state',headers={**headers,'host':'evil.test'}).status_code,403)
            self.assertEqual(client.post('/api/pause',headers=headers,content='{}').status_code,415)
            self.assertEqual(client.post('/api/play',headers=headers,json={'url':'x','position':-1}).status_code,422)
            self.assertEqual(client.post('/api/pause',headers=headers,json={}).status_code,200)
            self.assertEqual(client.post('/api/pause',headers={**headers,'content-length':'5000'},json={}).status_code,413)
            self.assertEqual(client.get('/',headers={'host':'localhost'}).status_code,200)
            self.assertIn("default-src 'self'",client.get('/',headers={'host':'localhost'}).headers['content-security-policy'])
        self.service.start.assert_called_once();self.service.close.assert_called_once()
    def test_remote_requires_key_even_if_host_allowed(self):
        with TestClient(create_app(self.service,token='',allowed_hosts=['192.168.1.5']),client=('192.168.1.10',123)) as client:
            self.assertEqual(client.get('/',headers={'host':'192.168.1.5'}).status_code,403)
    def test_control_failure_exposed_as_conflict(self):
        self.service.execute.side_effect=ServiceError('No hay estado reciente.')
        with TestClient(create_app(self.service,token='')) as client:
            response=client.post('/api/pause',headers={'host':'localhost'},json={})
            self.assertEqual(response.status_code,409)
            self.assertEqual(response.json()['detail'],'No hay estado reciente.')

if __name__ == '__main__': unittest.main()
