# Multi-stage reproducible Docker container for Solana Inside the Block Analyzer
FROM python:3.11-slim as base

WORKDIR /app

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    SOLANA_RPC_URL="https://api.mainnet-beta.solana.com"

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source tree
COPY . .

# Default execution: run tests to verify integrity, then execute dry-run pipeline
CMD ["sh", "-c", "pytest -v && python -m analyzer.cli --dry-run"]
