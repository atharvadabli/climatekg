param(
    [switch]$Force,
    [int]$Limit = 0
)

$ErrorActionPreference = "Stop"
$CodeRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$ProjectRoot = "F:\Atharv\lulc_suggestor_poc\19_aug_final"
$Python = Join-Path $ProjectRoot ".venv-climatekg\Scripts\python.exe"
$Dataset = Join-Path $PSScriptRoot "questions.json"
$Graph = Join-Path $ProjectRoot "climatekg\runtime\outputs\three_system_benchmark\parquet_graph_analysis_case_patch_v1"
$Output = Join-Path $ProjectRoot "climatekg\runtime\outputs\climatekg_30_cross_paper_v1"

if (-not (Test-Path $Python)) {
    throw "ClimateKG Python environment not found: $Python"
}
if (-not (Test-Path (Join-Path $Graph "papers.parquet"))) {
    throw "115-paper Parquet graph not found: $Graph"
}

$arguments = @(
    (Join-Path $CodeRoot "scripts\run_query_architecture_benchmark.py"),
    "--project-root", $ProjectRoot,
    "--code-root", $CodeRoot,
    "--variant", "candidate_context_rescore_v2",
    "--graph-root", $Graph,
    "--dataset", $Dataset,
    "--output", $Output,
    "--system", "climatekg",
    "--live-query-planning"
)
if ($Force) { $arguments += "--force" }
if ($Limit -gt 0) { $arguments += @("--limit", $Limit) }

& $Python -u @arguments
if ($LASTEXITCODE -ne 0) {
    throw "ClimateKG query run failed with exit code $LASTEXITCODE."
}

& $Python -u (Join-Path $PSScriptRoot "summarize.py") `
    --dataset $Dataset `
    --run-root (Join-Path $Output "candidate_context_rescore_v2") `
    --output (Join-Path $Output "report")
if ($LASTEXITCODE -ne 0) {
    throw "Evaluation report generation failed with exit code $LASTEXITCODE."
}

Write-Host "Raw traces: $Output"
Write-Host "Summary: $(Join-Path $Output 'report\REPORT.md')"
