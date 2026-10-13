#!/bin/sh
# The Fly.io version of publish_snapshot.sh, run daily by deploy/crontab: refresh the data, freeze it
# to JSON, draft the Substack note and deploy the read-only dashboard to Vercel. The code is this image,
# which CI only deploys from a green main commit, so there is no worktree or CI check here.
# Pass --no-refresh to skip the jobs; set SKIP_SUBSTACK=1 to skip the Substack draft.
set -eu
cd /app
echo "== $(date) publish_server $*"
python scripts/export_snapshot.py "$@" # writes frontend/public/api/
# SKIP_SUBSTACK=1 (CI's code-only republish): leave the day's draft alone so hand edits in Substack survive
[ -n "${SKIP_SUBSTACK:-}" ] || python -m castelino.substack || echo "substack: push failed, continuing with the deploy"

cd frontend # VERCEL_ORG_ID / VERCEL_PROJECT_ID come from fly.toml, VERCEL_TOKEN from fly secrets
vercel pull --yes --environment=production --token "$VERCEL_TOKEN" >/dev/null
VITE_STATIC=1 vercel build --prod --token "$VERCEL_TOKEN"
vercel deploy --prebuilt --prod --token "$VERCEL_TOKEN"
echo "Deployed $(date)"
