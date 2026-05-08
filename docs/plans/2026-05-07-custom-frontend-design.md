# Custom Frontend — Replace OpenBB Workspace

**Date:** 2026-05-07
**Status:** Approved

## Problem

OpenBB Workspace is functional but feels generic — every widget renders inside their wrapper, the look is data-portal not trading-dashboard, and customization is limited to what their widget types support (we already hit this with `type: form` not being supported). User wants a custom UI matching the system's sophistication.

## Decision

Build a custom React + TypeScript frontend that replaces OpenBB Workspace. The existing FastAPI backend at `localhost:7779` stays as-is — it just gets a new consumer. The OpenBB Workspace integration remains supported (apps.json/widgets.json still served) so users can pick either UI.

## Stack

| Concern | Choice | Why |
|---------|--------|-----|
| Framework | React 18 + TypeScript | Standard, swappable |
| Build | Vite | Fast HMR, minimal config |
| Styling | Tailwind CSS | Utility-first, matches "modern SaaS" aesthetic |
| Components | shadcn/ui (Radix + Tailwind) | Used by Linear/Vercel — locked-in look |
| Charts | Recharts | Composable, declarative, good defaults |
| Data | TanStack Query | Polling, caching, background refetch |
| Routing | React Router v6 | Tab-based navigation |

## Layout

```
┌────────────────────────────────────────────────────────────┐
│  TopBar: CKM Capital · NAV · regime · status               │
├────┬───────────────────────────────────────────────────────┤
│Side│                                                       │
│bar │  <page content>                                       │
│    │                                                       │
└────┴───────────────────────────────────────────────────────┘
```

Sidebar tabs: Portfolio, Macro & Signals, Research, Risk, Agents, Approval Center. The Approval Center icon shows a red badge with the pending count.

## Polling Intervals

| Data | Interval |
|------|----------|
| Pending approvals | 5s |
| Portfolio metrics, positions | 30s |
| Charts (equity curve, exposure) | 60s |
| Macro indicators, calendar | 5min |

Auto-pause when tab is hidden via `document.visibilitychange`.

## Pages

### Portfolio
- 6 KPI tiles: NAV, cash, gross exposure, net exposure, unrealized P&L, realized P&L
- Open positions table with live marks, % NAV, P&L (colored)
- Equity curve chart (Recharts area)
- Recent fills feed

### Macro & Signals
- Regime quadrant visualizer — 4-cell grid with current cell highlighted
- Conviction ledger bars — 4 horizontal bars (growth↑↓, inflation↑↓)
- Risk-off probability gauge — circular progress + tier indicator
- Leading indicator catalog readouts
- News feed with Sonar deep-reads expandable per item

### Research
- TA chart (candlesticks + RSI/MACD/OBV overlays) with symbol picker
- Instrument screener
- Correlation heatmap
- Sector performance bars

### Risk
- Exposure donut by asset class
- Exposure bars by instrument
- Principle warnings table with severity colors

### Agents
- Verdicts table with bull/bear arguments expandable per row
- Guard decisions table

### Approval Center
- Pending items as cards (matches existing `/approval_form` UX)
- Each card: full hypothesis/verdict context, notes textarea, Approve/Reject buttons
- Decision history table

## Backend Changes (Minimal)

- Mount `frontend/dist/` as static files when present
- Add `CORSMiddleware` allowing `http://localhost:5173` (Vite dev server)
- Existing JSON endpoints unchanged
- Keep `/approval_form` HTML endpoint as fallback

## Directory Layout

```
frontend/
├── package.json
├── vite.config.ts
├── tailwind.config.ts
├── tsconfig.json
├── index.html
└── src/
    ├── main.tsx, App.tsx
    ├── api/{client,types,endpoints}.ts
    ├── hooks/use*.ts
    ├── components/
    │   ├── ui/                # shadcn primitives
    │   ├── layout/{Sidebar,TopBar}.tsx
    │   └── *Card, *Table, *Chart components
    ├── pages/
    │   ├── PortfolioPage.tsx
    │   ├── MacroPage.tsx
    │   ├── ResearchPage.tsx
    │   ├── RiskPage.tsx
    │   ├── AgentsPage.tsx
    │   └── ApprovalCenterPage.tsx
    └── lib/format.ts
```

## Build & Deploy

**Dev:**
```bash
cd frontend && npm install && npm run dev   # Vite at :5173
castelino serve                             # FastAPI at :7779
# /api proxied via vite.config.ts
```

**Production:**
```bash
cd frontend && npm run build                # outputs frontend/dist/
castelino serve                             # serves both API + dist/
# Single URL: http://localhost:7779
```

## Implementation Phases

1. **Scaffold** — package.json, vite, tailwind, tsconfig, App shell, routing
2. **API layer** — types matching Pydantic schemas, endpoint functions, React Query hooks
3. **Layout** — Sidebar + TopBar + page routing
4. **Approval Center** — port the working HTML form to React (priority — preserves the working flow)
5. **Portfolio page** — KPIs + positions table + equity curve
6. **Macro page** — regime viz + conviction ledger + risk-off gauge
7. **Risk page** — exposure charts + warnings
8. **Agents page** — verdicts + guard tables
9. **Research page** — TA chart + screener + correlation
10. **Backend integration** — static file mount + CORS + production build

## Files

| File | Change |
|------|--------|
| `frontend/**` | NEW — full React app |
| `dashboard/main.py` | Mount static files, add CORS |
| `.gitignore` | Add `frontend/node_modules/`, `frontend/dist/` |
| `README.md` | Add frontend dev/build instructions |
