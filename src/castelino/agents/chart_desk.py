"""Chart desk (admin → Charts): talk to the chart agent about any idea, or run one prompt on several
models side by side and vote for the best.

A chat thread's first message gets 2 or 3 questions with suggested answers and no charts (clarify(),
user ask 2026-10-24: ask first, then draw creative charts); the answers, or any later message, draw.

The model names forms and fred:/yahoo: series (Trade Lab's 12 forms); code fetches the data and draws
every chart (agents/trade/forms.py). For data FRED and Yahoo lack (a country's market P/E), it asks for
up to MAX_SEARCHES cited web searches and charts what they return with two cited forms (bars, a line):
every plotted value must be a number of the cited line it names, or the chart isn't drawn. Only for direct use:
its models live in config.yaml `chart_desk` and never change another workflow's model.

Each chat thread or compare run is one file, data/chart_desk/<id>/run.json, with its PNGs beside it.
A chat turn has one reply; a compare run has one turn with a reply per model."""

from __future__ import annotations

import math
import os
import re
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from castelino import benchmark
from castelino.agents.trade import forms, llm
from castelino.agents.update.facts import facts_from_search
from castelino.agents.update.fsio import atomic_write_text
from castelino.agents.update.guard import unsupported
from castelino.agents.update.models import Fact
from castelino.config import get_settings

MAX_CHARTS = 4
MAX_MODELS = 8
MAX_SEARCHES = (
    3  # cited web searches per reply (user ask 2026-10-21: Indonesia's P/E wasn't on FRED/Yahoo)
)
CITED = {
    "cited_bars": (
        "Values from cited web lines side by side, as bars: a snapshot such as a market's P/E "
        "against peers or its own 5-year average. points: 2 to 12.",
        2,
        12,
    ),
    "cited_line": (
        "Dated values from cited web lines as a line, in time order (label = the date or year): "
        "how a figure FRED/Yahoo lack has moved. points: 3 to 30.",
        3,
        30,
    ),
}
SEARCH = """You are a markets data desk. Report only figures that named sources published, one per line,
each with a citation and the date or period it refers to, exactly as published."""
KICKER = "CHART DESK"
MODEL_ID = re.compile(r"^[a-z0-9][a-z0-9._-]*(/[a-z0-9][a-z0-9._:-]*)?$")

SYSTEM = """You are ARC Research's chart desk. The user describes an idea (and may have answered your
questions about it); propose up to 4 charts that make its point (or exactly what a follow-up asks for:
change one, add one). Be creative, not basic: ask what a sharp strategist would show that a newspaper
wouldn't (a return split into stocks and currency, how far a market sits below its last peak, whether
two markets move together and when that broke, how one market did on a benchmark's worst days, where a
market sits in its range, what a fund really holds) and pick the form that shows it. Give each chart a
different form. Use a plain form (line, compare, bars) at most once per reply, and only when no other
form shows the point; the cited forms don't count, they are the only way to chart data FRED and Yahoo
lack. Reach past the obvious series too: the currency that splits a return, a peer group, a benchmark.
Unless the user asks for one chart, give 3 or 4 that look at the idea from different angles: the figure
they asked about, and around it the market moves that explain or test it (for a valuation: how far
prices fell, how much the currency took, whether peers moved with it). Follow the user's answers to your
questions. You never supply numbers: name a form, its series (fred:ID or
yahoo:TICKER, subject first), names (each series' full name in the same order, e.g. iShares MSCI
Japan ETF, 10-year Treasury yield), a window in days and, for threshold_band, the threshold. Titles are short
claims with no figures and no dashes. `why` says in one sentence what the chart shows for the idea.
`reply` is one or two sentences on what the set shows together, or what you changed.
FRED and Yahoo don't have everything (a country's stock market P/E, survey readings, a company's
segment figures). For data they lack, list up to 3 `searches`, each a precise data request ("Indonesia
IDX Composite trailing P/E ratio, latest and 5-year average", "MSCI Emerging Markets forward P/E,
latest"), and propose no chart from them yet: the cited lines come back as [W1], [W2] ..., and then you
chart them with cited_bars or cited_line, each point's value copied exactly from the line it cites
(fact_id) and `unit` its unit ("x" for a multiple, "%"). A reply can mix cited charts with FRED/Yahoo
ones; cited charts take no series. Leave `searches` empty when FRED/Yahoo have the data.
Forms:
{catalog}
{cited}"""
ASK = """You are ARC Research's chart desk. The user just described a new idea for charts. Before
drawing anything, ask 2 or 3 short questions whose answers would change which charts you draw: what
it should be measured against, what question sits behind it (what would prove or break it), which
markets or peers, what period. Never ask what the idea already says. Give each question 2 to 4 short
suggested answers (a few words each) that open different angles, including ones the user may not have
thought of and that lead to the unusual forms below. `reply` is one sentence on why the answers change
the charts. Forms you can draw:
{catalog}"""


class CitedPoint(BaseModel):
    label: str  # "Indonesia", "5-year average", "2023"
    value: float
    fact_id: str  # the [W#] line the value is copied from


class ChartIdea(BaseModel):  # what the model emits; forms.render reads the same fields as ChartSpec
    form: str
    series: list[str]
    names: list[str] | None = (
        None  # each series' full name, in order (charts print "Name (TICKER)")
    )
    window_days: int
    threshold: float | None
    title: str
    why: str
    points: list[CitedPoint] | None = None  # cited forms only
    unit: str | None = None  # cited forms: "x", "%", "$"


class Question(BaseModel):
    text: str
    options: list[str]  # 2 to 4 short suggested answers; the UI adds Other


class Questions(BaseModel):  # what the model emits on a thread's first message
    reply: str
    questions: list[Question]


class Proposal(BaseModel):
    reply: str
    charts: list[ChartIdea]
    searches: list[str] = []  # data requests FRED/Yahoo can't answer; cited lines come back


class Chart(ChartIdea):
    file: str | None = None  # the PNG, when drawn
    error: str | None = None  # why it wasn't drawn


class Reply(BaseModel):
    model: str
    state: Literal["running", "done", "failed"] = "running"
    text: str = ""
    charts: list[Chart] = []
    questions: list[Question] = []  # a thread's first reply: asked before anything is drawn
    seconds: float = 0.0
    usd: float = 0.0
    error: str | None = None  # the model call itself failed


class Turn(BaseModel):
    ask: str
    at: str
    replies: list[Reply]


class Run(BaseModel):
    id: str
    kind: Literal["chat", "compare"]
    title: str
    created_at: str
    updated_at: str
    turns: list[Turn] = []
    vote: str | None = None  # compare: the model you marked best


class Busy(RuntimeError):  # noqa: N818 - reads as "desk.Busy" at call sites, like Trade Lab's
    pass


# ---------- store ----------

_locks: dict[str, threading.Lock] = {}
_guard = threading.Lock()


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def root() -> Path:
    if env := os.environ.get("ARC_CHART_DESK_DIR", "").strip():
        return Path(env)
    cfg = get_settings()
    return cfg.root / cfg.chart_desk.data_dir


def run_dir(run_id: str) -> Path:
    return root() / run_id


def _lock(run_id: str) -> threading.Lock:
    with _guard:
        return _locks.setdefault(run_id, threading.Lock())


def save(run: Run) -> None:
    run.updated_at = now()
    atomic_write_text(run_dir(run.id) / "run.json", run.model_dump_json(indent=1))


def load(run_id: str) -> Run:
    p = run_dir(run_id) / "run.json"
    if not re.fullmatch(r"[0-9a-f]{10}", run_id) or not p.exists():
        raise KeyError(run_id)
    return Run.model_validate_json(p.read_text())


@contextmanager
def edit(run_id: str):
    with _lock(run_id):
        run = load(run_id)
        yield run
        save(run)


def all_runs() -> list[Run]:
    out = []
    for p in root().glob("*/run.json") if root().exists() else []:
        try:
            out.append(Run.model_validate_json(p.read_text()))
        except ValueError:
            continue
    return sorted(out, key=lambda r: r.updated_at, reverse=True)


def scoreboard() -> dict[str, int]:
    tally: dict[str, int] = {}
    for r in all_runs():
        if r.kind == "compare" and r.vote:
            tally[r.vote] = tally.get(r.vote, 0) + 1
    return dict(sorted(tally.items(), key=lambda kv: -kv[1]))


# ---------- the agent ----------


def cached(src: forms.Sources) -> forms.Sources:
    """One download per series per run: compare columns often name the same series."""
    yahoo, fred = lru_cache(None)(src.yahoo), lru_cache(None)(src.fred)
    return forms.Sources(lambda t: yahoo(t).copy(), lambda s: fred(s).copy(), src.sectors)


def _history(turns: list[Turn]) -> list[dict]:
    """Earlier turns as chat messages: the asks, and each reply's text, questions and charts' specs."""
    msgs = []
    for t in turns:
        r = t.replies[0]
        msgs.append({"role": "user", "content": t.ask})
        if r.questions:
            qs = "\n".join(f"- {q.text} (suggested: {'; '.join(q.options)})" for q in r.questions)
            msgs.append({"role": "assistant", "content": f"{r.text}\nQuestions:\n{qs}"})
            continue
        charts = "\n".join(
            f"- {c.form} {', '.join(c.series)} {c.window_days}d: {c.title}"
            + (f" (not drawn: {c.error})" if c.error else "")
            for c in r.charts
        )
        msgs.append({"role": "assistant", "content": f"{r.text}\nCharts:\n{charts}"})
    return msgs


def _search(queries: list[str]) -> list[Fact]:
    """The cited lines of up to MAX_SEARCHES web searches, as facts W1, W2 ... (uncited lines dropped)."""
    from castelino.data import web_search

    facts: list[Fact] = []
    for q in queries[:MAX_SEARCHES]:
        try:
            text, cites = web_search.search_cited(SEARCH, q)
        except Exception:  # noqa: BLE001 - a failed search just gives the model fewer lines
            continue
        facts += facts_from_search("W", text, cites)
    return [f.model_copy(update={"id": f"W{i}"}) for i, f in enumerate(facts, 1)]


def _cited_msg(facts: list[Fact]) -> str:
    if not facts:
        return "The searches found no cited figures; chart what FRED and Yahoo have instead."
    lines = "\n".join(f"[{f.id}] {f.text} ({f.source_title})" for f in facts)
    return (
        f"Cited lines from your searches:\n{lines}\n\nNow propose the charts (searches empty). "
        "Each cited_bars or cited_line point copies its value exactly from the line it cites."
    )


def _cited_errors(c: Chart, facts: dict[str, Fact]) -> list[str]:
    _, lo, hi = CITED[c.form]
    pts = c.points or []
    errs = [] if lo <= len(pts) <= hi else [f"{c.form} needs {lo} to {hi} points, got {len(pts)}"]
    for p in pts:
        f = facts.get(p.fact_id)
        if f is None:
            errs.append(f"{p.label}: {p.fact_id} is not one of the cited lines")
        elif not any(math.isclose(p.value, n, rel_tol=1e-9, abs_tol=1e-9) for n in f.numbers):
            errs.append(f"{p.label}: {p.value:g} is not in [{f.id}] {f.text[:80]}")
    return errs


def _draw_cited(
    c: Chart, facts: dict[str, Fact], path: Path, k: int, kicker: str = KICKER
) -> list[tuple[str, float]]:
    """A cited chart in the house frame: bars (a snapshot) or a line (dated points). X Scout draws
    its data charts here too, with its topic as the kicker."""
    from castelino.agents.trade.forms import GREEN, INK2, SLATE, _wrap
    from castelino.agents.weekly.charts import _frame

    pts, unit = c.points or [], c.unit or ""
    labels, vals = [p.label for p in pts], [p.value for p in pts]
    gap = " " if unit[:1].isalpha() and unit != "x" else ""  # "1.7 GW", but "2.1%" and "18.5x"
    fmt = lambda v: f"{v:,.2f}".rstrip("0").rstrip(".") + gap + unit  # noqa: E731

    def bars(ax):
        y = list(range(len(vals)))[::-1]
        ax.barh(y, vals, color=[GREEN] + [SLATE] * (len(vals) - 1), height=0.6)
        for yi, v in zip(y, vals, strict=True):
            ax.text(v, yi, " " + fmt(v), va="center", ha="left" if v >= 0 else "right",
                    fontsize=8.5, fontweight="bold")  # fmt: skip
        ax.set_yticks(y)
        ax.set_yticklabels([_wrap(lb) for lb in labels], fontsize=8.5)
        ax.axvline(0, color=INK2, lw=1)
        ax.set_xticks([])
        ax.margins(x=0.25)

    def line(ax):
        x = list(range(len(vals)))
        ax.plot(x, vals, color=GREEN, lw=2, marker="o", ms=3.5)
        ax.set_xticks(x)
        ax.set_xticklabels(labels, fontsize=8)
        ax.annotate(fmt(vals[-1]), (x[-1], vals[-1]), xytext=(4, 0), textcoords="offset points",
                    fontsize=8.5, color=GREEN, fontweight="bold", va="center")  # fmt: skip

    ids = dict.fromkeys(p.fact_id for p in pts)
    # the publisher, not the page title: "... Underwrite | Columbia Business School" ran off the footer
    sources = "; ".join(dict.fromkeys(facts[i].source_title.rsplit(" | ", 1)[-1][:60] for i in ids))
    sub = (
        "Cited values" + (f" ({unit})" if unit else "")
        if c.form == "cited_bars"
        else f"{labels[0]} to {labels[-1]}"
    )
    is_bars = c.form == "cited_bars"
    _frame(k, c.title, sub, f"web search, cited: {sources}", path, bars if is_bars else line,
           left=0.25 if is_bars else 0.1, kicker=kicker)  # fmt: skip
    return [(p.label, p.value) for p in pts]


def _draw(
    ideas: list[ChartIdea],
    src: forms.Sources,
    out: Path,
    prefix: str,
    k0: int,
    facts: dict[str, Fact] | None = None,
):
    charts, facts = [], facts or {}
    for k, idea in enumerate(ideas, k0):
        c = Chart(**idea.model_dump())
        if c.form in CITED:
            c.series = list(
                dict.fromkeys(f"web:{p.fact_id}" for p in c.points or [])
            )  # the UI's chips
            if errs := _cited_errors(c, facts):
                c.error = "; ".join(errs)
                charts.append(c)
                continue
            name = f"{prefix}-{k}.png"
            try:
                nums = _draw_cited(c, facts, out / name, k)
            except Exception as e:  # noqa: BLE001
                c.error = str(e)[:200]
            else:
                bad = unsupported([c.title], {v for _, v in nums})
                c.error, c.file = (
                    (f"title figure {', '.join(bad)} isn't in the chart", None)
                    if bad
                    else (None, name)
                )
            charts.append(c)
            continue
        if errs := forms.spec_errors(c):
            c.error = "; ".join(errs)
        else:
            name = f"{prefix}-{k}.png"
            try:
                nums = forms.render(c, src, out / name, k, kicker=KICKER)
            except Exception as e:  # noqa: BLE001 - an undrawable chart is shown as failed
                c.error = str(e)[:200]
            else:
                if bad := unsupported([c.title], {v for _, v in nums}):
                    c.error = f"title figure {', '.join(bad)} isn't in the chart"
                else:
                    c.file = name
        charts.append(c)
    return charts


def propose(
    ask: str, model: str, history: list[Turn], src: forms.Sources, out: Path, prefix: str
) -> Reply:
    """One reply from one model: up to 4 charts drawn; failures get one retry that is told why."""
    meter = llm.Meter()
    started = time.monotonic()
    reply = Reply(model=model)
    cited = "\n".join(f"- {n}: {d} Points: {lo} to {hi}." for n, (d, lo, hi) in CITED.items())
    msgs = [
        {"role": "system", "content": SYSTEM.format(catalog=forms.catalog_text(), cited=cited)},
        *_history(history),
        {"role": "user", "content": ask},
    ]
    facts: dict[str, Fact] = {}
    try:
        for attempt in range(2):
            p = llm.structured("chart_desk", model, msgs, Proposal, meter)
            if (
                p.searches and not facts and not attempt
            ):  # fetch the data FRED/Yahoo lack, then re-ask
                found = _search(p.searches)
                facts = {f.id: f for f in found}
                msgs += [
                    {"role": "assistant", "content": p.model_dump_json()},
                    {"role": "user", "content": _cited_msg(found)},
                ]
                p = llm.structured("chart_desk", model, msgs, Proposal, meter)
            reply.text = reply.text or p.reply
            room = MAX_CHARTS - sum(c.file is not None for c in reply.charts)
            new = _draw(p.charts[:room], src, out, prefix, len(reply.charts) + 1, facts)
            reply.charts += new
            failed = [c for c in new if c.error]
            if not failed or attempt:
                break
            msgs += [
                {"role": "assistant", "content": p.model_dump_json()},
                {
                    "role": "user",
                    "content": "These couldn't be drawn; propose one replacement for each: "
                    + "; ".join(f"{c.form} {', '.join(c.series)}: {c.error}" for c in failed),
                },
            ]
        reply.state = "done"
    except Exception as e:  # noqa: BLE001 - one model failing never breaks the others
        reply.state, reply.error = "failed", str(e)[:300]
    reply.seconds = round(time.monotonic() - started, 1)
    reply.usd = round(meter.total, 5)
    return reply


def clarify(idea: str, model: str) -> Reply:
    """A thread's first reply: 2 or 3 questions with suggested answers, nothing drawn."""
    meter = llm.Meter()
    started = time.monotonic()
    reply = Reply(model=model)
    msgs = [
        {"role": "system", "content": ASK.format(catalog=forms.catalog_text())},
        {"role": "user", "content": idea},
    ]
    try:
        q = llm.structured("chart_desk", model, msgs, Questions, meter)
        reply.text = q.reply
        reply.questions = [
            Question(text=x.text.strip(), options=[o.strip() for o in x.options if o.strip()][:4])
            for x in q.questions
            if x.text.strip()
        ][:3]
        if not reply.questions:
            raise ValueError("the agent asked no questions; say what you want drawn")
        reply.state = "done"
    except Exception as e:  # noqa: BLE001 - the thread stays open: the next message draws
        reply.state, reply.error = "failed", str(e)[:300]
    reply.seconds = round(time.monotonic() - started, 1)
    reply.usd = round(meter.total, 5)
    return reply


# ---------- jobs ----------


def _finish(run_id: str, i: int, reply: Reply) -> None:
    with edit(run_id) as run:
        run.turns[-1].replies[i] = reply


def _busy(run: Run) -> bool:
    return any(r.state == "running" for t in run.turns for r in t.replies)


def _new(kind: str, ask: str) -> Run:
    run = Run(
        id=uuid.uuid4().hex[:10],
        kind=kind,
        title=ask.strip()[:80],
        created_at=now(),
        updated_at=now(),
    )
    run_dir(run.id).mkdir(parents=True, exist_ok=True)
    save(run)
    return run


def check_models(models: list[str]) -> list[str]:
    out = list(dict.fromkeys(m.strip() for m in models if m.strip()))
    if not out or len(out) > MAX_MODELS:
        raise ValueError(f"pick 1 to {MAX_MODELS} models")
    if bad := [m for m in out if not MODEL_ID.match(m)]:
        raise ValueError(f"not a model id: {', '.join(bad)}")
    return out


def chat(ask: str, model: str | None, run_id: str | None, *, sync=False, src=None) -> Run:
    model = check_models([model or get_settings().chart_desk.chat_model])[0]
    run = _new("chat", ask) if run_id is None else load(run_id)
    if run.kind != "chat":
        raise ValueError("that run is a model comparison, not a chat")
    with edit(run.id) as r:
        if _busy(r):
            raise Busy("the chart agent is still answering")
        history = list(r.turns)
        r.turns.append(Turn(ask=ask.strip(), at=now(), replies=[Reply(model=model)]))
        n = len(r.turns)

    def work():
        if not history:  # a new idea: ask first
            return _finish(run.id, 0, clarify(ask, model))
        reply = propose(
            ask, model, history, src or cached(forms.Sources.live()), run_dir(run.id), f"t{n}"
        )
        _finish(run.id, 0, reply)

    work() if sync else threading.Thread(target=work, daemon=True).start()
    return load(run.id)


def compare(ask: str, models: list[str], *, sync=False, src=None) -> Run:
    models = check_models(models)
    run = _new("compare", ask)
    with edit(run.id) as r:
        r.turns.append(Turn(ask=ask.strip(), at=now(), replies=[Reply(model=m) for m in models]))
    shared = src or cached(forms.Sources.live())

    def one(i: int, m: str):
        _finish(run.id, i, propose(ask, m, [], shared, run_dir(run.id), f"m{i + 1}"))

    def work():
        with ThreadPoolExecutor(max_workers=len(models)) as pool:
            list(pool.map(one, range(len(models)), models))

    work() if sync else threading.Thread(target=work, daemon=True).start()
    return load(run.id)


def vote(run_id: str, model: str) -> Run:
    with edit(run_id) as run:
        if run.kind != "compare" or model not in {r.model for r in run.turns[0].replies}:
            raise ValueError("vote for a model in this comparison")
        run.vote = None if run.vote == model else model
        picked = run.vote
    benchmark.record_action("chart_vote", run_id=run_id, model=picked, ask=run.title)
    return load(run_id)


def recover_interrupted() -> int:
    """A restart kills running replies; mark them failed so the page stops waiting."""
    n = 0
    for run in all_runs():
        if _busy(run):
            with edit(run.id) as r:
                for t in r.turns:
                    for rep in t.replies:
                        if rep.state == "running":
                            rep.state, rep.error = "failed", "The server restarted while this ran."
                            n += 1
    return n
