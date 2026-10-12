#!/bin/sh
# Fly machine entrypoint. The volume mounted on /app/data hides the committed config files there
# (indicator YAMLs, the PMI csv), so copy this image's versions onto it, then run the daily cron.
set -e
cp -f /app/seed-data/* /app/data/
exec supercronic /app/deploy/crontab
