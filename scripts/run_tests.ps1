Write-Host "==========================================" -ForegroundColor Cyan
Write-Host " Running Solana Analyzer Verification Suite" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan

Write-Host "[1/3] Checking environment & imports..." -ForegroundColor Yellow
python -c "import numpy; import scipy; print('Numpy and Scipy: OK')"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "[2/3] Executing unit tests..." -ForegroundColor Yellow
python -m pytest -v tests/
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "[3/3] Running batch analysis on empirical block traces..." -ForegroundColor Yellow
python scripts/run_batch_analysis.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "==========================================" -ForegroundColor Green
Write-Host " All tests and analyses passed 100%!" -ForegroundColor Green
Write-Host "==========================================" -ForegroundColor Green
