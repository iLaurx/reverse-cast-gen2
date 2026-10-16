# Cast web: YouTube desde el navegador

Sitio: [Cast web](https://reverse-cast-web.onrender.com/).

El navegador conecta con el Chromecast en la misma Wi-Fi. Para reproducir YouTube obtiene una sesión MDX del receptor y la envía por HTTPS a la API en Render. La API negocia Lounge y envía `setPlaylist` con el ID y la posición. No usa direcciones privadas desde Render y no requiere una PC intermediaria. El panel local Python original se conserva.

## Cambio de reproducción

La primera prueba abría el receptor YouTube pero usaba `loadMedia` con `x-youtube/video`. El propietario confirmó que la TV quedaba lista para transmitir sin abrir el video. Se sustituyó esa ruta por el intercambio MDX/Lounge que utiliza el controlador local: `getMdxSessionStatus` en el navegador y CastTube en el servidor.

La API solo acepta la URL de origen del panel, JSON acotado, un ID de video válido, una posición finita y una sesión temporal. No admite URLs de destino ni IP del dispositivo. Conecta únicamente a las rutas HTTPS fijas de YouTube, con tiempos límite y sin seguir redirecciones. No guarda sesiones ni tokens; conserva brevemente un digest de sesión para limitar órdenes repetidas. Los errores no incluyen credenciales. Origin limita el acceso desde otras webs; la capacidad de control sigue siendo el identificador de sesión obtenido del Chromecast, no una cuenta de usuario.

El servicio gratuito puede tardar en despertar. Antes de pedir una sesión MDX nueva, el panel consulta `/health`. El envío completo tiene un plazo de 90 segundos y no se reintenta automáticamente. Una respuesta HTTP correcta confirma el envío, no que el video o la posición sean correctos en la TV. Esta integración usa un protocolo no oficial de YouTube que puede cambiar; sigue requiriendo comprobación real con el dispositivo.

## Uso en celular

1. Abrir el sitio en Chrome compatible con Cast, conectado a la Wi-Fi del Chromecast.
2. Pulsar **Seleccionar Chromecast**. El selector y los permisos pertenecen al navegador y no pueden eliminarse desde el panel.
3. Pegar un enlace de YouTube y pulsar **Enviar a mi TV**. El nuevo video reemplaza la reproducción actual.
4. Comprobar imagen, pausa y posición en la TV. **Guardar punto sin anuncios** guarda la posición manualmente en este navegador; no se sincroniza entre dispositivos ni se importa SQLite.

Se retiraron el video de muestra, el selector de modos y los cuadros `confirm` del panel. Guardar el punto ya no abre una confirmación: el botón identifica la acción y exige que el propietario compruebe el contenido principal, sin anuncios. No se guarda automáticamente. La vista de celular usa una columna, controles táctiles de al menos 48 px e inputs de 16 px. Ayuda y detalles de envíos se despliegan dentro de la página.

Desconectar el navegador no envía STOP a la TV. Cerrar la página impide seguir actualizando el estado o ejecutar órdenes. Chrome en iOS no admite Web Sender; los navegadores integrados en otras apps pueden no exponer Cast.

## Omitir anuncios

La revisión del código identifica tres capas: el navegador mantiene la sesión Cast con el receptor YouTube (`233637DE`); MDX obtiene un `screenId` temporal; el relay usa ese identificador para vincular un control Lounge y enviar órdenes HTTPS a YouTube. El Chromecast reproduce el contenido; Render envía las órdenes y no transmite el video ni se conecta a la IP privada de la TV. No hay un volcado del firmware que permita describir su implementación interna completa.

```mermaid
sequenceDiagram
    participant U as Usuario
    participant W as Panel web
    participant C as YouTube en Chromecast
    participant R as Relay en Render
    participant Y as YouTube Lounge
    U->>W: Omitir anuncio
    W->>R: Despertar servicio (/health)
    W->>C: getMdxSessionStatus
    C-->>W: screenId temporal
    W->>R: POST /api/youtube/skip-ad
    R->>Y: Obtener token y vincular control
    R->>Y: skipAd
    Y-->>R: Respuesta al envío
    R-->>W: Solicitud enviada; resultado sin confirmar
    Note over C,Y: El receptor decide si el anuncio se puede omitir
```

**Omitir anuncio** se habilita al conectar una sesión y se bloquea mientras hay otra orden. No depende de una sesión multimedia identificable, que puede faltar durante un anuncio. Si hay `breakStatus`, `adBreakStatus` o `media.isPlayingAd`, la página indica **Anuncio detectado** y bloquea guardar ese tiempo como punto del video. La ausencia de esas marcas mantiene disponible el intento manual; no permite deducir que sea contenido principal ni habilita una omisión automática.

`web-cast/youtube.mjs` comparte con reproducir el despertar del relay, la negociación MDX, el plazo de 90 segundos y la comprobación de que la sesión siga siendo la misma antes del envío. El endpoint nuevo acepta exclusivamente `screen_id`; no acepta ID de video, posición, URLs, IP ni comandos arbitrarios. Comparte validación, Origin, límites de tamaño, concurrencia y espera de tres segundos entre órdenes con reproducir.

`app/lounge.py` extiende CastTube con `skip_ad`: obtiene el token, vincula el control y envía una sola orden `skipAd`, sin `setPlaylist`, `SEEK`, `next`, lanzamiento ni reintentos. La respuesta HTTP solo acredita el envío al servicio. Los anuncios no omitibles o un receptor incompatible pueden ignorarlo. No se promete que la TV haya vuelto al contenido y no se cambia el punto guardado.

El comando está documentado en el [código de PyYtLounge](https://pyytlounge.readthedocs.io/en/stable/_modules/pyytlounge/wrapper.html#YtLoungeApi.skip_ad). No se añadió esa biblioteca como dependencia: se usa la sesión CastTube ya instalada. Los [metadatos de pausas de Google Cast](https://developers.google.com/cast/docs/web_receiver/ad_breaks) explican la señal publicitaria, pero no garantizan que YouTube la publique en todas sus sesiones. Esta integración requiere probarse con un anuncio real del Chromecast del propietario.

Para actualizar Render se deben desplegar el sitio estático **y** el relay de esta versión. Una web nueva con un relay anterior recibirá error al pulsar el botón. El servicio gratuito puede tardar en despertar y el anuncio podría terminar durante esa espera.

## Render

El Blueprint define dos servicios:

| Servicio | Tipo | Configuración |
| --- | --- | --- |
| reverse-cast-web | Static Site | Build `node --check web-cast/app.mjs`; publicar `web-cast` |
| reverse-cast-relay | Web Service Python, Free | Build `pip install -r requirements-relay.txt`; inicio `python -m uvicorn app.relay:api --host 0.0.0.0 --port $PORT --workers 1 --no-access-log`; salud `/health` |

El relay usa `PYTHON_VERSION=3.12.7` y `CAST_SITE_ORIGIN=https://reverse-cast-web.onrender.com`. Su dirección pública se configura en `web-cast/youtube.mjs`. No necesita disco, claves de YouTube ni base de datos.

## Validación

```powershell
node --test tests/test_cast_web.mjs
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

El 16 de octubre de 2026 pasaron 13 pruebas JavaScript y 44 Python con receptores y respuestas upstream simulados. Comprueban MDX antes del envío, pérdida de sesión, ausencia de LOAD para YouTube, errores sin reintentos, protección HTTP y conservación del punto. Las pruebas nuevas cubren la orden `skipAd`, su endpoint, limitación compartida, rechazo de una sesión local cambiada, uso sin metadatos multimedia y bloqueo de guardado al detectar anuncios. Se comprobó visualmente el botón en la vista estrecha del navegador, sin conectar ni controlar la TV. `pip check` no encontró dependencias rotas. Las pruebas no afirman omisión real de anuncios con este cambio.

## Referencias

- [Mensajes personalizados de CastSession](https://developers.google.com/cast/docs/reference/web_sender/cast.framework.CastSession).
- [Controlador YouTube de PyChromecast](https://github.com/home-assistant-libs/pychromecast/blob/master/pychromecast/controllers/youtube.py).
- [CastTube](https://github.com/ur1katz/casttube).
- [Blueprint YAML de Render](https://render.com/docs/blueprint-spec).
