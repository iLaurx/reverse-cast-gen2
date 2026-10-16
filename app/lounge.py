"""Bounded Lounge requests shared by the local panel and the Render relay."""
import requests
from casttube import YouTubeSession
from casttube.YouTubeSession import BIND_URL, HEADERS, LOUNGE_TOKEN_URL, LOUNGE_ID_HEADER


class LoungeSession(YouTubeSession):
    def _do_post(self, url, data=None, params=None, headers=None, session_request=False):
        # Never replay an uncertain command or follow a redirect with credentials.
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

    def skip_ad(self, still_current=lambda: True):
        # Binding attaches a remote; it does not initialize or replace the queue.
        self._start_session()
        if not still_current():
            raise RuntimeError('La sesión cambió antes de enviar la orden.')
        self._do_post(BIND_URL,
                      data=self._format_session_params({'__sc': 'skipAd', 'count': 1}),
                      params={'SID': self._sid, 'gsessionid': self._gsession_id,
                              'RID': self._rid, 'VER': 8, 'CVER': 1},
                      headers={LOUNGE_ID_HEADER: self._lounge_token}, session_request=True)
