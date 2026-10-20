"""A finished research report → a Substack draft in the "Artificial Intelligence" section (never published;
you publish). Made when a report finishes, updated after each added angle and approved edit. A draft you
edited on Substack is never overwritten: push() keeps a hash of the text it pushed and skips when the draft no
longer matches. A deleted draft is recreated; a published one is left alone. Each point's chart is drawn as
an exhibit PNG in the Weekly Deep Dive's frame. push() never raises: why it didn't update goes in the note."""

from __future__ import annotations

import json
import logging
import os
import textwrap
import threading
from pathlib import Path
from types import SimpleNamespace

from castelino import substack as sb
from castelino.agents.research.deep import store
from castelino.agents.research.deep.models import PointChart, ResearchSession, SubstackDraft
from castelino.agents.trade.publish import _get, _set_section, _text, sha
from castelino.agents.weekly import charts as wc

log = logging.getLogger(__name__)
SECTION = (
    466773  # Substack section "artificial-intelligence-update", shown as "Artificial Intelligence"
)
FOOTER = (
    "Researched by ARC's research agents from cited web sources, X, FRED, Yahoo Finance, BLS and Polymarket, "
    "written by Claude, and charted by ARC from the cited figures. Not investment advice."
)
_lock = (
    threading.Lock()
)  # ponytail: one push at a time across reports; per-report locks if pushes pile up


def _short(s: str, n: int) -> str:
    return s if len(s) <= n else s[: n - 1] + "…"


def _line(ex):
    labels, vals = [p.label for p in ex.points], [p.value for p in ex.points]

    def draw(ax):
        x = list(range(len(vals)))
        ax.plot(x, vals, color=wc.GREEN, lw=2.2, marker="o")
        for xi, v in zip(x, vals, strict=True):
            ax.annotate(
                wc._fmt(v, ex.unit, signed=False),
                (xi, v),
                xytext=(0, 8),
                textcoords="offset points",
                ha="center",
                fontsize=8.5,
                fontweight="bold",
            )
        ax.set_xticks(x)
        ax.set_xticklabels([_short(lb, 14) for lb in labels], fontsize=8.5)
        lo, hi = min(vals), max(vals)
        pad = (hi - lo) * 0.25 or abs(hi) * 0.1 or 1
        ax.set_ylim(lo - pad, hi + pad)

    return draw, f"{labels[0]} to {labels[-1]}"


def _stat(ex):
    p = ex.points[0]

    def draw(ax):
        ax.axis("off")
        big = wc._fmt(p.value, ex.unit, signed=False)
        ax.text(
            0.5, 0.6, big, ha="center", va="center", fontsize=44, fontweight="bold", color=wc.GREEN
        )
        ax.text(
            0.5,
            0.15,
            textwrap.fill(p.label, 70),
            ha="center",
            va="center",
            fontsize=10,
            color=wc.INK2,
        )

    return draw, ""


def _exhibit(n: int, c: PointChart, data: str, path: Path) -> None:
    pts = [SimpleNamespace(label=_short(v.label, 30), value=v.value) for v in c.values]
    ex = SimpleNamespace(points=pts, unit=c.unit)
    left = 0.1
    if c.form == "bars":
        (draw, sub), left = wc._bars(ex, diverging=False, keep_order=True, signed=False), 0.3
    elif c.form == "dumbbell":
        draw, sub = wc._dumbbell(ex)
    elif c.form == "line":
        draw, sub = _line(ex)
    else:
        draw, sub = _stat(ex)
    wc._frame(n, c.title, sub, data, path, draw, left=left, kicker="DEEP RESEARCH")


def render(s: ResearchSession) -> dict[str, Path]:
    """One exhibit PNG per charted point, numbered in report order: {"p3.png": path}."""
    by, out = s.fact_map(), {}
    for p in s.report.points:
        if not p.chart:
            continue
        srcs = dict.fromkeys(by[v.fact_id].source_title for v in p.chart.values if v.fact_id in by)
        path = store.root() / s.id / "charts" / f"{p.id}.png"
        _exhibit(len(out) + 1, p.chart, ", ".join(srcs) or "ARC Research", path)
        out[path.name] = path
    return out


def _bullets(items: list[str], links: list[str] | None = None) -> dict:
    hrefs = links or [None] * len(items)
    return {
        "type": "bullet_list",
        "content": [
            {"type": "list_item", "content": [sb._p(sb._text(t, u))]}
            for t, u in zip(items, hrefs, strict=True)
        ],
    }


def _sources(s: ResearchSession) -> list[tuple[str, str]]:
    by, seen, out = s.fact_map(), set(), []
    for i in [i for p in s.report.points for i in p.fact_ids]:
        f = by.get(i)
        if f and f.source_url and f.source_url not in seen:
            seen.add(f.source_url)
            out.append((f.source_title, f.source_url))
    return out


def doc(s: ResearchSession, uploaded: dict[str, dict]) -> dict:
    rep = s.report
    c = [sb._p(sb._text(f"The question: {s.question}")), sb._heading("Key findings")]
    c.append(_bullets([p.headline for p in rep.points]))
    for p in rep.points:
        c += [sb._heading(p.headline), sb._p(sb._text(p.body))]
        if f"{p.id}.png" in uploaded:
            c.append(sb._image(uploaded[f"{p.id}.png"], p.chart.title))
    for head, items in (("Caveats", rep.caveats), ("Still open", rep.gaps_remaining)):
        if items:
            c += [sb._heading(head), _bullets(items)]
    if src := _sources(s):
        c += [sb._heading("Sources"), _bullets([t for t, _ in src], [u for _, u in src])]
    c.append(sb._p(sb._text(FOOTER)))
    return {"type": "doc", "content": c}


def _note(sid: str, note: str) -> None:
    with store.edit(sid) as x:
        x.substack = (x.substack or SubstackDraft()).model_copy(
            update={"note": note, "at": store.now()}
        )


def push(sid: str) -> None:
    with _lock:
        s = store.load(sid)
        if not s.report:
            return
        old = s.substack or SubstackDraft()
        try:
            if old.draft_id and old.sha:
                draft = _get(old.draft_id)
                if draft and not draft.get("is_published") and sha(_text(draft)) != old.sha:
                    _note(sid, "You edited the draft on Substack, so ARC didn't overwrite it.")
                    return
            marker = store.root() / sid / "substack.json"
            msg = sb.push(
                marker=marker,
                title=s.report.title,
                subtitle=f"ARC Deep Research · {s.report.subtitle}",
                pngs=render(s),
                body=lambda up: doc(s, up),
                label=f"Research {sid}",
            )
            if msg.startswith("skipped"):
                _note(sid, msg.removeprefix("skipped: "))
                return
            draft_id = json.loads(marker.read_text())["draft_id"]
            _set_section(draft_id, SECTION)
            pub = os.environ["SUBSTACK_PUBLICATION_URL"].rstrip("/")
            new = SubstackDraft(
                draft_id=draft_id,
                url=f"{pub}/publish/post/{draft_id}",
                sha=sha(_text(_get(draft_id) or {})),
                at=store.now(),
            )
        except Exception as e:  # noqa: BLE001 - shown in the Research tab with a Push again button
            log.exception("research %s: Substack draft failed", sid)
            _note(sid, f"Substack: {e}"[:300])
            return
        with store.edit(sid) as x:
            x.substack = new
