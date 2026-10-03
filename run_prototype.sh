#!/usr/bin/env bash
# ==============================================================================
# Personal AI Call Agent — Working Prototype Launcher
# ==============================================================================
set -e

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="${REPO_DIR}/backend"

echo "========================================================================"
echo "🚀 Launching Personal AI Call Agent Prototype"
echo "========================================================================"

cd "${BACKEND_DIR}"

if [ ! -d "venv" ]; then
    echo "📦 Creating Python virtual environment..."
    python3 -m venv venv
    source venv/bin/activate
    pip install --upgrade pip
    pip install -r requirements.txt
else
    source venv/bin/activate
fi

echo "🔍 Running quick automated sanity test..."
pytest tests/test_prototype.py -q

echo "========================================================================"
echo "✨ Prototype Server Ready!"
echo "🌐 Open your browser and navigate to: http://localhost:8000"
echo "========================================================================"

uvicorn app.main:api_app --host 0.0.0.0 --port 8000 --reload
