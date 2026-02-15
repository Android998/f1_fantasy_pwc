#!/usr/bin/env bash
set -e

echo "Running migrations..."
python manage.py migrate --noinput

echo "Collecting static..."
python manage.py collectstatic --noinput || true

echo "Starting gunicorn..."
gunicorn f1porra_website.wsgi:application --bind 0.0.0.0:${PORT} --workers 2 --timeout 120
