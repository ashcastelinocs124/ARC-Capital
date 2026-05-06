# Castelino-Capital

A mini multi-agent hedge fund system. Currently in brainstorming/architecture phase.

## Git push policy (HARD RULE)

Every push to a remote MUST go through the `/gitpush` skill. Never run `git push`, `gh repo create --push`, or any other push-equivalent directly in Bash, even for "simple" pushes to an already-tracked branch. The skill runs a pre-push secret scan (env files, `.pem`/`.key` files, credentials in diff hunks) that raw `git push` skips. If a push happens outside the skill, log it in `learnings.md` and run `/gitpush` retroactively against the pushed branch as an audit.

## Learnings

This project maintains a `learnings.md` file at the project root. Add entries whenever you discover something interesting. Each entry must include a **Ref** subtitle pointing to the relevant CLAUDE.md section. Only read `learnings.md` when its contents are directly relevant to the current task.

Use the `/capture-learnings` skill at the end of sessions to do this automatically.

## Memory System

### Short-term memory (`short_term_memory.md`)
Holds a detailed log of the **past 5 immediate tasks** — what was done, why, and the outcome. When a new task is completed, append it. If there are more than 5 entries, summarize the oldest one into `long_term_memory.md` before removing it.

### Long-term memory (`long_term_memory.md`)
When a task ages out of short-term memory, write a **condensed summary** (2-3 lines) here. This preserves historical context without clutter.

**Pruning rule:** Every 10 sessions, review `long_term_memory.md` against `CLAUDE.md`. Delete any entries no longer relevant to the current state of the project.

### Loading priority
At the start of every session, read both files into context:
1. **`short_term_memory.md` first** — most important, give it higher weight.
2. **`long_term_memory.md` second** — background context, defer to short-term when there's conflict.

## Architecture (proposed, evolving)

Multi-agent system inspired by an analyst desk:
- **Current Event Agent** → ingests news/macro signals
- **Macro Hypothesis Agent** → forms market thesis
- **Bull Agent / Bear Agent** → opposing views, each backed by Technical Analysis, Backtesting, Web, Risk sub-agents
- **Debate Agent** → adjudicates Bull vs Bear
- **Portfolio Agent** → translates verdict into positions
- **Portfolio** → execution / state

This is a starting point. The brainstorming session is exploring variations.

## Completed Work

### 2026-05-05 — OpenBB Integration
- Integrated OpenBB Platform SDK as primary data source with yfinance/FRED fallback (`src/castelino/data/openbb_adapter.py`)
- Built 6-tab OpenBB Workspace dashboard (FastAPI backend at port 7779, 22 widgets)
- Added human-in-the-loop approval gates (post-hypothesis, post-debate) — pipeline stalls until CLI approval
- New CLI commands: `castelino serve`, `castelino queue`, `castelino approve`, `castelino reject`, `castelino edit`
- Dashboard tabs: Portfolio, Macro & Signals, Research & Technicals, Risk & Attribution, Agent Decisions, Approval Queue
- Research agents (TA, risk, web) now pull data from OpenBB with pandas fallback
- Design doc: `docs/plans/2026-05-05-openbb-integration-design.md`
