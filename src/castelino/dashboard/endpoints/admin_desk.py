"""Admin Daily desk API: per-day agent findings, chat, re-run, rebuild, Substack draft.

Locally it is part of `ckm serve`. On Fly it is the only thing served (dashboard/desk_app.py),
behind the admin password, and the static site reaches it through /api/admin/live/*.
"""

from __future__ import annotations

import json
import os
import re
import threading
from datetime import datetime

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from castelino.agents.update import desk

router = APIRouter(prefix="/admin/desk")
_DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# one background job at a time per day: {"kind", "state": running|done|failed, "message", "at"}
_jobs: dict[str, dict] = {}
_jobs_lock = threading.Lock()


def _day_ok(day: str) -> str:
    if not _DAY.match(day):
        raise HTTPException(400, "day must be YYYY-MM-DD")
    _, updates = desk._dirs()
    if not (updates / f"{day}.json").exists():
        raise HTTPException(404, f"no Morning Note for {day}")
    return day


def _draft(day: str) -> dict | None:
    _, updates = desk._dirs()
    marker = updates / "substack" / f"{day}.json"
    if not marker.exists():
        return None
    draft_id = json.loads(marker.read_text()).get("draft_id")
    pub = os.getenv("SUBSTACK_PUBLICATION_URL", "").rstrip("/")
    return {"id": draft_id, "url": f"{pub}/publish/post/{draft_id}" if pub else None}


@router.get("/days")
def days():
    _, updates = desk._dirs()
    out = []
    for p in sorted(updates.glob("[0-9][0-9][0-9][0-9]-*.json"), reverse=True)[:30]:
        try:
            rec = json.loads(p.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if rec.get("version") == 2:
            out.append(
                {
                    "date": rec["date"],
                    "headline": rec["note"]["headline"],
                    "draft": _draft(rec["date"]),
                }
            )
    return {"days": out}


# ── X posts (declared before /{day} so "x" isn't read as a day) ───────────────────────────────

_SUBSTACK = "https://archresearch.substack.com/p/"
_x_lock = threading.Lock()  # one post chain at a time: a double click must not post twice


def _x_dir():
    from castelino.config import get_settings

    return get_settings().root / "data" / "x_posts"


def _published() -> list[dict]:
    """Published Substack posts we can share: the last 14 daily notes and 4 weekly deep dives."""
    from castelino.dashboard.endpoints.daily_posts import daily_posts
    from castelino.dashboard.endpoints.weekly_posts import weekly_posts

    rows = [
        {
            "kind": "daily",
            "when": p["date"],
            "title": p["title"],
            "takeaways": p.get("takeaways", []),
            "url": p["url"],
            "image": p.get("image"),
        }
        for p in daily_posts()[:14]
    ] + [
        {
            "kind": "weekly",
            "when": p["start"],
            "title": p["title"],
            "takeaways": p.get("takeaways", []),
            "url": p["url"],
            "image": p.get("image"),
        }
        for p in weekly_posts()[:4]
    ]
    out = []
    for r in sorted(rows, key=lambda r: r["when"], reverse=True):
        if not r["url"].startswith(_SUBSTACK):
            continue
        slug = r["url"][len(_SUBSTACK) :].strip("/").split("?")[0]
        if re.fullmatch(r"[a-z0-9-]+", slug):
            out.append({**r, "slug": slug})
    return out


def _x_record(slug: str) -> dict:
    p = _x_dir() / f"{slug}.json"
    return json.loads(p.read_text()) if p.exists() else {"ids": [], "texts": []}


@router.get("/x")
def x_posts():
    from castelino import x_post

    out = []
    for r in _published():
        rec = _x_record(r["slug"])
        out.append(
            {
                **r,
                "drafts": rec["texts"]
                or x_post.drafts(r["kind"], r["title"], r["takeaways"], r["url"]),
                "posted_ids": rec["ids"],
            }
        )
    return {"can_post": x_post.can_post(), "posts": out}


class XPostIn(BaseModel):
    texts: list[str]
    image: bool = False  # attach the post's cover to the first post


def _cover_bytes(image: str) -> bytes:
    """The post's cover as the site shows it: a hand-made /thumbs/ file, else Substack's image."""
    from castelino.config import get_settings

    if image.startswith("/thumbs/"):
        return (get_settings().root / "frontend" / "public" / image.lstrip("/")).read_bytes()
    if not image.startswith("https://"):
        raise ValueError(f"unexpected cover address {image[:60]}")
    r = httpx.get(image, timeout=30, follow_redirects=True)
    r.raise_for_status()
    return r.content


@router.post("/x/{slug}")
def x_post_chain(slug: str, body: XPostIn):
    """Post the chain; each post replies to the previous. Ids are saved as they succeed, so a failed
    reply can be retried from where it stopped and a finished chain is never posted twice."""
    from castelino import x_post

    match = next((r for r in _published() if r["slug"] == slug), None)
    if not match:
        raise HTTPException(404, "not a published Substack post")
    if not x_post.can_post():
        raise HTTPException(
            503,
            "X posting keys aren't set (X_API_KEY, X_API_SECRET, X_ACCESS_TOKEN, X_ACCESS_SECRET)",
        )
    if not _x_lock.acquire(blocking=False):
        raise HTTPException(409, "another X post is going out; try again in a moment")
    try:
        rec = _x_record(slug)
        if rec["ids"] and len(rec["ids"]) >= len(rec["texts"]):
            raise HTTPException(409, "already posted to X")
        if rec["ids"]:
            texts = rec["texts"]  # resume the chain exactly as it started
        else:
            texts = [t.strip() for t in body.texts if t.strip()]
            if not texts or len(texts) > 8:
                raise HTTPException(400, "send 1 to 8 posts")
            if too_long := [i + 1 for i, t in enumerate(texts) if x_post.xlen(t) > x_post.LIMIT]:
                raise HTTPException(400, f"post(s) {too_long} are over {x_post.LIMIT} characters")
            if match["url"] not in texts[-1]:
                raise HTTPException(400, "the last post must carry the Substack link")
        rec["texts"] = texts
        path = _x_dir() / f"{slug}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        media_id = None
        if body.image and not rec["ids"] and match.get("image"):
            try:  # before anything goes out, so a failed upload never leaves half a thread
                media_id = x_post.upload_image(_cover_bytes(match["image"]))
            except Exception as e:  # noqa: BLE001
                raise HTTPException(502, f"couldn't attach the cover: {str(e)[:250]}") from e
        error = None
        for t in texts[len(rec["ids"]) :]:
            try:
                first = not rec["ids"]
                rec["ids"].append(
                    x_post.post(
                        t,
                        reply_to=None if first else rec["ids"][-1],
                        media_id=media_id if first else None,
                    )
                )
            except Exception as e:  # noqa: BLE001 — keep what went out, report the rest
                error = str(e)[:300]
                break
            finally:
                path.write_text(json.dumps(rec, indent=1))
        from castelino import benchmark

        benchmark.record_action(
            "x_post",
            slug=slug,
            texts=texts,
            ids=rec["ids"],
            image=media_id is not None,
            error=error,
        )
        return {"posted_ids": rec["ids"], "total": len(texts), "error": error}
    finally:
        _x_lock.release()


@router.get("/{day}")
def day_detail(day: str):
    _, updates = desk._dirs()
    record, _facts = desk.load_day(updates, _day_ok(day))
    return {
        "date": record.date,
        "generated_at": record.generated_at,
        "note": record.note.model_dump(),
        "findings": [
            f.model_dump(include={"id", "agent", "claim", "fact_ids", "source_title", "source_url"})
            for f in record.findings
        ],
        "draft": _draft(day),
        "job": _jobs.get(day),
    }


class ChatIn(BaseModel):
    messages: list[dict]


@router.post("/{day}/{agent}/chat")
def chat(day: str, agent: str, body: ChatIn):
    if agent not in desk.DESK:
        raise HTTPException(404, f"unknown agent {agent}")
    from castelino import benchmark

    asked = next(
        (str(m.get("text", "")) for m in reversed(body.messages) if m.get("role") == "user"), ""
    )
    try:
        answer, call_id = desk.chat(_day_ok(day), agent, body.messages)
    except Exception as e:  # noqa: BLE001 — show the model error in the chat, don't 500
        benchmark.record_action("chat", day=day, agent=agent, text=asked, error=str(e)[:300])
        raise HTTPException(502, f"chat failed: {str(e)[:200]}") from e
    benchmark.record_action("chat", day=day, agent=agent, text=asked, call_id=call_id)
    return {"answer": answer, "call_id": call_id}


class RateIn(BaseModel):
    call_id: str
    rating: str  # "up" | "down"
    better: str = ""  # what the answer should have been (the benchmark's right answer)


@router.post("/rate")
def rate(body: RateIn):
    """A 👍 / 👎 on a chat answer, kept with the call it rates for testing new models later."""
    from castelino import benchmark

    if body.rating not in ("up", "down") or not re.fullmatch(r"[0-9a-f]{16}", body.call_id):
        raise HTTPException(400, "rating must be up or down, for a recorded call")
    benchmark.record_action(
        "rate", call_id=body.call_id, rating=body.rating, better=body.better.strip()[:4000]
    )
    return {"ok": True}


def _start(day: str, kind: str, fn, **record) -> dict:
    from castelino import benchmark

    with _jobs_lock:
        if (_jobs.get(day) or {}).get("state") == "running":
            raise HTTPException(409, f"{_jobs[day]['kind']} is already running for {day}")
        job = _jobs[day] = {
            "kind": kind,
            "state": "running",
            "message": "",
            "at": datetime.now().isoformat(timespec="seconds"),
        }

    def work():
        try:
            job.update(state="done", message=fn())
        except Exception as e:  # noqa: BLE001 — reported to the page
            job.update(state="failed", message=str(e)[:400])
        action = {"re-run": "rerun", "substack": "push_draft"}.get(kind.split()[0], kind.split()[0])
        benchmark.record_action(
            action, day=day, **record, result=job["message"][:400], state=job["state"]
        )

    threading.Thread(target=work, daemon=True).start()
    return job


class RerunIn(BaseModel):
    ask: str


@router.post("/{day}/{agent}/rerun")
def rerun(day: str, agent: str, body: RerunIn):
    if agent not in desk.AGENTS:
        raise HTTPException(404, f"can't re-run {agent}")
    ask = body.ask.strip()[: desk.MAX_CHARS]
    if not ask:
        raise HTTPException(400, "write what the agent should look into")
    return _start(
        _day_ok(day), f"re-run {agent}", lambda: desk.rerun(day, agent, ask), agent=agent, text=ask
    )


@router.post("/{day}/rebuild")
def rebuild(day: str):
    return _start(_day_ok(day), "rebuild", lambda: desk.rebuild(day))


@router.post("/{day}/substack")
def substack(day: str):
    from castelino.substack import push_draft

    return _start(_day_ok(day), "substack", lambda: push_draft(day))
