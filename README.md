# ARC Capital

A macro research platform: a multi-agent daily Morning Note, XGBoost regime nowcasters, Sector Sentiment, an AI Adoption Index and a Deep Research agent, with deterministic code underneath every number. The dashboard is branded **ARC Research**.

**Live (read-only):** [arcresearch.markets](https://arcresearch.markets) · **Newsletter:** [archresearch.substack.com](https://archresearch.substack.com/)

This is a portfolio piece, not investment advice.

---

## What it does

| Area | What you get | Where |
|---|---|---|
| **Regime models** | XGBoost nowcasters for next-month growth (Empire State + Philly Fed diffusion) and inflation (CPI m/m acceleration), mapped to a 4-quadrant regime, plus a risk-off classifier | `/models`, `/macro` |
| **Daily Update** | A multi-agent Morning Note at 17:00 New York: an Orchestrator briefs Macro (FRED, BLS, Yahoo), News (cited web search) and Alt (Polymarket, X) agents, an Editor writes 3-5 ranked items, a number guard checks every figure, and code draws an exhibit per item. Downloadable as PDF | `/updates` |
| **Sector Sentiment** | Per GICS sector, technical score minus fundamental score over its top 10 stocks; flags euphoric or fearful sectors and whether a move is stock-specific or sector-wide | `/models` |
| **AI Adoption Index** | Scores companies on Talk (AI claims in SEC filings), Hire (share of open AI/ML roles) and Spend ((capex + R&D) / revenue), rolled up by sector and size | `/models` |
| **Cross-Asset Drivers** | Explains what moved the S&P 500 and Treasuries over 1 week, 1 month and 3 months: a ridge regression of weekly returns on rates, risk, liquidity, dollar and CFTC positioning moves, with CPI/PCE/payrolls/ISM/GDP entering only as their surprise vs a cited consensus; unexplained moves are shown, not hidden | `/models` |
| **Weekly Deep Dive** | Every Sunday morning, a sell-side-style report on Monday–Friday: a Lead (OpenAI) picks the week's trends from the Morning Notes and staffs up to 4 specialist desks that pull their own data and share a board; a Deep Editor (Claude Opus 5.5) grills every desk, then writes a paged report (page 1 the week at a glance, then one trend per page). Also drafted in full on Substack | `/deep-research` |
| **Deep Research** | Multi-agent research: clarify → split into sub-questions → parallel web-search agents → cited report with charts from real market data | `/deep-research` |
| **Agent catalog** | Every LLM agent's live prompt, model, tools, memory, output schema and API-key status, from `agents.yaml` | `/agents` |

---

## Architecture

```
            DATA                          MODELS & AGENTS                       SURFACES
 ┌──────────────────────┐     ┌───────────────────────────────────┐     ┌────────────────────┐
 │ FRED · Yahoo Finance │────▶│ forecast/   XGBoost nowcasters    │────▶│ FastAPI  :7779     │
 │ SEC EDGAR            │     │ agents/update/   Daily Update     │     │ (ckm serve)        │
 │ Job boards           │────▶│ signals/    Sector Sentiment      │────▶│                    │
 │ OpenAI web search    │     │ adoption/   AI Adoption Index     │     │ React + Vite       │
 │ BLS · Polymarket     │────▶│ agents/research/deep/  Deep Res.  │────▶│ dashboard  :5173   │
 └──────────────────────┘     └───────────────────────────────────┘     │                    │
                                                                         │ Static snapshot    │
                                                                         │ → Vercel (public)  │
                                                                         └────────────────────┘
```

Design rules that hold everywhere:

- **Numbers come from code, words from LLMs.** Agents interpret, and deterministic code computes. Every LLM output is a Pydantic model, and agents cite facts by id rather than restating numbers.
- **Guards check the model.** The Morning Note's guard rejects any %, bp or pp figure that isn't in the facts behind the findings an item cites. The AI Adoption extractor keeps a claim only if its quote appears in the filing. The job-board Recipe Writer's output is accepted only if our own replay reproduces it.
- **All web search goes through one place**, `data/web_search.py` (OpenAI Responses API `web_search`).

### Weekly Deep Dive

`src/castelino/agents/weekly/` runs Sunday 06:00 New York (`scripts/publish_weekly.sh`), and is live by about 08:00:

1. **Deep Lead** (`gpt-6-sol`) reads the week's Morning Notes and memory, picks 3-4 trends and staffs ≤4 desks, each with a name, goal and the tools it may use.
2. **Desks** (`gpt-6-luna`, in parallel) call `fred_series`, `yahoo_prices`, `bls_series`, `polymarket_odds` and `web_search` (≤12 calls each). Code turns every result into a numbered fact, and related desks share facts on a board.
3. **Deep Editor** (`claude-opus-5-5`, effort high) grills the desks for up to 2 rounds in one append-only conversation, then writes the report. The number guard checks every %, bp and pp figure against the facts each part cites (one retry), and code draws one exhibit per chart over the window the Editor chose.
4. The record is written last to `data/deep/<YYYY-Www>.json`, served at `/weekly/*`, exported for the public site and drafted on Substack (`python -m castelino.substack_weekly`).

A report is due from Sunday until it exists, so Refresh only builds a missing one (and Saturday's daily publish never releases it early). Before any OpenAI spend the run makes one tiny Claude call, so a missing key or credit fails for free. It needs `ANTHROPIC_API_KEY` as well as `OPENAI_API_KEY`; note that `.env` doesn't override a key already exported in your shell. To rebuild a week by hand: `uv run python -c 'from castelino.agents.weekly.runner import build_default_runner as b; print(b().run_week("2026-W41"))'`.

### AI Adoption Index: how Hire is read

The Hire pillar reads companies' open job titles in three layers, and code (never a model) counts the AI/ML roles:

| Layer | How | Runs every refresh | Cost |
|---|---|---|---|
| 1. Platform readers | Public JSON behind Workday, Oracle Recruiting, UKG, Greenhouse, Lever and Amazon careers pages | Yes | Free |
| 2. Saved recipes | Fixed code replays a per-company recipe: a JSON address, or page elements read in headless Chromium | Yes | Free |
| 3. Recipe Writer | GPT-6 Astra explores a custom careers site **once** and proposes a recipe. It's saved only if our replay returns at least 90% of the jobs the site shows | Only for a new company or a broken recipe | ~$0.15 per site |

Boards live in `data/adoption/job_boards.csv` and recipes in `data/adoption/recipes/`. A company with neither has a missing Hire reading, not zero.

---

## Setup

Requires Python `>=3.11,<3.13`, [`uv`](https://docs.astral.sh/uv/) and Node.js.

```bash
git clone https://github.com/ashcastelinocs124/ARC-Capital.git
cd ARC-Capital
uv sync --python 3.12              # system Python 3.14 will not resolve
cd frontend && npm install && cd ..

cp .env.example .env               # then fill in or blank every placeholder
```

In `.env`:
- **`OPENAI_API_KEY`**: needed by every agent and by web search.
- **`FRED_API_KEY`**: optional. If it's blank, FRED falls back to its keyless CSV endpoint.
- **Every leftover `your_..._here` placeholder:** fill it in or blank it, because a placeholder is sent as if it were a real key. The `/agents` page shows which keys each agent needs and whether they're set.

For the AI Adoption Index, set `adoption.sec_user_agent` in `config.yaml` to a contact string (the SEC requires one).

To write job-board recipes (layer 3 above), also install the browser extra:

```bash
uv sync --python 3.12 --extra browser && uv run playwright install chromium
```

---

## Running

```bash
uv run ckm serve                 # FastAPI backend + OpenBB Workspace connector on :7779
cd frontend && npm run dev       # dashboard on http://localhost:5173 (proxies /api to :7779)
```

`ckm serve` doesn't auto-reload, so restart it after Python changes. Starting it refreshes nothing. The top-bar **Refresh** button runs the model refit, the Daily Update, Sector Sentiment and AI Adoption jobs in parallel (`POST /refresh`, status at `GET /refresh/status`). To add a data job, add it to `_RUNNERS` in `dashboard/endpoints/refresh.py`.

Other commands:

```bash
uv run ckm adoption universe-refresh     # rank the seed list, keep the top N per size bucket
uv run ckm adoption run                  # one bi-weekly AI Adoption period
uv run ckm adoption show                 # latest headline numbers

uv run python scripts/build_job_boards.py                              # find Greenhouse/Lever boards for new companies
uv run --extra browser python scripts/write_recipes.py AAPL=https://jobs.apple.com/en-us/search --budget 10
```

### Public dashboard

[arcresearch.markets](https://arcresearch.markets) is a static, read-only snapshot on Vercel. It has no backend, so visitors can't trigger refreshes or spend API credits.

- `scripts/export_snapshot.py` runs the refresh jobs, then saves every GET response the public pages need as a JSON file.
- `scripts/publish_snapshot.sh` builds with `VITE_STATIC=1` and deploys. A cron job runs it daily at 17:00 New York (`--no-refresh` redeploys without rerunning the jobs).
- `scripts/backfill_updates.py <dates>` rebuilds past Daily Updates as Morning Notes using data as of each date.

### CI/CD

- **CI** (`.github/workflows/ci.yml`) runs on every push to `main` and every pull request:
  - the full test suite;
  - ruff lint and format checks, on the Python files the change touches only, since the older code predates the lint config;
  - the frontend type check and the public build.
- **CD** is the 17:00 New York publish job. It takes the data from the machine running the backend, but builds the code from a clean copy of `origin/main`, and only from a commit whose CI passed.
  - If the newest `main` isn't green, it rebuilds the last deployed good commit with fresh data.
  - Uncommitted or failing code never reaches the public site.
  - The last deployed commit is recorded in `data/publish_last_sha`.
- **Don't connect Vercel's GitHub auto-deploy.** The snapshot data is gitignored, so a deploy straight from GitHub would publish a site with no data.

---

## Tests

```bash
uv run --extra dev pytest                          # full suite: over 10 minutes, run it in the background
uv run --extra dev pytest tests/test_adoption*.py  # or target files
```

The suite makes no network or LLM calls: `FakeLLMClient` and mock HTTP transports keep it deterministic.

---

## Repository layout

```
agents.yaml                 # registry of every LLM agent (drives /agents; enforced by a test)
config.yaml                 # models, thresholds, caps
data/                       # inputs (indicator catalogs) + generated state (gitignored)
src/castelino/
  forecast/                 # XGBoost regime + risk-off nowcasters
  agents/                   # update/ (Daily Update: orchestrator, macro/news/alt, editor, guard, charts), research/deep/ (Deep Research)
  signals/                  # Sector Sentiment
  adoption/                 # AI Adoption Index: extractor, scoring, job boards, recipe writer
  orchestrator/             # `ckm` CLI
  dashboard/                # FastAPI app and endpoints
  data/                     # FRED / Yahoo / OpenBB adapters, web_search.py
frontend/                   # React + Vite + Tailwind dashboard
scripts/                    # data builders, snapshot export/publish, job-board tools
tests/
```

---

## Disclaimer

ARC Research is for informational and educational purposes only. Nothing in this repository or on
[arcresearch.markets](https://arcresearch.markets) is investment, financial, legal or tax advice, or an offer or
solicitation to buy or sell any security. Its figures come from simulated models, AI-generated text and third-party
data that may be incomplete, delayed or wrong, and past performance does not predict future results. Do your own
research or consult a licensed professional before making any investment decision. You use it at your own risk; the
authors accept no liability for any loss arising from its use.

## License

A portfolio piece; no commercial use intended.

Built on `openai`, `pydantic`, `xgboost`, `scikit-learn`, `yfinance`, FRED, OpenBB, Playwright, FastAPI, React and Vite.
