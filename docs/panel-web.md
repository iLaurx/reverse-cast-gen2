# Panel web local: implementación y validación

## Componentes

- `app/web.py`: FastAPI, archivos estáticos, validación de entrada y protección de acceso. El ciclo de vida abre y cierra el servicio.
- `app/service.py`: un único trabajador consulta cada dos segundos. Un bloqueo serializa consultas, cambios de IP y comandos. Las consultas de la web leen una instantánea en memoria: no crean procesos ni conexiones Cast.
- `app/cast.py`: conexión persistente PyChromecast con reconexión interna; observador propio sin lanzamiento implícito. El controlador multimedia predeterminado se retira. Solo una acción explícita de reproducir/recuperar inicia YouTube; consultar el estado nunca lo hace.
- `app/protocol.py`: observadores MDX/multimedia y confirmación extraídos del experimento probado. `scripts/Recover-YouTube.py` conserva su interfaz y las pruebas anteriores importando esas funciones.
- `app/lounge.py`: peticiones HTTPS con timeout a las rutas fijas de YouTube, compartidas por el relay de Render y la omisión local. Incluye `skipAd` sin inicializar la cola ni reintentar comandos.
- `app/store.py`: SQLite con bloqueo, transacciones y campos permitidos: IP, ID de video, posición, tipo de registro y fecha UTC. Historial visible de hasta 100 entradas; los puntos anteriores siguen en la base. No se guardan URLs originales, tokens, screenId, sesiones, cookies ni respuestas completas.
- `app/static`: HTML, CSS y JavaScript servidos localmente. Interfaz adaptable, sondeo secuencial y acciones deshabilitadas mientras hay un comando pendiente.

Usar `python -m app`, un proceso y un worker. Sin varios workers ni recarga automática. Configuración, instalación, localhost y acceso desde teléfono: [README](../README.md#panel-web-local).

## Estado, antigüedad y recuperación

Los estados de receptor y multimedia tienen tiempos monotónicos de recepción independientes. La API informa su antigüedad. Más de diez segundos sin una observación válida deshabilita controles que dependen del estado. Una desconexión o cambio de sesión/aplicación descarta el estado multimedia actual. Los mensajes parciales no heredan campos anteriores. Una lectura HTTP no convierte un estado Cast antiguo en uno nuevo. Si la interfaz pierde el servicio también marca los datos como antiguos.

El punto de recuperación vive en SQLite y es independiente de esas instantáneas. Solo cambia con **Guardar este punto**, una confirmación humana explícita del video principal mostrado, sin anuncios, asociada al ID y posición mostrados. Se toleran hasta cinco segundos de avance mientras se confirma y se guarda el punto mostrado, no una posición posterior. Se rechazan anuncios marcados, cero, posiciones desconocidas, estados antiguos o un cambio concurrente del punto mostrado. No se guarda automáticamente el avance posterior. Esto conserva un punto seguro a costa de requerir guardados manuales: la ausencia de `breakStatus` no prueba que no haya anuncios.

Se detectan marcas de pausa publicitaria expuestas por el receptor, pero no existe un detector fiable de anuncios para esta sesión de YouTube. Los campos de tiempo de un break son tiempos del segmento publicitario, como describe [Google Cast BreakStatus](https://developers.google.com/cast/docs/reference/web_receiver/cast.framework.messages.BreakStatus). No se utilizan como progreso del video. No se interpretan anuncios a partir de una duración corta ni de ceros transitorios.

El historial diferencia solicitud enviada, reproducción confirmada y punto guardado por el usuario. Reproducir y recuperar pueden reemplazar la cola. Nunca se recupera automáticamente, incluso tras Backdrop o reconexión. Se obtiene una nueva sesión MDX en cada orden explícita, y las credenciales de CastTube permanecen temporalmente en memoria. No se modifica ninguna biblioteca instalada.

La confirmación de reproducción exige al menos tres observaciones nuevas a lo largo de cuatro segundos, recibidas después de completar el envío, YouTube activo y reciente, mismo ID, `PLAYING` y posición entre la solicitada menos tres segundos y la solicitada más el tiempo transcurrido más cinco segundos. Se rechaza una marca publicitaria detectada. Si `setPlaylist` conserva el tiempo anterior para el mismo video, dentro de esa orden explícita se envía como máximo un `SEEK` cuando hay estado fresco y soporte anunciado; después se comprueba de nuevo la posición. No se fuerza un reinicio de YouTube. La confirmación de Cast no demuestra visualmente ausencia de un anuncio no marcado: el punto de recuperación sigue intacto hasta la confirmación humana. Si no llega evidencia suficiente en 35 segundos, se informa orden enviada sin confirmar. Las fases de lanzamiento/MDX/HTTPS añaden sus propios plazos, por lo que la operación completa puede tardar aproximadamente dos minutos o más según la red; no hay reintentos automáticos de reproducción.

Pausa/reanudación requieren observación fresca, ID, sesión multimedia y capacidad de pausa (bit 1). Se envía la orden directamente al canal actual; se espera un estado nuevo del mismo video, con la misma generación de sesión y el estado esperado. La capacidad anunciada no es prueba de ejecución.

## Omitir anuncio

`POST /api/skip-ad` exige YouTube activo, conexión y estado del receptor de no más de diez segundos, sin exigir metadatos multimedia ni capacidad estándar de pausa. `CastAdapter.skip_ad` obtiene una respuesta MDX nueva, vincula Lounge y comprueba la generación de sesión y aplicación de nuevo antes de enviar `skipAd`. No lanza aplicaciones, no carga videos, no busca posiciones y no escribe historial o puntos guardados. Comparte el bloqueo de operaciones del servicio.

La interfaz permite solicitar la omisión cuando el usuario ve la opción en la TV, aun sin marcas publicitarias. Si el receptor publica una marca, indica **Anuncio detectado**. El resultado devuelve `confirmed: false`: confirma únicamente que se envió la solicitud. YouTube puede no admitir la omisión o ignorarla. No hay reintento ni omisión automática. Para activar esta versión, reinicia el servicio local y recarga el navegador.

Validación del 16 de octubre de 2026: 44 pruebas Python y 13 JavaScript completadas con dispositivos y peticiones simulados. Se comprobó que omitir conserva el historial, admite ausencia de multimedia, rechaza estado antiguo/otra aplicación y no lanza YouTube. La negociación local descarta la referencia MDX al terminar y vuelve a comprobar la sesión antes del comando. La prueba durante un anuncio real queda pendiente.

## Protección y límites

El lanzador escucha en 127.0.0.1 por defecto. Para LAN exige clave y lista explícita de hosts. La API protege también la lectura del historial, verifica Host/Origin y exige JSON para comandos. No hay CORS permisivo. La clave se entrega mediante cabecera, no URL, y la interfaz no la persiste en almacenamiento del navegador. HTTP en LAN requiere una red privada de confianza; no es un servicio para Internet. No se cambian reglas de firewall ni router.

La IPv4 del Chromecast se valida como dirección privada. La conexión al equipo usa siempre el puerto Cast 8009; no hay descarga de URLs arbitrarias. Los errores de bibliotecas se sustituyen por mensajes genéricos para evitar exponer credenciales. Las cabeceras del panel limitan scripts a archivos locales, impiden incrustación y desactivan caché. Esto es una protección sencilla para un entorno doméstico, sin cuentas de usuario, HTTPS ni límites por cliente.

No corrige el cierre interno de YouTube, no elimina anuncios, no conserva/restaura la cola anterior ni da acceso root. El historial se comparte entre usuarios autorizados del panel en esta PC. El cambio de IP conserva los puntos guardados y cierra la conexión anterior antes de abrir otra. Al apagar el servicio se cierra su conexión de control, sin ordenar detener YouTube. Un comando en curso puede retrasar el apagado hasta terminar su fase acotada.

## Verificación de esta versión

Se conservan las seis pruebas de observación y recuperación anteriores. La suite completa incluye 28 pruebas: enlaces y tiempos, dominios engañosos, IDs inválidos, valores no finitos, persistencia tras reapertura, conservación del punto ante incertidumbre, anuncios, Backdrop y desconexión, datos antiguos, recuperación correcta y sin confirmar, pausa/reanudación simuladas, comandos concurrentes, cambio de IP, conexión única/cierre, consultas sin lanzamiento y protección HTTP. Todas pasaron con Python 3.12. `pip check` no detectó dependencias incompatibles.

Las pruebas HTTP necesitaron ejecutarse fuera del aislamiento de herramientas porque Windows bloqueaba el socket interno de asyncio. Eso no es un requisito de ejecutar la aplicación como administrador. Hay un aviso de obsolescencia de Starlette sobre su cliente de pruebas HTTPX; no afectó a las pruebas completadas.

Se revisó la interfaz en navegador con un adaptador simulado: pausa y reanudación mostraron el estado esperado; escritorio de 1280 píxeles y móvil de 390, sin desbordamiento horizontal. Capturas locales: `evidence/web-desktop-01.png`, `evidence/web-mobile-01.png`. Esas capturas son datos de demostración, no prueba de reproducción en la TV. El servidor simulado se detuvo antes de iniciar la prueba real.

La evidencia anterior `youtube-recovery-01.json`, `youtube-exit-01.json`, `youtube-session-01-summary.json` y `user-confirmations-01.json` está disponible y se conservó. Registra una recuperación del experimento original en 507.434 segundos tras solicitar 506, confirmada visualmente por el propietario. No equivale a una prueba de la nueva interfaz.

### Prueba real autorizada de la nueva API

Se ejecutó `POST /api/play` con `MtpG0sVMTfM` y posición 506. Los primeros dos intentos conservaron un tiempo lejano al solicitado, se informaron sin confirmar y se preservaron en `evidence/web-real-play-01.json` y `web-real-play-02.json`. El segundo exploró un lanzamiento forzado, que no resolvió el caso y se retiró.

Tras incorporar el ajuste de posición con `SEEK`, `evidence/web-real-play-03.json` registró el mismo video, `PLAYING`, posición 506 y antigüedad de 0.1 s. El propietario primero indicó que seguía cerca del minuto 36, después corrigió esa apreciación y confirmó que sí había retrocedido al punto de prueba: «fue correcta la prueba». La corrección está documentada separadamente en `evidence/web-user-confirmation-01.json`, sin alterar los resultados anteriores.

Se añadió después una comprobación sostenida de varios estados para reforzar la confirmación; tiene pruebas automáticas específicas para posición transitoria y posición sostenida, pero ese refinamiento no se volvió a probar en la TV para evitar otra interrupción. Pausa/reanudación, guardado y recuperación de un punto desde la nueva base se verificaron con simulador; la prueba real utilizó la ruta de reproducción con posición, compartida por la recuperación. Acceso físico desde teléfono y comportamiento durante un anuncio real siguen pendientes. El servidor temporal se detuvo al finalizar; no se envió una orden de parada a la TV.

## Título del video actual

El observador conserva `media.metadata.title` únicamente para el video identificado en ese mensaje, sin heredar títulos de otro video. Ese campo forma parte de los [metadatos de Google Cast](https://developers.google.com/cast/docs/reference/web_receiver/cast.framework.messages.GenericMediaMetadata). Si el receptor no entrega título, `app/titles.py` consulta el endpoint fijo HTTPS de YouTube oEmbed con una URL canónica construida desde un ID validado. No se descarga la URL pegada por el usuario ni se usan cookies, credenciales de Cast o redirecciones.

La consulta ocurre en un trabajador independiente, fuera del bloqueo de operaciones Cast y de la respuesta HTTP del estado. La interfaz muestra el ID mientras llega el título, y lo sustituye en el siguiente sondeo. Caché en memoria de hasta 256 IDs: seis horas para títulos y cinco minutos para resultados sin título o fallos. Se deduplican solicitudes simultáneas, con un solo trabajador y hasta ocho consultas pendientes; cada solicitud limita conexión/lectura y tamaño de respuesta. La caché se libera al reiniciar el servicio. Los títulos recibidos del Chromecast tienen prioridad, incluso si llega después una respuesta web pendiente. No se usan metadatos de un anuncio marcado para resolver el título.

El título solo cambia la presentación de **En la televisión**; IDs, historial, puntos y reglas de recuperación mantienen su función. La consulta de respaldo comunica a YouTube el ID público del video y la IP de la PC como cualquier solicitud a ese servicio. Si YouTube no responde, el control sigue disponible y el ID permanece visible.

Verificación: se obtuvo realmente el título «Creando Aviones con un Ingeniero Aerospacial en Minecraft» para `n_UU5OJg-rs`, el video de la captura del propietario, sin cambiar la reproducción. Se añadieron seis pruebas automáticas de preferencia de metadatos nativos, consulta sin bloqueo/deduplicación, caché de errores, prioridad frente a respuestas pendientes, rechazo de IDs inválidos y separación de títulos al cambiar de video.

Para cargar esta mejora, detener y volver a iniciar el servicio con el mismo comando y recargar el navegador. No se reinició el servidor del propietario ni se enviaron comandos al Chromecast durante este cambio.
