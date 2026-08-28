param(
    [string]$Neo4jPassword = "climatekg-test",
    [string]$Neo4jImage = "neo4j:5.26-community"
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$runtime = Join-Path $root "climatekg\runtime\neo4j"
$data = Join-Path $runtime "data"
$logs = Join-Path $runtime "logs"
$plugins = Join-Path $runtime "plugins"

New-Item -ItemType Directory -Force -Path $data, $logs, $plugins | Out-Null

Write-Host "[1/6] Verifying Docker Desktop"
docker info | Out-Null

Write-Host "[2/6] Starting Neo4j"
$container = docker ps -a --filter "name=^/climatekg-neo4j$" --format "{{.Names}}"
if ($container -eq "climatekg-neo4j") {
    docker start climatekg-neo4j | Out-Null
} else {
    docker run -d `
        --name climatekg-neo4j `
        -p 7474:7474 `
        -p 7687:7687 `
        -e "NEO4J_AUTH=neo4j/$Neo4jPassword" `
        -e "NEO4J_server_memory_heap_initial__size=1G" `
        -e "NEO4J_server_memory_heap_max__size=4G" `
        -e "NEO4J_server_memory_pagecache_size=2G" `
        -v "${data}:/data" `
        -v "${logs}:/logs" `
        -v "${plugins}:/plugins" `
        $Neo4jImage | Out-Null
}

Write-Host "[3/6] Waiting for Neo4j HTTP and Bolt ports"
$deadline = (Get-Date).AddMinutes(5)
$env:NEO4J_PASSWORD = $Neo4jPassword
Set-Location $root
do {
    $http = Test-NetConnection -ComputerName localhost -Port 7474 -WarningAction SilentlyContinue
    $bolt = Test-NetConnection -ComputerName localhost -Port 7687 -WarningAction SilentlyContinue
    $ready = $false
    if ($http.TcpTestSucceeded -and $bolt.TcpTestSucceeded) {
        python -c "from climatekg.graph import Neo4jHttp; Neo4jHttp().execute([{'statement':'RETURN 1'}])" 2>$null
        $ready = $LASTEXITCODE -eq 0
    }
    if ($ready) {
        break
    }
    if ((Get-Date) -ge $deadline) {
        docker logs --tail 100 climatekg-neo4j
        throw "Neo4j did not open ports 7474 and 7687 within five minutes."
    }
    Start-Sleep -Seconds 3
} while ($true)

Write-Host "[4/6] Ingesting and verifying the ten finalized papers"
python -m climatekg.cli ingest
if ($LASTEXITCODE -ne 0) {
    throw "Graph ingestion failed with exit code $LASTEXITCODE."
}

Write-Host "[5/6] Running generic and context-dependent query validation"
python -m climatekg.cli validate-queries
if ($LASTEXITCODE -ne 0) {
    throw "Query validation completed with failed checks. Inspect climatekg/runtime/outputs/query_validation."
}

Write-Host "[6/6] Complete"
$latest = Get-ChildItem -LiteralPath (Join-Path $root "climatekg\runtime\outputs\query_validation") -Directory |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1
Write-Host "Results: $($latest.FullName)"
