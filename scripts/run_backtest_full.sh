#!/usr/bin/env bash
# Full historical backtest — gpt-4o, Oct 2023 → today.
#
# Runs the four stages in order, with resumability between stages:
#   1. Build prices archive (yfinance, ~10 min, free)
#   2. Build NYT news archive (~1-3 hours, free, rate-limited)
#   3. Build Sonar Trump archive (~5 min, ~$1.50)
#   4. Run --with-graph backtest (~6-8 hours, ~$60-80)
#   5. Generate summary.json + report.html
#
# Each stage skips itself if its output already exists. Stage 4 can be
# re-run with a fresh --run-id without re-doing 1-3.
#
# Usage:
#   bash scripts/run_backtest_full.sh                      # full pipeline
#   bash scripts/run_backtest_full.sh --skip-data          # just run backtest
#   bash scripts/run_backtest_full.sh --run-id myrun-001   # custom run-id
#   bash scripts/run_backtest_full.sh --end 2024-12-31     # custom end date
#   bash scripts/run_backtest_full.sh --dry-run            # show what would run

set -euo pipefail

# ── Configuration ────────────────────────────────────────────────────────

START="${BACKTEST_START:-2023-10-01}"
END="${BACKTEST_END:-$(date +%Y-%m-%d)}"
RUN_ID="${BACKTEST_RUN_ID:-ckm-bt-$(date +%Y%m%d-%H%M)}"
SKIP_DATA=false
DRY_RUN=false

while [[ $# -gt 0 ]]; do
  case $1 in
    --skip-data) SKIP_DATA=true; shift ;;
    --dry-run)   DRY_RUN=true;   shift ;;
    --start)     START="$2";     shift 2 ;;
    --end)       END="$2";       shift 2 ;;
    --run-id)    RUN_ID="$2";    shift 2 ;;
    -h|--help)
      sed -n '2,18p' "$0" | sed 's/^# \?//'
      exit 0 ;;
    *) echo "Unknown arg: $1" >&2; exit 1 ;;
  esac
done

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_ROOT"

PRICES_PARQUET="data/cache/historical_prices.parquet"
NEWS_PARQUET="data/cache/historical_news.parquet"
LOG_DIR="data/backtest_runs/$RUN_ID/logs"
mkdir -p "$LOG_DIR"

START_YM="$(echo "$START" | cut -c1-7)"   # YYYY-MM
END_YM="$(echo "$END" | cut -c1-7)"

# ── Helpers ──────────────────────────────────────────────────────────────

log()     { printf '\n[%s] %s\n' "$(date +%H:%M:%S)" "$*"; }
section() { printf '\n%.0s═' {1..72}; printf '\n %s\n' "$1"; printf '═%.0s' {1..72}; printf '\n'; }
run() {
  if $DRY_RUN; then
    printf '[dry-run] %s\n' "$*"
  else
    "$@"
  fi
}

require_key() {
  python -c "
from castelino.config import get_settings
s = get_settings()
v = getattr(s, '$1', None) or (lambda: None)
key = s.openai_api_key if '$1' == 'openai_api_key' else getattr(s, '$1')
if not key: raise SystemExit('$1 is not set in .env')
print('$1: set')
" || exit 1
}

# ── Stage 0: pre-flight ──────────────────────────────────────────────────

section "Stage 0: pre-flight checks"

log "Run id:    $RUN_ID"
log "Window:    $START → $END"
log "Logs dir:  $LOG_DIR"

require_key openai_api_key
require_key perplexity_api_key
require_key nyt_api_key

# Confirm intent unless --dry-run or --skip-data (already past prompts)
if ! $DRY_RUN && ! $SKIP_DATA; then
  cat <<EOF

WARNING: Stage 4 (--with-graph) will spend an estimated USD \$60–80 on
the OpenAI API and run for ~6–8 hours wall-clock.

Press Ctrl-C now to abort. Continuing in 10 seconds...
EOF
  sleep 10
fi

# ── Stage 1: prices ──────────────────────────────────────────────────────

section "Stage 1: historical prices archive"

if $SKIP_DATA && [[ -f "$PRICES_PARQUET" ]]; then
  log "Stage 1 skipped — $PRICES_PARQUET exists"
elif [[ -f "$PRICES_PARQUET" ]]; then
  log "$PRICES_PARQUET exists — skipping (delete to rebuild)"
else
  run python scripts/build_historical_prices.py \
    --start "$START" --end "$END" \
    2>&1 | tee "$LOG_DIR/01_prices.log"
fi

# ── Stage 2: NYT archive ─────────────────────────────────────────────────

section "Stage 2: NYT news archive"

if $SKIP_DATA && [[ -f "$NEWS_PARQUET" ]]; then
  log "Stage 2 skipped — $NEWS_PARQUET exists"
else
  log "Pulling NYT for $START_YM → $END_YM (rate-limited; flushes per-month)"
  log "If interrupted, re-run — already-flushed months are reused."
  run python scripts/build_nyt_archive.py \
    --start "$START_YM" --end "$END_YM" \
    2>&1 | tee "$LOG_DIR/02_nyt.log"
fi

# ── Stage 3: Sonar Trump archive ─────────────────────────────────────────

section "Stage 3: Sonar Trump archive"

if $SKIP_DATA; then
  log "Stage 3 skipped (--skip-data)"
else
  run python scripts/build_sonar_trump_archive.py \
    --start "$START_YM" --end "$END_YM" \
    2>&1 | tee "$LOG_DIR/03_sonar_trump.log"
fi

# ── Stage 4: backtest ────────────────────────────────────────────────────

section "Stage 4: --with-graph backtest"

log "Resetting live state (portfolio.json, approval_queue.json, exposure_snapshot.json)"
log "Backup will be written to /tmp/backtest-backup-pre-$RUN_ID/"

BACKUP_DIR="/tmp/backtest-backup-pre-$RUN_ID"
run mkdir -p "$BACKUP_DIR"
for f in data/portfolio.json data/approval_queue.json data/exposure_snapshot.json; do
  if [[ -f "$f" ]]; then
    run cp "$f" "$BACKUP_DIR/"
    run rm "$f"
  fi
done

log "Running backtest --with-graph (~6-8h, ~\$60-80)"

run python -m castelino.orchestrator.cli backtest \
  --with-graph \
  --start "$START" --end "$END" \
  --run-id "$RUN_ID" \
  2>&1 | tee "$LOG_DIR/04_backtest.log"

# ── Stage 5: report ──────────────────────────────────────────────────────

section "Stage 5: report"

run python -m castelino.orchestrator.cli backtest-report "$RUN_ID" \
  2>&1 | tee "$LOG_DIR/05_report.log"

# ── Summary ──────────────────────────────────────────────────────────────

section "Done"

OUT_DIR="data/backtest_runs/$RUN_ID"
cat <<EOF

  Run id:           $RUN_ID
  Window:           $START → $END
  Daily NAV:        $OUT_DIR/portfolio_history.parquet
  Summary JSON:     $OUT_DIR/summary.json
  HTML report:      $OUT_DIR/report.html
  Per-stage logs:   $LOG_DIR
  State backup:     $BACKUP_DIR

  Restore live state:
    cp $BACKUP_DIR/*.json data/

  Top-line metrics:
EOF

if [[ -f "$OUT_DIR/summary.json" ]] && ! $DRY_RUN; then
  python -c "
import json, sys
d = json.load(open('$OUT_DIR/summary.json'))
t = d['top_line']
print(f'    Total return:    {t[\"total_return\"]:+.2%}')
print(f'    Annualized:      {t[\"annualized_return\"]:+.2%}')
print(f'    Sharpe ratio:    {t[\"sharpe_ratio\"]:.2f}')
print(f'    Max drawdown:    {t[\"max_drawdown\"]:.2%}')
print(f'    % months pos:    {t[\"pct_months_positive\"]:.0%}')
for b in d['benchmarks']:
    print(f'    vs {b[\"name\"]}:   alpha {b[\"alpha_annualized\"]:+.2%}, beta {b[\"beta\"]:+.2f}')
"
fi
