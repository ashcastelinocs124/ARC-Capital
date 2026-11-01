import type { ReactNode } from "react";
import { PageIntro } from "@/components/layout/PageIntro";
import { C } from "@/lib/theme";
import { Chapter, SourceLink } from "@/components/dashboards/aiCapex/Chapter";
import { ChartTitle, Legend } from "@/components/dashboards/aiCapex/charts";
import { Coef, Lines, P, RowBars, Scatter, Table, VBars, pct, pp, pval, sgn, spct, type Cell } from "@/components/dashboards/partisanGap/charts";
// a fixed 1921–2024 study, bundled from its outputs by scripts/build_partisan_gap_data.py
import D from "@/components/dashboards/partisanGap/data.json";

const OUTS = ["sp_tr", "bond_tr", "rvol", "vix_avg"] as const;
type Out = (typeof OUTS)[number];
const NAME: Record<Out, string> = {
  sp_tr: "S&P 500 total return", bond_tr: "10-yr Treasury return", rvol: "S&P 500 realized volatility", vix_avg: "VIX, annual average",
};
const SHORT: Record<Out, string> = { sp_tr: "S&P 500", bond_tr: "10-yr Treasury", rvol: "Stock volatility", vix_avg: "VIX" };
/** a level (returns in %, the VIX in points) and an effect or difference (pp, or VIX points) */
const lvl = (o: string, v: number | null | undefined) => (o === "vix_avg" ? (v == null ? "—" : v.toFixed(1)) : pct(v));
const eff = (o: string, v: number | null | undefined) => (o === "vix_avg" ? (v == null ? "—" : `${sgn(v, 1)} pts`) : pp(v));

const STOCKS = C.accent, BONDS = C.jobs, FAR = C.accent, CLOSE = C.muted;
const PAIR: [string, string][] = [["S&P 500 total return", STOCKS], ["10-yr Treasury return", BONDS]];
const APART: [string, string][] = [["Parties close together", CLOSE], ["Parties far apart", FAR]];
const BELIEFS = ["Close together", "Far apart"]; // the study's labels for APART, in the same order

const A = D.annual;
const last = A[A.length - 1];
const corr = (period: string, o: string) => D.correlations.find((r) => r.period === period && r.outcome === o)?.corr;
const v4 = (o: string) => D.value.find((r) => r.version.startsWith("4") && r.outcome === o);
const cell = (o: string, gov: string, bel: string) => D.control_cells.find((r) => r.outcome === o && r.government === gov && r.beliefs === bel);
const ctest = (o: string, test: string) => D.control_tests.find((r) => r.outcome === o && r.test === test);
const legR = D.leg_tests.find((r) => r.outcome === "vote_gap" && r.spec === "Simple")?.corr;
const { best, recent_sig, post_sig, min_years } = D.derived;
const reliable = (p: number) => (p < 0.05 ? `statistically reliable, p ${pval(p)}` : `not statistically reliable, p ${pval(p)}`);
const ord = (n: number) => `${n}${n % 100 >= 11 && n % 100 <= 13 ? "th" : ["th", "st", "nd", "rd"][n % 10] ?? "th"}`;

function Card({ id, eyebrow, title, children }: { id: string; eyebrow: string; title: string; children: ReactNode }) {
  return (
    <section id={id} aria-labelledby={`${id}-h`} className="bg-surface border border-border rounded-xl shadow-card px-4 py-4 md:px-5 scroll-mt-4">
      <div className="eyebrow">{eyebrow}</div>
      <h2 id={`${id}-h`} className="font-serif font-bold text-[22px] leading-tight text-text mt-1 mb-3">{title}</h2>
      {children}
    </section>
  );
}

function Tile({ label, value, sub }: { label: string; value: string; sub: string }) {
  return (
    <div className="rounded-lg border border-border bg-surface-2 px-3.5 py-3">
      <div className="text-xs text-muted">{label}</div>
      <div className="num font-serif font-bold text-[28px] leading-tight text-text my-1">{value}</div>
      <div className="text-xs leading-[17px] text-muted">{sub}</div>
    </div>
  );
}

const Note = ({ children }: { children: ReactNode }) => <p className="text-xs leading-[18px] text-muted mt-2">{children}</p>;
const Two = ({ children }: { children: ReactNode }) => <div className="grid gap-5 lg:grid-cols-2">{children}</div>;
const Box = ({ title, children }: { title: string; children: ReactNode }) => <div className="min-w-0"><ChartTitle>{title}</ChartTitle>{children}</div>;

function ShortAnswer() {
  const oos = (o: Out) => spct(v4(o)?.oos_r2);
  const findings: ReactNode[] = [
    <><b>The parties' belief gap doesn't move markets.</b> Its correlation with S&amp;P 500 returns is <b>{sgn(corr("1921–2022", "sp_tr"))}</b> over 1921–2022 and <b>{sgn(corr("1950–2022", "sp_tr"))}</b> since 1950, where 0 means no relationship.</>,
    <><b>It doesn't help forecasting.</b> Added to a forecast built on interest rates, inflation and last year's return, it made out-of-sample stock forecasts worse (R² change <b>{oos("sp_tr")}</b>).</>,
    <><b>Recent-decade signals were trend coincidences.</b> Since 1980, <b>{recent_sig.simple}</b> of <b>{recent_sig.total}</b> period tests looked significant; <b>{recent_sig.trend}</b> survive once the long-run trend is removed.</>,
    <><b>Elections don't change the picture.</b> Of <b>{post_sig.total}</b> tests of market moves 1–6 months after elections, <b>{post_sig.sig}</b> were significant.</>,
    <><b>Who holds power matters more.</b> 10-year Treasuries returned <b>{pct(cell("bond_tr", "Divided", "All")?.mean)}</b> a year under split government vs <b>{pct(cell("bond_tr", "Unified", "All")?.mean)}</b> under one-party control (p-value <b>{pval(ctest("bond_tr", "Divided vs unified")?.p)}</b>). Stocks showed no reliable difference.</>,
    <><b>Which mix has been best?</b> Measured against its own era, stocks did best under <b>{best.sp_tr.combo}</b> ({pp(best.sp_tr.value)} a year over {best.sp_tr.n} years; {reliable(best.sp_tr.p)}) and bonds under <b>{best.bond_tr.combo}</b> ({pp(best.bond_tr.value)} a year over {best.bond_tr.n} years; {reliable(best.bond_tr.p)}).</>,
    <><b>Words and votes diverge.</b> What parties write in platforms has a correlation of <b>{sgn(legR)}</b> with how divided Congress actually votes.</>,
  ];
  return (
    <Card id="findings" eyebrow="The short answer" title="A good gauge of polarization, not a market signal">
      <div className="grid gap-5 lg:grid-cols-[1fr_340px]">
        <ol className="list-decimal pl-5 grid gap-2 text-[13.5px] leading-[21px] text-text-2 marker:text-accent marker:font-semibold">
          {findings.map((f, i) => <li key={i}>{f}</li>)}
        </ol>
        <div className="grid gap-3 grid-cols-2 content-start">
          <Tile label="Gap index, 2023–24" value={sgn(last.gap_index)} sub="SD from the 1921–2024 average; the widest year on record" />
          <Tile label="Forecast value · S&P 500" value={oos("sp_tr")} sub="Out-of-sample R² added; below 0 = worse forecasts" />
          <Tile label="Forecast value · Treasuries" value={oos("bond_tr")} sub="Out-of-sample R² added; below 0 = worse forecasts" />
          <Tile label="Forecast value · volatility" value={oos("rvol")} sub="Out-of-sample R² added; below 0 = worse forecasts" />
        </div>
      </div>
    </Card>
  );
}

const COMPONENTS: [keyof (typeof A)[number], string, string][] = [
  ["vote_gap_z", "Congress voting gap", C.accent],
  ["econ_gap_z", "Economy platform", C.jobs],
  ["business_gap_z", "Business / regulation platform", C.warning],
  ["immig_gap_z", "Immigration / identity platform", C.inflation],
  ["foreign_gap_z", "Foreign policy platform", C.ai],
];

function TheGap() {
  const z = (v: number) => `${sgn(v, 2)} SD`;
  return (
    <Chapter id="index" n="01" tag="THE GAP" question="How far apart are the parties?"
      sentence={`The index puts 2023–24 at **${sgn(last.gap_index)} SD**, the widest point since 1921. It was narrow at the New Deal and in the 1960s–70s and has risen steadily since the 1990s.`}
      note="Half from how far apart the parties vote in Congress, half from how far apart their platforms are. Higher = further apart. Standardized: 0 is the 1921–2024 average, 1 is one standard deviation.">
      <div className="grid gap-5">
        <Box title="Composite Partisan Policy Gap index, SD">
          <Lines xs={A.map((r) => r.year)} xFmt={String} yFmt={z} tickFmt={(v) => sgn(v, 0)} refY={{ at: 0, label: "1921–2024 average" }}
            series={[{ name: "Gap index", color: C.accent, values: A.map((r) => r.gap_index), step: true }]}
            label={`Partisan Policy Gap index by year, 1921 to 2024, ending at ${sgn(last.gap_index)} standard deviations in 2024.`} />
        </Box>
        <Box title="The five parts, SD">
          <Legend items={COMPONENTS.map(([, n, c]) => [n, c])} />
          <Lines xs={A.map((r) => r.year)} xFmt={String} yFmt={z} tickFmt={(v) => sgn(v, 0)} refY={{ at: 0 }}
            series={COMPONENTS.map(([k, name, color]) => ({ name, color, values: A.map((r) => r[k] as number | null), step: true }))}
            label="The index's five parts as standard scores by year: the Congress voting gap and the economy, business, immigration and foreign policy platform gaps." />
          <Note>Platforms change only every four years, so those lines step.</Note>
        </Box>
      </div>
    </Chapter>
  );
}

function NarrowWide() {
  const { terciles, direction } = D.derived;
  return (
    <Chapter id="levels" n="02" tag="NARROW VS WIDE" question="Do markets do better when the gap is wide?"
      sentence="Wide-gap years look better for stocks and calmer, but **neither difference is reliable**: the narrow third holds the 1929–40 Depression."
      note="Left: years split into equal thirds by the index level (VIX: thirds within 1990–2024). Right: years when the index widened vs narrowed at the latest new Congress. Calendar-year averages.">
      <Two>
        {OUTS.map((o) => {
          const rows = [...terciles[o], ...direction[o]];
          return (
            <Box key={o} title={NAME[o]}>
              <VBars groups={rows.map((r) => r.bucket)} series={[["Average", C.accent]]} values={rows.map((r) => [r.mean])} ns={rows.map((r) => [r.n])}
                fmt={(v) => lvl(o, v)} bands={[{ from: 0, label: "Gap level" }, { from: 3, label: "Gap direction" }]}
                label={`${NAME[o]} by gap level and direction: ${rows.map((r) => `${r.bucket} ${lvl(o, r.mean)}`).join(", ")}.`} />
            </Box>
          );
        })}
      </Two>
    </Chapter>
  );
}

function Tests() {
  const n = D.regressions.length;
  const sig = D.regressions.filter((r) => r.p < 0.05);
  const pts = A.filter((r) => r.gap_change != null && r.bond_tr != null).map((r) => ({ x: r.gap_change!, y: r.bond_tr!, name: String(r.year) }));
  return (
    <Chapter id="tests" n="03" tag="TESTS" question="Is any link statistically real?"
      sentence={sig.length
        ? `With foreign policy in the index, only **${sig.length} of ${n}** tests ${sig.length === 1 ? "is" : "are"} significant at 5% (${sig.map((r) => `${SHORT[r.outcome as Out].toLowerCase()}, ${r.spec_label.toLowerCase()}, p ${pval(r.p)}`).join("; ")}), about what chance alone would give across ${n} tests.`
        : `With foreign policy in the index, **none** of the ${n} tests is significant at 5%.`}
      note="Effect of a 1-SD higher index (level) or a 1-SD widening (change) on each outcome, with 95% intervals from Newey-West standard errors. A filled dot is significant at 5%; a hollow one's interval crosses zero.">
      <div className="grid gap-5">
        <Two>
          {OUTS.map((o) => (
            <Box key={o} title={NAME[o]}>
              <Coef rows={D.regressions.filter((r) => r.outcome === o).map((r) => ({ name: r.spec_label, beta: r.beta, se: r.se, p: r.p, n: r.n }))}
                fmt={(v) => eff(o, v)} label={`Effect of the gap on ${NAME[o]} in ${D.regressions.filter((r) => r.outcome === o).length} tests; none crosses the 5% line unless marked.`} />
            </Box>
          ))}
        </Two>
        <Two>
          <Box title="Gap change vs 10-yr Treasury return, 1923–2022">
            <Scatter points={pts} xFmt={(v) => sgn(v, 1)} yFmt={(v) => pct(v, 0)} xTitle="Gap change at new Congress (SD)" yTitle="10-yr Treasury return"
              color={C.jobs} label="One dot per year: the gap's change at the new Congress against that year's 10-year Treasury return. The fitted line slopes only slightly down." />
            <Note>Each dot is a year. The fitted line slopes only slightly down and the link is not statistically reliable.</Note>
          </Box>
          <Box title="Which topic matters? One at a time, 1921–2022">
            <Table caption="Each topic's gap alone against each outcome" head={["Topic", "Outcome", "Effect / SD", "p"]} left={2} tall
              rows={D.components.map((r) => [r.component_label, SHORT[r.outcome as Out], { v: eff(r.outcome, r.beta), bold: r.p < 0.05 }, P(r.p)])} />
            <Note>Bold = significant at 5%. With fifteen tests, about one false positive is expected; immigration and foreign policy point in opposite directions for bonds, a sign of noise.</Note>
          </Box>
        </Two>
      </div>
    </Chapter>
  );
}

function Forecast() {
  const vers = [...new Set(D.value.map((r) => r.version))];
  return (
    <Chapter id="useful" n="04" tag="FORECAST VALUE" question="Does it help forecast markets?"
      sentence={`Added to a controls-only forecast, it made out-of-sample stock forecasts **worse (${spct(v4("sp_tr")?.oos_r2)} R²)**. No version adds forecasting value for stocks, bonds or the VIX.`}
      note="Controls are the outcome's prior-year value, the 10-yr yield at the start of the year and prior-year inflation. The real-time version uses only what was known on January 1 (last Congress's votes, latest platforms).">
      <Two>
        <Box title="Out-of-sample forecast gain, R²">
          <Legend items={[["4 topics (with foreign policy)", C.accent], ["3 topics (original)", C.muted]]} />
          <VBars groups={OUTS.map((o) => SHORT[o])} series={[["4 topics", C.accent], ["3 topics", C.muted]]} fmt={(v) => spct(v)}
            values={OUTS.map((o) => vers.map((v) => D.value.find((r) => r.outcome === o && r.version === v)?.oos_r2 ?? null))}
            tipTitle={(g, s) => `${SHORT[OUTS[g]]} · ${vers[s]}`}
            label={`Out-of-sample R squared added by the gap: ${OUTS.map((o) => `${SHORT[o]} ${spct(v4(o)?.oos_r2)}`).join(", ")}.`} />
          <Note>Expanding-window forecasts from 1950 (VIX from 2000). Above 0 = the gap improved forecasts.</Note>
        </Box>
        <Box title="p-values for the gap-widening effect">
          <Table caption="p-values for the gap-widening effect" head={["Index", "Outcome", "Simple", "Controls", "Real time", "Permutation"]} left={2}
            rows={D.value.map((r) => [r.version.startsWith("4") ? "4 topics" : "3 topics", SHORT[r.outcome as Out], P(r.chg_p), P(r.ctrl_p), P(r.rt_p), P(r.perm_p)])} />
          <Note>Bold = below 0.05. Permutation p shuffles which Congresses widened 2,000 times. The three-topic index's link to lower stock volatility survives controls and the permutation test, but not real-time use or out-of-sample forecasting, and fades once foreign policy is added.</Note>
        </Box>
      </Two>
    </Chapter>
  );
}

function Recent() {
  const bond = D.recent.filter((r) => r.outcome === "bond_tr");
  return (
    <Chapter id="recent" n="05" tag="RECENT DECADES" question="Does it hold since 1980?"
      sentence={`Since 1980, **${recent_sig.simple} of ${recent_sig.total}** period tests looked significant; **${recent_sig.trend}** survive once the long-run trend is removed.`}
      note="Since 1980 the gap rose almost every Congress while bond yields fell, so the two move together without one driving the other.">
      <Two>
        <Box title="10-yr Treasury: p-value by starting year">
          <Legend items={[["Simple test", C.accent], ["Time trend removed", C.jobs]]} />
          <Lines xs={bond.map((r) => r.start)} xFmt={(v) => `From ${v}`} xTickFmt={String} xTicks={() => bond.map((r) => r.start)}
            yFmt={(v) => v.toFixed(2)} refY={{ at: 0.05, label: "p = 0.05" }} height={220}
            series={[{ name: "Simple test", color: C.accent, values: bond.map((r) => r.p) }, { name: "Time trend removed", color: C.jobs, values: bond.map((r) => r.p_trend) }]}
            label={`p-values for the gap against 10-year Treasury returns by starting year: ${bond.map((r) => `${r.start} ${pval(r.p)}, trend removed ${pval(r.p_trend)}`).join("; ")}.`} />
          <Note>Below the dashed line = significant at 5%.</Note>
        </Box>
        <Box title="Every period and outcome">
          <Table caption="Correlation and p-values by period and outcome" head={["Period", "Outcome", "Corr.", "p", "p, no trend"]} left={2} tall
            rows={D.recent.map((r) => [r.window, SHORT[r.outcome as Out], sgn(r.corr), P(r.p), P(r.p_trend)])} />
          <Note>Bold = p &lt; 0.05.</Note>
        </Box>
      </Two>
    </Chapter>
  );
}

function Vix() {
  const V = D.vix;
  const mon = (i: number) => new Date(`${V[i].m}-15`).toLocaleDateString("en-US", { month: "short", year: "numeric" });
  const jan = (w: number) => V.flatMap((r, i) => (r.m.endsWith("-01") && +r.m.slice(0, 4) % (w < 480 ? 10 : 5) === 0 ? [i] : []));
  const xs = V.map((_, i) => i);
  const vt = D.vix_tests[0];
  const ter = D.derived.vix_terciles;
  return (
    <Chapter id="vix" n="06" tag="VIX" question="Does polarization move the VIX?"
      sentence={`Monthly VIX against the gap: correlation **${sgn(vt.corr)}**, p = ${pval(vt.p)}; with the trend removed, p = ${pval(D.vix_tests[1].p)}. Weak, and never significant at 5%.`}
      note="Monthly VIX, 1990–2024. The gap changes only every two years, so tests correct for its repeated values (Newey-West, 24 lags).">
      <div className="grid gap-5">
        <Box title="Monthly VIX (top) and the gap index (bottom)">
          <Lines xs={xs} xFmt={mon} xTickFmt={(i) => V[i].m.slice(0, 4)} xTicks={jan} yFmt={(v) => v.toFixed(1)} tickFmt={(v) => v.toFixed(0)} height={190}
            series={[{ name: "VIX", color: C.accent, values: V.map((r) => r.vix) }]}
            label="Monthly average VIX, January 1990 to December 2024. Spikes line up with crises such as 1998, 2008 and 2020." />
          <Lines xs={xs} xFmt={mon} xTickFmt={(i) => V[i].m.slice(0, 4)} xTicks={jan} yFmt={(v) => `${sgn(v, 2)} SD`} tickFmt={(v) => sgn(v, 0)} height={120}
            series={[{ name: "Gap index", color: C.jobs, values: V.map((r) => r.gap), step: true }]}
            label="The gap index by month, 1990 to 2024, stepping at each new Congress." />
          <Note>VIX spikes line up with crises such as 1998, 2008 and 2020, not with moves in the gap.</Note>
        </Box>
        <Two>
          <Box title="Average VIX by gap thirds, monthly">
            <VBars groups={ter.map((r) => r.bucket)} series={[["VIX", C.accent]]} values={ter.map((r) => [r.mean])} ns={ter.map((r) => [r.n])} nUnit="months"
              fmt={(v) => v.toFixed(1)} label={`Average monthly VIX by gap thirds: ${ter.map((r) => `${r.bucket} ${r.mean?.toFixed(1)}`).join(", ")}.`} />
          </Box>
          <Box title="VIX tests, per 1 SD, in VIX points">
            <Table caption="VIX tests" head={["Test", "n", "Corr.", "Effect", "p"]}
              rows={D.vix_tests.map((r) => [r.test, r.n, sgn(r.corr), { v: sgn(r.beta, 1), bold: r.p < 0.05 }, P(r.p)])} />
          </Box>
        </Two>
      </div>
    </Chapter>
  );
}

function Power() {
  const OUT3 = ["sp_tr", "bond_tr", "rvol"] as const;
  const govs = ["Unified", "Divided"];
  return (
    <Chapter id="control" n="07" tag="WHO HOLDS POWER" question="Does it matter who controls government?"
      sentence={`10-yr Treasuries returned **${pct(cell("bond_tr", "Divided", "All")?.mean)}** a year under split government vs **${pct(cell("bond_tr", "Unified", "All")?.mean)}** under one-party control (p ${pval(ctest("bond_tr", "Divided vs unified")?.p)}). No stock difference is statistically reliable, and the gap adds little once you know who controls government.`}
      note={'Unified = one party holds the White House, Senate and House; divided = anything else. "Far apart" = gap index above its 1921–2022 median. Calendar-year averages, 1921–2022. VIX is left out: one cell has only two years.'}>
      <div className="grid gap-5">
        <Legend items={APART} />
        <div className="grid gap-5 md:grid-cols-3">
          {OUT3.map((o) => (
            <Box key={o} title={NAME[o]}>
              <VBars groups={govs} series={APART} fmt={(v) => lvl(o, v)}
                values={govs.map((g) => BELIEFS.map((b) => cell(o, g, b)?.mean ?? null))}
                ns={govs.map((g) => BELIEFS.map((b) => cell(o, g, b)?.n ?? null))}
                tipTitle={(g, s) => `${govs[g]} government, ${APART[s][0].toLowerCase()}`}
                label={`${NAME[o]} by government and gap: ${govs.flatMap((g) => BELIEFS.map((b) => `${g}, ${b.toLowerCase()} ${lvl(o, cell(o, g, b)?.mean)}`)).join("; ")}.`} />
            </Box>
          ))}
        </div>
        <Box title="Are the differences real? Newey-West regressions">
          <Table caption="Divided vs unified government tests" head={["Outcome", "Comparison", "Difference", "p"]} left={2} tall
            rows={D.control_tests.map((r) => [SHORT[r.outcome as Out], r.test, { v: eff(r.outcome, r.beta), bold: r.p < 0.05 }, P(r.p)])} />
          <Note>Bold = p &lt; 0.05. Returns and volatility in percentage points, VIX in points.</Note>
        </Box>
      </div>
    </Chapter>
  );
}

function BestMix() {
  const { era } = D.derived;
  const raw = new Map(D.combos.map((r) => [r.combo, r]));
  const rawDetail = new Map(D.control_detail.map((r) => [r.setup, r]));
  const avg = raw.get("All years (average)");
  const lead = era.combos.find((e) => e.name === "Dem president, Rep House, Rep Senate"); // the raw ranking's leader
  const vs = (v: number | null) => `${pp(v)} a year vs its era`;
  return (
    <Chapter id="best-mix" n="08" tag="BEST MIX" question="Which mix of president and Congress has been best?"
      sentence={`Measured against its own era, stocks did best under **${best.sp_tr.combo}** (${pp(best.sp_tr.value)} a year over ${best.sp_tr.n} years; ${reliable(best.sp_tr.p)}) and bonds under **${best.bond_tr.combo}** (${pp(best.bond_tr.value)} a year over ${best.bond_tr.n} years; ${reliable(best.bond_tr.p)}).`}
      note={<>Mixes fell in very different years, from the Depression to the 2010s, so each year's return is measured against the average of the {era.window} years around it (5 either side): 0 = that era's average. Raw averages are in the table. "p vs rest" shuffles whole Congresses 20,000 times. Mixes with fewer than {min_years} years are faded and not ranked as "best". Published studies (Edelman, Bespoke, CFRA, Retirement Researcher) rank raw returns, where a Democratic president with a Republican Congress leads{lead && <> at {pct(raw.get(lead.name)?.sp_tr)} a year; against its era that mix made {pp(lead.sp_tr)}</>}.</>}>
      <div className="grid gap-5">
        <Legend items={PAIR} />
        <Two>
          <Box title="Every president / House / Senate mix, vs its era">
            <RowBars series={PAIR} fmt={(v) => pp(v)}
              rows={era.combos.map((e) => {
                const r = raw.get(e.name);
                return {
                  name: `${e.name} · ${e.n} yrs`, values: [e.sp_tr, e.bond_tr], faded: e.n < min_years,
                  tip: { title: e.name, lines: [
                    `S&P 500 ${vs(e.sp_tr)} (raw ${pct(r?.sp_tr)}), p ${pval(e.sp_tr_p)}`,
                    `10-yr Treasury ${vs(e.bond_tr)} (raw ${pct(r?.bond_tr)}), p ${pval(e.bond_tr_p)}`,
                    `${e.n} years: ${r?.years}`,
                  ] },
                };
              })}
              label={`Average annual return against its era by party mix: ${era.combos.map((e) => `${e.name}, stocks ${pp(e.sp_tr)}, bonds ${pp(e.bond_tr)}`).join("; ")}.`} />
          </Box>
          <Box title="By type of split, vs its era">
            <RowBars series={PAIR} fmt={(v) => pp(v)}
              rows={era.detail.map((e) => {
                const r = rawDetail.get(e.name);
                return {
                  name: `${e.name} · ${e.n} yrs`, values: [e.sp_tr, e.bond_tr],
                  tip: { title: e.name, lines: [`S&P 500 ${vs(e.sp_tr)} (raw ${pct(r?.sp_tr)})`, `10-yr Treasury ${vs(e.bond_tr)} (raw ${pct(r?.bond_tr)})`, `${e.n} years: ${r?.years}`] },
                };
              })}
              label={`Average annual return against its era by who held the White House and Congress: ${era.detail.map((e) => `${e.name}, stocks ${pp(e.sp_tr)}, bonds ${pp(e.bond_tr)}`).join("; ")}.`} />
            <Note>Small groups can swing on one crash: the Republican-president, split-Congress row includes 1931–32 and 2001–02.</Note>
          </Box>
        </Two>
        <Box title="The numbers">
          <Table caption="Returns by party mix, against their era and raw" head={["President, House, Senate", "Years", "S&P 500 vs era", "p vs rest", "10-yr vs era", "p vs rest", "S&P 500 raw", "10-yr raw"]}
            rows={era.combos.map((e) => {
              const r = raw.get(e.name);
              return [e.name, e.n, { v: pp(e.sp_tr), bold: e.sp_tr_p < 0.05 }, P(e.sp_tr_p), { v: pp(e.bond_tr), bold: e.bond_tr_p < 0.05 }, P(e.bond_tr_p), pct(r?.sp_tr), pct(r?.bond_tr)];
            })} />
          <Note>Bold = p &lt; 0.05. Raw average of all {avg?.n} years: {pct(avg?.sp_tr)} for stocks, {pct(avg?.bond_tr)} for 10-yr Treasuries.</Note>
        </Box>
      </div>
    </Chapter>
  );
}

function Elections() {
  const wins = ["1m", "3m", "6m"], wl = ["1 month", "3 months", "6 months"];
  const get = (k: string, w: string, b: string) => D.post_cells.find((r) => r.sample === "All elections" && r.outcome === `${k}_${w}` && r.beliefs === b);
  const bars = (k: string, name: string) => (
    <Box title={`${name} after the election`}>
      <VBars groups={wl} series={APART} fmt={(v) => pct(v)} nUnit="elections"
        values={wins.map((w) => BELIEFS.map((b) => get(k, w, b)?.mean ?? null))}
        ns={wins.map((w) => BELIEFS.map((b) => get(k, w, b)?.n ?? null))}
        tipTitle={(g, s) => `${wl[g]} after, ${APART[s][0].toLowerCase()}`}
        label={`${name} after elections: ${wins.map((w, i) => `${wl[i]}: close ${pct(get(k, w, "Close together")?.mean)}, far ${pct(get(k, w, "Far apart")?.mean)}`).join("; ")}.`} />
    </Box>
  );
  return (
    <Chapter id="post-election" n="09" tag="AFTER ELECTIONS" question="Do elections change the picture?"
      sentence={`Of **${post_sig.total}** tests of market moves 1–6 months after elections, **${post_sig.sig}** were significant. Stocks usually rise after elections whatever the result, and the VIX usually falls as uncertainty clears.`}
      note={'All 52 November elections, 1920–2022. Returns run from October\'s level through 1, 3 and 6 months later. "Far apart" = the gap the election produced is above the median of all elections. Shiller monthly averages, so windows are approximate.'}>
      <div className="grid gap-5">
        <Legend items={APART} />
        <Two>{bars("sp", "S&P 500 total return")}{bars("bond", "10-yr Treasury return")}</Two>
        <Box title="p-values: does the gap explain post-election moves?">
          <Table caption="Post-election tests" head={["Outcome", "Elections", "n", "Far − close", "p", "Gap p", "+ trend p", "Widening p"]} left={2} tall
            rows={D.post_tests.map((r) => [r.outcome_label, r.sample, r.n, r.outcome === "vix_chg_60d" ? `${sgn(r.far_diff, 1)} pts` : pp(r.far_diff), P(r.far_p), P(r.gap_p), P(r.gap_trend_p), P(r.chg_p)])} />
          <Note>Far − close = difference in averages; Gap = per 1 SD of the gap the election produced; + trend = the same with a time trend; Widening = whether the election widened the gap. VIX change runs from the day before the election to 60 days after (1990 on).</Note>
        </Box>
      </div>
    </Chapter>
  );
}

const TOPIC: Record<string, string> = { econ_gap_z: "Economy", business_gap_z: "Business / regulation", immig_gap_z: "Immigration / identity", foreign_gap_z: "Foreign policy" };
const MEASURE: Record<string, string> = {
  vote_gap: "Voting gap", unity: "Party-unity votes", bipartisan: "Bipartisan votes", consensus: "Near-unanimous votes", public_laws: "Laws enacted", law_pages: "Pages of law",
};

function Congress() {
  const G = D.legislative.filter((r) => r.platform_z != null && r.vote_gap_z != null);
  const byYear = new Map(D.legislative.map((r) => [r.year, r]));
  const name = (y: number) => {
    const r = byYear.get(y);
    return r ? `${ord(r.congress)} Congress, ${y}–${String(y + 1).slice(2)}` : String(y);
  };
  const raw = (v: number | null) => (v == null ? "—" : Math.abs(v) >= 10 ? sgn(v, 0) : sgn(v, 3));
  const share = (k: string) => k !== "public_laws" && k !== "law_pages";
  return (
    <Chapter id="legislation" n="10" tag="CONGRESS" question="Do platform differences show up in Congress?"
      sentence={`What the parties write in platforms has a correlation of **${sgn(legR)}** with how divided Congress actually votes. Markets price what passes, not what parties say.`}
      note="The platform half of the index measures what the parties say they believe. Here it is tested against what each of the 52 Congresses from 1921 to 2024 did: how polarized the voting was, how often the parties voted together, and how many laws passed.">
      <div className="grid gap-5">
        <Two>
          <Box title="Platform gap vs actual voting gap, SD">
            <Legend items={[["Platform gap (what they say)", C.jobs], ["Voting gap (how they vote)", C.accent]]} />
            <Lines xs={G.map((r) => r.year)} xFmt={name} xTickFmt={String} yFmt={(v) => `${sgn(v, 2)} SD`} tickFmt={(v) => sgn(v, 0)} refY={{ at: 0 }}
              series={[{ name: "Platform gap", color: C.jobs, values: G.map((r) => r.platform_z) }, { name: "Voting gap", color: C.accent, values: G.map((r) => r.vote_gap_z) }]}
              label={`Platform gap and voting gap by Congress, 1921 to 2024, as standard scores; correlation ${sgn(legR)}.`} />
          </Box>
          <Box title="Platform gap vs party-line voting">
            <Scatter points={G.filter((r) => r.unity != null).map((r) => ({ x: r.platform_z!, y: r.unity!, name: name(r.year) }))}
              xFmt={(v) => sgn(v, 1)} yFmt={(v) => pct(v, 0)} xTitle="Platform gap (SD)" yTitle="Party-unity vote share" color={C.jobs}
              label="One dot per Congress: the platform gap against the share of roll calls where most Democrats voted against most Republicans." />
            <Note>Party-unity share = roll calls where most Democrats voted against most Republicans (House and Senate averaged).</Note>
          </Box>
        </Two>
        <Two>
          <Box title="Divided vs unified government, average per Congress">
            <Table caption="Congress under unified vs divided government" head={["Measure", "Unified", "Divided"]}
              rows={D.derived.leg_div.map((r) => [r.label, ...[r.unified, r.divided].map((v) => (share(r.measure) ? pct(v) : Math.round(v).toLocaleString()))])} />
            <Note>1921–2022 for laws, 1921–2024 for votes. Divided government passed about 120 fewer laws per Congress, but that fades once the long decline in law counts is accounted for.</Note>
          </Box>
          <Box title="Which topic's gap tracks Congress?">
            <Table caption="Correlation of each platform topic's gap with each Congress outcome" head={["Topic", "Outcome", "Corr.", "p"]} left={2} tall
              rows={D.leg_topics.map((r) => [TOPIC[r.topic], MEASURE[r.outcome], { v: sgn(r.corr), bold: r.p < 0.05 }, P(r.p)])} />
          </Box>
        </Two>
        <Box title="Platform gap effects, with and without controls">
          <Table caption="Platform gap effects on Congress" head={["Outcome", "Model", "n", "Effect (SD)", "p", "Divided effect", "p"]} left={2} tall
            rows={D.leg_tests.map((r): Cell[] => [MEASURE[r.outcome], r.spec, r.n, { v: sgn(r.beta_sd), bold: r.p < 0.05 }, P(r.p), raw(r.divided_beta), P(r.divided_p)])} />
          <Note>Effect of a 1-SD wider platform gap, in standard deviations of each outcome (Newey-West). "Divided" = the separate effect of divided government in the same model, in the outcome's own units. Wider platform gaps came with slightly <i>more</i> bipartisan votes (mostly the business-regulation topic), not fewer. Laws are getting fewer and longer, so counts alone understate output.</Note>
        </Box>
      </div>
    </Chapter>
  );
}

function Learned() {
  return (
    <Card id="conclusions" eyebrow="What we learned" title="Power beats beliefs">
      <ul className="list-disc pl-5 grid gap-2 text-[13.5px] leading-[21px] text-text-2 marker:text-accent max-w-4xl">
        <li><b className="text-text">Polarization is real and rising.</b> The gap index puts 2023–24 at the widest point in over a century.</li>
        <li><b className="text-text">It is not a market signal.</b> Neither how far apart the parties are nor whether the gap is widening reliably explains stock returns, Treasury returns, volatility or the VIX: in any period, with or without controls, or in the months after elections. Out of sample, it made forecasts worse.</li>
        <li><b className="text-text">Early hints were coincidences.</b> Links to bonds and the VIX faded when foreign policy was added, and recent-decade results vanished once the long-run trend was removed.</li>
        <li><b className="text-text">Power beats beliefs.</b> Split government has reliably come with better Treasury returns, plausibly because gridlock limits big spending and borrowing. For stocks, no difference between combinations is statistically reliable.</li>
        <li><b className="text-text">Words and votes diverge.</b> Platform distance does not track how divided Congress votes or how much law it passes.</li>
      </ul>
    </Card>
  );
}

function Method() {
  return (
    <Card id="method" eyebrow="Method" title="How the index is built">
      <div className="grid gap-6 lg:grid-cols-2 text-[13px] leading-[20px] text-text-2">
        <ol className="list-decimal pl-5 grid gap-1.5">
          <li><b className="text-text">Congress voting gap:</b> distance between the Republican and Democratic party means on the first (economic) DW-NOMINATE dimension, averaged over the House and Senate, for each Congress (Voteview).</li>
          <li><b className="text-text">Platform gaps:</b> for each presidential platform since 1920, a log-ratio position score per topic from the Manifesto Project's coded share of sentences; the gap is Republican minus Democratic, applied to the four years after its election. Topics: economy, business regulation, immigration / identity and foreign policy.</li>
          <li><b className="text-text">Composite:</b> each part standardized over 1921–2024; index = ½ voting gap + ½ average of the four platform topics, then re-standardized.</li>
          <li><b className="text-text">Party control:</b> majorities per Congress from the published party-division tables, cross-checked with Voteview. The 72nd House is counted Democratic, the 107th Senate Democratic (after the 2001 Jeffords switch), and 2021–22 unified Democratic.</li>
          <li><b className="text-text">Outcomes:</b> S&amp;P 500 calendar-year total return and realized volatility from Shiller's monthly data; 10-yr Treasury return as a constant-maturity par bond from Shiller's long rate; VIX from Cboe (1990 on). Shiller dividends end mid-2023, so return tests stop at 2022.</li>
          <li><b className="text-text">Tests:</b> Newey-West standard errors throughout, with era splits, the Depression excluded, time-trend controls, block permutation tests, expanding-window out-of-sample forecasts and a real-time version that uses only what was known on January 1.</li>
        </ol>
        <div>
          <h3 className="text-[15px] font-semibold text-text mb-1">Caveats</h3>
          <ul className="list-disc pl-5 grid gap-1.5">
            <li>Results depend on how the index is built: adding foreign policy erased the three-topic index's significant links to Treasuries and the VIX. Treat any single finding as fragile.</li>
            <li>The index level trends with eras (low mid-century, high today), so level comparisons mostly compare decades. Changes are the cleaner test.</li>
            <li>About 100 years but only ~50 Congresses, so effective samples are small. Across well over 100 tests, a few p &lt; 0.05 results are expected by chance alone.</li>
            <li>The 2020 Republican platform re-adopted 2016's, so those topic scores repeat. 2024 platforms are not yet coded.</li>
            <li>Law counts for 2021–24 are left out: that source is incomplete there.</li>
            <li>Shiller prices are monthly averages, which slightly smooth returns and volatility. Correlation, not causation.</li>
          </ul>
        </div>
      </div>
    </Card>
  );
}

const SOURCES: [string, string, string][] = [
  ["Voteview", "https://voteview.com", "DW-NOMINATE scores, roll calls and member votes (Lewis, Poole, Rosenthal et al.)"],
  ["Manifesto Project", "https://manifesto-project.wzb.eu", "coded U.S. party platforms, dataset MPDS2024a"],
  ["Robert Shiller's market data", "https://github.com/datasets/s-and-p-500", "monthly S&P 500, dividends, CPI and long-term interest rate"],
  ["Cboe VIX history", "https://github.com/datasets/finance-vix", "daily VIX closes"],
  ["Libgober (2024), Scientific Data", "https://doi.org/10.1038/s41597-023-02758-z", "a comprehensive dataset of U.S. federal laws"],
  ["Party divisions of United States Congresses", "https://en.wikipedia.org/wiki/Party_divisions_of_United_States_Congresses", "party control by Congress"],
  ["Azzimonti (2018), Journal of Monetary Economics", "https://econpapers.repec.org/RePEc:eee:moneco:v:93:y:2018:i:c:p:114-131", "partisan conflict and private investment"],
];

function SourcesAndData() {
  return (
    <Card id="sources" eyebrow="Sources" title="Data and annual figures">
      <ul className="grid gap-1 text-[13px] leading-[20px] text-muted">
        {SOURCES.map(([t, u, d]) => <li key={u}><SourceLink title={t} url={u} />: {d}</li>)}
      </ul>
      <details className="mt-4 group">
        <summary className="cursor-pointer text-[13px] font-semibold text-text hover:text-accent rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent">
          Show the annual data, 1921–2024
        </summary>
        <div className="mt-2">
          <Table caption="Index, change at the new Congress, and outcomes by year" tall
            head={["Year", "Gap index", "Change", "S&P TR", "10-yr TR", "Real. vol", "VIX"]}
            rows={[...A].reverse().map((r) => [String(r.year), sgn(r.gap_index), sgn(r.gap_change), pct(r.sp_tr), pct(r.bond_tr), pct(r.rvol), r.vix_avg?.toFixed(1) ?? "—"])} />
        </div>
      </details>
    </Card>
  );
}

export default function PartisanGapPage() {
  return (
    <div className="grid gap-4">
      <PageIntro
        kicker="Dashboard · Partisan Policy Gap"
        title="Do markets care how far apart the parties are?"
        steps={["The gap", "Markets", "Forecasts", "Who holds power", "Elections", "Congress"]}
        when={{ label: "Study period", value: "1921–2024", note: <span className="block">A fixed study, not updated daily</span> }}
      >
        A Partisan Policy Gap index built from a century of congressional votes and party platforms (economy, business regulation,
        immigration and foreign policy), tested against stocks, Treasuries, volatility and the VIX, against who controls government,
        and against what Congress actually passes.
      </PageIntro>
      <ShortAnswer />
      <TheGap />
      <NarrowWide />
      <Tests />
      <Forecast />
      <Recent />
      <Vix />
      <Power />
      <BestMix />
      <Elections />
      <Congress />
      <Learned />
      <Method />
      <SourcesAndData />
    </div>
  );
}
