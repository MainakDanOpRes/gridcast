function Run($cmd) {
    Write-Host ">> $cmd" -ForegroundColor Cyan
    Invoke-Expression $cmd
    if ($LASTEXITCODE -ne 0) {
        Write-Host "FAILED: $cmd" -ForegroundColor Red
        exit $LASTEXITCODE
    }
}

Run "uv run ruff check ."
Run "uv run ruff format --check ."
Run "uv run mypy"
Run "uv run pytest -q"

Write-Host "All checks passed" -ForegroundColor Green