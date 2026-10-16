import {STORAGE_KEY, youtubeInput, validCheckpoint, adDetected} from './core.mjs';
import {playYouTube, skipYouTubeAd} from './youtube.mjs';
const $ = id => document.getElementById(id);
const fmt = n => Number.isFinite(n) ? `${Math.floor(n / 60)}:${String(Math.floor(n % 60)).padStart(2, '0')}` : '—';
let context, ready = false, busy = false, observed = null, checkpoint = null, polling = false;
let generation = 0;
const session = () => context?.getCurrentSession();
const say = text => { $('feedback').textContent = text; };
function log(text) {
  const item = document.createElement('li'); item.textContent = text;
  $('diagnostics').prepend(item);
  while ($('diagnostics').children.length > 8) $('diagnostics').lastChild.remove();
}
try { const p = JSON.parse(localStorage.getItem(STORAGE_KEY)); if (validCheckpoint(p)) checkpoint = p; } catch { /* Storage may be disabled. */ }
function current() {
  const s = session();
  return observed && observed.session === s && observed.media === s?.getMediaSession() && Date.now() - observed.at < 10000 ? observed : null;
}
function render() {
  const s = session(), o = current(), m = o?.media;
  $('connect').disabled = !ready || busy || !!s;
  $('disconnect').disabled = !s || busy;
  $('load').disabled = !s || busy;
  $('connection').textContent = s ? s.getCastDevice().friendlyName : 'Sin sesión';
  $('player').textContent = m?.playerState || 'Sin datos recientes';
  $('current-video').textContent = m?.media?.metadata?.title || m?.media?.contentId || 'Sin video identificado';
  $('time').textContent = fmt(o?.position); $('duration').textContent = fmt(m?.media?.duration);
  $('progress').style.width = m?.media?.duration > 0 ? `${Math.min(100, 100 * o.position / m.media.duration)}%` : '0%';
  $('freshness').textContent = o ? 'Estado recibido del Chromecast' : 'Sin estado reciente; controles deshabilitados';
  const canPause = !!m?.supportsCommand(chrome.cast.media.MediaCommand.PAUSE);
  $('pause').disabled = busy || !canPause || m.playerState !== 'PLAYING';
  $('resume').disabled = busy || !canPause || m.playerState !== 'PAUSED';
  $('skip-ad').disabled = busy || !s;
  $('ad-status').textContent = adDetected(m)
    ? 'Anuncio detectado. Puedes solicitar que se omita cuando YouTube lo permita.'
    : 'Cuando aparezca «Omitir anuncio» en la TV, pulsa el botón. Algunos anuncios no se pueden omitir.';
  const id = m?.media?.contentId;
  const recognized = /^[A-Za-z0-9_-]{11}$/.test(id || '');
  $('save').disabled = busy || adDetected(m) || !recognized || !o || !(o.position > 0 && o.position <= 86400) || !['PLAYING', 'PAUSED'].includes(m.playerState);
  $('recover').disabled = busy || !s || !checkpoint;
  $('clear').disabled = !checkpoint;
  $('checkpoint').textContent = checkpoint ? `${checkpoint.id} · ${fmt(checkpoint.position)}` : 'Todavía no guardaste un punto.';
}
function code(error) { return String(error?.code || (typeof error === 'string' ? error : 'error')).replace(/[^a-zA-Z0-9_-]/g, '').slice(0, 60); }
async function operation(fn) {
  if (busy) return;
  busy = true; render();
  try { await fn(); } catch (e) { say(`No se completó la orden (${code(e)}). Revisa la TV antes de repetir.`); log(`Orden rechazada o sin confirmar: ${code(e)}.`); }
  finally { busy = false; render(); }
}
function callbackCall(invoke) {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject({code: 'timeout'}), 15000);
    invoke(() => { clearTimeout(timer); resolve(); }, error => { clearTimeout(timer); reject(error); });
  });
}
async function poll() {
  if (polling) return;
  const s = session(), media = s?.getMediaSession(), g = generation;
  if (!media) { observed = null; render(); return; }
  polling = true;
  try {
    await callbackCall((ok, fail) => media.getStatus(null, ok, fail));
    if (s === session() && g === generation && media === s.getMediaSession()) observed = {session: s, media, at: Date.now(), position: media.currentTime};
  } catch { observed = null; }
  finally { polling = false; render(); }
}
async function load(id, time) {
  const s = session(); if (!s) throw Error('No hay sesión');
  const g = generation;
  observed = null;
  say('Conectando con YouTube… El primer envío puede tardar hasta un minuto y medio.');
  await playYouTube(s, id, time, () => s === session() && g === generation);
  log('Orden enviada mediante la sesión YouTube.');
  if (s !== session() || g !== generation) return;
  await poll();
  const o = current();
  if (o?.media.media?.contentId === id && !adDetected(o.media) && o.media.playerState === 'PLAYING' && Math.abs(o.position - time) <= 10) {
    say('El receptor reporta el video en reproducción cerca del punto solicitado. Confírmalo en la TV.'); log('Receptor reporta video y posición solicitados.');
  } else { say('Orden aceptada; video y posición todavía sin confirmar. Revisa la TV.'); log('Orden aceptada sin confirmar reproducción ni posición.'); }
}
$('connect').onclick = () => {
  operation(async () => { await context.requestSession(); log('Sesión Cast abierta.'); say('Conectado. Ahora puedes probar la reproducción.'); });
};
$('disconnect').onclick = () => { context.endCurrentSession(false); observed = null; generation++; render(); };
$('skip-ad').onclick = () => operation(async () => {
  const s = session(), g = generation;
  if (!s) throw {code: 'session_changed'};
  say('Solicitando omitir anuncio… El servicio puede tardar en activarse.');
  await skipYouTubeAd(s, () => s === session() && g === generation);
  say('Solicitud enviada. Comprueba la TV; YouTube decide si el anuncio se puede omitir.');
  log('Solicitud de omitir anuncio enviada; resultado en la TV sin confirmar.');
  await poll();
});
$('play-form').onsubmit = e => { e.preventDefault(); operation(async () => {
  const p = youtubeInput($('url').value.trim(), $('position').value);
  await load(p.id, p.position);
}); };
for (const action of ['pause', 'resume']) $(action).onclick = () => operation(async () => {
  const o = current(); if (!o) throw {code: 'stale_status'};
  const expected = action === 'pause' ? 'PAUSED' : 'PLAYING';
  await callbackCall((ok, fail) => action === 'pause' ? o.media.pause(null, ok, fail) : o.media.play(null, ok, fail));
  await poll();
  say(current()?.media.playerState === expected ? 'El receptor confirma el cambio. Compruébalo en la TV.' : 'Orden aceptada, estado todavía sin confirmar.');
});
$('save').onclick = () => {
  const o = current(); if (!o || $('save').disabled) return;
  const p = {mode: 'youtube', id: o.media.media.contentId, position: o.position};
  if (!validCheckpoint(p)) return;
  try { localStorage.setItem(STORAGE_KEY, JSON.stringify(p)); checkpoint = p; say('Punto guardado en este navegador.'); }
  catch { say('El navegador no permite guardar el punto. No se guardó.'); }
  render();
};
$('recover').onclick = () => operation(() => load(checkpoint.id, checkpoint.position));
$('clear').onclick = () => {
  try { localStorage.removeItem(STORAGE_KEY); checkpoint = null; render(); } catch { say('No se pudo borrar el punto.'); }
};
window.__onGCastApiAvailable = available => {
  if (!available) { $('sdk-status').textContent = 'Google Cast no está disponible en este navegador. Prueba Chrome compatible con Cast.'; return; }
  context = cast.framework.CastContext.getInstance(); ready = true;
  context.addEventListener(cast.framework.CastContextEventType.SESSION_STATE_CHANGED, () => { generation++; observed = null; render(); poll(); });
  context.addEventListener(cast.framework.CastContextEventType.CAST_STATE_CHANGED, () => {
    $('sdk-status').textContent = context.getCastState() === cast.framework.CastState.NO_DEVICES_AVAILABLE ? 'No se detectan dispositivos. Revisa la Wi-Fi, los permisos de red local y que Chromecast esté encendido.' : 'Google Cast disponible. Selecciona tu Chromecast.';
  });
  context.setOptions({receiverApplicationId: '233637DE', autoJoinPolicy: chrome.cast.AutoJoinPolicy.PAGE_SCOPED});
  render(); $('sdk-status').textContent = 'Listo para conectar con tu Chromecast.';
};
render();
if (!window.isSecureContext) $('sdk-status').textContent = 'Abre esta web mediante HTTPS o localhost para usar Cast.';
else {
  const script = document.createElement('script');
  script.src = 'https://www.gstatic.com/cv/js/sender/v1/cast_sender.js?loadCastFramework=1';
  script.onerror = () => { $('sdk-status').textContent = 'No se pudo cargar Google Cast. Comprueba la conexión o los bloqueadores.'; };
  document.head.append(script);
  setTimeout(() => { if (!ready) $('sdk-status').textContent = 'Cast no está disponible. Usa Chrome compatible, fuera del navegador integrado de otra app.'; }, 15000);
}
setInterval(() => { render(); poll(); }, 2500);
