"""Cover art for the Morning Note, Weekly Deep Dive and Theme Charts Substack drafts.

The Cover Artist (fast tier) turns the finished post into a 2-3 word title, the public figures
it names (Fed officials, CEOs) and a few things to draw; code keeps only people whose name is in
the post, wraps it all in one fixed style (the look of the hand-made covers of October 2026) and
the image model draws it once. If the image model refuses a real person, it redraws once with
generic people. Nobody on the last 3 covers appears again (`RECENT`, logged in
`data/cover_people.json`), so one face doesn't top every post. The PNG is cached next to the
post's data, so a rerun never pays twice. substack.push() asks for a cover only when the draft has none, so a cover set by hand in
Substack is never replaced. The site and X read Substack's cover, so nothing else changes.

Redo one: `uv run python -m castelino.cover <YYYY-MM-DD | YYYY-Www | YYYY-MM-DD-am> ["Name, Name"]`
redraws it and replaces the draft's cover (an unpublished draft only); names given pick the people.
"""

from __future__ import annotations

import base64
import json
import logging
import re
import sys
import time
from datetime import date
from pathlib import Path

from pydantic import BaseModel

from castelino.agents.base import StructuredAgent
from castelino.config import get_settings

log = logging.getLogger(__name__)


class Person(BaseModel):
    name: str  # full name: "Jensen Huang"
    role: str  # "San Francisco Fed President", "Nvidia CEO"
    org: str  # the company or institution exactly as the post writes it: "NVIDIA", "Fed", "TSMC"
    look: str  # "thoughtful, studying a report"


class CoverBrief(BaseModel):
    title: str
    people: list[Person]
    scene: list[str]


BRIEF = """You design the cover image for an ARC Research markets newsletter post.
From its headline and stories, return:
- title: 2 or 3 punchy words naming the main story, like a magazine cover ("INFLATION HEATS UP",
  "MIXED SIGNALS", "PRICE PRESSURE"). No numbers, tickers or punctuation.
- people: 2 or 3 public figures who put a face on the main stories, the most newsworthy first.
  Look at the companies and data the stories cover and take the people linked to them: anyone
  the post names, then the leader of a company it covers (Tesla -> Elon Musk, Meta -> Mark
  Zuckerberg, NVIDIA -> Jensen Huang, TSMC -> its CEO). A central banker or minister only when a
  story is about that institution's own decision or that person's own words, not when the post
  only mentions rate expectations. Only someone who holds that
  role on the date given; leave out anyone you are not sure of. People only, by full name: never
  a company, fund or index (those go in the scene). For each: role, org (the company or
  institution exactly as the post writes it, e.g. "NVIDIA", "Fed") and a dignified, newsroom
  look ("thoughtful, hand on chin", "studying a report", "speaking at a podium"). Empty if
  nobody fits.
- scene: 3 to 5 concrete things to draw, one per main story, naming the companies the post
  covers so their logos or nameplates show: a labelled market screen with a rising or falling
  trend line ("a screen labelled TREASURY YIELDS with a falling blue line"), a place ("the
  Federal Reserve building at dusk", "a TSMC chip fab") or an object ("racks of CoreWeave
  servers", "a Bank of America nameplate beside a Q3 EARNINGS report"). Labels are 1-3 words."""

STYLE = """Cinematic, photo-real 16:9 editorial cover for a financial markets newsletter. Dusk
lighting, deep navy and warm amber palette, dramatic depth of field. A dense collage of: {scene}.
{people} Large gold serif capital letters across the lower third read "{title}", spelled
exactly, with a thin gold rule beneath. No other words except the short labels on the screens,
logos and nameplates."""

PEOPLE = """In the foreground, large and in sharp focus, editorial portraits of {who}: recognisable
likenesses in their public roles, in dark business suits, with dignified expressions."""

GENERIC = """Two or three generic businesspeople in dark suits react in the foreground
(thoughtful, concerned); they must not resemble any real, recognisable person."""


class CoverArtist(StructuredAgent[CoverBrief]):
    name = "cover_artist"
    output_schema = CoverBrief
    tier = "fast"

    def system_prompt(self) -> str:
        return BRIEF

    def user_prompt(
        self, *, headline: str, stories: list[str], avoid: list[str], use: list[str]
    ) -> str:
        ask = (
            f"People: exactly {', '.join(use)}.\n\n"
            if use
            else f"Not these people, who were on the last covers: {', '.join(avoid)}.\n\n"
            if avoid
            else ""
        )
        return f"Date: {date.today():%B %-d, %Y}\n\n{ask}Headline: {headline}\n\nStories:\n\n" + "\n\n".join(stories)  # fmt: skip


def prompt(brief: CoverBrief, text: str, *, people: bool = True) -> str:
    """The image prompt. Code keeps only people tied to the post's `text`: named in it, or leading
    a company or institution it names (its CEO for NVIDIA), by full name (so a company listed as a
    person can't become a face), and clamps the title so a chatty brief can't fill the cover."""
    tied = [p for p in brief.people if p.name in text or (p.org.strip() and p.org in text)]
    named = [p for p in tied if len(p.name.split()) >= 2][:3] if people else []
    who = "; ".join(f"{p.name} ({p.role}), {p.look}" for p in named)
    title = " ".join(brief.title.upper().split()[:3])[:28]
    return STYLE.format(
        scene="; ".join(brief.scene[:5]),
        people=PEOPLE.format(who=who) if named else GENERIC,
        title=title,
    )


_NAME = re.compile(r"[A-Z][\w.'-]*(?: [A-Z][\w.'-]*){1,3}")  # "Jensen Huang", "Lisa D. Cook"


def holder(p: Person) -> str | None:
    """Who holds `p`'s role today, by one web search: for people the post doesn't name, because the
    brief model's knowledge can be out of date (it picked Jerome Powell as Fed chair in October
    2026, after his term as chair ended). None when the search fails or answers with no name."""
    from castelino.data import web_search

    try:
        answer, _ = web_search.search(
            "Answer with the person's full name only.",
            f"As of {date.today():%B %-d, %Y}, who is the {p.role} of {p.org}?",
        )
    except Exception:
        return None
    m = _NAME.fullmatch(answer.split("(")[0].strip().rstrip("."))  # drop an inline citation
    return m.group(0) if m else None


RECENT = 3  # covers back whose people can't appear again (user rule 2026-10-21: new faces)


def _log() -> Path:
    return get_settings().root / "data" / "cover_people.json"


def _rows() -> list[dict]:
    try:
        return json.loads(_log().read_text())
    except (OSError, ValueError):
        return []


def recent_people(key: str) -> list[str]:
    """Everyone on the last RECENT covers but `key`'s own (a redraw doesn't count against itself)."""
    rows = [r for r in _rows() if r["key"] != key][-RECENT:]
    return list(dict.fromkeys(n for r in rows for n in r["people"]))


def _remember(key: str, people: list[str]) -> None:
    from castelino.agents.update.fsio import atomic_write_text

    rows = [r for r in _rows() if r["key"] != key] + [{"key": key, "people": people}]
    _log().parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(_log(), json.dumps(rows[-20:]))


def draw(text: str, path: Path) -> None:
    from openai import OpenAI

    from castelino import benchmark

    cfg = get_settings()
    model, sent = cfg.cover.model, {"prompt": text, "size": cfg.cover.size}
    started = time.monotonic()
    try:
        r = OpenAI(api_key=cfg.openai_api_key, timeout=300).images.generate(
            model=model, prompt=text, size=cfg.cover.size, quality=cfg.cover.quality, n=1
        )
    except Exception as e:
        benchmark.record_call("cover_artist", model, sent, started=started, error=str(e)[:500])
        raise
    benchmark.record_call(
        "cover_artist", model, sent, str(path), started=started, tokens=benchmark.usage_of(r)
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(base64.b64decode(r.data[0].b64_json))


def make(
    path: Path, headline: str, stories: list[str], *, force: bool = False, use: list[str] = ()
) -> Path | None:
    """The cover PNG at `path`, drawn if missing (or `force`). `use` names the people (the
    analyst's pick); otherwise the brief picks, minus anyone on the last covers. None on any
    failure: a draft without a cover is today's behaviour, so the cover must never break the draft."""
    if path.exists() and not force:
        return path
    try:
        avoid = [] if use else recent_people(path.name)
        brief = CoverArtist()(headline=headline, stories=stories, avoid=avoid, use=list(use))
        text = "\n".join([headline, *stories, *use])  # a name the analyst gave counts as tied
        brief.people = [  # named in the post as is; anyone else by who holds the role today
            p if p.name in text else p.model_copy(update={"name": who})
            for p in brief.people
            if p.name in text or (who := holder(p))
        ]
        brief.people = [p for p in brief.people if p.name not in avoid]
        try:
            draw(prompt(brief, text), path)
        except Exception:  # e.g. the image model refused a real person: redraw with generic people
            if not brief.people:
                raise
            log.warning("cover: %s with people failed; redrawing without", path.name, exc_info=True)
            draw(prompt(brief, text, people=False), path)
        log.info(
            "cover: %s drew %r with %s", path.name, brief.title, [p.name for p in brief.people]
        )
        _remember(path.name, [p.name for p in brief.people])
        return path
    except Exception:
        log.warning("cover: %s failed; the draft goes out without one", path.name, exc_info=True)
        return None


def for_note(day: str, *, force: bool = False, use: list[str] = ()) -> Path | None:
    cfg = get_settings()
    updates = cfg.root / cfg.update_agent.updates_dir
    note = json.loads((updates / f"{day}.json").read_text())["note"]
    stories = [f"{i['title']}\n{i['body']}" for i in note.get("items", [])]
    return make(updates / "covers" / f"{day}.png", note["headline"], stories, force=force, use=use)


def for_week(week: str, *, force: bool = False, use: list[str] = ()) -> Path | None:
    cfg = get_settings()
    deep = cfg.root / cfg.deep_dive.data_dir
    report = json.loads((deep / f"{week}.json").read_text())["report"]
    stories = [f"{s['title']}\n" + " ".join(s.get("what_happened", [])) for s in report["sections"]]
    return make(deep / "covers" / f"{week}.png", report["title"], stories, force=force, use=use)


def for_theme(run: dict, *, force: bool = False, use: list[str] = ()) -> Path | None:
    """A Theme Charts run (agents/themes.py): the theme, its why and its three signals."""
    cfg = get_settings()
    stories = [run["why"], *(f"{s['headline']}\n{s['note']}" for s in run.get("signals", []))]
    path = cfg.root / cfg.themes.data_dir / "covers" / f"{run['run_id']}.png"
    return make(path, run["theme"], stories, force=force, use=use)


if __name__ == "__main__":
    from castelino import substack

    logging.basicConfig(level=logging.INFO)
    key = sys.argv[1]
    use = [n.strip() for n in sys.argv[2].split(",") if n.strip()] if len(sys.argv) > 2 else []
    cfg = get_settings()
    kind = "week" if "-W" in key else "theme" if key.endswith(("-am", "-pm")) else "note"
    dirs = {
        "week": cfg.deep_dive.data_dir,
        "theme": cfg.themes.data_dir,
        "note": cfg.update_agent.updates_dir,
    }
    base = cfg.root / dirs[kind]
    if kind == "theme":
        png = for_theme(json.loads((base / f"{key}.json").read_text()), force=True, use=use)
    else:
        png = (for_week if kind == "week" else for_note)(key, force=True, use=use)
    if not png:
        sys.exit("cover: failed (see the log above)")
    print("cover:", png)
    print("substack:", substack.set_cover(base / "substack" / f"{key}.json", png))
