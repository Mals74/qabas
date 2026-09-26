#!/usr/bin/env bash
# One command to run Qabas (used by Replit's Run button and deployments).
set -e
cd "$(dirname "$0")"

# 1) Python packages
pip install -q -r backend/requirements.txt

# 2) Build the React app if Node is available (a prebuilt copy is in frontend/dist)
if command -v npm >/dev/null 2>&1; then
  (cd frontend && npm install --silent && npm run build --silent)
fi

# 3) Start the API + web app on the port Replit provides
cd backend
exec python -m uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
