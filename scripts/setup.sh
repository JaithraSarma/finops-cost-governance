#!/usr/bin/env bash
# setup.sh — Bootstrap local development environment
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

echo "=== FinOps Cost Governance — Local Setup ==="

# ── Python virtual environment ───────────────────────────────────────────────
if [ ! -d ".venv" ]; then
    echo "[1/4] Creating Python virtual environment..."
    python3 -m venv .venv
else
    echo "[1/4] Virtual environment already exists."
fi

echo "[2/4] Installing Python dependencies..."
source .venv/bin/activate 2>/dev/null || .venv/Scripts/activate 2>/dev/null
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt

# ── Environment file ─────────────────────────────────────────────────────────
if [ ! -f ".env" ]; then
    echo "[3/4] Creating .env from .env.example..."
    cp .env.example .env
    echo "       ⚠  Edit .env with your Azure subscription details."
else
    echo "[3/4] .env already exists — skipping."
fi

# ── Docker (Azurite + Grafana) ───────────────────────────────────────────────
if command -v docker &>/dev/null && command -v docker-compose &>/dev/null; then
    echo "[4/4] Starting Azurite & Grafana via Docker Compose..."
    docker-compose up -d
else
    echo "[4/4] Docker not found — skipping containers."
    echo "       Install Docker to run Azurite and Grafana locally."
fi

echo ""
echo "Setup complete! Next steps:"
echo "  1. Edit .env with your Azure subscription ID and credentials."
echo "  2. Seed sample data:    make seed"
echo "  3. Run tests:           make test"
echo "  4. Open Grafana:        http://localhost:3000  (admin/admin)"
