# ARC Capital

A multi-asset macro research platform and simulated hedge fund, built as LLM agents on top of a deterministic floor: XGBoost nowcasters, pure-function accounting, and hard-coded risk rules. The dashboard is branded **ARC Research**.

**Live (read-only):** [arcresearch.markets](https://arcresearch.markets) · **Newsletter:** [archresearch.substack.com](https://archresearch.substack.com/)

This is a portfolio piece: a working simulation, not connected to a real broker.

---

## What it does

| Area | What you get | Where |
|---|---|---|
| **Regime models** | XGBoost nowcasters for next-month growth (Empire State + Philly Fed diffusion) and inflation (CPI m/m acceleration), mapped to a 4-quadrant regime, plus a risk-off classifier | `/models`, `/macro` |
| **Daily Update** | Once a day: refit the regime models (promoted only if out-of-sample Brier doesn't get worse), collect releases and cross-asset moves, write one fact-checked briefing | `/updates` |
| **Sector Sentiment** | Per GICS sector, technical score minus fundamental score over its top 10 stocks; flags euphoric or fearful sectors and whether a move is stock-specific or sector-wide | `/models` |
| **AI Adoption Index** | Scores companies on Talk (AI claims in SEC filings), Hire (share of open AI/ML roles) and Spend ((capex + R&D) / revenue), rolled up by sector and size | `/models` |
| **Deep Research** | Multi-agent research: clarify → split into sub-questions → parallel web-search agents → cited report with charts from real market data | `/deep-research` |
| **Agent catalog** | Every LLM agent's live prompt, model, tools, memory, output schema and API-key status, from `agents.yaml` | `/agents` |
| **Trading pipeline** | Trigger layer → Current Event → Hypothesis → Asset Selection → Research Desk → Bull/Bear → Debate → Principles Guard → Portfolio → simulated broker | `/portfolio`, `/risk`, `/research` |

The trading pipeline's code, schemas and tests are intact. Since 2026-09-30 it has no CLI or UI to start a run or approve its two human-in-the-loop gates.

---

## Architecture

```
            DATA                          MODELS & AGENTS                       SURFACES
 ┌──────────────────────┐     ┌───────────────────────────────────┐     ┌────────────────────┐
 │ FRED · Yahoo Finance │────▶│ forecast/   XGBoost nowcasters    │────▶│ FastAPI  :7779     │
 │ SEC EDGAR            │     │ agents/update/   Daily Update     │     │ (ckm serve)        │
 │ Job boards           │────▶│ signals/    Sector Sentiment      │────▶│                    │
 │ OpenAI web search    │     │ adoption/   AI Adoption Index     │     │ React + Vite       │
 │ RSS · Polymarket     │────▶│ agents/research/deep/  Deep Res.  │────▶│ dashboard  :5173   │
 └──────────────────────┘     │ triggers/ + agents/   trading DAG │     │                    │
                              │ execution/  broker + NAV floor    │     │ Static snapshot    │
                              └───────────────────────────────────┘     │ → Vercel (public)  │
                                                                         └────────────────────┘
```

Design rules that hold everywhere:

- **Numbers come from code, words from LLMs.** Agents interpret, and deterministic code computes. Every LLM output is a Pydantic model with hard constraints (a hypothesis without `kill_criteria` fails validation; a position over 5% of NAV is rejected before the guard sees it).
- **Guards check the model.** The Daily Update rejects any figure not in its collected data. The AI Adoption extractor keeps a claim only if its quote appears in the filing. The job-board Recipe Writer's output is accepted only if our own replay reproduces it.
- **All web search goes through one place**, `data/web_search.py` (OpenAI Responses API `web_search`).

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

`ckm serve` doesn't auto-reload, so restart it after Python changes. Starting it refreshes nothing. The top-bar **Refresh** button runs the Daily Update, Sector Sentiment and AI Adoption jobs in parallel (`POST /refresh`, status at `GET /refresh/status`). To add a data job, add it to `_RUNNERS` in `dashboard/endpoints/refresh.py`.

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
- `scripts/publish_snapshot.sh` builds with `VITE_STATIC=1` and deploys. A daily 7:00 cron job runs it.
- Portfolio, Risk and Research are private-only. To publish one, remove it from `frontend/src/pages/visibility.ts` and add its endpoints back in the export script.

### CI/CD

- **CI** (`.github/workflows/ci.yml`) runs on every push to `main` and every pull request:
  - the full test suite;
  - ruff lint and format checks, on the Python files the change touches only, since the older code predates the lint config;
  - the frontend type check and the public build.
- **CD** is the 7:00 publish job. It takes the data from the machine running the backend, but builds the code from a clean copy of `origin/main`, and only from a commit whose CI passed.
  - If the newest `main` isn't green, it rebuilds the last deployed good commit with fresh data.
  - Uncommitted or failing code never reaches the public site.
  - The last deployed commit is recorded in `data/publish_last_sha`.
- **Don't connect Vercel's GitHub auto-deploy.** The snapshot data is gitignored, so a deploy straight from GitHub would publish a site with no data.

---

## Tests

```bash
uv run --extra dev pytest                          # full suite: over 10 minutes, run it in the background
uv run --extra dev pytest tests/test_adoption*.py  # or target files
uv run --extra dev pytest -m backtest              # regression suite over deterministic components
```

The suite makes no network or LLM calls: `FakeLLMClient`, mock HTTP transports and pricing stubs keep it deterministic. 4 persona tests fail on `main` for environmental reasons.

---

## Repository layout

```
agents.yaml                 # registry of every LLM agent (drives /agents; enforced by a test)
config.yaml                 # models, thresholds, caps
data/                       # inputs (constitution, indicator catalogs, lexicons) + generated state (gitignored)
src/castelino/
  forecast/                 # XGBoost regime + risk-off nowcasters
  agents/                   # trading DAG agents, update/ (Daily Update), research/deep/ (Deep Research)
  signals/                  # Sector Sentiment
  adoption/                 # AI Adoption Index: extractor, scoring, job boards, recipe writer
  triggers/                 # news, calendar, conviction ledger, figure/speech deviation, risk-off gate
  execution/ · memory/      # pure-function broker, NAV floor, journals
  orchestrator/             # LangGraph state + graph, `ckm` CLI
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

Built on `langgraph`, `openai`, `pydantic`, `xgboost`, `scikit-learn`, `yfinance`, FRED, OpenBB, Playwright, FastAPI, React and Vite.
