#!/bin/bash
PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_DIR"

if [ -f .venv/bin/activate ]; then
    source .venv/bin/activate
fi

exec uvicorn jlc_search.api:app --host 0.0.0.0 --port 8000
