export const STORAGE_KEY = 'cast-web-checkpoint-v1';
export function adDetected(media) {
  return media?.breakStatus != null || media?.adBreakStatus != null || media?.media?.isPlayingAd === true;
}
export function position(value) {
  const n = Number(value);
  if (!Number.isFinite(n) || n < 0 || n > 86400) throw Error('Usa una posición entre 0 y 86400 segundos.');
  return n;
}
export function youtubeInput(value, override = '') {
  let u;
  try { u = new URL(value); } catch { throw Error('Introduce un enlace válido de YouTube.'); }
  if (!['https:', 'http:'].includes(u.protocol) || u.username || u.password || u.port) throw Error('Enlace de YouTube no permitido.');
  const host = u.hostname.toLowerCase(), parts = u.pathname.split('/').filter(Boolean);
  let id;
  if (host === 'youtu.be' && parts.length === 1) id = parts[0];
  else if (['youtube.com', 'www.youtube.com', 'm.youtube.com'].includes(host)) {
    if (u.pathname === '/watch') id = u.searchParams.get('v');
    else if (['shorts', 'live', 'embed'].includes(parts[0]) && parts.length === 2) id = parts[1];
  }
  if (!/^[A-Za-z0-9_-]{11}$/.test(id || '')) throw Error('El enlace no contiene un ID de YouTube válido.');
  let time = u.searchParams.get('t') ?? u.searchParams.get('start') ?? '0';
  if (override !== '') time = override;
  else if (/^(?=\d)(?:\d+h)?(?:\d+m)?(?:\d+s)?$/.test(time)) {
    const m = time.match(/^(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?$/);
    time = Number(m[1] || 0) * 3600 + Number(m[2] || 0) * 60 + Number(m[3] || 0);
  }
  return {id, position: position(time)};
}
export function validCheckpoint(p) {
  return !!p && p.mode === 'youtube' && typeof p.id === 'string'
    && /^[A-Za-z0-9_-]{11}$/.test(p.id)
    && typeof p.position === 'number' && Number.isFinite(p.position) && p.position > 0 && p.position <= 86400;
}
