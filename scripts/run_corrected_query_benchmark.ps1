param(
    [string]$ProjectRoot = "F:\Atharv\lulc_suggestor_poc\19_aug_final"
)

$ErrorActionPreference = "Stop"
$Python = Join-Path $ProjectRoot ".venv-climatekg\Scripts\python.exe"
$Harness = Join-Path $ProjectRoot "climatekg\runtime\worktrees\query-architecture-benchmark"
$Dataset = Join-Path $ProjectRoot "evaluation\output\climatekg_benchmark\dataset_v2_current_findings_10\cases.json"
$Output = Join-Path $ProjectRoot "evaluation\output\query_architecture_benchmark_v2"
$Variants = Join-Path $Output "variants"
$Specs = Join-Path $Output "query_parse\specs"
$Graph = Join-Path $ProjectRoot "climatekg\runtime\outputs\three_system_benchmark\parquet_graph"
$Plain = Join-Path $ProjectRoot "evaluation\shared\indexes\plain_rag"
$GraphRag = Join-Path $ProjectRoot "climatekg\runtime\outputs\three_system_benchmark\baselines\graphrag"
$Baseline = Join-Path $ProjectRoot "climatekg\runtime\worktrees\query-baseline"
$EvidenceUnion = Join-Path $ProjectRoot "climatekg\runtime\worktrees\query-evidence-union"
$SoftContext = Join-Path $ProjectRoot "climatekg\runtime\worktrees\query-soft-context"
$GraphExpansion = Join-Path $ProjectRoot "climatekg\runtime\worktrees\query-graph-expansion"
$Runner = Join-Path $Harness "scripts\run_query_architecture_benchmark.py"

function Run-Variant {
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

Run-Variant "plain_rag" "plain_rag" $Baseline
Run-Variant "graphrag" "graphrag" $Baseline
Run-Variant "baseline" "climatekg" $Baseline
Run-Variant "evidence_union" "climatekg" $EvidenceUnion
Run-Variant "soft_context" "climatekg" $SoftContext
Run-Variant "graph_expansion" "climatekg" $GraphExpansion

& $Python (Join-Path $Harness "scripts\summarize_query_architecture_benchmark_v2.py") `
    --dataset $Dataset `
    --variants-root $Variants `
    --output $Output
if ($LASTEXITCODE -ne 0) {
    throw "Summary generation failed with exit code $LASTEXITCODE"
}
