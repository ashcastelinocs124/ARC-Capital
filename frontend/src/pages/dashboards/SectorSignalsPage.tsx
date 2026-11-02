import { useState } from "react";
import { PageIntro } from "@/components/layout/PageIntro";
import { CardBoundary } from "@/components/modelCard";
import { Chapter } from "@/components/dashboards/aiCapex/Chapter";
import { useSectorSignals } from "@/hooks/useSectorSignals";
import { Drilldown, HoldChart, Heatmap, LiveList, day, pct, useDefaultSel, type Sel } from "@/components/dashboards/sectorSignals/parts";
import { cn } from "@/lib/cn";

// Sector Signal Significance (dashboards/sector_signals/run.py → GET /dashboards/sector-signals). Rebuilt by the
// sector_signals Refresh job after each close.

function Horizon({ hs, h, set }: { hs: number[]; h: number; set: (h: number) => void }) {
  return (
    <div role="radiogroup" aria-label="Horizon" className="inline-flex rounded-full border border-border-strong bg-surface p-0.5">
      {hs.map((x) => (
        <button key={x} type="button" role="radio" aria-checked={x === h} onClick={() => set(x)}
          className={cn("px-3 py-1 text-[12.5px] font-semibold rounded-full", x === h ? "bg-text text-surface" : "text-text-2 hover:text-text")}>
          {x} days
        </button>
      ))}
    </div>
  );
}

export default function SectorSignalsPage() {
  const { data: d, isLoading } = useSectorSignals();
  const fallback = useDefaultSel(d);
  const [picked, setPicked] = useState<Sel | null>(null);
  const [hPicked, setH] = useState<number | null>(null);
  const sel = picked ?? fallback;
  const h = hPicked ?? (d ? Math.max(...d.params.horizons) : 20);
  const pick = (s: Sel) => {
    setPicked(s);
    document.getElementById("drilldown")?.scrollIntoView({ behavior: "smooth", block: "start" });
  };
  const counts = d?.summary.counts[String(h)];
  const rn = d?.regime_now;
  const oos = d?.summary.oos;

  return (
    <div className="grid gap-4">
      <PageIntro
        kicker="Dashboard · Sector Signals"
        title="Is today's sector signal real, or noise?"
        steps={["Today", "The map", "Drilldown", "Does it hold?"]}
        when={d ? {
          label: "Prices to",
          value: day(d.as_of),
          note: rn && <span className="block">VIX {rn.vix?.toFixed(1)} ({rn.vix_state}) · SPY {rn.trend_state === "up" ? "above" : "below"} its 200-day</span>,
        } : undefined}
      >
        Every technical signal on the 11 SPDR sector ETFs, judged by that sector's own history: what each sector did after
        every past RSI extreme, moving-average cross, breakout and volume surge since 1998, against the same calendar shifted to
        random dates, with a correction for testing hundreds of combinations at once.
      </PageIntro>

      {isLoading ? (
        <p className="text-sm text-muted">Loading…</p>
      ) : !d ? (
        <p className="text-sm text-muted">The dashboard hasn't been built yet. It updates after each US close.</p>
      ) : (
        <>
          <CardBoundary name="Today">
            <Chapter id="today" n="01" tag="Today" question="What fired in the last week?"
              sentence={d.live.length
                ? `**${d.live.length}** signals fired in the last ${d.params.live_lookback_days} sessions; **${d.live.filter((e) => e.verdict === "signal").length}** have a track record that clears the bar.`
                : undefined}
              note={<>Each row is judged at the horizon where its record is strongest. Click a row for the full picture.</>}>
              <LiveList d={d} sel={sel} onPick={pick} />
            </Chapter>
          </CardBoundary>

          <div className="flex flex-wrap items-center gap-3 text-xs text-text-2">
            <span className="font-semibold text-text">Horizon</span>
            <Horizon hs={d.params.horizons} h={h} set={setH} />
            <span>changes the map and the drilldown</span>
          </div>

          <CardBoundary name="The map">
            <Chapter id="map" n="02" tag="The map" question="Which signals have meant something, sector by sector?"
              sentence={counts ? `At ${h} days, **${counts.signal}** of ${d.summary.tests / d.params.horizons.length} sector-signal pairs pass, **${counts.weak}** are weak, and **${counts.noise}** look like noise.` : undefined}
              note={<>Color is the direction of the move after the signal versus usual; strength of color is the verdict.
                A signal can work on one sector and be noise on the next.</>}>
              <Heatmap d={d} h={h} sel={sel} onPick={pick} />
            </Chapter>
          </CardBoundary>

          <CardBoundary name="Drilldown">
            <Chapter id="drilldown" n="03" tag="Drilldown" question="What happened after, each time?"
              note={<>Returns run from the close on the day the signal fired. The gray band is where the same number of
                random dates usually lands; a line outside it is unusual.</>}>
              {sel ? <Drilldown d={d} sel={sel} h={h} /> : <p className="text-sm text-muted">Pick a cell on the map.</p>}
            </Chapter>
          </CardBoundary>

          <CardBoundary name="Does it hold?">
            <Chapter id="holds" n="04" tag="Does it hold?" question="Would this method have fooled itself?"
              sentence={oos?.signal.rate != null
                ? `Run on the first ${Math.round(d.params.oos_split * 100)}% of history only, the pairs it called signals kept their direction in the years it never saw **${pct(oos.signal.rate, 0, false)}** of the time; the ones it called noise, **${pct(oos.noise.rate, 0, false)}**.`
                : `Run on the first ${Math.round(d.params.oos_split * 100)}% of history only, nothing cleared the bar, so there is nothing to check yet; noise kept its direction **${pct(oos?.noise.rate, 0, false)}** of the time.`}
              note={<>Noise should land near a coin flip. If "signals" don't beat it, treat today's signals as noise too.</>}>
              <HoldChart d={d} />
            </Chapter>
          </CardBoundary>

          <section className="text-xs leading-[18px] text-muted grid gap-1.5 px-1">
            <p><b className="text-text-2">How it's judged.</b> Each signal counts once per spell, then can't refire on that sector
              for {d.params.cooldown} sessions. For every sector, signal and horizon, the average return after past events is compared
              with {d.params.bootstrap.toLocaleString()} copies of the same event calendar slid to random dates, which keeps how
              often and how bunched the signal fires. Returns are scaled by the prior {d.params.vol_window}-day volatility for the
              p-value, so signals that cluster in wild markets don't pass for edges. Benjamini–Hochberg then caps false discoveries
              at {Math.round(d.params.fdr * 100)}% across all {d.summary.tests} tests. Pairs with fewer than {d.params.min_events} events aren't judged.</p>
            <p><b className="text-text-2">What it isn't.</b> A statement about the past, not a forecast or a trade: no costs, and a
              real edge can fade. Source: {d.source}.{d.gaps.length > 0 && ` Not enough history: ${d.gaps.map((g) => g.etf).join(", ")}.`}</p>
          </section>
        </>
      )}
    </div>
  );
}
