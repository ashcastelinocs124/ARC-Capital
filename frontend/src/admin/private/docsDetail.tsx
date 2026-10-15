import type { ReactNode } from "react";
import type { DocDetail } from "@/pages/DocsPage";

// PRIVATE: the detailed method, inputs and testing for each model. This module is only ever loaded by
// pages/AdminPage.tsx via import(), and vite.config.ts emits it as /admin/chunks/*.js, which the
// Vercel middleware password-gates. Never import it statically from a public page.

const C = ({ children }: { children: ReactNode }) => (
  <code className="font-mono text-[11.5px] bg-surface-2 px-1 py-px rounded">{children}</code>
);

const WALK_FORWARD = (
  <p>
    Walk-forward: the history is split into 5 time blocks, and the model trains on everything before a block and is scored
    on that block, so it never sees the future. We report accuracy and the Brier score (the mean squared error of the
    probability: 0 is perfect, 0.25 is a coin flip). The Update Agent refits daily and only promotes a new fit whose Brier
    score is no more than 0.02 worse than the current model's.
  </p>
);


export const DETAIL: Record<string, DocDetail> = {
  "pulse": [
      ["Target in detail", <p>The target is the average of the Empire State and Philly Fed manufacturing diffusion indexes, a free stand-in for the ISM PMI (FRED stopped carrying the ISM series in 2024). A reading above 0 means more firms report growth than decline. The label is 1 when next month's reading is above 0.</p>],
      ["Inputs", <>
        <ul className="list-disc pl-5 space-y-1">
          <li>10-year Treasury yield (FRED <C>DGS10</C>)</li>
          <li>Initial jobless claims (<C>ICSA</C>)</li>
          <li>Philly Fed leading index (<C>USSLIND</C>; discontinued in 2020, so recent rows are blank)</li>
          <li>Cyclicals vs defensives, <C>XLY/XLP</C> (Yahoo Finance)</li>
          <li>Real disposable personal income (<C>DSPIC96</C>)</li>
          <li>The target's own recent values</li>
        </ul>
        <p className="mt-2">Each input enters as its current value plus 3 monthly lags.</p>
      </>],
      ["Method", <p>100 boosted trees of depth 1 (each tree is a single yes/no split, which keeps the model simple and hard to overfit), learning rate 0.1, trained on monthly data since 2000. The output is a probability; 50% or more is the "expansion" call.</p>],
      ["How it is tested", WALK_FORWARD],
  ],
  "pressure": [
      ["Target in detail", <p>The label is 1 when next month's CPI All Items (seasonally adjusted) month-over-month change is larger than this month's. An earlier version asked "will CPI go up?", but CPI rises in about 82% of months, so that question carried almost no signal.</p>],
      ["Inputs", <p>PPI, WTI and Brent crude, the Bloomberg Commodity Index, 5- and 10-year breakevens, the trade-weighted dollar, University of Michigan 1-year inflation expectations, rent CPI, average hourly earnings and Case-Shiller home prices. Each enters as 1-month and 12-month % changes, with 3 monthly lags.</p>],
      ["Method", <p>The same setup as Pulse: 100 depth-1 boosted trees, learning rate 0.1, monthly data since 2000.</p>],
      ["How it is tested", WALK_FORWARD],
  ],
  "risk-off": [
      ["Target in detail", <p>For each month-end, the label is 1 if SPY's largest peak-to-trough drop over the following 30 days is worse than −5%.</p>],
      ["Inputs", <ul className="list-disc pl-5 space-y-1">
        <li>High-yield and investment-grade credit spreads (<C>BAMLH0A0HYM2</C>, <C>BAMLC0A0CM</C>)</li>
        <li>VIX (<C>VIXCLS</C>) and MOVE bond-market volatility (<C>^MOVE</C>)</li>
        <li>The broad trade-weighted dollar (<C>DTWEXBGS</C>)</li>
        <li>The HYG/IEF ratio, high-yield vs Treasury bond ETFs</li>
      </ul>],
      ["Method", <p>200 boosted trees of depth 4 with 80% row and feature sampling. Drawdowns are rare, so class weights scale up the drawdown months to keep the model from always answering "no".</p>],
  ],
  "sector-sentiment": [
      ["Fear & Greed needle", <p>signals/fear_greed.py, run inside the Sector Sentiment refresh (since 2026-10-15). One 3-year Yahoo download (^GSPC, ^VIX, IEF and the ~115 Sector Sentiment stocks) plus FRED BAMLH0A0HYM2 give five daily signals: S&amp;P 500 ÷ its 125-day average − 1; the share of the stocks above their 200-day average; VIX ÷ its 50-day average − 1 (inverted); the high-yield spread (inverted); S&amp;P 500 minus IEF 20-day return. Each is turned into its percentile within the trailing 504 trading days (at least 252 needed) and the needle is the mean of the five; a day counts only with all five. The look-backs (previous close, 1 week, 1 month, 1 year) are read off the same series, so they exist from day one. If any download fails the snapshot ships without the needle.</p>],
      ["Sector score", <p>50 + 25 × divergence ÷ 0.30, clipped to 0–100, so the euphoric and fearful lines (±0.30, config.yaml) land on 75 and 25; computed in Python (fear_greed.sector_score) and stored as fg_score.</p>],
      ["Technical score", <p>RSI-14, MACD histogram, price vs the 50- and 200-day averages, and 3-month return. Each metric is z-scored across all stocks, clipped at ±3σ, scaled to −1…+1 and averaged.</p>],
      ["Fundamental score", <p>Two thirds forward, one third trailing (since 2026-10-14), because markets price expected earnings and estimate revisions move stocks. Forward: forward P/E relative to the sector median (cheaper scores higher) and the 90-day change in analysts' next-year EPS estimate (Yahoo's eps_trend). Trailing: last fiscal year's revenue growth, net income growth and trailing P/E relative to the sector median. Each metric is scored the same way; a side with no data leaves the other to count alone. Prices, fundamentals and estimates come from Yahoo Finance.</p>],
      ["Divergence and labels", <p>Divergence = technical − fundamental per stock, then market-cap-weighted across the sector's top 10. At +0.30 or above a sector is labelled euphoric (price ahead of fundamentals); at −0.30 or below, fearful (fundamentals nobody is buying); otherwise fair.</p>],
      ["Stock-specific or sector-wide", <p>Code, not the LLM, decides the verdict. If one stock supplies at least 50% of the divergence it is stock-specific. If at least 7 of the 10 stocks share its sign it is sector-wide. Otherwise it is mixed.</p>],
      ["Explainer", <p>Two LLM agents write the summary and per-sector prose from the numbers. They describe and never recommend; if they fail, the page shows the numbers alone.</p>],
  ],
  "adoption": [
      ["Talk", <p>An LLM reads AI passages in the latest 10-K or 10-Q and rates each claim 1 (pilot), 2 (deployed) or 3 (revenue-linked). Every quote must appear word for word in the filing or it is dropped. The score is depth-weighted claims per 1,000 words. A filing is only ever sent to the LLM once.</p>],
      ["Hire", <>
        <p>The share of open job postings that are AI/ML roles. Code, not an LLM, decides which titles count. Postings are read three ways:</p>
        <ul className="list-disc pl-5 space-y-1">
          <li><b>Platform readers</b> for Greenhouse, Lever, Workday, Oracle, UKG and Amazon, up to 2,000 postings per company.</li>
          <li><b>Saved recipes</b> for companies with their own careers site: a small file saying where the titles are, replayed by code every run.</li>
          <li><b>The Recipe Writer</b>, an LLM agent that explores a careers site once to write that recipe. It is kept only if it finds at least 90% of the jobs the site shows.</li>
        </ul>
        <p className="mt-2">The reading is averaged over the last 7 bi-weekly snapshots.</p>
      </>],
      ["Spend", <p>Capex plus R&amp;D as a share of revenue, trailing twelve months, from Yahoo Finance.</p>],
      ["Score and roll-up", <p>Each pillar is z-scored across all companies, clipped at ±3σ and mapped to 0–100 (average 50). A company needs at least 2 of the 3 pillars. Scores roll up equal-weighted (the headline) and market-cap-weighted per sector and size bucket; a cell with fewer than 5 companies is flagged thin.</p>],
  ],
  "cross-asset": [
      ["Drivers", <p>Weekly moves in the 2-year yield, the 10-year real yield and breakeven, the term premium, the high-yield spread, NFCI and the Fed balance sheet (FRED), VIX (Yahoo), the broad dollar, and speculators' net futures positioning in each asset (CFTC). Each asset only uses the drivers that plausibly matter for it: the dollar isn't used for Treasuries and the breakeven isn't used for equities.</p>],
      ["Surprises, not data", <p>Markets price the consensus before a release, so CPI, PCE, payrolls, ISM and GDP enter as actual minus consensus, divided by that release's typical surprise. Both numbers come from a cited web search and are kept only if both appear in the cited source; otherwise that release counts as no surprise and is listed as a data gap.</p>],
      ["Fit", <p>For each asset, a ridge regression of weekly returns on the drivers over the last 104 weeks. Ridge shrinks sensitivities when drivers overlap; its strength is picked automatically.</p>],
      ["Contributions", <p>A driver's contribution is its sensitivity times how much it moved over the window. Whatever the drivers don't explain is shown as Unexplained, so the bars always add up to the actual move.</p>],
      ["Groups", <p>Drivers that move together (the rate measures; VIX and credit spreads; the two liquidity measures) are shown as one bar. The model gets their joint effect right but can't reliably split it, so the split inside a group is marked uncertain.</p>],
  ],
};
