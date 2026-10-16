import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import vm from 'node:vm';
import * as core from '../web-cast/core.mjs';
import {playYouTube, MDX} from '../web-cast/youtube.mjs';

test('YouTube links and explicit zero preserve requested position', () => {
  for (const url of ['https://youtu.be/abcdefghijk?t=1m30s', 'https://www.youtube.com/watch?v=abcdefghijk&start=90', 'https://youtube.com/shorts/abcdefghijk?t=90']) {
    assert.deepEqual(core.youtubeInput(url), {id: 'abcdefghijk', position: 90});
    assert.equal(core.youtubeInput(url, '0').position, 0);
  }
});
test('reject misleading domains, credentials, invalid IDs and nonfinite positions', () => {
  for (const url of ['https://youtube.com.evil/watch?v=abcdefghijk', 'https://user:pass@youtube.com/watch?v=abcdefghijk', 'https://youtube.com/watch?v=abc', 'https://youtu.be/abcdefghijk?t=NaN']) assert.throws(() => core.youtubeInput(url));
  for (const p of [-1, Infinity, NaN, 86401]) assert.throws(() => core.position(p));
});
test('saved points accept only the expected receiver and content', () => {
  assert.ok(core.validCheckpoint({mode: 'youtube', id: 'abcdefghijk', position: 12}));
  assert.equal(core.validCheckpoint({mode: 'demo', id: 'https://example.com/video.mp4', position: 12}), false);
  for (const p of [{mode: 'demo', id: 'https://evil.example/video.mp4', position: 12}, {mode: 'youtube', id: 'abcdefghijk', position: 0}, {mode: 'youtube', id: 'abcdefghijk', position: '12'}]) assert.equal(core.validCheckpoint(p), false);
});

async function harness({storageBlocked = false} = {}) {
  const elements = new Map();
  function el(id) {
    if (!elements.has(id)) elements.set(id, {value: id === 'mode' ? 'demo' : '', textContent: '', disabled: false, style: {}, children: [], prepend(item) { this.children.unshift(item); }, remove() {}});
    return elements.get(id);
  }
  const timers = [], intervals = [], listeners = {}, storage = new Map();
  let active = null, loads = 0, relays = 0, rejectLoad = false, getterFails = false;
  const media = {media: {contentId: 'abcdefghijk', duration: 600}, currentTime: 50, playerState: 'PLAYING', supportsCommand: () => true,
    getStatus(_, ok, fail) { getterFails ? fail({code: 'timeout'}) : ok(); },
    pause(_, ok) { this.playerState = 'PAUSED'; ok(); }, play(_, ok) { this.playerState = 'PLAYING'; ok(); }};
  const castSession = {getCastDevice: () => ({friendlyName: 'Receptor simulado'}), getMediaSession: () => media,
    async loadMedia() { loads++; if (rejectLoad) throw {code: 'load_media_failed'}; }};
  const context = {getCurrentSession: () => active, setOptions() {}, getCastState: () => 'AVAILABLE',
    addEventListener(event, callback) { listeners[event] = callback; }, async requestSession() { active = castSession; listeners.session(); },
    endCurrentSession(stop) { assert.equal(stop, false); active = null; listeners.session(); }};
  const sandbox = { ...core, console, URL, Date, setTimeout(fn) { timers.push(fn); return timers.length; }, clearTimeout() {}, setInterval(fn) { intervals.push(fn); },
    async playYouTube() { relays++; if (rejectLoad) throw {code: 'youtube_relay_failed'}; },
    confirm: () => { throw Error('Unexpected popup'); }, localStorage: {getItem: k => storage.get(k), setItem(k, v) { if (storageBlocked) throw Error(); storage.set(k, v); }, removeItem: k => storage.delete(k)},
    document: {getElementById: el, createElement: () => ({}), head: {append() {}}},
    chrome: {cast: {AutoJoinPolicy: {PAGE_SCOPED: 'PAGE'}, media: {DEFAULT_MEDIA_RECEIVER_APP_ID: 'DEFAULT', MediaCommand: {PAUSE: 'pause'}, MediaInfo: function(id, type) { this.contentId = id; this.contentType = type; }, LoadRequest: function(info) { this.media = info; }}}},
    cast: {framework: {CastContext: {getInstance: () => context}, CastContextEventType: {SESSION_STATE_CHANGED: 'session', CAST_STATE_CHANGED: 'cast'}, CastState: {NO_DEVICES_AVAILABLE: 'NONE'}}}};
  sandbox.window = sandbox; sandbox.isSecureContext = true;
  const source = (await readFile(new URL('../web-cast/app.mjs', import.meta.url), 'utf8')).replace(/^import .*;\r?\n/gm, '');
  vm.runInNewContext(source, sandbox);
  const tick = async () => { for (let i = 0; i < 12; i++) await Promise.resolve(); };
  const connect = async () => { sandbox.__onGCastApiAvailable(true); el('connect').onclick(); await tick(); };
  return {el, sandbox, tick, connect, timers, intervals, media, storage, loads: () => loads, relays: () => relays, failLoad() { rejectLoad = true; }, failStatus() { getterFails = true; }};
}
test('unavailable SDK keeps all playback controls disabled', async () => {
  const h = await harness(); h.sandbox.__onGCastApiAvailable(false);
  for (const id of ['connect', 'load', 'pause', 'resume', 'save', 'recover']) assert.equal(h.el(id).disabled, true);
});
test('fresh receiver status enables pause; disconnect disables control without stopping TV', async () => {
  const h = await harness(); await h.connect(); assert.equal(h.el('pause').disabled, false);
  h.el('pause').onclick(); await h.tick(); assert.equal(h.media.playerState, 'PAUSED'); assert.equal(h.el('resume').disabled, false);
  h.el('disconnect').onclick(); assert.equal(h.el('save').disabled, true); assert.equal(h.el('pause').disabled, true);
});
test('status failure removes stale controls and preserves manually saved point', async () => {
  const h = await harness(); await h.connect(); h.el('save').onclick();
  assert.equal(h.storage.size, 1); h.failStatus(); h.intervals[0](); await h.tick();
  assert.equal(h.el('save').disabled, true); assert.equal(h.el('pause').disabled, true); assert.equal(h.storage.size, 1);
});
test('rejected YouTube load is reported once and never saved as success', async () => {
  const h = await harness(); h.el('mode').value = 'youtube'; await h.connect(); h.failLoad(); h.el('url').value = 'https://youtu.be/abcdefghijk';
  h.el('play-form').onsubmit({preventDefault() {}}); await h.tick();
  assert.equal(h.loads(), 0); assert.equal(h.relays(), 1); assert.match(h.el('feedback').textContent, /No se completó/); assert.equal(h.storage.size, 0);
});
test('storage denial is reported without claiming point was saved', async () => {
  const h = await harness({storageBlocked: true}); await h.connect(); h.el('save').onclick();
  assert.match(h.el('feedback').textContent, /No se guardó/); assert.equal(h.el('recover').disabled, true);
});

test('YouTube negotiates fresh MDX then posts only to the relay', async () => {
  const originalFetch = globalThis.fetch, calls = [];
  let listener, removed = false;
  const s = {addMessageListener(ns, fn) { assert.equal(ns, MDX); listener = fn; }, removeMessageListener() { removed = true; },
    async sendMessage(ns, body) { assert.equal(body.type, 'getMdxSessionStatus'); listener(ns, JSON.stringify({type: 'mdxSessionStatus', data: {screenId: 'simulated-screen'}})); }};
  globalThis.fetch = async (url, options) => { calls.push({url, options}); return {ok: true}; };
  try {
    await playYouTube(s, 'abcdefghijk', 90);
    assert.equal(removed, true); assert.equal(calls.length, 2);
    assert.ok(calls[0].url.endsWith('/health'));
    assert.ok(calls[1].url.endsWith('/api/youtube/play'));
    assert.deepEqual(JSON.parse(calls[1].options.body), {screen_id: 'simulated-screen', video_id: 'abcdefghijk', position: 90});
  } finally { globalThis.fetch = originalFetch; }
});
test('disconnect during MDX prevents sending a command to an old session', async () => {
  const originalFetch = globalThis.fetch;
  let alive = true, listener, posts = 0;
  const s = {addMessageListener(ns, fn) { listener = fn; }, removeMessageListener() {},
    async sendMessage(ns) { alive = false; listener(ns, {type: 'mdxSessionStatus', data: {screenId: 'simulated-screen'}}); }};
  globalThis.fetch = async (_, options) => { if (options.method === 'POST') posts++; return {ok: true}; };
  try { await assert.rejects(playYouTube(s, 'abcdefghijk', 0, () => alive), e => e.code === 'session_changed'); assert.equal(posts, 0); }
  finally { globalThis.fetch = originalFetch; }
});
