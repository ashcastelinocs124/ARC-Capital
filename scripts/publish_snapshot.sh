#!/bin/zsh
# Refresh the data, freeze it to JSON and deploy the read-only dashboard to Vercel.
# Run by cron (see crontab -l); log at data/publish.log. Pass --no-refresh to skip the jobs.
set -euo pipefail
export PATH="/opt/homebrew/bin:$HOME/.local/bin:$HOME/.cargo/bin:/usr/local/bin:$PATH"
cd "$(dirname "$0")/.."

uv run python scripts/export_snapshot.py "$@"

cd frontend
# ponytail: prebuilt deploy so the gitignored public/api snapshot ships without being committed.
vercel pull --yes --environment=production >/dev/null
VITE_STATIC=1 vercel build --prod
vercel deploy --prebuilt --prod
