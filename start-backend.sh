#!/bin/sh
set -eu
echo "=== NESTORA ENGINE VERSION 2.4.0 ==="

python -m app.worker &
worker_pid=$!

cleanup() {
  kill "$worker_pid" 2>/dev/null || true
}

trap cleanup INT TERM EXIT

exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
