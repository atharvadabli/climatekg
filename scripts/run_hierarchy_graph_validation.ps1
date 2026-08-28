param(
    [string]$Neo4jPassword = "climatekg-hierarchy-test",
    [string]$Neo4jImage = "neo4j:5.26-community"
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$runtime = Join-Path $root "climatekg\runtime\neo4j_hierarchy"
$data = Join-Path $runtime "data"
$logs = Join-Path $runtime "logs"
$output = Join-Path $root "climatekg\runtime\outputs\hierarchy_e2e_het_v10"
$containerName = "climatekg-neo4j-hierarchy"

New-Item -ItemType Directory -Force -Path $data, $logs, $output | Out-Null

Write-Host "[1/5] Verifying Docker Desktop"
docker info | Out-Null

Write-Host "[2/5] Starting isolated Neo4j on ports 7475/7688"
$container = docker ps -a --filter "name=^/$containerName$" --format "{{.Names}}"
if ($container -eq $containerName) {
    docker start $containerName | Out-Null
} else {
    docker run -d `
        --name $containerName `
        -p 7475:7474 `
        -p 7688:7687 `
        -e "NEO4J_AUTH=neo4j/$Neo4jPassword" `
        -e "NEO4J_server_memory_heap_initial__size=512m" `
        -e "NEO4J_server_memory_heap_max__size=2G" `
        -e "NEO4J_server_memory_pagecache_size=1G" `
        -v "${data}:/data" `
        -v "${logs}:/logs" `
        $Neo4jImage | Out-Null
}

Write-Host "[3/5] Waiting for authenticated Neo4j HTTP"
$deadline = (Get-Date).AddMinutes(5)
Set-Location $root
do {
    python -c "from climatekg.graph import Neo4jHttp; Neo4jHttp(http_uri='http://localhost:7475',password='$Neo4jPassword').execute([{'statement':'RETURN 1'}])" 2>$null
    if ($LASTEXITCODE -eq 0) { break }
    if ((Get-Date) -ge $deadline) {
        docker logs --tail 100 $containerName
        throw "Isolated Neo4j did not become ready within five minutes."
    }
    Start-Sleep -Seconds 3
} while ($true)

Write-Host "[4/5] Ingesting and round-tripping the hierarchy paper"
python scripts\validate_single_paper_graph.py `
    --source-final climatekg\runtime\outputs\hierarchy_e2e_het_v10\final\final_paper.json `
    --http-uri http://localhost:7475 `
    --password $Neo4jPassword `
    --output climatekg\runtime\outputs\hierarchy_e2e_het_v10\neo4j_round_trip.json `
    --round-trip-final climatekg\runtime\outputs\hierarchy_e2e_het_v10\graph_roundtrip_final.json
if ($LASTEXITCODE -ne 0) { throw "Neo4j round-trip validation failed." }

Write-Host "[5/5] Running queries from graph-reloaded data"
python scripts\run_hierarchy_query_examples.py `
    --source-final climatekg\runtime\outputs\hierarchy_e2e_het_v10\graph_roundtrip_final.json `
    --output-root climatekg\runtime\outputs\hierarchy_e2e_het_v10\queries_graph
if ($LASTEXITCODE -ne 0) { throw "Graph-backed query validation failed." }

Write-Host "Results: $output"
