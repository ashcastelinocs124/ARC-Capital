#!/usr/bin/env bash
# Copy the jobs' state between data/ and a checkout of the private `data` branch.
# Used by .github/workflows/publish.yml: `pull` before a run, `push` after a daily refresh.
# usage: scripts/state_sync.sh pull|push <state-dir>    (ARC_ROOT overrides the repo root)
set -euo pipefail
cd "${ARC_ROOT:-$(dirname "$0")/..}"
mode=$1 state=$2
# Gitignored state only; tracked inputs (yaml, universe_seed.csv, lexicons) come from the code checkout.
PATHS=(
  data/updates data/update_agent data/research
  data/adoption/adoption.db data/adoption/job_boards.csv data/adoption/recipes data/adoption/universe.csv
  data/sector_sentiment.json data/sector_universe.json data/regime_forecast.json
)
for p in "${PATHS[@]}"; do
  if [[ $mode == pull ]]; then src="$state/$p" dst="$p"; else src="$p" dst="$state/$p"; fi
  [[ -e $src ]] || continue
  mkdir -p "$(dirname "$dst")"
  if [[ -d $src ]]; then
    rsync -a --delete --exclude run.lock --exclude status.json "$src/" "$dst/"
  else
    cp -p "$src" "$dst"
  fi
done
