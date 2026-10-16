'use strict';
const $ = id => document.getElementById(id);
let state = null, busy = false, key = '', lastFetch = 0;
const format = value => Number.isFinite(value) ? `${Math.floor(value/60)}:${String(Math.floor(value%60)).padStart(2,'0')}` : '—';
const age = value => value === null || value === undefined ? 'Sin datos' : `Hace ${Math.floor(value)} s`;
const feedback = text => { $('feedback').textContent = text; };
async function api(path, body) {
  const options = {headers:{'X-Cast-Key':key}};
  if (body !== undefined) Object.assign(options, {method:'POST', body:JSON.stringify(body), headers:{...options.headers,'Content-Type':'application/json'}});
  const response = await fetch(`/api/${path}`, options);
  const data = await response.json();
  if (!response.ok) throw Error(typeof data.detail === 'string' ? data.detail : 'Revisa los datos introducidos.');
  return data;
}
function render() {
  if (!state) return;
  const s = state, m = s.media;
  const elapsed = Math.max(0, (Date.now()-lastFetch)/1000);
  const stale = s.stale || elapsed > 10;
  $('connection').textContent = elapsed > 10 ? 'Servicio sin respuesta' : ({CONNECTED:'Conectado',CONNECTING:'Conectando…',DISCONNECTED:'Desconectado',LOST:'Reconectando…'}[s.connection] || 'Reconectando…');
  $('connection-dot').classList.toggle('online', s.connection === 'CONNECTED' && elapsed <= 10);
  $('app-name').textContent = s.app_name || 'Desconocida';
  $('receiver-age').textContent = age(s.receiver_age_s === null ? null : s.receiver_age_s + elapsed);
  $('media-age').textContent = `${stale?'Datos no vigentes · ':''}${age(s.media_age_s === null ? null : s.media_age_s + elapsed)}${m?.ad_detected?' · Anuncio detectado':''}`;
  $('current-video').textContent = m?.title || (m?.video_id ? `Video ${m.video_id}` : 'Sin video identificado');
  $('player').textContent = stale ? 'Sin datos recientes' : ({PLAYING:'En reproducción',PAUSED:'En pausa',BUFFERING:'Cargando',IDLE:'En espera'}[m?.player_state] || 'Desconocido');
  $('time').textContent = format(m?.position); $('duration').textContent = format(m?.duration);
  $('progress').style.width = m?.duration > 0 ? `${Math.min(100,100*(m.position||0)/m.duration)}%` : '0%';
  $('pause').disabled = busy || s.busy || stale || !s.can_pause || m?.player_state !== 'PLAYING';
  $('resume').disabled = busy || s.busy || stale || !s.can_resume || m?.player_state !== 'PAUSED';
  $('skip-ad').disabled = busy || s.busy || elapsed > 10 || !s.can_skip_ad || s.receiver_age_s + elapsed > 10;
  $('ad-status').textContent = m?.ad_detected && !stale
    ? 'Anuncio detectado. Puedes solicitar que se omita cuando YouTube lo permita.'
    : 'Cuando aparezca «Omitir anuncio» en la TV, pulsa el botón. Algunos anuncios no se pueden omitir.';
  $('save').disabled = busy || s.busy || stale || !m?.video_id || !m?.position || m.ad_detected || !['PLAYING','PAUSED'].includes(m.player_state);
  $('recover').disabled = busy || s.busy || !s.checkpoint;
  $('checkpoint').textContent = s.checkpoint ? `${s.checkpoint.video_id} · Punto guardado en ${format(s.checkpoint.position)}` : 'Guarda un punto del video para volver a él cuando lo necesites.';
  if (document.activeElement !== $('host')) $('host').value = s.host;
  const history = $('history'); history.replaceChildren();
  if (!s.history.length) { const p = document.createElement('p');p.className='hint';p.textContent='Tus videos y puntos guardados aparecerán aquí.';history.append(p); }
  s.history.forEach(item => {
    const row = document.createElement('div');row.className='history-row';
    const text = document.createElement('div'), p = document.createElement('p'), small = document.createElement('small');
    p.textContent=`${item.video_id} · ${format(item.position)}`;
    small.textContent=`${{checkpoint:'Punto guardado',requested:'Reproducción solicitada',confirmed:'Estado Cast confirmado'}[item.kind] || item.kind} · ${new Date(item.created_at).toLocaleString('es-MX')}`;
    text.append(p,small);row.append(text);
    if (item.kind === 'checkpoint') { const button=document.createElement('button');button.type='button';button.textContent='Continuar';button.disabled=busy||s.busy;button.onclick=()=>recover(item.id);row.append(button); }
    history.append(row);
  });
}
async function refresh() {
  if (busy) return;
  try { state = await api('state'); lastFetch=Date.now(); render(); if(state.issue) feedback(state.issue); }
  catch (error) { feedback(error.message === 'Failed to fetch' ? 'No hay respuesta del servicio local. Se conserva tu historial.' : error.message); render(); }
}
async function command(action, body={}) {
  if (busy) return;
  busy=true; render(); document.querySelectorAll('form button').forEach(b=>b.disabled=true);
  feedback('Procesando… La confirmación puede tardar hasta dos minutos.');
  try { const result=await api(action,body); feedback(result.message); }
  catch (error) {feedback(error.message === 'Failed to fetch' ? 'Se perdió la conexión. Revisa la TV antes de repetir la orden.' : error.message);}
  finally {busy=false;document.querySelectorAll('form button').forEach(b=>b.disabled=false);await refresh();}
}
function recover(id=null) {
  if (confirm('Continuar abrirá YouTube y puede reemplazar la cola actual. ¿Continuar?')) command('recover',id?{checkpoint_id:id}:{});
}
$('play-form').onsubmit=event=>{event.preventDefault();if(confirm('Reproducir este video puede reemplazar la cola del Chromecast. ¿Continuar?'))command('play',{url:$('url').value,position:$('position').value===''?null:Number($('position').value)});};
$('host-form').onsubmit=event=>{event.preventDefault();command('host',{host:$('host').value});};
$('key-form').onsubmit=event=>{event.preventDefault();key=$('key').value;$('key').value='';feedback('Clave aplicada a esta pestaña.');refresh();};
$('pause').onclick=()=>command('pause');$('resume').onclick=()=>command('resume');$('recover').onclick=()=>recover();
$('skip-ad').onclick=()=>command('skip-ad');
$('save').onclick=()=>{const m=state?.media;if(m&&confirm(`¿La TV muestra el video principal ${m.video_id} en ${format(m.position)}, sin anuncios?`))command('save',{content_confirmed:true,video_id:m.video_id,position:m.position});};
async function poll(){await refresh();setTimeout(poll,2000);}poll();
setInterval(()=>{if(lastFetch&&Date.now()-lastFetch>10000)render();},1000);
