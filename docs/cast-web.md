# Prueba web de Google Cast y Render

Esta versión comprueba la arquitectura **Render → navegador → Chromecast en la misma Wi-Fi**, sin un servicio Python ni una PC intermediaria. Los archivos publicados son únicamente los de `web-cast/`. El panel Python original permanece disponible con `python -m app`.

## Qué se puede comprobar

1. Abrir la página HTTPS en Chrome con soporte Cast, conectado a la misma Wi-Fi que el Chromecast. Permitir acceso a red local si el navegador lo solicita. Los navegadores integrados en otras apps pueden no exponer Cast; Chrome en iOS no admite casting mediante Web Sender.
2. Seleccionar **Conexión Cast · video de muestra**, pulsar **Seleccionar Chromecast** y elegir el equipo. La conexión puede abrir otra aplicación en la TV.
3. Pulsar **Reproducir muestra**. Comprobar imagen en TV, pausa, reanudación y posición. El video es Big Buck Bunny desde un archivo público de Google.
4. Guardar manualmente un punto cuando la TV muestre el contenido principal y volver a él. Se guarda solo en el almacenamiento de ese navegador y origen; no sincroniza Android y laptop ni importa SQLite.
5. Desconectar el navegador, elegir **YouTube · experimental**, reconectar y probar un enlace. Anotar si acepta la sesión, si reproduce el ID correcto y si respeta la posición. Una conexión exitosa o una orden aceptada no prueban reproducción correcta.

El modo YouTube usa el ID de receptor `233637DE` observado en el proyecto y prueba `LOAD` con un ID validado y tipo `x-youtube/video`. **Es un experimento, no una integración oficial de YouTube ni una equivalencia con PyChromecast/CastTube.** La ruta Python obtiene una sesión MDX/Lounge; esa negociación no se ha trasladado al navegador. Si YouTube rechaza `LOAD` o no expone un estado multimedia utilizable, esa función no queda resuelta por alojar la web en Render. El receptor estándar de la muestra no reproduce páginas `watch` de YouTube.

Los controles dependen de un estado recibido hace menos de diez segundos y de la capacidad de pausa anunciada. No se reenvían órdenes automáticamente tras errores o plazos vencidos. Los puntos no se actualizan automáticamente. Un cambio reportado por Cast requiere comprobación visual, especialmente durante anuncios. Cerrar/desconectar la web no envía `STOP`; el navegador ya no podrá actualizar el estado ni ejecutar órdenes.

## Publicación en Render

El `render.yaml` de la raíz define un **Static Site**, sin disco, base de datos, secretos ni servidor Python.

Desde Render, crear un Blueprint a partir de este repositorio y revisar que publique `web-cast`. Alternativamente crear un **Static Site** manualmente con:

| Campo | Valor |
| --- | --- |
| Repository | `https://github.com/iLaurx/reverse-cast-gen2` |
| Branch | `main` |
| Build Command | `node --check web-cast/app.mjs` |
| Publish Directory | `web-cast` |

No usar el inicio de FastAPI para este despliegue. Abrir la URL HTTPS que Render asigne; no se ha fijado una URL antes de que el servicio exista. No es necesario registrar el Default Media Receiver ni abrir puertos del router. No introducir claves del panel local en esta página.

## Validación automatizada

```powershell
node --check web-cast/app.mjs
node --test tests/test_cast_web.mjs
```

Las pruebas usan un SDK/receptor simulado: verifican validación de enlaces, aislamiento del punto, pérdida de estado, desconexión sin detener TV, errores de reproducción y almacenamiento bloqueado. No verifican descubrimiento real, compatibilidad de Android ni reproducción real de YouTube. Estas últimas comprobaciones requieren el navegador y la TV del propietario.

## Referencias

- [Integración oficial de Web Sender](https://developers.google.com/cast/docs/web_sender/integrate).
- [Compatibilidad y HTTPS de Web Sender](https://developers.google.com/cast/docs/web_sender).
- [Referencia Media de Web Sender](https://developers.google.com/cast/docs/reference/web_sender/chrome.cast.media.Media).
- [Static Sites de Render](https://render.com/docs/static-sites).
- [Blueprint YAML de Render](https://render.com/docs/blueprint-spec).
