param(
    [int]$Port = 8765,
    [string]$HostAddress = "127.0.0.1"
)

$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
python .\visualizer\server.py --host $HostAddress --port $Port
