param(
    [int]$Port = 8780
)

$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root ".venv-climatekg\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) {
    throw "Python environment not found: $python"
}

Push-Location $root
try {
    & $python -m webapp.server --port $Port
}
finally {
    Pop-Location
}
