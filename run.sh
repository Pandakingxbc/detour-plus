#!/usr/bin/env bash
set -e

cd "$(dirname "$0")"

# Load env vars
if [ -f .env ]; then
  export $(grep -v '^#' .env | grep -v '^\s*$' | xargs)
fi

# Start Python agent backend
echo "Starting agent backend on :8000..."
python -m uvicorn api.app:app --host 0.0.0.0 --port 8000 --reload &
BACKEND_PID=$!

# Start frontend
echo "Starting frontend on :3000..."
cd frontend && npm run dev &
FRONTEND_PID=$!

cd ..

trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null" EXIT
wait
