"""Serialized operations and polling; callbacks only update bounded memory."""
import threading
import time
from app.protocol import confirms_playback
from app.validation import host as validate_host, position as validate_position, youtube_url
from app.titles import TitleResolver

class ServiceError(Exception):
    pass

class Service:
    def __init__(self, store, factory, confirmation_timeout=35, confirmation_stability=4, title_resolver=None):
        self.store, self.factory = store, factory
        self.operation = threading.Lock()
        self.stop_event = threading.Event()
        self.adapter = None
        self.host = store.get_host()
        self.thread = None
        self.timeout = confirmation_timeout
        self.stability = confirmation_stability
        self.issue = None
        self.titles = title_resolver if title_resolver is not None else TitleResolver()

    def start(self):
        self.thread = threading.Thread(target=self._run, name='cast-service', daemon=True)
        self.thread.start()

    def _run(self):
        while not self.stop_event.is_set():
            if self.operation.acquire(blocking=False):
                try:
                    if self.adapter is None:
                        self.adapter = self.factory(self.host)
                    self.adapter.poll()
                    self.issue = None
                except Exception:
                    self.issue = 'No se pudo actualizar el Chromecast. Se reintentará la conexión.'
                finally:
                    self.operation.release()
            self.stop_event.wait(2)

    def close(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=10)
        with self.operation:
            if self.adapter:
                self.adapter.close()
                self.adapter = None
        self.titles.close()

    def raw(self):
        adapter = self.adapter
        return adapter.snapshot() if adapter else dict(connection='CONNECTING', receiver=None, media=None)

    def fresh(self, raw):
        now = time.monotonic()
        return (raw['connection'] == 'CONNECTED' and raw.get('receiver') is not None
                and raw['receiver'].get('app_id') == '233637DE'
                and now - raw['receiver']['observed_monotonic'] <= 10
                and raw.get('media') is not None
                and now - raw['media']['observed_monotonic'] <= 10)

    def can_skip_ad(self, raw):
        receiver = raw.get('receiver') or {}
        return (raw['connection'] == 'CONNECTED' and receiver.get('app_id') == '233637DE'
                and time.monotonic() - receiver['observed_monotonic'] <= 10)

    def status(self):
        raw = self.raw()
        now = time.monotonic()
        receiver, media = raw.get('receiver'), raw.get('media')
        age = lambda obj: round(max(0, now - obj['observed_monotonic']), 1) if obj else None
        fresh = self.fresh(raw)
        public_media = ({k: media.get(k) for k in ('video_id','position','duration','player_state','ad_detected')} if media else None)
        if public_media is not None:
            public_media['title'] = (self.titles.get(media.get('video_id'), media.get('title'))
                                     if not media.get('ad_detected') else None)
        return dict(host=self.host, connection=raw['connection'],
                    app_name=receiver.get('app_name') if receiver else None,
                    receiver_age_s=age(receiver), media_age_s=age(media), stale=not fresh,
                    media=public_media, busy=self.operation.locked(), issue=self.issue,
                    can_skip_ad=self.can_skip_ad(raw),
                    can_pause=bool(fresh and media.get('commands', 0) & 1 and media.get('media_session_id') is not None and not media.get('ad_detected')),
                    can_resume=bool(fresh and media.get('commands', 0) & 1 and media.get('media_session_id') is not None and not media.get('ad_detected')),
                    checkpoint=self.store.checkpoint(), history=self.store.history(),
                    progress_note='Los anuncios no se distinguen con fiabilidad. El punto guardado solo cambia al confirmar manualmente el contenido principal.')

    def execute(self, action, payload):
        if not self.operation.acquire(blocking=False):
            raise ServiceError('Hay otra operación en curso. Espera a que termine.')
        try:
            if action == 'host':
                selected = validate_host(payload['host'])
                if selected != self.host:
                    if self.adapter:
                        self.adapter.close()
                        self.adapter = None
                    self.store.set_host(selected)
                    self.host = selected
                return {'message': 'Dirección guardada. Conectando sin cambiar la reproducción.'}
            if not self.adapter:
                raise ServiceError('El Chromecast todavía no está conectado.')
            raw = self.raw()
            if action == 'skip-ad':
                if not self.can_skip_ad(raw):
                    raise ServiceError('Conecta una sesión reciente de YouTube para omitir el anuncio.')
                self.adapter.skip_ad(raw.get('generation'))
                return {'message': 'Solicitud de omitir anuncio enviada. Comprueba la TV; YouTube decide si se puede omitir.', 'confirmed': False}
            if action == 'save':
                media = raw.get('media') or {}
                if not self.fresh(raw) or not media.get('video_id') or media.get('player_state') not in ('PLAYING','PAUSED'):
                    raise ServiceError('Falta una observación reciente de un video de YouTube.')
                if media.get('ad_detected') or media.get('position') is None or media['position'] <= 0:
                    raise ServiceError('No se puede guardar una posición cero, desconocida o de un anuncio.')
                if payload.get('content_confirmed') is not True:
                    raise ServiceError('Confirma que la TV muestra el video principal, sin anuncios.')
                # Bind user confirmation to the exact displayed observation, avoiding races.
                selected_position = validate_position(payload.get('position'))
                if payload.get('video_id') != media['video_id'] or selected_position <= 0 or abs(selected_position - media['position']) > 5:
                    raise ServiceError('La posición cambió. Revisa el estado y vuelve a guardar.')
                self.store.add(media['video_id'], selected_position, 'checkpoint')
                return {'message': 'Punto guardado en esta PC.'}
            if action in ('pause','resume'):
                media = raw.get('media') or {}
                if not self.fresh(raw) or not media.get('video_id') or not media.get('commands', 0) & 1 or media.get('media_session_id') is None or media.get('ad_detected'):
                    raise ServiceError('El estado actual no permite confirmar este control.')
                requested = time.monotonic()
                self.adapter.control(action, media)
                expected = 'PAUSED' if action == 'pause' else 'PLAYING'
                return self._confirm(media['video_id'], None, requested, expected, raw.get('generation'))
            if action == 'recover':
                point = self.store.checkpoint(payload.get('checkpoint_id'))
                if not point:
                    raise ServiceError('Todavía no hay un punto guardado para continuar.')
                video, position = point['video_id'], point['position']
            elif action == 'play':
                video, url_position = youtube_url(payload['url'])
                position = validate_position(payload['position']) if payload.get('position') is not None else url_position
            else:
                raise ValueError('Operación desconocida.')
            if raw['connection'] != 'CONNECTED':
                raise ServiceError('No hay conexión con el Chromecast.')
            requested = time.monotonic()
            self.store.add(video, position, 'requested')
            self.adapter.play(video, position)
            requested = time.monotonic()  # Confirm only observations received after sending completes.
            result = self._confirm(video, position, requested, 'PLAYING')
            if result['confirmed']:
                self.store.add(video, position, 'confirmed')
            return result
        except (ValueError, ServiceError):
            raise
        except Exception:
            # Never expose library errors: they may include credentials or signed URLs.
            raise ServiceError('No se completó la operación. La reproducción puede haber cambiado; revisa la TV y el estado.') from None
        finally:
            self.operation.release()

    def _confirm(self, video, position, requested, expected, generation=None):
        deadline = time.monotonic() + self.timeout
        sought = False
        stable_since = None
        stable_samples = 0
        last_sample = None
        while not self.stop_event.is_set() and time.monotonic() < deadline:
            self.adapter.poll()
            raw = self.raw()
            media = raw.get('media') or {}
            if raw.get('error_at', 0) >= requested:
                raise ServiceError('El Chromecast informó que no pudo ejecutar la orden.')
            if generation is not None and raw.get('generation') != generation:
                raise ServiceError('La sesión cambió durante el control; no se confirmó el resultado.')
            if self.fresh(raw) and not media.get('ad_detected'):
                if position is None:
                    confirmed = (media.get('observed_monotonic', -1) > requested and media.get('video_id') == video and media.get('player_state') == expected)
                else:
                    confirmed = confirms_playback(media, video, position, requested)
                if (not confirmed and position is not None and not sought
                        and time.monotonic() - requested >= 1
                        and media.get('observed_monotonic', -1) > requested
                        and media.get('video_id') == video
                        and media.get('player_state') in ('PLAYING','PAUSED')
                        and media.get('position') is not None
                        and abs(media['position'] - position) > 5
                        and media.get('commands', 0) & 2
                        and media.get('media_session_id') is not None):
                    # setPlaylist can keep the current time for an already active video.
                    # One explicit SEEK completes the user's requested start position.
                    self.adapter.seek(media, position)
                    sought = True
                    requested = time.monotonic()
                if confirmed:
                    stamp = media['observed_monotonic']
                    if stable_since is None:
                        stable_since = stamp
                    if stamp != last_sample:
                        stable_samples += 1
                        last_sample = stamp
                    if position is None or self.stability == 0 or (stamp - stable_since >= self.stability and stable_samples >= 3):
                        return {'confirmed': True, 'confirmation_scope':'cast_status',
                                'message': 'El Chromecast confirma el estado solicitado. Comprueba la imagen en la TV; los anuncios pueden no estar identificados.'}
                else:
                    stable_since = last_sample = None
                    stable_samples = 0
            else:
                stable_since = last_sample = None
                stable_samples = 0
            self.stop_event.wait(min(.5, max(0, deadline - time.monotonic()) / 2))
        return {'confirmed': False, 'message': 'Orden enviada, sin confirmación suficiente. Revisa la TV; se conserva el punto guardado.'}
