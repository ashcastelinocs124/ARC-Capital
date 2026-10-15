"""Theme Charts agent: the single most popular macro theme right now, charted, once a day.

Code gathers three signal sets as facts (N: the macro themes news and financial X discuss most,
M: 1d/1w/1m market moves, P: Polymarket odds swings); one LLM call picks the theme and 6 charts (at
least 5 must pass the checks, or the retry is told why);
code fetches every series and draws it with the Weekly Deep Dive's renderer plus this page's own
forms (`theme_charts`: heatmap, scatter, range), so the LLM never supplies a plotted number. Each run is data/themes/<YYYY-MM-DD>-<am|pm>.json + its PNGs; each exhibit
also carries its plotted numbers (`data`), which /themes draws interactively. Run by deploy/crontab at 08:00 ET on weekdays: python -m castelino.agents.themes
The cron line then publishes the run on Substack (--substack) and, once the site is
redeployed, posts it to X as a thread linking that post (--post); no approval step for either.
"""

from __future__ import annotations

import json
import logging
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel

from castelino import x_post
from castelino.agents import theme_charts
from castelino.agents.base import StructuredAgent
from castelino.agents.update.charts import default_fetch
from castelino.agents.update.facts import facts_from_search
from castelino.agents.update.fsio import atomic_write_text
from castelino.agents.update.guard import unsupported
from castelino.agents.update.models import Fact
from castelino.agents.weekly.charts import default_series, make_weekly_exhibits
from castelino.agents.weekly.guard import _pick_errors
from castelino.agents.weekly.models import ExhibitPick
from castelino.agents.weekly.tools import series_fact
from castelino.config import get_settings

log = logging.getLogger(__name__)
ET = ZoneInfo("America/New_York")
SignalKind = Literal["coverage", "move", "odds"]
# A chart may fetch a series the signals didn't carry: "fred:T5YIE", "yahoo:BZ=F".
SERIES = re.compile(r"^(fred|yahoo):([A-Za-z0-9^=._-]{1,20})$")


class Signal(BaseModel):
    kind: SignalKind
    headline: str
    note: str


class ThemeChart(ExhibitPick):
    kind: Literal["line", "compare", "movers", "heatmap", "scatter", "range"]
    names: list[str]  # reader names for fact_ids, in order ("WTI crude", "10y yield")


class ThemePick(BaseModel):  # LLM output (closed schema: no defaults)
    theme: str
    why: str
    lead: SignalKind
    signals: list[Signal]
    same_as_last: bool
    fact_ids: list[str]
    charts: list[ThemeChart]


class ThemeExhibit(BaseModel):
    n: int
    kind: str
    title: str
    subtitle: str
    file: str
    data: dict | None = None  # theme_charts.chart_data; None in runs before 2026-10-15 (PNG only)


class ThemeRun(BaseModel):
    run_id: str  # 2026-10-14-am
    date: str
    slot: Literal["am", "pm"]
    generated_at: str
    theme: str
    why: str
    lead: SignalKind
    signals: list[Signal]
    streak: int  # runs in a row this theme has been #1
    fact_ids: list[str]
    exhibits: list[ThemeExhibit]
    facts: list[Fact]


SEARCH_SYSTEM = (
    "You are a markets news desk. Report only what reputable outlets and named accounts "
    "published; quote figures exactly."
)
SEARCH_USER = """It is {now} New York time. List the 8 US macro themes (rates, inflation, the Fed,
growth, jobs, oil, the dollar, credit, equities) that news outlets and financial X discussed most
in the last 12 hours, most-discussed first. One bullet per theme, one line each: the theme and what
is being said, with the exact figures sources report, ending with its citation. No other text."""

SYSTEM = """You pick the single most popular US macro theme right now for ARC Research's Theme
Charts page, and the charts that show it. You get three signal sets as numbered facts:
- N facts: the macro themes news outlets and financial X discussed most in the last 12 hours,
  most-discussed first.
- M facts: 1d/1w/1m moves across equities, rates, credit, commodities and FX.
- P facts: Polymarket economy and Fed markets with the biggest odds moves.
Popular means widely discussed AND visible in prices or odds. Weigh all three; `lead` names the
signal that mattered most.
Rules:
- theme: one headline under 70 characters saying what is happening.
- fact_ids: the ids of the listed facts the theme, why and signals rest on.
- why: 2-3 plain sentences. Use only numbers that appear in the facts listed in fact_ids. Never
  compute, round differently or invent a figure.
- signals: exactly three, one per kind (coverage, move, odds). headline: the one-line read, under
  40 characters; note: a short supporting detail. Coverage says how high the theme ranks among
  the most-discussed themes, never a story count you can't see. If a signal set says nothing
  about the theme, say so. Write for readers: never mention fact ids or the N, M and P sets.
- same_as_last: true if this is the same theme as the newest one under Recent themes, however it
  is worded.
- charts: 6 exhibits that show the theme (at least 5 must be drawable). Use at least 4 different
  forms. At most two may be line or compare, and never both heatmap and movers (both show moves).
  Two charts of the same form must show different series (one compare of stock prices, another
  of yields). Forms:
  - line: one series; the right form for a Polymarket market's odds.
  - compare: 2-4 series on one chart; prices rebased to 100, rates shown as levels.
  - movers: 2-8 bars, each point's value one of the numbers of the fact its fact_id names.
  - heatmap: 2-8 daily series, each row's 1d/1w/1m/3m move shaded by how unusual it is; shows
    how far a theme reaches across markets.
  - scatter: exactly 2 daily series plotted against each other week by week; shows whether they
    move together (oil vs breakevens, yields vs the dollar).
  - range: 2-6 daily series, where each sits between its 1-year low and high and where it was a
    month ago; shows which markets are stretched.
  heatmap, scatter and range take only FRED or Yahoo series. fact_ids name listed facts, or fetch
  a new series as "fred:SERIES_ID" (e.g. fred:T5YIE, fred:DGS10, fred:BAMLH0A0HYM2) or
  "yahoo:TICKER" (e.g. yahoo:BZ=F, yahoo:^GSPC, yahoo:XLE). window_days: 90 for line and compare
  unless the theme needs longer; 180 for scatter; 7 for a Polymarket line; heatmap and range
  ignore it. title: plain words, no numbers. names: a short reader name for each fact_id, in
  order ("WTI crude", "10y yield", "Energy stocks (XLE)"), never a value; [] for line and
  movers. points: [] unless movers. unit: the movers bars' unit (% or bp), else "".
- Never cite an id that isn't listed, or a series spec in any other form."""


class ThemePicker(StructuredAgent[ThemePick]):
    name = "theme_picker"
    output_schema = ThemePick
    tier = "reasoning"

    def __init__(self) -> None:
        cfg = get_settings().themes
        self.model = cfg.picker_model
        self.max_output_tokens = cfg.max_output_tokens

    def system_prompt(self) -> str:
        return SYSTEM

    def user_prompt(
        self, *, now: str, recent: list[str], facts: list[Fact], fix: list[str] | None = None
    ) -> str:
        lines = "\n".join(f"[{f.id}] {f.text} — {f.source_title}" for f in facts)
        out = f"Now: {now} New York time.\nRecent themes, newest first:\n"
        out += "\n".join(recent) or "(none yet)"
        out += f"\n\nFacts:\n{lines}"
        if fix:
            out += "\n\nYour last answer had problems. Fix them:\n" + "\n".join(
                f"- {e}" for e in fix
            )
        return out


def gather(now: datetime) -> list[Fact]:
    """The three signal sets as facts. One dead source must not sink the run."""
    from castelino.agents.update.collector import collect
    from castelino.agents.update.macro import market_facts
    from castelino.agents.update.sources import polymarket
    from castelino.data import web_search

    def coverage() -> list[Fact]:
        user = SEARCH_USER.format(now=f"{now:%a %b %d, %H:%M}")
        text, cites = web_search.search_cited(
            SEARCH_SYSTEM, user, model=get_settings().themes.search_model
        )
        return facts_from_search("N", text, cites)

    def moves() -> list[Fact]:
        snap = collect(today=now.date().isoformat(), prediction={}, model_note=None)
        return market_facts(snap, start=1)

    def odds() -> list[Fact]:
        events = {
            e.get("id"): e for tag in ("economy", "fed") for e in polymarket.fetch_events(tag)
        }
        return polymarket.facts(list(events.values()))

    facts: list[Fact] = []
    for fn in (coverage, moves, odds):
        try:
            facts += fn()
        except Exception as e:  # noqa: BLE001
            log.warning("themes: %s failed: %s", fn.__name__, e)
    return facts


def fetch_series(provider: str, sid: str, fid: str, start: datetime) -> Fact:
    import pandas as pd

    from castelino.forecast import regime

    fn = regime._fetch_fred_series if provider == "fred" else regime._fetch_yf_close
    s = fn(sid)
    s = s[s.index >= pd.Timestamp(start.date())]
    if provider == "fred":
        title, url = f"FRED {sid}", f"https://fred.stlouisfed.org/series/{sid}"
    else:
        title, url = f"Yahoo Finance {sid}", f"https://finance.yahoo.com/quote/{sid}"
    return series_fact(fid, s, provider=provider, sid=sid, title=title, url=url)


def resolve(
    pick: ThemePick, facts: list[Fact], now: datetime, fetch=fetch_series
) -> tuple[list[ThemeChart], dict[str, Fact], list[str]]:
    """Fetch each "fred:ID" / "yahoo:TICKER" a chart names as an S fact, then keep the charts the
    weekly guard passes. Returns (charts, {spec: fetched fact}, why each dropped chart dropped)."""
    fetched: dict[str, Fact] = {}
    for spec in dict.fromkeys(i for ch in pick.charts for i in ch.fact_ids if SERIES.match(i)):
        provider, sid = SERIES.match(spec).groups()
        # heatmap and range ignore window_days (it may be 0): a month keeps the fact's moves real
        days = max(30, *(ch.window_days for ch in pick.charts if spec in ch.fact_ids))
        try:
            fetched[spec] = fetch(provider, sid, f"S{len(fetched) + 1}", now - timedelta(days=days))
        except Exception as e:  # noqa: BLE001 — a bad ticker drops its chart, not the run
            log.warning("themes: %s failed: %s", spec, e)
    by = {f.id: f for f in [*facts, *fetched.values()]}
    known = SimpleNamespace(fact_ids=list(by))
    keep, dropped = [], []
    for ch in pick.charts[: get_settings().themes.max_charts]:
        ids = [fetched[i].id if i in fetched else i for i in ch.fact_ids]
        ch = ch.model_copy(update={"fact_ids": ids})
        errs = _pick_errors(ch, known, by)
        if ch.kind in theme_charts.FORMS:
            errs += theme_charts.form_errors(ch, by)
        if errs:
            dropped += [f"chart '{ch.title}': {e}" for e in errs]
        else:
            keep.append(ch)
    return keep, fetched, dropped


def _cached_series():
    """default_series, but each FRED/Yahoo series is downloaded once per run."""
    import pandas as pd

    full: dict[tuple[str, str], pd.Series] = {}

    def series(ref, window_days: int) -> pd.Series:
        key = (ref.provider, ref.id)
        if key not in full:
            full[key] = default_series(ref, 100_000)
        s = full[key]
        return s[s.index >= s.index[-1] - pd.Timedelta(days=window_days)]

    return series


def _exhibit_data(exhibits, charts, drawn: dict[str, Fact], series) -> list[dict | None]:
    """Each drawn exhibit's browser data. The renderer skips a chart it can't draw and numbers the
    rest in order, so walk the charts and match each exhibit by its form and first fact. A chart
    whose data fails keeps its PNG (data None)."""
    out, rest = [], iter(charts)
    for ex in exhibits:
        for ch in rest:
            ids = list(dict.fromkeys(ch.fact_ids + [p.fact_id for p in ch.points]))
            if ch.kind == ex.kind and ids[0] == ex.fact_id:
                break
        try:
            cited = [drawn[i] for i in ids]
            d = theme_charts.chart_data(ch, cited, series, default_fetch)
            out.append({**d, "sources": list(dict.fromkeys(f.source_title for f in cited))})
        except Exception as e:  # noqa: BLE001 — the page falls back to the PNG
            log.warning("themes: no browser data for '%s': %s", ch.title, e)
            out.append(None)
    return out


def _dir() -> Path:
    cfg = get_settings()
    return cfg.root / cfg.themes.data_dir


def recent_runs(d: Path, n: int) -> list[dict]:
    out = []
    for p in sorted(d.glob("????-??-??-?m.json"), reverse=True)[:n]:
        try:
            out.append(json.loads(p.read_text()))
        except (OSError, ValueError):  # half-written or malformed file
            continue
    return out


def run(
    now: datetime | None = None, *, gather_fn=gather, fetch=fetch_series, picker=None
) -> ThemeRun:
    """One run. Raises (and saves nothing) when the picker fails or no chart can be drawn, so the
    page keeps showing the previous run and the cron line skips the deploy."""
    cfg = get_settings().themes
    now = now or datetime.now(ET)
    slot = "am" if now.hour < 14 else "pm"
    run_id, d = f"{now:%Y-%m-%d}-{slot}", _dir()
    past = [r for r in recent_runs(d, cfg.memory_runs + 1) if r.get("run_id") != run_id]
    past = past[: cfg.memory_runs]
    recent = [f"{r['date']} {r['slot']}: {r['theme']}" for r in past]
    facts = gather_fn(now)
    if not facts:
        raise RuntimeError("no signals: every source failed")
    picker = picker or ThemePicker()
    fix: list[str] | None = None
    for attempt in range(2):  # one retry with the guard's complaints
        pick = picker(now=f"{now:%a %b %d %Y, %H:%M}", recent=recent, facts=facts, fix=fix)
        charts, specs, dropped = resolve(pick, facts, now, fetch)
        fetched = list(specs.values())
        fact_ids = [specs[i].id if i in specs else i for i in pick.fact_ids]
        by = {f.id: f for f in [*facts, *fetched]}
        nums = {x for i in fact_ids if i in by for x in by[i].numbers}
        texts = [pick.theme, pick.why, *(t for s in pick.signals for t in (s.headline, s.note))]
        fix = [f"{x} is not a number of the facts in fact_ids" for x in unsupported(texts, nums)]
        fix += [f"fact_ids names an unknown id {i}" for i in fact_ids if i not in by]
        # ponytail: the retry's charts are kept even if it drew fewer than the first try
        need = cfg.min_charts if attempt == 0 else 1  # the retry publishes whatever passed
        if len(charts) < need:
            fix += [
                f"only {len(charts)} of your charts can be drawn; give at least {cfg.min_charts}"
            ]
            fix += dropped
        if not fix:
            break
        log.warning("themes: attempt %d rejected: %s", attempt + 1, fix)
    if fix:
        raise RuntimeError(f"picker failed the guard twice: {fix}")
    # Charts label series by their ids (CL_F, DGS10; a Polymarket question runs long and gets cut
    # mid-word); use the picker's reader names instead, and a line chart's plain title.
    drawn = {f.id: f for f in [*facts, *fetched]}
    for ch in charts:
        # ponytail: a series on two charts keeps its last name
        for fid, name in zip(
            ch.fact_ids, [ch.title] if ch.kind == "line" else ch.names, strict=False
        ):
            if name and (f := drawn[fid]).series is not None:
                drawn[fid] = f.model_copy(
                    update={"series": f.series.model_copy(update={"label": name})}
                )
    series = _cached_series()  # the PNGs and the browser data share one download per series
    exhibits = make_weekly_exhibits(
        SimpleNamespace(sections=[SimpleNamespace(exhibits=charts)]),
        list(drawn.values()),
        d / "charts" / run_id,
        series=series,
        kicker="THEME CHARTS",
        forms=theme_charts.FORMS,
    )
    if not exhibits:
        raise RuntimeError("no chart could be drawn")
    data = _exhibit_data(exhibits, charts, drawn, series)
    streak = past[0].get("streak", 1) + 1 if pick.same_as_last and past else 1
    cited = set(fact_ids) | {
        i for ch in charts for i in [*ch.fact_ids, *(p.fact_id for p in ch.points)]
    }
    rec = ThemeRun(
        run_id=run_id,
        date=f"{now:%Y-%m-%d}",
        slot=slot,
        generated_at=datetime.now(ET).isoformat(timespec="seconds"),
        theme=pick.theme,
        why=pick.why,
        lead=pick.lead,
        signals=pick.signals,
        streak=streak,
        fact_ids=fact_ids,
        exhibits=[
            ThemeExhibit(
                n=e.n, kind=e.kind, title=e.title, subtitle=e.subtitle, file=e.file, data=dt
            )
            for e, dt in zip(exhibits, data, strict=True)
        ],
        facts=[f for f in [*facts, *fetched] if f.id in cited],
    )
    atomic_write_text(d / f"{run_id}.json", rec.model_dump_json(indent=2))
    return rec


SITE = "https://arcresearch.markets/themes"
EXHIBIT = re.compile(r"^Exhibit \d+: ")  # the chart title's prefix; the thread numbers posts itself
SECTION = 453292  # Substack section "financial-markets"
SIGNAL = {"coverage": "News & X", "move": "Biggest move", "odds": "Polymarket"}


def _marker(run_id: str) -> Path:
    return _dir() / "substack" / f"{run_id}.json"


def post_url(run_id: str) -> str | None:
    """The run's Substack post, once published."""
    p = _marker(run_id)
    return json.loads(p.read_text()).get("url") if p.exists() else None


def substack_doc(rec: ThemeRun, uploaded: dict[str, dict]) -> dict:
    from castelino import substack as sb

    cited = set(rec.fact_ids)
    sources = {f.source_title: f.source_url for f in rec.facts if f.id in cited}
    signals = [
        sb._p(sb._bold(f"{SIGNAL[s.kind]}: "), sb._text(f"{s.headline}. {s.note}"))
        for s in rec.signals
    ]
    c = [sb._p(*sb._rich(rec.why)), _bullets(signals)]
    c += [
        sb._image(uploaded[e.file], f"{e.title}. {e.subtitle}")
        for e in rec.exhibits
        if e.file in uploaded
    ]
    if sources:
        c.append(sb._heading("Sources"))
        c.append(_bullets([sb._p(sb._text(t, u or None)) for t, u in sources.items()]))
    c.append(
        sb._p(sb._text("Every plotted number is market data drawn by code. Not investment advice."))
    )
    return {"type": "doc", "content": c}


def _bullets(paras: list[dict]) -> dict:
    return {
        "type": "bullet_list",
        "content": [{"type": "list_item", "content": [p]} for p in paras],
    }


def publish_substack(rec: ThemeRun) -> str:
    """Draft and publish the run on Substack, web only (no email). Returns the post's URL; the
    marker in data/themes/substack/ makes a rerun return it instead of posting again."""
    from castelino import substack as sb

    charts = _dir() / "charts" / rec.run_id
    sb.push(
        marker=_marker(rec.run_id),
        title=rec.theme,
        subtitle=f"ARC Theme Charts · {datetime.fromisoformat(rec.date):%A, %B %-d, %Y}",
        pngs={e.file: charts / e.file for e in rec.exhibits},
        body=lambda up: substack_doc(rec, up),
        label=rec.run_id,
    )
    return sb.publish(_marker(rec.run_id), section_id=SECTION)


def thread(rec: ThemeRun, url: str | None = None) -> list[str]:
    """The run as an X thread: the theme and as much of the why as fits (chart 1 rides on it), one
    post per further chart with its code-written subtitle, then the link to the Substack post.
    Every word is the guarded pick's or code's, so posting needs no model and no approval."""
    text, sep = f"Before the open: {rec.theme} 🧵", "\n\n"
    for s in re.split(r"(?<=[.!?])\s+", rec.why):
        if x_post.xlen(nxt := f"{text}{sep}{s}") > x_post.LIMIT:
            break
        text, sep = nxt, " "
    n = len(rec.exhibits)
    charts = f"All {n} charts" if n > 1 else "The chart"
    return [
        text,
        *(f"{e.n}/ {EXHIBIT.sub('', e.title)}\n{e.subtitle}" for e in rec.exhibits[1:]),
        f"{charts} with sources → {url or SITE}",
    ]


def post_thread(rec: ThemeRun, root: Path | None = None, *, post=None, upload=None) -> list[str]:
    """Post a run's thread. Ids are saved after every post to data/x_posts/themes/<run_id>.json, so
    a run is never posted twice and a broken chain resumes where it stopped."""
    post, upload = post or x_post.post, upload or x_post.upload_image
    texts = thread(rec, post_url(rec.run_id))
    if long := [t for t in texts if x_post.xlen(t) > x_post.LIMIT]:
        raise ValueError(f"over {x_post.LIMIT}: {long}")  # before anything is sent
    path = (root or get_settings().root) / "data" / "x_posts" / "themes" / f"{rec.run_id}.json"
    ids = json.loads(path.read_text())["ids"] if path.exists() else []
    for i, text in enumerate(texts[len(ids) :], len(ids)):
        media = None
        if i < len(rec.exhibits):
            png = _dir() / "charts" / rec.run_id / rec.exhibits[i].file
            try:
                media = upload(png.read_bytes())
            except Exception as e:  # noqa: BLE001 — the post without its chart beats a broken chain
                log.warning("themes: chart %d upload failed, posting text only: %s", i + 1, e)
        ids.append(post(text, reply_to=ids[-1] if ids else None, media_id=media))
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(
            path, json.dumps({"ids": ids, "texts": texts}, indent=2, ensure_ascii=False)
        )
    return ids


def _today_am(now: datetime) -> ThemeRun | None:
    """Today's 08:00 run on a weekday, the one run that is published; None at weekends."""
    if now.weekday() >= 5:
        log.info("themes: weekend, nothing published")
        return None
    return ThemeRun.model_validate_json((_dir() / f"{now:%Y-%m-%d}-am.json").read_text())


def post_today(now: datetime | None = None, root: Path | None = None, **fakes) -> list[str] | None:
    """The 08:00 cron's last step, after /themes is live: today's am run to X, weekdays only."""
    if not (rec := _today_am(now or datetime.now(ET))):
        return None
    if not (fakes or x_post.can_post()):
        log.warning("themes: X keys not set, would post:\n%s", "\n---\n".join(thread(rec)))
        return None
    return post_thread(rec, root, **fakes)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    if "--substack" in sys.argv[1:]:  # never fails the cron line: the site and X go out regardless
        try:
            rec = _today_am(datetime.now(ET))
            print(f"substack: {publish_substack(rec)}" if rec else "substack: weekend, skipped")
        except Exception as e:  # noqa: BLE001
            print(f"substack: FAILED: {e}", file=sys.stderr)
        sys.exit(0)
    if "--post" in sys.argv[1:]:  # non-zero exit on a failed post; the site is already published
        ids = post_today()
        print(f"X thread: {len(ids)} posts, first {ids[0]}" if ids else "X thread: nothing posted")
        sys.exit(0)
    try:
        r = run()
    except Exception as e:  # noqa: BLE001 — non-zero exit makes the cron line skip the deploy
        log.error("themes: run failed: %s", e)
        sys.exit(1)
    print(f"{r.run_id}: {r.theme} ({len(r.exhibits)} charts, streak {r.streak})")
