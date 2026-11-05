import { useEffect, useMemo, useState, type ReactNode } from "react";
import { PageIntro } from "@/components/layout/PageIntro";
import { Segmented } from "@/components/admin/shell";
import { C } from "@/lib/theme";
import { Chapter, SourceLink } from "@/components/dashboards/aiCapex/Chapter";
import { Box, Card, Note, Tile, Two } from "@/components/dashboards/parts";
import { Dots, RowBars, Table, type Cell } from "@/components/dashboards/partisanGap/charts";
import { IndexScatter, PartyBars, StackRows, TileMap, TrendLines, month, type Seg, type TileCell } from "@/components/dashboards/dcRegulation/charts";
// a fixed Nov 4, 2026 snapshot, bundled from the study by scripts/build_dc_regulation_data.py
import D from "@/components/dashboards/dcRegulation/data.json";

type Office = "senate" | "gov";
type Race = (typeof D.senate)[number] & { opponent?: string; results_source?: string };
interface Score { state: string; name: string; rank: number; composite: number; n_pending: number; [comp: string]: string | number }
interface Ev { state: string; indicator: string; level: number | null; evidence: string; pending: string; confidence: string; source_date: string; source_url: string }

const SC = D.scores as unknown as Score[];
const IND = D.indicators as unknown as Record<string, [string, string]>;
const NAMES = D.names as Record<string, string>;
const S = D.summary;
const RACES: Record<Office, Race[]> = { senate: D.senate, gov: D.governors };
const WHO: Record<Office, string> = { senate: "Senate", gov: "governor" };

// stance colors run from restrictive (warm) to permissive (cool); every stance is also written out
const DC: [string, string][] = [["Moratorium", C.danger], ["Make them pay", C.warning], ["Local control / mixed", C.ai], ["Supportive", C.jobs], ["No clear record", C.muted]];
const AI: [string, string][] = [["Stronger regulation", C.danger], ["Mixed", C.ai], ["Light-touch", C.jobs], ["No clear record", C.muted]];
const color = (kind: "dc" | "ai", stance: string) => (kind === "dc" ? DC : AI).find(([s]) => s === stance)?.[1] ?? C.muted;
const COMPS: [string, number, string][] = [
  ["Power", 0.3, C.jobs], ["Permitting", 0.25, C.ai], ["Tax", 0.15, C.warning],
  ["Environment", 0.15, C.co.NBIS], ["Operating rules", 0.1, C.co.CRWV], ["Administration", 0.05, C.muted],
];
const COMP_ORDER = Object.fromEntries(COMPS.map(([c], i) => [c, i]));
const TINT = 0.45; // a stance tile's tint: the most that keeps its label at 4.5:1 in both themes
const ramp = (v: number) => 0.08 + 0.67 * Math.max(0, Math.min(1, v / 100)); // index tiles, orange; text holds to 0.79
const swatch = (base: string, a: number) => `color-mix(in srgb, ${base} ${Math.round(a * 100)}%, ${C.surface})`;

const money = (v: number) => `$${v.toLocaleString("en-US", { minimumFractionDigits: 1, maximumFractionDigits: 1 })}B`;
const share = (v: number) => `${Math.round(v * 100)}%`;
const amt = (r: (typeof D.investments)[number]) => Number(r.amount_b ?? 0);
const COUNTED = D.investments.filter((r) => r.counted === "Yes");
const STATE_DOLLARS = COUNTED.reduce<Record<string, number>>((m, r) => ({ ...m, [r.abbr]: (m[r.abbr] ?? 0) + amt(r) }), {});

function tally(rows: Race[]) {
  const c = rows.filter((r) => r.result !== "Uncalled");
  const n = (f: (r: Race) => boolean) => c.filter(f).length;
  const limit = (r: Race) => r.dc_stance === "Moratorium" || r.dc_stance === "Make them pay";
  return {
    called: c.length, flips: n((r) => r.result === "Flip"), uncalled: rows.filter((r) => r.result === "Uncalled").map((r) => r.state),
    moratorium: n((r) => r.dc_stance === "Moratorium"), pay: n((r) => r.dc_stance === "Make them pay"), limit: n(limit),
    supportive: n((r) => r.dc_stance === "Supportive"), dcNone: n((r) => r.dc_stance === "No clear record"),
    aiReg: n((r) => r.ai_stance === "Stronger regulation"), aiNone: n((r) => r.ai_stance === "No clear record"),
    dLimit: n((r) => r.party === "D" && limit(r)), d: n((r) => r.party === "D"),
    rLimit: n((r) => r.party === "R" && limit(r)), r: n((r) => r.party === "R"),
  };
}
const T: Record<Office, ReturnType<typeof tally>> = { senate: tally(D.senate), gov: tally(D.governors) };

const CATS = [...DC.map(([s]) => s), "Not yet called", "No 2026 race"];
const CAT_SEG = (cat: string): Omit<Seg, "value"> =>
  cat === "Not yet called" ? { name: cat, color: C.muted, dashed: true } : cat === "No 2026 race" ? { name: cat, color: C.muted2 } : { name: cat, color: color("dc", cat) };

/** Each company's counted dollars split by the data center stance of the state's new officeholder. */
function exposure(rows: Race[]) {
  const stanceOf = new Map(rows.map((w) => [w.abbr, w.result === "Uncalled" ? "Not yet called" : w.dc_stance]));
  const by = new Map<string, Record<string, number>>();
  for (const r of COUNTED) {
    const cat = stanceOf.get(r.abbr) ?? "No 2026 race";
    const v = by.get(r.company) ?? Object.fromEntries(CATS.map((c) => [c, 0]));
    v[cat] += amt(r);
    by.set(r.company, v);
  }
  const companies = [...by.entries()].map(([company, v]) => {
    const total = CATS.reduce((s, c) => s + v[c], 0), limit = v.Moratorium + v["Make them pay"];
    return { company, v, total, limit, share: total ? limit / total : 0 };
  }).sort((a, b) => b.total - a.total);
  const sum = (f: (c: (typeof companies)[number]) => number) => companies.reduce((s, c) => s + f(c), 0);
  const total = sum((c) => c.total), limit = sum((c) => c.limit);
  return { companies, total, limit, share: total ? limit / total : 0, uncalled: sum((c) => c.v["Not yet called"]), norace: sum((c) => c.v["No 2026 race"]) };
}
const X: Record<Office, ReturnType<typeof exposure>> = { senate: exposure(D.senate), gov: exposure(D.governors) };

const poll = (chart: string) => D.polls.filter((r) => r.chart === chart).sort((a, b) => a.order - b.order);
const callout = (group: string) => D.polls.find((r) => r.chart === "callout" && r.group === group)!;
const trend = [...new Set(poll("trend").map((r) => r.group))].map((name) => ({
  name, pts: poll("trend").filter((r) => r.group === name).map((r) => ({ m: month(r.item), v: r.pct, note: r.source_type })).sort((a, b) => a.m - b.m),
}));
const EXIT_AI = poll("exit").find((r) => r.item === "AI and data centers")!;
const TOP_MONEY = Object.entries(STATE_DOLLARS).sort((a, b) => b[1] - a[1])[0];

const find = (rows: Cell[][], q: string) => (q ? rows.filter((r) => r.some((c) => String(typeof c === "object" ? c.v : c).toLowerCase().includes(q.toLowerCase()))) : rows);
const link = (url: string, text = "Link"): Cell => (/^https?:\/\//.test(url) ? { v: text, href: url } : url);

type Mark = [string, string, ("dashed" | "hollow")?];
/** The page's legend: a filled swatch per item, or a dashed outline / hollow ring for marks drawn that way. */
function Key({ items }: { items: Mark[] }) {
  return (
    <div className="flex flex-wrap gap-x-3.5 gap-y-1 text-xs text-text-2 mb-2">
      {items.map(([n, c, mark]) => (
        <span key={n} className="flex items-center gap-1.5">
          <i aria-hidden className={`inline-block w-2.5 h-2.5 ${mark === "hollow" ? "rounded-full border-[1.5px]" : "rounded-sm"} ${mark === "dashed" ? "border border-dashed" : ""}`}
            style={mark ? { borderColor: c } : { background: c }} />
          {n}
        </span>
      ))}
    </div>
  );
}

function Search({ value, onChange, label }: { value: string; onChange: (v: string) => void; label: string }) {
  return (
    <input type="search" value={value} onChange={(e) => onChange(e.target.value)} aria-label={label} placeholder={label}
      className="mb-2 w-full max-w-xs rounded-md border border-border bg-surface px-2.5 py-1.5 text-[13px] text-text placeholder:text-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent" />
  );
}

function Pick({ label, value, options, onChange }: { label: string; value: string; options: [string, string][]; onChange: (v: string) => void }) {
  return (
    <label className="inline-flex items-center gap-2 text-xs text-muted">
      {label}
      <select value={value} onChange={(e) => onChange(e.target.value)}
        className="rounded-md border border-border bg-surface px-2 py-1 text-[13px] text-text focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent">
        {options.map(([v, t]) => <option key={v} value={v}>{t}</option>)}
      </select>
    </label>
  );
}

/** A table behind a disclosure, with a search box above it. */
function Sourced({ summary, caption, head, rows, cols, search }: { summary: string; caption: string; head: string[]; rows: Cell[][]; cols?: string[]; search: string }) {
  const [q, setQ] = useState("");
  return (
    <details className="mt-4">
      <summary className="cursor-pointer text-[13px] font-semibold text-text hover:text-accent rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent">{summary}</summary>
      <div className="mt-2">
        <Search value={q} onChange={setQ} label={search} />
        <Table caption={caption} head={head} rows={find(rows, q)} left={head.length} cols={cols} tall />
      </div>
    </details>
  );
}

const OfficeSwitch = ({ office, set }: { office: Office; set: (o: Office) => void }) => (
  <Segmented label="Office" value={office} onChange={set} options={[["senate", "Senate"], ["gov", "Governors"]]} />
);

function ShortAnswer() {
  const s = T.senate, g = T.gov, top = SC[0], bottom = SC[SC.length - 1];
  const opp = poll("trend").filter((r) => r.group === trend[0].name);
  const findings: ReactNode[] = [
    <><b>Winners lean toward limits.</b> <b>{s.limit} of the {s.called}</b> called Senate winners want to pause data centers or make them pay their own power and grid costs, against <b>{s.supportive}</b> who are openly supportive. Among governors it is <b>{g.limit} of {g.called}</b>, against <b>{g.supportive}</b>.</>,
    <><b>It is mostly a Democratic position.</b> <b>{s.dLimit} of {s.d}</b> Democratic Senate winners back a pause or make-pay, against <b>{s.rLimit} of {s.r}</b> Republicans; for governors, <b>{g.dLimit} of {g.d}</b> Democrats and <b>{g.rLimit} of {g.r}</b> Republicans.</>,
    <><b>AI rules split the same way, more quietly.</b> <b>{s.aiReg}</b> Senate winners back stronger AI regulation; <b>{s.aiNone}</b> have no clear public AI record.</>,
    <><b>Much of the money sits where winners want limits.</b> <b>{money(X.senate.limit)} of {money(X.senate.total)}</b> in data center investment announced since January 2024 (<b>{share(X.senate.share)}</b>) is in states whose new senator wants a pause or make-pay; by new governor, <b>{share(X.gov.share)}</b>.</>,
    <><b>Rules, not bans.</b> No state has a statewide moratorium in effect; <b>{S.moratorium_pending}</b> have one proposed or partial. Power rules drive most of the restriction: <b>{S.tariff_approved}</b> states have an approved large-load tariff and <b>{S.cost_alloc}</b> a mandatory rule making data centers bear their own grid costs. {top.name} ranks most restrictive (<b>{top.composite.toFixed(1)}</b>), {bottom.name} least (<b>{bottom.composite.toFixed(1)}</b>).</>,
    <><b>Strict rules haven't kept the money away.</b> The most announced money, <b>{money(TOP_MONEY[1])} in {NAMES[TOP_MONEY[0]]}</b>, went to a state ranked <b>{SC.find((r) => r.state === TOP_MONEY[0])!.rank} of 50</b> for restrictiveness.</>,
    <><b>The public has turned against local builds.</b> In {trend[0].name}'s polls, opposition to a nearby data center rose from <b>{opp[0].pct}%</b> to <b>{opp[opp.length - 1].pct}%</b>, and <b>{EXIT_AI.pct}%</b> of voters called AI and data centers a crucial or major factor in their vote for Congress (NBC exit poll, news summary).</>,
  ];
  return (
    <Card id="findings" eyebrow="The short answer" title="A backlash in the winners and the polls, not yet in the law">
      <div className="grid gap-5 lg:grid-cols-[1fr_340px]">
        <ol className="list-decimal pl-5 grid gap-2 text-[13.5px] leading-[21px] text-text-2 marker:text-accent marker:font-semibold">
          {findings.map((f, i) => <li key={i}>{f}</li>)}
        </ol>
        <div className="grid gap-3 grid-cols-2 content-start">
          <Tile label="Senate winners for limits" value={`${s.limit} of ${s.called}`} sub="Want a pause, or data centers to pay their own costs" />
          <Tile label="Governor winners for limits" value={`${g.limit} of ${g.called}`} sub="Same test, 2026 governor races" />
          <Tile label="Money in limit states" value={share(X.senate.share)} sub={`Of ${money(X.senate.total)} announced, by new senator's stance`} />
          <Tile label="Index, national median" value={S.median.toFixed(1)} sub="0 = fewest rules and costs, 100 = most restrictive" />
        </div>
      </div>
    </Card>
  );
}

function raceRows(office: Office): Cell[][] {
  const rank: Record<string, number> = { Flip: 0, Hold: 1, Uncalled: 2 };
  return [...RACES[office]].sort((a, b) => rank[a.result] - rank[b.result] || a.state.localeCompare(b.state)).map((r) => [
    r.state, r.winner, r.party, ...(office === "gov" ? [r.opponent ?? ""] : []), r.result, r.newcomer,
    r.dc_stance, r.dc_summary, r.ai_stance, r.ai_summary, link(r.source_1, "Source 1"), link(r.source_2, "Source 2"),
    ...(office === "gov" ? [link(r.results_source ?? "", "Result")] : []),
  ]);
}

function Winners({ office, setOffice }: { office: Office; setOffice: (o: Office) => void }) {
  const [topic, setTopic] = useState<"dc" | "ai">("dc");
  const t = T[office], rows = RACES[office];
  const cells: Record<string, TileCell> = Object.fromEntries(rows.map((r) => {
    const stance = topic === "dc" ? r.dc_stance : r.ai_stance, open = r.result === "Uncalled";
    return [r.abbr, {
      fill: open ? C.surface : color(topic, stance), tint: open ? 0 : TINT, edge: open ? C.muted : color(topic, stance), dashed: open, dot: r.newcomer === "Yes",
      tip: {
        title: `${r.state} ${WHO[office]} · ${open ? "not yet called" : `${r.result === "Flip" ? "flipped" : "held"} · ${r.party}`}`,
        lines: [r.winner, `${topic === "dc" ? "Data centers" : "AI policy"}: ${stance}`, topic === "dc" ? r.dc_summary : r.ai_summary],
      },
    }];
  }));
  const head = ["State", "Winner", "Party", ...(office === "gov" ? ["Opponent"] : []), "Result", "New to seat", "Data centers", "What they've said or done", "AI policy", "What they've said or done", "Source", "Source", ...(office === "gov" ? ["Result source"] : [])];
  const wide = head.map((h) => (h.startsWith("What") ? "min-w-[16rem]" : ""));
  return (
    <Chapter id="winners" n="01" tag="THE WINNERS" question="Where does each new senator and governor stand?"
      sentence={`**${t.limit} of the ${t.called}** called ${WHO[office]} winners want to pause data centers or make them pay their own power and grid costs; **${t.supportive}** are openly supportive. **${t.aiReg}** back stronger AI regulation, and **${t.aiNone}** have no clear public AI record.`}
      note={<>Results as projected on Nov 4, 2026; still uncalled: {t.uncalled.join(" and ")}. Governor results are AP calls as compiled by MultiState and network projections. Stances come from campaign plans, Senate votes and statements, and news coverage, 2025–2026.</>}>
      <div className="grid gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <OfficeSwitch office={office} set={setOffice} />
          <Segmented label="Map shows" value={topic} onChange={setTopic} options={[["dc", "Data centers"], ["ai", "AI policy"]]} />
        </div>
        <Key items={[...(topic === "dc" ? DC : AI).map(([n, c]): Mark => [n, swatch(c, TINT)]), ["Not yet called", C.muted, "dashed"], ["No race this year", C.grid]]} />
        <TileMap cells={cells} label={`Tile map of the 2026 ${WHO[office]} winners by state, colored by their ${topic === "dc" ? "data center" : "AI policy"} stance. A dot marks someone new to the office.`} />
        <Note>Each square is a state; hover or use the arrow keys for the winner and their position. A dot marks someone new to the office.</Note>
        <div className="grid gap-3 grid-cols-2 sm:grid-cols-3 xl:grid-cols-6 mt-1">
          <Tile label={office === "senate" ? "Seats called" : "Governorships called"} value={String(t.called)} sub={`${t.uncalled.length} still uncalled`} />
          <Tile label="Flipped to Democrats" value={String(t.flips)} sub="Seats that changed party" />
          <Tile label="Back a moratorium" value={String(t.moratorium)} sub="Pause new builds" />
          <Tile label="Make them pay" value={String(t.pay)} sub="Own power and grid costs, no pause" />
          <Tile label="Supportive" value={String(t.supportive)} sub="Promote building them" />
          <Tile label="No clear record" value={String(t.dcNone)} sub="No sourced position found" />
        </div>
        <Sourced summary={`Every ${WHO[office]} race, with sources`} caption={`Every 2026 ${WHO[office]} race with the winner's stances and sources`}
          head={head} rows={raceRows(office)} cols={wide} search="Search name, state or stance" />
      </div>
    </Chapter>
  );
}

function ByParty({ office }: { office: Office }) {
  const t = T[office], c = RACES[office].filter((r) => r.result !== "Uncalled");
  const bars = (kind: "dc" | "ai") => (kind === "dc" ? DC : AI).map(([name, col]) => ({
    name, color: col, D: c.filter((r) => r.party === "D" && (kind === "dc" ? r.dc_stance : r.ai_stance) === name).length,
    R: c.filter((r) => r.party === "R" && (kind === "dc" ? r.dc_stance : r.ai_stance) === name).length,
  }));
  const rTop = [...bars("dc")].sort((a, b) => b.R - a.R).slice(0, 2).map((b) => `${b.name.toLowerCase()} (${b.R})`);
  return (
    <Chapter id="party" n="02" tag="BY PARTY" question="Is it a party split?"
      sentence={`Mostly. **${t.dLimit} of ${t.d}** Democratic ${WHO[office]} winners back a pause or make-pay, against **${t.rLimit} of ${t.r}** Republicans, whose most common answers are ${rTop.join(" and ")}.`}
      note={`Winners in called ${WHO[office]} races. Switch between Senate and governors in chapter 01.`}>
      <Two>
        <Box title="Data center stance by party">
          <PartyBars rows={bars("dc")} label={`Data center stance of ${WHO[office]} winners by party: ${bars("dc").map((b) => `${b.name} ${b.D} Democrats, ${b.R} Republicans`).join("; ")}.`} />
        </Box>
        <Box title="AI policy stance by party">
          <PartyBars rows={bars("ai")} label={`AI policy stance of ${WHO[office]} winners by party: ${bars("ai").map((b) => `${b.name} ${b.D} Democrats, ${b.R} Republicans`).join("; ")}.`} />
        </Box>
      </Two>
    </Chapter>
  );
}

const COMPANIES = [...new Set(D.investments.map((r) => r.company))];

function Exposure({ office, setOffice }: { office: Office; setOffice: (o: Office) => void }) {
  const [co, setCo] = useState("");
  const x = X[office], winners = new Map(RACES[office].map((w) => [w.abbr, w]));
  const rows = COUNTED.filter((r) => !co || r.company === co);
  const byState = rows.reduce<Record<string, Record<string, number>>>((m, r) => {
    m[r.abbr] = { ...m[r.abbr], [r.company]: (m[r.abbr]?.[r.company] ?? 0) + amt(r) };
    return m;
  }, {});
  const totals = Object.fromEntries(Object.entries(byState).map(([st, v]) => [st, Object.values(v).reduce((a, b) => a + b, 0)]));
  const max = Math.max(1, ...Object.values(totals));
  const cells: Record<string, TileCell> = Object.fromEntries(Object.entries(NAMES).map(([st, name]) => {
    const w = winners.get(st), v = totals[st] ?? 0;
    const who = !w ? `No 2026 ${WHO[office]} race` : w.result === "Uncalled" ? `${WHO[office]} race not yet called` : `${office === "senate" ? "Senate" : "Governor"}: ${w.winner} (${w.party}) · ${w.dc_stance}`;
    return [st, {
      fill: C.jobs, tint: v ? 0.1 + 0.55 * Math.sqrt(v / max) : 0, edge: v ? undefined : C.border, sub: v ? `$${Math.round(v)}B` : undefined,
      stripe: !w || w.result === "Uncalled" ? undefined : color("dc", w.dc_stance),
      tip: {
        title: `${name}: ${v ? `${money(v)} announced${co ? ` by ${co}` : ""}` : `no counted announcements${co ? ` by ${co}` : ""}`}`,
        lines: [who, ...(!co && v ? Object.entries(byState[st]).sort((a, b) => b[1] - a[1]).map(([c, a]) => `${c}: ${money(a)}`) : [])],
      },
    }];
  }));
  const invRows: Cell[][] = D.investments.filter((r) => !co || r.company === co)
    .sort((a, b) => (a.counted === b.counted ? 0 : a.counted === "Yes" ? -1 : 1) || amt(b) - amt(a))
    .map((r) => [r.id, r.company, r.state, r.site, r.amount_b == null ? "" : String(r.amount_b), r.counted, r.announced, r.status, r.note, link(r.source_url, r.publisher)]);
  return (
    <Chapter id="exposure" n="03" tag="COMPANY EXPOSURE" question="How much company money sits where winners want limits?"
      sentence={`**${money(x.limit)} of ${money(x.total)}** in data center investment announced since January 2024 sits in states whose 2026 ${WHO[office]} winner wants a pause or wants data centers to pay their own costs: **${share(x.share)}** of the total.`}
      note="Dollar figures as announced by each company or a state or local official, Jan 2024 – Nov 2026. Superseded, cancelled, land-only, lease-value and multi-state figures are listed in the table but not counted. The list is a floor: some announcements gave no dollar figure.">
      <div className="grid gap-5">
        <div className="flex flex-wrap items-center gap-2"><OfficeSwitch office={office} set={setOffice} /></div>
        <div className="grid gap-3 grid-cols-2 sm:grid-cols-3 xl:grid-cols-5">
          <Tile label="Announced, counted" value={money(x.total)} sub={`${COUNTED.length} announcements`} />
          <Tile label="In pause / make-pay states" value={money(x.limit)} sub={`${share(x.share)} of the total`} />
          <Tile label="In uncalled races" value={money(x.uncalled)} sub={T[office].uncalled.join(", ")} />
          <Tile label={`No 2026 ${WHO[office]} race`} value={money(x.norace)} sub="Officeholders there aren't shown" />
          <Tile label="Largest single state" value={money(TOP_MONEY[1])} sub={NAMES[TOP_MONEY[0]]} />
        </div>
        <Box title={`Each company's announced dollars, by the stance of the new ${WHO[office]} winner`}>
          <Key items={CATS.map((c): Mark => (c === "Not yet called" ? [c, C.muted, "dashed"] : [c, CAT_SEG(c).color]))} />
          <StackRows labelW={124} label={`Announced dollars per company split by the stance of each state's new ${WHO[office]} winner; the share in pause or make-pay states follows each bar.`}
            rows={x.companies.map((c) => ({
              name: c.company, end: `${money(c.total)} · ${share(c.share)}`,
              segs: CATS.map((cat) => ({ ...CAT_SEG(cat), value: c.v[cat] })),
              tip: { title: c.company, lines: [`${money(c.total)} counted, ${share(c.share)} in pause or make-pay states`, ...CATS.filter((cat) => c.v[cat] > 0).map((cat) => `${cat}: ${money(c.v[cat])}`)] },
            }))} />
          <Note>The percentage after each bar is the share in pause or make-pay states.</Note>
        </Box>
        <Box title="Announced dollars by state">
          <div className="mb-2"><Pick label="Company" value={co} onChange={setCo} options={[["", "All companies"], ...COMPANIES.map((c): [string, string] => [c, c])]} /></div>
          <TileMap cells={cells} label={`Tile map of announced data center dollars by state${co ? ` for ${co}` : ""}; darker squares hold more, and the stripe along the bottom is the ${WHO[office]} winner's data center stance.`} />
          <Note>Darker squares hold more announced dollars. The stripe along the bottom of each square is the data center stance of the 2026 {WHO[office]} winner (colors as in chapter 01); no stripe means no 2026 race or a race not yet called.</Note>
        </Box>
        <Sourced summary="Every announcement, with sources" caption="Every announced data center investment with its source and whether it is counted"
          head={["#", "Company", "State", "Site", "$ billions", "Counted", "Announced", "Status", "Note", "Source"]} rows={invRows}
          cols={["", "", "", "min-w-[10rem]", "", "", "", "", "min-w-[14rem]", "min-w-[8rem]"]} search="Search site, state or note" />
      </div>
    </Chapter>
  );
}

const pickState = (st: string, set: (s: string) => void) => {
  set(st);
  const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  document.getElementById("state")?.scrollIntoView({ behavior: reduce ? "auto" : "smooth", block: "start" });
};

function Index({ onPick, picked }: { onPick: (st: string) => void; picked: string }) {
  const [comp, setComp] = useState("composite");
  const top = SC[0], bottom = SC[SC.length - 1];
  const cells: Record<string, TileCell> = Object.fromEntries(SC.map((r) => {
    const v = Number(r[comp]);
    return [r.state, {
      fill: C.inflation, tint: ramp(v), sub: v.toFixed(0),
      tip: { title: `${r.name} · rank ${r.rank} of ${SC.length}`, lines: [`Composite ${r.composite.toFixed(1)}`, ...COMPS.map(([c]) => `${c}: ${Number(r[c]).toFixed(0)}`)] },
    }];
  }));
  return (
    <Chapter id="index" n="04" tag="THE INDEX" question="How hard is it to build in each state?"
      sentence={`On a 0 (fewest rules and costs) to 100 (most restrictive) scale, **${top.name} ranks most restrictive at ${top.composite.toFixed(1)}** and ${bottom.name} least at ${bottom.composite.toFixed(1)}; the national median is **${S.median.toFixed(1)}**. No state has a statewide moratorium in effect; power rules drive most of the restriction.`}
      note={<>Weighted composite of six components: Power 30%, Permitting 25%, Tax 15%, Environment 15%, Operating rules 10%, Administration 5%. Each component averages rubric-scored indicators from PUC dockets, statutes, executive orders, agency rules and reporting. Newest source: {S.newest_source}.</>}>
      <div className="grid gap-5">
        <div className="grid gap-3 grid-cols-2 sm:grid-cols-3">
          <Tile label="Statewide moratorium in effect" value={String(S.moratorium_now)} sub="States" />
          <Tile label="Statewide pause proposed or partial" value={String(S.moratorium_pending)} sub="States" />
          <Tile label="Large-load tariff approved" value={String(S.tariff_approved)} sub="States" />
          <Tile label="Mandatory cost-allocation rule" value={String(S.cost_alloc)} sub="Data centers bear their own grid costs" />
          <Tile label="Rows from primary or reputable sources" value={share(S.confident_share)} sub={`The rest are low confidence, mostly "no rule found"`} />
          <Tile label="Unscored indicators" value={String(S.unscored)} sub={`Of ${S.rows.toLocaleString("en-US")}; left out of averages`} />
        </div>
        <Box title="Index by state">
          <div className="mb-2"><Pick label="Show" value={comp} onChange={setComp}
            options={[["composite", "Composite index"], ...COMPS.map(([c, w]): [string, string] => [c, `${c} (${w * 100}%)`])]} /></div>
          <Key items={[0, 25, 50, 75, 100].map((v): Mark => [v === 0 ? "0 least restrictive" : v === 100 ? "100 most restrictive" : String(v), swatch(C.inflation, ramp(v))])} />
          <TileMap cells={cells} selected={picked} onPick={onPick}
            label={`Tile map of ${comp === "composite" ? "the composite regulatory index" : `the ${comp} component`} by state; darker squares are more restrictive. Click or press Enter on a state for every indicator behind its score.`} />
          <Note>Darker squares are more restrictive. Click a state, or press Enter on it, to see every indicator behind its score below.</Note>
        </Box>
        <Box title="All 50 states, ranked">
          <Key items={COMPS.map(([c, , col]): Mark => [c, col])} />
          <StackRows labelW={48} rowH={18} max={100} ticks={[0, 25, 50, 75, 100]} onPick={onPick} selected={picked}
            label="States ranked by composite regulatory index, each bar split into what each weighted component contributes."
            rows={SC.map((r) => ({
              key: r.state, name: `${r.rank}. ${r.state}`, end: r.composite.toFixed(1),
              segs: COMPS.map(([c, w, col]) => ({ name: c, value: Number(r[c]) * w, color: col })),
              tip: { title: `${r.rank}. ${r.name} · ${r.composite.toFixed(1)}`, lines: COMPS.map(([c, w]) => `${c} ${Number(r[c]).toFixed(0)} × ${w * 100}% = ${(Number(r[c]) * w).toFixed(1)}`) },
            }))} />
          <Note>Each bar is the composite score, split into what each weighted component contributes.</Note>
        </Box>
      </div>
    </Chapter>
  );
}

function MoneyVsRules({ onPick }: { onPick: (st: string) => void }) {
  const pts = SC.map((r) => ({
    st: r.state, x: r.composite, y: STATE_DOLLARS[r.state] ?? 0,
    tip: { title: r.name, lines: [`Index ${r.composite.toFixed(1)} · rank ${r.rank}`, `${money(STATE_DOLLARS[r.state] ?? 0)} announced, counted`] },
  }));
  const above = pts.filter((p) => p.x > S.median), withMoney = pts.filter((p) => p.y > 0);
  const aboveMoney = above.reduce((s, p) => s + p.y, 0), all = pts.reduce((s, p) => s + p.y, 0);
  const [first, ...next] = [...withMoney].sort((a, b) => b.y - a.y).slice(0, 3).map((p) => SC.find((r) => r.state === p.st)!);
  return (
    <Chapter id="money" n="05" tag="MONEY VS RULES" question="Is the money avoiding the strict states?"
      sentence={`Not overall. States scoring above the national median hold **${money(aboveMoney)} of ${money(all)}** announced (**${share(aboveMoney / all)}**), and ${first.name}, the biggest destination, ranks **${first.rank} of 50**. The next two, ${next.map((r) => `${r.name} (${r.rank})`).join(" and ")}, sit among the least restrictive.`}
      note={`Each dot is a state: index score across, announced and counted data center dollars up (Jan 2024 – Nov 2026, all companies). ${withMoney.length} states have counted announcements; the rest sit on the floor. Announcements trail rule changes, so this shows where money went, not how rules steer it.`}>
      <IndexScatter points={pts} median={S.median} onPick={onPick}
        label={`Index score against announced data center dollars for each state; the dashed line is the national median of ${S.median.toFixed(1)}.`} />
    </Chapter>
  );
}

function StateDetail({ picked, onPick }: { picked: string; onPick: (st: string) => void }) {
  const [ev, setEv] = useState<Ev[] | null>(null);
  useEffect(() => {
    // the 1,000 evidence rows are their own chunk, fetched only when this chapter mounts
    import("@/components/dashboards/dcRegulation/evidence.json").then((m) => setEv(m.default as Ev[]));
  }, []);
  const r = SC.find((x) => x.state === picked) ?? SC[0];
  const rows = useMemo(() => (ev ?? []).filter((e) => e.state === r.state)
    .sort((a, b) => COMP_ORDER[IND[a.indicator][1]] - COMP_ORDER[IND[b.indicator][1]]), [ev, r.state]);
  const top = rows.filter((e) => e.level === 100).map((e) => IND[e.indicator][0]);
  return (
    <Chapter id="state" n="06" tag="STATE DETAIL" question={`${r.name}: ${r.composite.toFixed(1)}, rank ${r.rank} of ${SC.length}`}
      sentence={top.length ? `Scored at the most restrictive level on **${top.length}** of 20 indicators: ${top.join(", ")}.` : "No indicator is at the most restrictive level."}
      note={<>Every indicator for the selected state: the rubric level (0–100), what was found, and the source. "Pending" flags bills, dockets or pledges that could change the score. {r.n_pending} pending here.</>}>
      <div className="grid gap-4">
        <Pick label="State" value={r.state} onChange={onPick}
          options={[...SC].sort((a, b) => a.name.localeCompare(b.name)).map((x): [string, string] => [x.state, `${x.name} (${x.composite.toFixed(1)})`])} />
        <Box title="Component scores, 0–100">
          <RowBars series={[["Score", C.muted]]} fmt={(v) => v.toFixed(0)} label={`${r.name}'s six component scores: ${COMPS.map(([c]) => `${c} ${Number(r[c]).toFixed(0)}`).join(", ")}.`}
            rows={COMPS.map(([c, w, col]) => ({ name: `${c} (${w * 100}%)`, values: [Number(r[c])], color: col, tip: { title: `${r.name} · ${c}`, lines: [`Score ${Number(r[c]).toFixed(0)} of 100`, `Adds ${(Number(r[c]) * w).toFixed(1)} to the composite`] } }))} />
        </Box>
        {ev ? (
          <Table caption={`Every indicator behind ${r.name}'s score`} tall left={8}
            head={["Component", "Indicator", "Level", "What we found", "Pending", "Confidence", "Source date", "Link"]}
            cols={["", "", "", "min-w-[18rem]", "min-w-[10rem]", "", "", ""]}
            rows={rows.map((e) => [IND[e.indicator][1], IND[e.indicator][0], e.level == null ? "unscored" : String(e.level), e.evidence, e.pending, e.confidence, e.source_date, link(e.source_url)])} />
        ) : <p className="text-sm text-muted">Loading the evidence…</p>}
      </div>
    </Chapter>
  );
}

function Opinion() {
  const local = [...new Set(poll("local").map((r) => r.group))].map((group) => {
    const v = poll("local").filter((r) => r.group === group), meta = v[0];
    const oppose = v.find((r) => r.item === "Oppose")?.pct ?? 0, support = v.find((r) => r.item === "Support")?.pct;
    return { group, oppose, support, meta };
  });
  const impacts = [...new Set(poll("impacts").map((r) => r.item))].map((item) => ({
    item, jan: poll("impacts").find((r) => r.item === item && r.group === "Jan 2026")!.pct, aug: poll("impacts").find((r) => r.item === item && r.group === "Aug 2026")!.pct,
  }));
  const COMFORT: [string, string, string][] = [["Extremely/very comfortable", "Very comfortable", C.jobs], ["Somewhat comfortable", "Somewhat", C.ai],
    ["Not too/not at all comfortable", "Not comfortable", C.danger], ["Haven't heard of data centers", "Haven't heard of them", C.muted]];
  const party = [...new Set(poll("party").map((r) => r.group))].map((group) => ({ group, v: COMFORT.map(([item]) => poll("party").find((r) => r.group === group && r.item === item)?.pct ?? 0) }));
  const tiles: [string, string, string][] = [["bills", "Expect a local data center to raise their electric bill", "Economist / YouGov, Aug 2026"],
    ["env_great", "Worry a great deal about data centers' environmental impact", `Gallup, Mar 2026 (another ${callout("env_fair").pct}% a fair amount)`],
    ["slower", "Want construction slowed to address concerns", `Fox News, Jul 2026 ("nearly 8 in 10")`],
    ["ai_reg", "Say government isn't doing enough to regulate AI", "NBC News Decision Desk, Aug 2026 (news summary)"]];
  const opp = trend[0].pts;
  return (
    <Chapter id="opinion" n="07" tag="PUBLIC OPINION" question="What does the public think?"
      sentence={`Opposition to a nearby data center is now the majority view in every poll here, and it has climbed: **${opp[0].v}% to ${opp[opp.length - 1].v}%** in ${trend[0].name}'s repeated polls. Discomfort crosses party lines.`}
      note="National polls, 2025–2026. Question wording, populations and answer options differ between pollsters, so compare within a chart rather than across them. Rows marked as news summaries could not be checked against the pollster's own release.">
      <div className="grid gap-5">
        <div className="grid gap-3 grid-cols-2 xl:grid-cols-4">
          {tiles.map(([g, label, sub]) => <Tile key={g} label={label} value={`${callout(g).pct}%`} sub={sub} />)}
        </div>
        <Box title="Would you want a data center in your area?">
          <Key items={[["Oppose", C.danger], ["Support", C.jobs], ["Neither / not sure / not published", C.grid]]} />
          <StackRows above labelW={0} max={100} ticks={[0, 25, 50, 75, 100]} label="Share opposing and supporting a data center built locally, by poll."
            rows={local.map((r) => ({
              name: r.group, end: `${r.oppose}%`,
              segs: [{ name: "Oppose", value: r.oppose, color: C.danger }, { name: "Rest", value: 100 - r.oppose - (r.support ?? 0), color: C.grid }, { name: "Support", value: r.support ?? 0, color: C.jobs }],
              tip: { title: `${r.meta.pollster} · ${r.meta.fielded}`, lines: [`Oppose: ${r.oppose}%`, r.support == null ? "Support: not published" : `Support: ${r.support}%`, r.meta.population, r.meta.question, r.meta.source_type] },
            }))} />
          <Note>The figure after each bar is the share opposed.</Note>
        </Box>
        <Two>
          <Box title="Local opposition has climbed since 2025">
            <TrendLines series={trend.map((s, i) => ({ ...s, color: i ? C.ai : C.danger }))} label={`Share opposing a nearby data center: ${trend.map((s) => `${s.name} from ${s.pts[0].v}% to ${s.pts[s.pts.length - 1].v}%`).join("; ")}.`} />
            <Note>Embold / Heatmap (registered voters) and Emerson (likely voters).</Note>
          </Box>
          <Box title="What people think data centers harm">
            <Key items={[["Jan 2026", C.danger, "hollow"], ["Aug 2026", C.danger]]} />
            <Dots rows={impacts.map((r) => ({ name: r.item, from: r.jan, to: r.aug, tip: { title: r.item, lines: [`Jan 2026: ${r.jan}%`, `Aug 2026: ${r.aug}%`] } }))}
              fmt={(v) => `${v}%`} color={C.danger} label={`Pew: share saying data centers are mostly bad for each area, January vs August 2026: ${impacts.map((r) => `${r.item} ${r.jan}% to ${r.aug}%`).join(", ")}.`} />
            <Note>Pew: share saying data centers are mostly bad for each area.</Note>
          </Box>
        </Two>
        <Two>
          <Box title="Discomfort crosses party lines">
            <Key items={COMFORT.map(([, n, c]): Mark => [n, c])} />
            <StackRows labelW={110} max={100} label="Pew, July–August 2026: how comfortable people would be with a new data center in their area, by party."
              rows={party.map((p) => ({
                name: p.group, end: `${p.v[2]}%`, segs: COMFORT.map(([item, , c], k) => ({ name: item, value: p.v[k], color: c })),
                tip: { title: `Pew · ${p.group}`, lines: COMFORT.map(([, n], k) => `${n}: ${p.v[k]}%`) },
              }))} />
            <Note>Pew, Jul–Aug 2026; the figure after each bar is the share not comfortable. Gallup's share who strongly oppose a local AI data center: {poll("strong").map((r) => `${r.group} ${r.pct}%`).join(", ")}.</Note>
          </Box>
          <Box title="How much it mattered at the ballot box">
            <RowBars series={[["Crucial or major factor", C.muted]]} fmt={(v) => `${v}%`}
              label={`NBC News exit poll: share calling each issue a crucial or major factor in their vote for Congress: ${poll("exit").map((r) => `${r.item} ${r.pct}%`).join(", ")}.`}
              rows={poll("exit").map((r) => ({ name: r.item, values: [r.pct], color: r.item === EXIT_AI.item ? C.danger : C.muted, tip: { title: r.item, lines: [`${r.pct}% crucial or major factor`] } }))} />
            <Note>NBC News exit poll, Nov 3, 2026 (news summary of the exit poll).</Note>
          </Box>
        </Two>
        <Sourced summary="Every poll figure, with sources" caption="Every poll figure with its pollster, question and source"
          head={["#", "Chart", "Pollster", "Fielded", "Population", "Question", "Group", "Answer / item", "%", "Source type", "Link"]}
          cols={["", "", "", "", "min-w-[10rem]", "min-w-[14rem]", "", "", "", "", ""]} search="Search pollster or question"
          rows={D.polls.map((r) => [r.id, r.chart, r.pollster, r.fielded, r.population, r.question, r.group, r.item, `${r.pct}%`, r.source_type, link(r.source_url)])} />
      </div>
    </Chapter>
  );
}

function Method() {
  return (
    <Card id="method" eyebrow="Method" title="How stances and the index were scored">
      <div className="grid gap-6 lg:grid-cols-2 text-[13px] leading-[20px] text-text-2">
        <ol className="list-decimal pl-5 grid gap-1.5">
          <li><b className="text-text">Data center stances:</b> <i>Moratorium</i> = called for pausing or stopping new construction. <i>Make them pay</i> = wants data centers to cover their own power, grid or water costs, or to lose tax breaks, without a pause. <i>Local control / mixed</i> = says communities should decide, or weighs benefits against costs. <i>Supportive</i> = promotes building them. <i>No clear record</i> = no sourced position found, which is not the same as no position.</li>
          <li><b className="text-text">AI policy:</b> <i>Stronger regulation</i> = new rules, a regulator, testing mandates or opposing a ban on state AI laws; <i>Light-touch</i> = emphasizing build-out and competing with China over new rules; <i>Mixed</i> = narrower or competing positions. Read from public records and news; some rest on a single source or aggregator summaries, and nothing was inferred from party.</li>
          <li><b className="text-text">Governors:</b> all 36 races classified the same way. Several governor-elect stances are campaign pledges rather than enacted policy; incumbents' records include signed bills and executive orders.</li>
          <li><b className="text-text">Exposure:</b> each company's announced US data center dollars (Jan 2024 – Nov 2026) are placed in the state where the site is and labeled with the data center stance of that state's 2026 winner. Only figures stated by the company, a state or local official, or the company's permit filings count; a later figure replaces an earlier one; Stargate sites are listed under OpenAI / Stargate rather than Oracle; "at least" figures count at their floor.</li>
          <li><b className="text-text">Regulatory index:</b> 20 indicators per state on a fixed rubric (allowed levels only, e.g. moratorium 0 / 25 / 60 / 100). A component is the average of its scored indicators; the composite is 0.30·Power + 0.25·Permitting + 0.15·Tax + 0.15·Environment + 0.10·Operating rules + 0.05·Administration. Governor-elect pledges count only as "proposed" levels; indicators with no source are left unscored.</li>
        </ol>
        <div>
          <h3 className="text-[15px] font-semibold text-text mb-1">Limits</h3>
          <ul className="list-disc pl-5 grid gap-1.5">
            <li>Only {share(S.confident_share)} of index rows come from primary documents or reputable secondary sources. Most of the rest are "no rule found" rows scored at the unrestricted level, so a low score partly reflects less evidence, not only fewer rules.</li>
            <li>Environment, Operating rules and backlog indicators are the thinnest: most research batches hit a search budget near the end.</li>
            <li>The weights were set by the study's author, not estimated from data; a check of the ranking under other weights has not been run. Within a component, every indicator counts the same.</li>
            <li>Dollar totals are a floor, and states with no 2026 race still have officeholders whose views aren't shown.</li>
            <li>Results are as projected on Nov 4, 2026; uncalled races may change the counts.</li>
          </ul>
        </div>
      </div>
    </Card>
  );
}

function Sources() {
  return (
    <Card id="sources" eyebrow="Sources" title="Where the figures come from">
      <ul className="grid gap-1 text-[13px] leading-[20px] text-muted max-w-4xl">
        <li>Every stance, announcement, index indicator and poll figure links its own source in the tables above.</li>
        <li>Election results: AP calls as compiled by MultiState, and network projections, Nov 3–4, 2026.</li>
        <li>Index indicators: state PUC dockets and orders, statutes, executive orders, agency rules, NCSL and trade press, researched in November 2026.</li>
        <li>Polls: Fox News, Gallup, Pew Research Center, Economist / YouGov, Embold / Heatmap, Emerson and the NBC News exit poll and Decision Desk.</li>
        <li>The study: <SourceLink title="AI data center regulatory index (GitHub)" url="https://github.com/ashcastelinocs124/spx-drawdown-risk-model" />, Nov 4, 2026 snapshot.</li>
      </ul>
    </Card>
  );
}

export default function DataCentersPage() {
  const [office, setOffice] = useState<Office>("senate");
  const [picked, setPicked] = useState(SC[0].state);
  const onPick = (st: string) => pickState(st, setPicked);
  return (
    <div className="grid gap-4">
      <PageIntro
        kicker="Dashboard · AI Data Centers & the 2026 Vote"
        title="Did the 2026 election turn against AI data centers?"
        steps={["Winners", "By party", "Company exposure", "Regulatory index", "Money vs rules", "Public opinion"]}
        when={{ label: "As of", value: "Nov 4, 2026", note: <span className="block">Results as projected; a fixed snapshot</span> }}
      >
        Where every 2026 Senate and governor winner stands on data centers and AI, how much announced company money sits in
        their states, a 50-state index of how hard it is to build and run a large AI data center, and what national polls show.
      </PageIntro>
      <ShortAnswer />
      <Winners office={office} setOffice={setOffice} />
      <ByParty office={office} />
      <Exposure office={office} setOffice={setOffice} />
      <Index onPick={onPick} picked={picked} />
      <MoneyVsRules onPick={onPick} />
      <StateDetail picked={picked} onPick={setPicked} />
      <Opinion />
      <Method />
      <Sources />
    </div>
  );
}
