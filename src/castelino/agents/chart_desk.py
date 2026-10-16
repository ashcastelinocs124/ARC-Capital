"""Chart desk (admin → Charts): talk to the chart agent about any idea, or run one prompt on several
models side by side and vote for the best.

The model only names forms and fred:/yahoo: series (Trade Lab's 12 forms); code fetches the data and
draws every chart (agents/trade/forms.py), so it never supplies a plotted number. Only for direct use:
its models live in config.yaml `chart_desk` and never change another workflow's model.

Each chat thread or compare run is one file, data/chart_desk/<id>/run.json, with its PNGs beside it.
A chat turn has one reply; a compare run has one turn with a reply per model."""

from __future__ import annotations

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
from castelino.agents.update.fsio import atomic_write_text
from castelino.agents.update.guard import unsupported
from castelino.config import get_settings

MAX_CHARTS = 4
MAX_MODELS = 8
KICKER = "CHART DESK"
MODEL_ID = re.compile(r"^[a-z0-9][a-z0-9._-]*(/[a-z0-9][a-z0-9._:-]*)?$")

SYSTEM = """You are ARC Research's chart desk. The user describes an idea; propose up to 4 charts
that make its point fastest (or exactly what a follow-up asks for: change one, add one). Be inventive:
prefer the non-plain forms. You never supply numbers: name a form, its series (fred:ID or
yahoo:TICKER, subject first), names (each series' full name in the same order, e.g. iShares MSCI
Japan ETF, 10-year Treasury yield), a window in days and, for threshold_band, the threshold. Titles are short
claims with no figures and no dashes. `why` says in one sentence what the chart shows for the idea.
`reply` is one or two sentences on what the set shows together, or what you changed.
Forms:
{catalog}"""


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


class Proposal(BaseModel):
    reply: str
    charts: list[ChartIdea]


class Chart(ChartIdea):
    file: str | None = None  # the PNG, when drawn
    error: str | None = None  # why it wasn't drawn


class Reply(BaseModel):
    model: str
    state: Literal["running", "done", "failed"] = "running"
    text: str = ""
    charts: list[Chart] = []
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
    """Earlier turns as chat messages: the asks, and each reply's text plus its charts' specs."""
    msgs = []
    for t in turns:
        r = t.replies[0]
        msgs.append({"role": "user", "content": t.ask})
        charts = "\n".join(
            f"- {c.form} {', '.join(c.series)} {c.window_days}d: {c.title}"
            + (f" (not drawn: {c.error})" if c.error else "")
            for c in r.charts
        )
        msgs.append({"role": "assistant", "content": f"{r.text}\nCharts:\n{charts}"})
    return msgs


def _draw(ideas: list[ChartIdea], src: forms.Sources, out: Path, prefix: str, k0: int):
    charts = []
    for k, idea in enumerate(ideas, k0):
        c = Chart(**idea.model_dump())
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
    msgs = [
        {"role": "system", "content": SYSTEM.format(catalog=forms.catalog_text())},
        *_history(history),
        {"role": "user", "content": ask},
    ]
    try:
        for attempt in range(2):
            p = llm.structured("chart_desk", model, msgs, Proposal, meter)
            reply.text = reply.text or p.reply
            room = MAX_CHARTS - sum(c.file is not None for c in reply.charts)
            new = _draw(p.charts[:room], src, out, prefix, len(reply.charts) + 1)
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
