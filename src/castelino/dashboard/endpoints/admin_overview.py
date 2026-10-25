"""GET /admin/desk/overview: the admin home (/admin → Overview) and the sidebar's counts in one read.

What needs the admin (a Trade Lab idea waiting for their view, research rewrites to approve, today's Daily Update
draft not yet published, a failed step to retry), what is running, today's and this month's spend, and what went
out today on X and Substack. Everything is read from the files the sections already write; nothing here starts a
job, calls a model or bills X. Each section is read on its own, so one broken store never blanks the page.
Registered before admin_desk (in main.py and desk_app.py), whose /admin/desk/{day} would otherwise catch it."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import APIRouter

from castelino.config import get_settings

log = logging.getLogger(__name__)
router = APIRouter(prefix="/admin/desk")
ET = ZoneInfo("America/New_York")


def _today() -> str:
    return datetime.now(ET).date().isoformat()


def _data() -> Path:
    return get_settings().root / "data"


def _item(
    section: str,
    title: str,
    detail: str,
    *,
    at: str | None = None,
    cost: float | None = None,
    action: str | None = None,
    url: str | None = None,
    tone: str = "ok",
) -> dict:
    href = "/admin" if section == "overview" else f"/admin/{section}"
    return {
        "section": section,
        "title": title,
        "detail": detail,
        "at": at,
        "cost_usd": cost,
        "action": action,
        "href": href,
        "url": url,
        "tone": tone,
    }


def _x_url(post_id: str) -> str:
    from castelino.dashboard.endpoints.x_feed import HANDLE

    return f"https://x.com/{HANDLE}/status/{post_id}"


def _failed(job) -> bool:
    return bool(job and job.state in ("failed", "interrupted"))


# ── per section: (waiting, running, went_out) ───────────────────────────────
def trade() -> tuple[list, list, list]:
    from castelino.agents.trade import runner, store

    waiting, running = [], []
    for i in store.all():
        title = i.frame.title if i.frame else i.idea[:80]
        if runner.busy(i):
            running.append(
                _item(
                    "trade-lab",
                    title,
                    f"Trade Lab · {i.job.step.replace('_', ' ')}"
                    + (f" · {i.job.message}" if i.job.message else ""),
                    at=i.job.at,
                    cost=i.cost_usd,
                    tone="run",
                )
            )
        elif _failed(i.job):
            waiting.append(
                _item(
                    "trade-lab",
                    title,
                    f"Trade Lab · {i.job.step.replace('_', ' ')} {i.job.state}: "
                    f"{i.job.message or 'no message'}",
                    at=i.job.at,
                    action="Retry",
                    tone="fail",
                )
            )
        elif i.status == "awaiting_view":
            waiting.append(
                _item(
                    "trade-lab",
                    title,
                    "Trade Lab · the debate is done; it waits for your view",
                    at=i.updated_at,
                    action="Give your view",
                    tone="wait",
                )
            )
        elif i.status == "awaiting_charts":
            waiting.append(
                _item(
                    "trade-lab",
                    title,
                    "Trade Lab · pick one chart per section",
                    at=i.updated_at,
                    action="Pick charts",
                    tone="wait",
                )
            )
    return waiting, running, []


def research() -> tuple[list, list, list]:
    from castelino.agents.research.deep import runner, store

    waiting, running = [], []
    for s in store.all():
        title = s.report.title if s.report else s.topic
        if runner.busy(s):
            running.append(
                _item(
                    "research",
                    title,
                    f"Research · {s.job.step} · {s.status}"
                    + (f" · {s.job.message}" if s.job.message else ""),
                    at=s.job.at,
                    cost=s.cost_usd,
                    tone="run",
                )
            )
        elif _failed(s.job):
            waiting.append(
                _item(
                    "research",
                    title,
                    f"Research · {s.job.step} {s.job.state}: {s.job.message or 'no message'}",
                    at=s.job.at,
                    action="Retry",
                    tone="fail",
                )
            )
        elif s.status == "awaiting_answers":
            waiting.append(
                _item(
                    "research",
                    title,
                    "Research · the clarifier's questions wait for your answers",
                    at=s.updated_at,
                    action="Answer",
                    tone="wait",
                )
            )
        if adding := sum(a.status == "running" for a in s.additions):
            running.append(
                _item(
                    "research",
                    title,
                    f"Research · adding angles ({adding} running)",
                    at=s.updated_at,
                    cost=s.cost_usd,
                    tone="run",
                )
            )
        if pending := sum(p.status == "pending" for p in s.proposals):
            waiting.append(
                _item(
                    "research",
                    title,
                    f"Research · {pending} point rewrite{'s' * (pending > 1)} to approve",
                    at=s.updated_at,
                    action="Review",
                    tone="wait",
                )
            )
    return waiting, running, []


def consultants(today: str) -> tuple[list, list, list]:
    from castelino.agents.consultants import store

    waiting, running, out = [], [], []
    for c in store.all():
        day = store.day_log(c.slug, today)
        if c.status == "building":
            running.append(
                _item(
                    "consultants",
                    c.topic,
                    "Consultant · daily build",
                    cost=day.cost_usd,
                    tone="run",
                )
            )
        elif c.status == "failed":
            waiting.append(
                _item(
                    "consultants",
                    c.topic,
                    f"Consultant · {c.error or 'build failed'}",
                    action="Build now",
                    tone="fail",
                )
            )
        post = next(
            (h.post for h in reversed(store.history(c.slug)) if h.day == today and h.post), None
        )
        if post and day.post_id:
            out.append(
                _item(
                    "consultants", f"Consultant {c.code} · {c.topic}", post, url=_x_url(day.post_id)
                )
            )
        elif skip := next((n for n in day.notes if n.startswith("X post skipped")), None):
            out.append(
                _item(
                    "consultants",
                    f"Consultant {c.code} · post skipped",
                    skip.removeprefix("X post skipped: "),
                    tone="off",
                )
            )
    return waiting, running, out


def daily(today: str) -> tuple[list, list, list]:
    """Today's Daily Update draft waits for the admin until it shows on the Substack feed (read hourly)."""
    from castelino.agents.update import desk
    from castelino.dashboard.endpoints.admin_desk import _draft
    from castelino.dashboard.endpoints.daily_posts import parse_daily_posts
    from castelino.dashboard.endpoints.videos import feed_xml

    _, updates = desk._dirs()
    note = updates / f"{today}.json"
    draft = _draft(today) if note.exists() else None
    if not draft:
        return [], [], []
    try:
        published = any(
            p.get("date") == today and p.get("kind", "note") == "note"
            for p in parse_daily_posts(feed_xml())
        )
    except Exception:  # noqa: BLE001 - offline: say so rather than guess
        published = None
    headline = json.loads(note.read_text()).get("note", {}).get("headline", "")
    if published:
        return [], [], [_item("daily-desk", f"Daily Update · {today}", headline, tone="ok")]
    detail = (
        "Daily desk · Substack draft ready, not published"
        if published is False
        else "Daily desk · Substack draft ready (couldn't check the feed)"
    )
    return (
        [
            _item(
                "daily-desk",
                f"Daily Update · {today}",
                detail,
                action="Open draft",
                url=draft.get("url"),
                tone="wait",
            )
        ],
        [],
        [],
    )


def x_today(today: str) -> tuple[list, list, list]:
    """Posts that went out today (dry runs and unsent records skipped)."""
    base = _data() / "x_posts"
    out = []

    def read(p: Path) -> dict:
        try:
            return json.loads(p.read_text()) if p.exists() else {}
        except (OSError, json.JSONDecodeError):
            return {}

    for r in read(base / "scout" / f"{today}.json").get("posts", []):
        if r.get("ids") and not r.get("dry_run"):
            n = len(r["ids"])
            out.append(
                _item(
                    "x-posts",
                    f"X Scout · {r.get('headline', '')}",
                    f"X {'thread' if n > 1 else 'post'}" + (f" · {n} posts" if n > 1 else ""),
                    at=r.get("at"),
                    url=_x_url(r["ids"][0]),
                )
            )
    cal = read(base / "calendar" / f"{today}.json")
    card = cal.get("card") or {}
    if card.get("id") and not card.get("dry_run"):
        out.append(
            _item(
                "x-posts",
                f"Release card · {card.get('title', 'today')}",
                "X post",
                at=card.get("at"),
                url=_x_url(card["id"]),
            )
        )
    for r in cal.get("releases", []):
        if r.get("id") and not r.get("dry_run"):
            out.append(
                _item(
                    "x-posts",
                    "Release · " + r.get("text", "").split("\n")[0][:90],
                    "X post",
                    at=r.get("at"),
                    url=_x_url(r["id"]),
                )
            )
    for r in read(base / "moves" / f"{today}.json").get("posts", []):
        if r.get("id") and not r.get("dry_run"):
            out.append(
                _item(
                    "x-posts",
                    "Market alert · " + ", ".join(r.get("markets", [])),
                    "X post",
                    at=r.get("at"),
                    url=_x_url(r["id"]),
                )
            )
    for run in sorted((_data() / "themes" / "substack").glob(f"{today}-*.json")):
        url = read(run).get("url")
        theme = read(_data() / "themes" / run.name).get("theme", "")
        if url:
            out.append(
                _item(
                    "x-posts",
                    f"Theme Charts · {theme}".rstrip(" ·"),
                    "Substack post and X thread",
                    at=f"{today}T08:00",
                    url=url,
                )
            )
    return [], [], out


def spend(today: str) -> dict:
    from castelino import costs

    t = datetime.fromisoformat(today).date()
    rows = costs.summary(t.day, today=t)["rows"]
    day = [r for r in rows if r["day"] == today]
    return {
        "today_usd": round(sum(r["usd"] or 0 for r in day), 4),
        "calls": sum(r["calls"] or 0 for r in day if r["provider"] not in ("fly",)),
        "tokens": sum((r["tokens_in"] or 0) + (r["tokens_out"] or 0) for r in day),
        "month_usd": round(sum(r["usd"] or 0 for r in rows if r["day"][:7] == today[:7]), 4),
    }


@router.get("/overview")
def overview():
    today = _today()
    parts: dict[str, Callable[[], tuple[list, list, list]]] = {
        "trade-lab": trade,
        "research": research,
        "consultants": lambda: consultants(today),
        "daily-desk": lambda: daily(today),
        "x-posts": lambda: x_today(today),
    }
    needs, running, out, counts, errors = [], [], [], {}, []
    for section, read in parts.items():
        try:
            w, r, o = read()
        except Exception as e:  # noqa: BLE001 - one section's error never blanks the page
            log.warning("overview: %s failed", section, exc_info=True)
            errors.append(f"{section}: {str(e)[:120]}")
            continue
        needs += w
        running += r
        out += o
        counts[section] = {"waiting": len(w), "running": len(r)}
    try:
        money = spend(today)
    except Exception as e:  # noqa: BLE001
        errors.append(f"costs: {str(e)[:120]}")
        money = None
    counts["overview"] = {"waiting": len(needs), "running": 0}
    return {
        "day": today,
        "needs_you": sorted(needs, key=lambda i: i["at"] or ""),  # oldest first
        "running": sorted(running, key=lambda i: i["at"] or ""),
        "went_out": sorted(out, key=lambda i: i["at"] or "", reverse=True),
        "spend": money,
        "counts": counts,
        "errors": errors,
    }
