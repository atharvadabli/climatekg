param(
    [string]$ProjectRoot = "F:\Atharv\lulc_suggestor_poc\19_aug_final"
)

$ErrorActionPreference = "Stop"
$Python = Join-Path $ProjectRoot ".venv-climatekg\Scripts\python.exe"
$Harness = Join-Path $ProjectRoot "climatekg\runtime\worktrees\query-architecture-benchmark"
$Dataset = Join-Path $ProjectRoot "evaluation\output\climatekg_benchmark\dataset_v3_current_findings_30\cases.json"
$Output = Join-Path $ProjectRoot "evaluation\output\query_architecture_benchmark_v3_30"
$Variants = Join-Path $Output "variants"
$Specs = Join-Path $Output "query_parse\specs"
$Graph = Join-Path $ProjectRoot "climatekg\runtime\outputs\three_system_benchmark\parquet_graph"
$Plain = Join-Path $ProjectRoot "evaluation\shared\indexes\plain_rag"
$GraphRag = Join-Path $ProjectRoot "climatekg\runtime\outputs\three_system_benchmark\baselines\graphrag"
$Baseline = Join-Path $ProjectRoot "climatekg\runtime\worktrees\query-baseline"
$EvidenceUnion = Join-Path $ProjectRoot "climatekg\runtime\worktrees\query-evidence-union"
$Runner = Join-Path $Harness "scripts\run_query_architecture_benchmark.py"

& $Python (Join-Path $Harness "scripts\prepare_query_specs.py") `
    --project-root $ProjectRoot `
    --code-root $Baseline `
    --dataset $Dataset `
    --output (Join-Path $Output "query_parse")
if ($LASTEXITCODE -ne 0) {
    throw "Query parsing failed with exit code $LASTEXITCODE"
}

function Run-System {
    param([string]$Name, [string]$System, [string]$CodeRoot)
    Write-Host "Starting $Name"
    $arguments = @(
        $Runner,
        "--project-root", $ProjectRoot,
        "--code-root", $CodeRoot,
        "--variant", $Name,
        "--system", $System,
        "--graph-root", $Graph,
        "--dataset", $Dataset,
        "--output", $Variants,
        "--plain-index", $Plain,
        "--graphrag-index", $GraphRag,
        "--spec-dir", $Specs
    )
    & $Python @arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$Name failed with exit code $LASTEXITCODE"
    }
}

Run-System "plain_rag" "plain_rag" $Baseline
Run-System "graphrag" "graphrag" $Baseline
Run-System "climatekg_evidence_union" "climatekg" $EvidenceUnion

& $Python (Join-Path $Harness "scripts\summarize_query_architecture_benchmark_v3.py") `
    --dataset $Dataset `
    --variants-root $Variants `
    --output $Output
if ($LASTEXITCODE -ne 0) {
    throw "Summary generation failed with exit code $LASTEXITCODE"
}

& $Python (Join-Path $Harness "scripts\analyze_query_benchmark_misses.py") `
    --dataset $Dataset `
    --variants-root $Variants `
    --output (Join-Path $Output "retrieval_miss_trace.md")
if ($LASTEXITCODE -ne 0) {
    throw "Retrieval miss analysis failed with exit code $LASTEXITCODE"
}

& $Python (Join-Path $Harness "scripts\judge_query_benchmark_30.py") `
    --project-root $ProjectRoot `
    --code-root $Baseline `
    --dataset $Dataset `
    --variants-root $Variants `
    --output (Join-Path $Output "blinded_judge")
if ($LASTEXITCODE -ne 0) {
    throw "Blinded answer review failed with exit code $LASTEXITCODE"
}
