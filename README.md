# reverse-cast-gen2

Entorno de investigación de un Chromecast de segunda generación mediante consultas de red, capturas y análisis estático. El dispositivo seleccionado está en `192.168.1.6`.

## Prueba web para Render

Abre [Cast web en Render](https://reverse-cast-web.onrender.com/) desde un navegador compatible conectado a la Wi-Fi del Chromecast. El sitio ya está publicado; la reproducción real y el modo YouTube requieren comprobarse con la TV.

La carpeta `web-cast/` contiene el panel de YouTube adaptado a celular, sin video de muestra ni cuadros de confirmación. El navegador conecta con el Chromecast en tu Wi-Fi y una API en Render envía los videos mediante la sesión MDX/Lounge. No necesitas mantener una PC intermediaria encendida. Incluye pausa/reanudación, barra de volumen de 0 a 100 %, botones −/+ de cinco puntos, silenciar/activar sonido y un punto guardado por navegador. `render.yaml` define el sitio estático y la API Python.

El volumen se controla directamente mediante la sesión Cast, sin pasar por el relay. El nivel se actualiza con lo que informa el receptor y no se envían cambios al conectar. Para publicar este cambio de volumen solo hace falta desplegar el sitio estático. Se verificó con pruebas simuladas; falta comprobarlo en la TV. Consulta [control de volumen](docs/cast-web.md#volumen).

### Omitir anuncios

Los dos paneles incluyen **Omitir anuncio**. Conecta YouTube y pulsa el botón cuando la TV permita omitir el anuncio. Se solicita `skipAd` mediante la sesión MDX/Lounge actual; esta acción no carga otro video, no busca una posición ni reemplaza la cola o el punto guardado. YouTube decide si el anuncio admite omisión.

El botón permanece disponible durante la sesión porque YouTube no siempre publica metadatos de anuncios. Cuando el receptor sí informa una pausa publicitaria, la página indica **Anuncio detectado**. No hay detección completa ni omisión automática. Una solicitud enviada no confirma que el anuncio haya desaparecido: compruébalo en la TV.

La implementación del 16 de octubre de 2026 pasó 44 pruebas Python y 13 JavaScript con respuestas simuladas. Falta comprobar `skipAd` durante un anuncio real en este Chromecast. Para verlo en Render hay que desplegar **ambos servicios**, web y relay, desde esta versión; editar estos archivos no actualiza por sí solo la publicación. Para el panel local, reinicia el servicio y recarga la página. Consulta [funcionamiento y límites](docs/cast-web.md#omitir-anuncios).

El propietario confirmó la conexión Cast de la primera versión, pero la orden multimedia estándar no iniciaba el video. Se sustituyó por MDX/Lounge; el envío y la posición con esta ruta requieren comprobación en la TV. El panel Python funcional de abajo se conserva. Consulta [publicación, límites y prueba en la TV](docs/cast-web.md).

## Panel web local

Primera versión con FastAPI y una interfaz en español: enlaces de YouTube, posición inicial, IP configurable, estado reciente, pausa/reanudación, historial persistente y recuperación manual. La investigación y sus archivos originales se conservan más abajo.

Desde PowerShell:

```powershell
Set-Location C:\Users\ele\Documents\Proyectos\reverse-cast-gen2
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m app
```

Abre [el panel local](http://127.0.0.1:8765). Para detenerlo, pulsa `Ctrl+C` en esa terminal. Usa **un solo proceso**, sin `--reload` ni varios workers. La PC debe permanecer encendida. La IP inicial es `192.168.1.6`; puedes cambiarla en **Configurar conexión**.

En **En la televisión** se muestra el título cuando está disponible. Se toma del Chromecast; si no lo entrega, se consulta YouTube en segundo plano y se conserva en caché. La consulta no bloquea los controles ni el estado. Mientras carga o si falla, se muestra el ID del video. No necesitas dependencias nuevas.

Pega el enlace y pulsa **Reproducir**. Acepta `watch`, `youtu.be`, `shorts`, `live` y `embed`, con ID de once caracteres. Usa el tiempo `t`/`start` del enlace si dejas vacía la posición inicial; introducir 0 fuerza el inicio. No descarga URLs ni conserva sus parámetros.

**Guardar este punto** pide confirmar que la TV muestra el video principal sin anuncios. **Continuar donde iba** utiliza el último punto guardado, y el historial permite elegir anteriores. El estado actual nunca sustituye automáticamente ese punto: la ausencia de metadatos de anuncios no demuestra que sea contenido principal. Los puntos sobreviven a timeouts, desconexiones, Backdrop, ceros temporales y reinicios del servicio. No hay recuperación automática.

Iniciar o recuperar puede reemplazar la cola. Pausa y reanudación requieren una sesión reciente y la capacidad de pausa anunciada. El panel distingue orden enviada y resultado confirmado; si vence el plazo, revisa la TV antes de repetir. Omitir anuncio solicita la función de YouTube; no bloquea publicidad ni corrige la causa del cierre.

El historial y la IP se guardan en `data/history.sqlite3`, excluido de Git. Para respaldarlos, detén el servicio y copia `data`. No se importó automáticamente el progreso de los experimentos anteriores. No se persisten credenciales de YouTube ni información de sesiones Cast. Los IDs de video y puntos guardados sí revelan historial de uso local.

### Acceso desde el teléfono

La PC y el teléfono deben estar en la misma red privada. Consulta la IPv4 Wi-Fi de la PC con `ipconfig`; no uses la IP del Chromecast en la dirección del navegador. Ejemplo si la **PC** tiene `192.168.1.5`:

```powershell
$env:CAST_WEB_TOKEN = .\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(24))"
$env:CAST_WEB_HOSTS = '127.0.0.1,localhost,192.168.1.5'
.\.venv\Scripts\python.exe -m app --host 192.168.1.5
```

Abre `http://192.168.1.5:8765` en el teléfono y coloca el valor de `CAST_WEB_TOKEN` en **Configurar conexión → Clave de acceso a la red → Usar clave**. Puedes consultar ese valor solo en tu propia terminal; no lo compartas en capturas ni commits. Si Windows solicita permiso de red, permite Python únicamente en redes privadas. No se abrió el firewall automáticamente. Si necesitas una regla, limita TCP 8765 al perfil privado y a tu subred local.

La clave también se exige desde la PC mientras esté configurada. Se conserva únicamente en memoria de la pestaña. Los comandos y el historial requieren clave; además se validan Host, Origin y JSON. El lanzador rechaza LAN sin clave de al menos 20 caracteres y una lista de hosts explícita. HTTP no cifra la clave en la LAN: úsalo solo en tu Wi-Fi privada de confianza. No abras puertos en el router ni publiques este servicio en Internet. Para volver a localhost, detén el servicio y ejecuta:

```powershell
Remove-Item Env:CAST_WEB_TOKEN -ErrorAction SilentlyContinue
Remove-Item Env:CAST_WEB_HOSTS -ErrorAction SilentlyContinue
.\.venv\Scripts\python.exe -m app
```

### Pruebas y arquitectura

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m pip check
```

La [documentación del panel](docs/panel-web.md) explica módulos, conservación de puntos, seguridad y verificación. Pasaron 28 pruebas automáticas con un dispositivo simulado. Además se probó la nueva API con el Chromecast real: mismo video en PLAYING desde 506 segundos, y el propietario confirmó visualmente el retroceso. Pausa/reanudación reales y acceso desde teléfono siguen pendientes; el refinamiento posterior de confirmación sostenida se verificó con pruebas automáticas.

## Investigación de YouTube

La [documentación de la investigación](docs/investigacion-chromecast.md) explica el protocolo, la evidencia del cierre al fondo de fotos, las limitaciones y la propuesta de control web.

Se observó una salida inesperada de YouTube sin pérdida de la conexión Cast del monitor ni reinicio observado del tiempo encendido. Después, el programa abrió el mismo video solicitando la posición 506 segundos; el Chromecast confirmó reproducción en 507.434 segundos y el propietario confirmó que se veía correctamente. Es una primera recuperación manual probada, no una corrección de la causa interna ni una vulnerabilidad demostrada.

El monitor `scripts/Observe-Chromecast.py` consulta el estado sin iniciar ni detener aplicaciones. El experimento `scripts/Recover-YouTube.py` sí abre YouTube y reemplaza la cola. Sus comandos, resultados y diferencias están descritos en la documentación.

## Entorno

| Componente | Estado |
| --- | --- |
| REA 6.5.0 | Instalado en Windows y Linux; Codex configurado para usar Linux |
| Ghidra 12.1.4 y JDK 21 | Instalados; comprobaciones de REA y descompilación ARM directa correctas |
| Wireshark / TShark 4.6.9 | Instalados; captura y análisis real mediante REA verificados |
| PyChromecast 14.0.10 | Instalado en `.venv` con Python 3.12 |
| Npcap 1.89 | Instalado; controlador activo e interfaz Wi-Fi verificada |
| WSL 2.7.13 y Ubuntu 24.04 | Activos; usuario de análisis `rea` sin privilegios de administrador |
| Binwalk 3.1.0 | Compilado desde la etiqueta oficial; detección mediante REA verificada |
| Unblob 26.6.4 | Instalado; todos sus extractores externos detectados y extracción de prueba verificada |
| Ghidra y Java dentro de Linux | Descompilación ELF ARM mediante REA verificada |

Las herramientas de Windows están en `%LOCALAPPDATA%\REA\tools`. Las de Linux están en `/home/rea/.local/share/rea`; Binwalk está en `/home/rea/.cargo/bin`. La conexión de Codex lanza `wsl.exe -d Ubuntu-24.04 -u rea --exec /home/rea/.local/bin/rea-linux mcp`. Cierra y vuelve a abrir Codex para cargar el cambio; no hace falta volver a reiniciar Windows.

La configuración anterior de Codex se conserva en `%USERPROFILE%\.codex\config.toml.rea.windows-20261015-202348.backup`. La prueba de conexión usó exactamente el comando guardado y verificó las 207 herramientas y la disponibilidad de Ghidra; informe en `evidence/linux-check/mcp-check.json`.

## Consultar el Chromecast

Desde PowerShell, en la carpeta del proyecto:

```powershell
. .\scripts\Enter-Rea.ps1
.\.venv\Scripts\python.exe scripts\Inspect-Chromecast.py
```

El comando realiza conexiones TCP a los puertos 8008, 8009 y 8443 y consultas HTTP GET a `/ssdp/device-desc.xml` y `/setup/eureka_info`. Muestra únicamente campos seleccionados del fabricante, modelo y versión. No guarda las respuestas completas que pueden contener datos de red e identificadores.

Para guardar un informe nuevo sin sobrescribir evidencia anterior:

```powershell
.\.venv\Scripts\python.exe scripts\Inspect-Chromecast.py --output evidence\consulta-02.json
```

La primera consulta obtuvo respuestas HTTP 200, fabricante `Google Inc.`, modelo anunciado `Eureka Dongle` y firmware `1.56.467165`. Estos datos por sí solos no confirman la revisión física del dispositivo.

La verificación del entorno incluyó una descompilación directa con Ghidra de un ELF ARM sintético que devuelve 42. El resultado recuperó `return 0x2a`. Esto comprueba el funcionamiento básico del descompilador; no es análisis del firmware del Chromecast. El registro está en `evidence/tools-check/ghidra-arm.log`.

## Capturas

Después de instalar Npcap, enumera las interfaces:

```powershell
. .\scripts\Enter-Rea.ps1
tshark -D
```

Selecciona la interfaz conectada a la misma red del Chromecast y captura durante un periodo acotado; sustituye `NUMERO`:

```powershell
.\scripts\Capture-Chromecast.ps1 -Interface NUMERO -Seconds 60
```

El filtro de captura es `host 192.168.1.6`. El comando guarda un archivo nuevo en `captures` y muestra su SHA-256. Solo verá tráfico visible para esa interfaz: estar en la misma Wi-Fi no garantiza observar las comunicaciones del Chromecast con el teléfono o Internet. Para ello puede requerirse una captura en el router o una interfaz de monitor compatible. El contenido cifrado permanece cifrado.

La captura de prueba en Wi-Fi guardó 52 paquetes de las consultas entre la PC y el Chromecast. REA la procesó correctamente, con los dos extremos y las dos rutas HTTP esperadas. Evidencia: `ev_fa7135f5f67ad529e1429b2d933f1f2aaf8263dedee2fe9d04c5ff497a9dd328`, guardada en `evidence/pcap-check.json`. La comprobación cubre esa captura; no establece visibilidad de todo el tráfico del dispositivo.

REA puede resumir una captura guardada:

```powershell
rea inspect-pcap-client --json
rea inspect-pcap-capture "C:\ruta\captura.pcapng" --json
```

## Firmware y Linux

REA limita su proveedor Ghidra de Windows a ciertos formatos PE y raw 6502. Los ELF ARM del firmware deben analizarse con Ghidra directamente o con REA dentro de Linux; instalar Ghidra en Windows no elimina esa limitación del proveedor.

Para ejecutar REA en Linux desde PowerShell:

```powershell
.\scripts\Invoke-ReaLinux.ps1 doctor --provider ghidra --json
.\scripts\Invoke-ReaLinux.ps1 inspect-firmware-regions /mnt/c/ruta/firmware.bin --json
.\scripts\Invoke-ReaLinux.ps1 extract-firmware /mnt/c/ruta/firmware.bin /home/rea/analysis/extraccion-nueva --json
```

Los comandos reciben rutas Linux. Una ruta `C:\ruta\archivo.bin` corresponde a `/mnt/c/ruta/archivo.bin`. El directorio de salida de extracción debe ser nuevo y estar bajo `/home/rea/analysis`, en el disco nativo de Linux. La extracción hacia el disco compartido de Windows falló en la comprobación de permisos `fchmod`; no se desactivaron controles para eludirla. Puedes abrir los resultados desde el Explorador en `\\wsl.localhost\Ubuntu-24.04\home\rea\analysis`.

El lanzador carga `scripts/rea-linux-env.sh`, con las rutas de Ghidra, Java, Binwalk, Unblob y las utilidades de Linux. Los paquetes del sistema incluyen `procps`, `util-linux`, OpenJDK 21, herramientas de compilación, `libfontconfig1-dev`, `liblzma-dev`, `libbz2-dev`, `zlib1g-dev`, `libssl-dev`, Python con venv, TShark, `unzip`, SquashFS, e2fsprogs, mtd-utils, 7zip, unar, zstd, lz4, lzop, device-tree-compiler, cabextract, erofs-utils, lziprecover, partclone y android-sdk-libsparse-utils. Sasquatch se instaló desde la publicación oficial de ONEKEY `sasquatch-v4.5.1-6`, verificando su SHA-256. Rust se instaló con rustup y se usó para compilar Binwalk 3.1.0 con su archivo de dependencias bloqueadas.

`Install-ReaLinux.sh` permite reinstalar los componentes de usuario si las dependencias del sistema y Rust ya están configurados. Requiere la descarga de Ghidra conservada en `evidence/tool-downloads`; no registra por sí mismo el servidor en Codex. La instalación npm omite scripts opcionales de instalación; no se ha configurado Frida para instrumentación dinámica.

## Verificación del entorno Linux

Se probaron las siguientes operaciones con un archivo generado localmente, sin ejecutar firmware del dispositivo:

- Detección de una región gzip con Binwalk a través de REA: `evidence/linux-check/regions.json`.
- Extracción gzip → TAR → ELF ARM con Unblob y comparación exacta del ELF recuperado contra el original: `evidence/linux-check/extraction-linux.json`.
- Descompilación ELF ARM con Ghidra a través de REA, recuperando `return 0x2a`: `evidence/linux-check/arm-decompile.json`.
- Análisis en Linux de la captura de 52 paquetes del Chromecast: `evidence/linux-check/pcap-linux.json`.
- Inicio del servidor MCP usando la configuración guardada de Codex: `evidence/linux-check/mcp-check.json`.

La extracción del archivo de prueba terminó con cobertura completa y sin extractores faltantes. Estas comprobaciones verifican el entorno y esos formatos de prueba; un firmware real puede tener formatos, cifrado o límites de tamaño diferentes. REA admite entradas de firmware de hasta 128 MiB en esta versión.

No se ha obtenido un volcado de firmware ni acceso al sistema del Chromecast. Las consultas de red realizadas no implican acceso a su memoria flash ni disponibilidad de ADB.

## Evidencia local

`evidence`, `captures`, `firmware`, `extracted` y `.venv` están excluidos de Git. Conserva los originales del firmware y realiza el análisis sobre copias. Las capturas pueden contener información privada.

## Referencias

- [REA: instalación](https://github.com/morluto/rea/blob/main/docs/installation.md)
- [REA: Ghidra en Windows](https://github.com/morluto/rea/blob/main/docs/windows-ghidra-p0.md)
- [REA: firmware](https://github.com/morluto/rea/blob/main/docs/firmware-analysis.md)
- [REA: capturas guardadas](https://github.com/morluto/rea/blob/main/docs/pcap-analysis.md)
- [WSL](https://learn.microsoft.com/windows/wsl/install)
- [Npcap](https://npcap.com/)
