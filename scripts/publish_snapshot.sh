#!/bin/zsh
# Refresh the data, freeze it to JSON and deploy the read-only dashboard to Vercel.
# Run by cron (see crontab -l); log at data/publish.log. Pass --no-refresh to skip the jobs.
#
# Data comes from this machine (the backend's gitignored state). Code comes from a clean copy of
# origin/main, and only from a commit whose CI run (.github/workflows/ci.yml) succeeded. If the
# newest main commit isn't green, the last deployed good commit is rebuilt with today's data, so
# uncommitted or failing code never goes live but the numbers still update.
set -euo pipefail
export PATH="/opt/homebrew/bin:$HOME/.local/bin:$HOME/.cargo/bin:/usr/local/bin:$PATH"
cd "$(dirname "$0")/.."
REPO=$PWD
LAST="$REPO/data/publish_last_sha" # last commit deployed, i.e. the last known-good code
WT="$HOME/.cache/arc-publish"      # clean worktree the site is built from

uv run python scripts/export_snapshot.py "$@" # writes frontend/public/api/
# Draft today's Morning Note on Substack (you publish it there). Never blocks the deploy.
uv run python -m castelino.substack || echo "substack: push failed, continuing with the deploy"

git fetch -q origin main
SHA=$(git rev-parse origin/main)
# A gh failure (no auth, no network) counts as not green: fail safe to the last good commit.
CI=$(gh run list --workflow ci.yml --commit "$SHA" --json conclusion -q '.[0].conclusion' 2>/dev/null || true)
if [[ "$CI" == success ]]; then
  DEPLOY=$SHA
elif [[ -s "$LAST" ]]; then
  DEPLOY=$(<"$LAST")
  echo "CI for ${SHA:0:7} is '${CI:-unknown}': redeploying last good ${DEPLOY:0:7} with fresh data"
else
  echo "No CI-green main commit deployed yet and CI for ${SHA:0:7} is '${CI:-unknown}': not deploying" >&2
  exit 1
fi

git worktree remove --force "$WT" 2>/dev/null || true
git worktree prune
git worktree add -q --detach "$WT" "$DEPLOY"
# The private catalog (api/admin/) ships only in a build that has the password gate.
EXCLUDE=()
[[ -f "$WT/frontend/middleware.ts" ]] || EXCLUDE=(--exclude admin/)
rsync -a --delete "${EXCLUDE[@]}" frontend/public/api/ "$WT/frontend/public/api/" # the snapshot is gitignored
cp -R frontend/.vercel "$WT/frontend/"                            # project link

cd "$WT/frontend"
npm ci --silent
# ponytail: prebuilt deploy so the gitignored public/api snapshot ships without being committed.
vercel pull --yes --environment=production >/dev/null
VITE_STATIC=1 vercel build --prod
vercel deploy --prebuilt --prod
echo "$DEPLOY" >"$LAST"
echo "Deployed ${DEPLOY:0:7}"
