#!/bin/sh
# Fly machine entrypoint. The volume mounted on /app/data hides the committed config files there
# (indicator YAMLs, the PMI csv), so copy this image's versions onto it, then run the daily cron.
set -e
cp -f /app/seed-data/* /app/data/
# The admin Daily desk API (password-gated; the only thing reachable from the internet).
uvicorn castelino.dashboard.desk_app:app --host 0.0.0.0 --port 8080 &
exec supercronic /app/deploy/crontab
