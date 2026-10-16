$ErrorActionPreference = 'Stop'
$reaTools = Join-Path $env:LOCALAPPDATA 'REA\tools'
$env:GHIDRA_INSTALL_DIR = Join-Path $reaTools 'ghidra_12.1.4_PUBLIC'
$env:JAVA_HOME = Join-Path $reaTools 'jdk-21.0.12.1+1'
$env:REA_TSHARK_COMMAND = Join-Path $env:ProgramFiles 'Wireshark\tshark.exe'
$env:REA_CAPINFOS_COMMAND = Join-Path $env:ProgramFiles 'Wireshark\capinfos.exe'
$env:Path = "$($env:JAVA_HOME)\bin;$env:ProgramFiles\Wireshark;$env:Path"
