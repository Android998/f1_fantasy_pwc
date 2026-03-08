#!/usr/bin/env bash
set -e

echo "Running migrations..."
python manage.py migrate --noinput

echo "Collecting static..."
python manage.py collectstatic --noinput || true

echo "Starting GP results watcher (background, interval=60 min)..."
python manage.py process_gp_results --watch --interval 60 >> /tmp/watcher.log 2>&1 &
WATCHER_PID=$!
echo "Watcher started (PID: $WATCHER_PID) — logs at /tmp/watcher.log"

# Ensure the watcher is stopped when the container shuts down
trap "kill $WATCHER_PID 2>/dev/null; wait $WATCHER_PID 2>/dev/null" EXIT TERM INT

echo "Starting gunicorn..."
gunicorn f1porra_website.wsgi:application --bind 0.0.0.0:${PORT} --workers 2 --timeout 120
