#!/usr/bin/env bash
set -e

echo "=========================================="
echo " Running Solana Analyzer Verification Suite"
echo "=========================================="

echo "[1/3] Checking environment & imports..."
python -c "import numpy; import scipy; print('Numpy and Scipy: OK')"

echo "[2/3] Executing unit tests..."
python -m pytest -v tests/

echo "[3/3] Running batch analysis on empirical block traces..."
python scripts/run_batch_analysis.py

echo "=========================================="
echo " All tests and analyses passed 100%!"
echo "=========================================="
