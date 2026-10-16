export const MDX = 'urn:x-cast:com.google.youtube.mdx';
export const RELAY = 'https://reverse-cast-relay.onrender.com';

export function screenId(session, stillCurrent = () => true) {
  return new Promise((resolve, reject) => {
    let done = false;
    const finish = (error, id) => {
      if (done) return;
      done = true; clearTimeout(timer);
      try { session.removeMessageListener(MDX, receive); } catch { /* A disconnected session may have removed it already. */ }
      error ? reject(error) : resolve(id);
    };
    const receive = (_, raw) => {
      if (!stillCurrent()) return finish({code: 'session_changed'});
      let msg;
      try { msg = typeof raw === 'string' ? JSON.parse(raw) : raw; } catch { return; }
      if (msg?.type !== 'mdxSessionStatus') return;
      const id = msg.data?.screenId;
      if (typeof id === 'string' && /^[A-Za-z0-9_-]{1,256}$/.test(id)) finish(null, id);
    };
    const timer = setTimeout(() => finish({code: 'youtube_session_timeout'}), 12000);
    try {
      session.addMessageListener(MDX, receive);
      Promise.resolve(session.sendMessage(MDX, {type: 'getMdxSessionStatus'})).catch(error => finish(error));
    } catch (error) { finish(error); }
  });
}

export async function playYouTube(session, id, position, stillCurrent = () => true) {
  // Wake the free Render service before asking for a fresh receiver capability.
  const abort = new AbortController();
  const timer = setTimeout(() => abort.abort(), 90000);
  try {
    const wake = await fetch(`${RELAY}/health`, {signal: abort.signal, cache: 'no-store'});
    if (!wake.ok) throw {code: 'relay_unavailable'};
    if (!stillCurrent()) throw {code: 'session_changed'};
    const screen_id = await screenId(session, stillCurrent);
    if (!stillCurrent()) throw {code: 'session_changed'};
    const response = await fetch(`${RELAY}/api/youtube/play`, {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({screen_id, video_id: id, position}), signal: abort.signal,
      credentials: 'omit', cache: 'no-store',
    });
    if (!response.ok) throw {code: response.status === 429 ? 'wait_before_retry' : 'youtube_relay_failed'};
    if (!stillCurrent()) throw {code: 'session_changed'};
  } catch (error) {
    if (error?.name === 'AbortError') throw {code: 'relay_timeout_check_tv'};
    throw error;
  } finally { clearTimeout(timer); }
}
