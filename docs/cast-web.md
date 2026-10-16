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

Pasaron 10 pruebas JavaScript y 39 Python con receptores y respuestas upstream simulados. Comprueban MDX antes del envío, pérdida de sesión, ausencia de LOAD para YouTube, errores sin reintentos, protección HTTP y conservación del punto. Las pruebas no afirman reproducción real con el cambio nuevo.

## Referencias

- [Mensajes personalizados de CastSession](https://developers.google.com/cast/docs/reference/web_sender/cast.framework.CastSession).
- [Controlador YouTube de PyChromecast](https://github.com/home-assistant-libs/pychromecast/blob/master/pychromecast/controllers/youtube.py).
- [CastTube](https://github.com/ur1katz/casttube).
- [Blueprint YAML de Render](https://render.com/docs/blueprint-spec).
