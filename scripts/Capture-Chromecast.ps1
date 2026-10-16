param(
    [Parameter(Mandatory)][string]$Interface,
    [ValidateRange(1, 600)][int]$Seconds = 60,
    [ipaddress]$DeviceAddress = '192.168.1.6'
)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'Enter-Rea.ps1')
$captureRoot = Join-Path (Split-Path $PSScriptRoot -Parent) 'captures'
New-Item -ItemType Directory -Path $captureRoot -Force | Out-Null
$captureFile = Join-Path $captureRoot ("chromecast-{0}-{1}.pcapng" -f (Get-Date -Format 'yyyyMMdd-HHmmss'), ([guid]::NewGuid().ToString('N').Substring(0, 8)))
& $env:REA_TSHARK_COMMAND -i $Interface -f "host $DeviceAddress" -a "duration:$Seconds" -w $captureFile
if ($LASTEXITCODE -ne 0) { throw 'No se pudo capturar. Comprueba Npcap y la interfaz con tshark -D.' }
Get-FileHash -LiteralPath $captureFile -Algorithm SHA256
