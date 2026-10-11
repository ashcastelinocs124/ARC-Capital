#!/bin/zsh
# Sunday-morning Weekly Deep Dive: build the week's report, draft it on Substack, publish the site.
# Cron: Sunday 06:00 America/New_York (Mac crontab in Pacific time: 0 3 * * 0). Log: data/publish.log.
set -euo pipefail
export PATH="/opt/homebrew/bin:$HOME/.local/bin:$HOME/.cargo/bin:/usr/local/bin:$PATH"
cd "$(dirname "$0")/.."

uv run python -c 'from castelino.dashboard.endpoints.refresh import job_weekly_deep_dive as j; print("weekly:", j())' \
  || echo "weekly: no report built (skipped or failed; see GET /weekly/status)"
uv run python -m castelino.substack_weekly || echo "substack weekly: push failed, continuing"
scripts/publish_snapshot.sh --no-refresh
