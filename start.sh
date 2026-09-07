#!/usr/bin/env bash

set -e

echo "========================================="
echo "Starting YouTube Music backend"
echo "========================================="

echo "Starting PO Token provider..."

python -m bgutil_ytdlp_pot_provider.server \
    --port 4416 &

POT_PID=$!

echo "PO Token provider PID: $POT_PID"

sleep 3

echo "Starting Flask/Gunicorn..."

exec gunicorn \
    --bind 0.0.0.0:${PORT:-10000} \
    --workers 1 \
    --threads 4 \
    --timeout 120 \
    app:app
