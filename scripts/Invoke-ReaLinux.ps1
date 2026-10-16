# Example: .\scripts\Invoke-ReaLinux.ps1 doctor --provider ghidra --json
$ErrorActionPreference = 'Stop'
& wsl.exe -d Ubuntu-24.04 -u rea --exec /home/rea/.local/bin/rea-linux @args
exit $LASTEXITCODE
