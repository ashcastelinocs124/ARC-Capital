"""Live data for the research agents, read from the JSON that two public pages embed (Next.js flight data):
the Ramp AI Index (the monthly share of U.S. businesses on Ramp paying for AI, by vendor, industry and size,
and weekly token spend by model maker) and OpenRouter's rankings (the most-used models now, each tagged
open-weight or closed from OpenRouter's models API). Every figure becomes a dated fact, so the writer's
latest-data check can see its date. A page whose layout changed raises ToolError and the agent moves on."""

from __future__ import annotations

import json
import re
import statistics
from datetime import date
from functools import lru_cache

import httpx

from castelino.adoption.index import headline
from castelino.adoption.store import AdoptionStore
from castelino.adoption.universe import load_universe
from castelino.agents.update.models import Fact
from castelino.agents.weekly.tools import ToolError
from castelino.config import get_settings

RAMP = "https://ramp.com/data/ai-index"
OPENROUTER = "https://openrouter.ai/rankings"
OPENROUTER_MODELS = "https://openrouter.ai/api/v1/models"
RAMP_VIEWS = ("overall", "vendors", "industries", "sizes", "tokens")
MAKERS = {
    "openai": "OpenAI",
    "anthropic": "Anthropic",
    "google": "Google",
    "xai": "xAI",
    "meta": "Meta",
}
TOP = 10  # OpenRouter models listed
_UA = {"User-Agent": "Mozilla/5.0 (compatible; ARC Research)"}


def _get(url: str) -> str:
    r = httpx.get(url, headers=_UA, timeout=60, follow_redirects=True)
    r.raise_for_status()
    return r.text


@lru_cache(maxsize=4)
def _flight(url: str, day: str) -> str:
    """The page's flight data as one string; fetched once a day per process (Ramp's page is ~11 MB)."""
    out = []
    for c in re.findall(r'self\.__next_f\.push\(\[1,"(.*?)"\]\)', _get(url), flags=re.S):
        try:
            out.append(json.loads(f'"{c}"'))
        except ValueError:
            continue
    return "".join(out)


def _series(url: str, key: str) -> list:
    flight = _flight(url, date.today().isoformat())
    i = flight.find(f'"{key}":[')
    if i < 0:
        raise ToolError(f"the page no longer has {key}; its layout may have changed")
    rows, _ = json.JSONDecoder().raw_decode(flight, i + len(key) + 3)
    return rows


def _month(d: str) -> str:
    return f"{date.fromisoformat(d):%B %Y}"


def _pp(x: float) -> str:
    return f"{x:+.1f} pp"


def _fact(text: str, numbers: list[float], title: str, url: str) -> Fact:
    return Fact(
        id="tmp", text=text, numbers=numbers, provenance="data", source_title=title, source_url=url
    )


def _latest(rows: list[dict], label: str, what: str) -> Fact:
    last = max(r["date_month"] for r in rows)
    top = sorted(
        (r for r in rows if r["date_month"] == last), key=lambda r: -r["adoption_rate_pct"]
    )
    parts = ", ".join(f"{r[label]} {r['adoption_rate_pct']:.1f}%" for r in top)
    text = f"Ramp AI Index, {_month(last)}: {what}: {parts}."
    return _fact(text, [round(r["adoption_rate_pct"], 1) for r in top], "Ramp AI Index", RAMP)


def ramp(view: str) -> list[Fact]:
    if view not in RAMP_VIEWS:
        raise ToolError(f"view must be one of {', '.join(RAMP_VIEWS)}")
    if view == "overall":
        rows = sorted(_series(RAMP, "adoptionOverall"), key=lambda r: r["date_month"])[-6:]
        now = rows[-1]
        trail = ", ".join(f"{_month(r['date_month'])} {r['adoption_rate_pct']:.1f}%" for r in rows)
        changes = [
            (now[k], w)
            for k, w in (("mom_change_pp", "month"), ("yoy_change_pp", "year"))
            if now.get(k) is not None
        ]
        said = f" ({', '.join(f'{_pp(x)} on the {w}' for x, w in changes)})" if changes else ""
        text = (
            f"Ramp AI Index, {_month(now['date_month'])}: {now['adoption_rate_pct']:.1f}% of U.S. businesses on "
            f"Ramp paid for AI{said}. Last six months: {trail}."
        )
        nums = [round(r["adoption_rate_pct"], 1) for r in rows] + [round(x, 1) for x, _ in changes]
        return [_fact(text, nums, "Ramp AI Index", RAMP)]
    if view == "vendors":
        return [
            _latest(
                _series(RAMP, "adoptionVendor"),
                "vendor",
                "share of U.S. businesses paying each AI vendor",
            )
        ]
    if view == "industries":
        rows = _series(RAMP, "adoptionIndustry")
        return [
            _latest(rows, "naics_sector", "share of U.S. businesses paying for AI, by industry")
        ]
    if view == "sizes":
        rows = _series(RAMP, "adoptionSize")
        return [_latest(rows, "business_size", "share of U.S. businesses paying for AI, by size")]
    rows = [r for r in _series(RAMP, "tokenPrices") if r["token_type"] == "all_tokens"]
    last = max(r["usage_date"] for r in rows)
    week = [r for r in rows if r["usage_date"] == last]
    tokens, cost = sum(r["token_count_7d"] for r in week), sum(r["token_cost_usd_7d"] for r in week)
    week.sort(key=lambda r: -r["token_count_7d"])
    name = lambda r: MAKERS.get(r["model_maker"], r["model_maker"].title())  # noqa: E731
    t = [round(100 * r["token_count_7d"] / tokens, 1) for r in week]
    c = [round(100 * r["token_cost_usd_7d"] / cost, 1) for r in week]
    d = date.fromisoformat(last)
    text = (
        f"Ramp AI Index, week to {d:%B} {d.day}, {d.year}: share of AI tokens businesses bought through Ramp, by "
        f"model maker: {', '.join(f'{name(r)} {x:.1f}%' for r, x in zip(week, t, strict=True))}; share of "
        f"token spend: {', '.join(f'{name(r)} {x:.1f}%' for r, x in zip(week, c, strict=True))}."
    )
    return [_fact(text, t + c, "Ramp AI Index", RAMP)]


@lru_cache(maxsize=2)
def _open_weights(day: str) -> dict[str, bool]:
    """Model id → open weights (OpenRouter lists a Hugging Face id for open-weight models)."""
    return {
        m["id"]: bool(m.get("hugging_face_id")) for m in json.loads(_get(OPENROUTER_MODELS))["data"]
    }


def openrouter() -> list[Fact]:
    day = date.today()
    ranked = sorted(_series(OPENROUTER, "itemListElement"), key=lambda r: r["position"])[:TOP]
    if not ranked:
        raise ToolError("OpenRouter's rankings list is empty")
    weights = _open_weights(day.isoformat())
    tag = {True: "open weights", False: "closed"}
    parts, n_open = [], 0
    for r in ranked:
        is_open = weights.get(r["item"].removeprefix("https://openrouter.ai/"))
        n_open += bool(is_open)
        parts.append(f"{r['position']} {r['name']} ({tag.get(is_open, 'weights unknown')})")
    text = (
        f"OpenRouter's most-used models by tokens, rankings as of {day:%B} {day.day}, {day.year}: "
        f"{', '.join(parts)}. {n_open} of the top {len(ranked)} are open-weight."
    )
    return [_fact(text, [float(n_open), float(len(ranked))], "OpenRouter rankings", OPENROUTER)]


ARC = "ARC AI Adoption Index"


def _universe_names() -> dict[str, str]:
    cfg = get_settings()
    path = cfg.root / cfg.adoption.data_dir / "universe.csv"
    return {c.ticker: c.name for c in load_universe(path)} if path.exists() else {}


def arc_index(store=None, names: dict[str, str] | None = None) -> list[Fact]:
    """ARC's own AI Adoption Index (adoption/), its latest run as dated facts: the overview, sector and size
    cells, and the three pillars' raw values (AI hiring share, AI claims in filings, capex plus R&D)."""
    st = store or AdoptionStore()
    names = _universe_names() if names is None else names
    periods = st.periods()
    if not periods:
        raise ToolError("the AI Adoption Index has no run yet")
    p = periods[-1]
    d = date.fromisoformat(p)
    head = f"{ARC}, run of {d:%B} {d.day}, {d.year}"
    cells, rows = st.cells(p), [r for r in st.companies(p) if r.get("score") is not None]
    hl = headline(cells)

    def who(r: dict, extra: str = "") -> str:
        """ "Name (TICKER)", or the bare ticker when the universe has no name for it."""
        t, name = r["ticker"], names.get(r["ticker"])
        return f"{name} ({t}{extra})" if name else f"{t}{f' ({extra[2:]})' if extra else ''}"

    def top(key: str, scale: float, fmt: str) -> tuple[list[dict], list[float]]:
        ranked = sorted((r for r in rows if r.get(key)), key=lambda r: -r[key])[:5]
        return ranked, [round(r[key] * scale, 2 if fmt == ".2f" else 1) for r in ranked]

    large = sum(r["bucket"] == "large" for r in rows)
    out = [
        _fact(
            f"{head}: {len(rows)} U.S. companies ({large} large, {len(rows) - large} small) scored from what they "
            "say about AI in their latest SEC filing, the share of their open job postings that are AI or ML "
            "roles, and their capex plus R&D as a share of revenue. On the equal-weighted score, large companies "
            f"average {hl['large_ew']:.1f} and small companies {hl['small_ew']:.1f}; scores are centred on 50 "
            "each run, so they rank companies against each other rather than measure adoption.",
            [
                float(len(rows)),
                float(large),
                float(len(rows) - large),
                round(hl["large_ew"], 1),
                round(hl["small_ew"], 1),
                50.0,
            ],
            ARC,
            "",
        )
    ]
    by_cell = sorted((c for c in cells if c.sector), key=lambda c: -(c.ew or 0))
    parts = [
        f"{c.sector} {c.bucket} {c.ew:.1f} ({c.n}, thin)"
        if c.thin
        else f"{c.sector} {c.bucket} {c.ew:.1f} ({c.n} companies)"
        for c in by_cell
    ]
    out.append(
        _fact(
            f"{head}: equal-weighted score by sector and size (a cell with fewer than 5 companies is thin): "
            f"{', '.join(parts)}.",
            [round(c.ew, 1) for c in by_cell],
            ARC,
            "",
        )
    )
    hires = [r["hire_raw"] for r in rows if r.get("hire_raw") is not None]
    if hires:
        ranked, nums = top("hire_raw", 100, ".1f")
        m = round(100 * statistics.median(hires), 1)
        out.append(
            _fact(
                f"{head}: AI and ML roles as a share of open job postings, for the {len(hires)} companies with "
                f"job-board data: median {m:.1f}%; highest "
                f"{', '.join(f'{who(r)} {n:.1f}%' for r, n in zip(ranked, nums, strict=True))}.",
                [m, *nums],
                ARC,
                "",
            )
        )
    talk = [r for r in rows if r.get("talk_raw") is not None]
    if talk:
        ranked, nums = top("talk_raw", 1, ".2f")
        none = sum(r["talk_raw"] == 0 for r in talk)
        out.append(
            _fact(
                f"{head}: verified AI claims per 1,000 words of each company's latest SEC filing: {none} of "
                f"{len(talk)} filings make none; highest "
                f"{', '.join(f'{who(r)} {n:.2f}' for r, n in zip(ranked, nums, strict=True))}.",
                [float(none), float(len(talk)), *nums],
                ARC,
                "",
            )
        )
    spend = [r["spend_raw"] for r in rows if r.get("spend_raw") is not None]
    if spend:
        ranked, nums = top("spend_raw", 100, ".1f")
        m = round(100 * statistics.median(spend), 1)
        out.append(
            _fact(
                f"{head}: capex plus R&D as a share of revenue: median {m:.1f}%; highest "
                f"{', '.join(f'{who(r)} {n:.1f}%' for r, n in zip(ranked, nums, strict=True))}.",
                [m, *nums],
                ARC,
                "",
            )
        )
    lead = sorted(rows, key=lambda r: -r["score"])[:5]
    leaders = [f"{who(r, ', ' + r['bucket'])} {r['score']:.1f}" for r in lead]
    out.append(
        _fact(
            f"{head}: highest overall scores: {', '.join(leaders)}.",
            [round(r["score"], 1) for r in lead],
            ARC,
            "",
        )
    )
    return out
