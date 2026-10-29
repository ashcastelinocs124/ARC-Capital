"""Cover art for the Morning Note, Weekly Deep Dive and Theme Charts Substack drafts.

The Cover Artist (fast tier) turns the finished post into a 2-3 word title, one visual idea for the
main story (a tug of war, a see-saw), 1 or 2 public figures acting in it and a few background
details; code keeps only people tied to the post and the image model draws it once, in the next of
four styles (`STYLES`, so no two covers in a row look alike; user ask 2026-10-29: more creative,
bright not gloomy, people with tension in their faces, no numbers). If the image model refuses a real person, it redraws once with
generic people. Nobody on the last 3 covers appears again (`RECENT`, logged with each cover's
style in `data/cover_people.json`), so one face doesn't top every post. The PNG is cached next to the
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
    concept: str  # one visual metaphor for the main story, people by role only
    people: list[Person]
    scene: list[str]


BRIEF = """You design the cover image for an ARC Research markets newsletter post. The cover must
make a reader stop scrolling: one clever visual idea, not a collage of chart screens.
From its headline and stories, return:
- title: 2 or 3 punchy words naming the main story, like a magazine cover ("INFLATION HEATS UP",
  "MIXED SIGNALS", "PRICE PRESSURE"). No numbers, tickers or punctuation.
- concept: ONE visual metaphor for the main story, in one sentence: a concrete, surprising scene a
  reader gets in a second. Examples: "a tug of war on Wall Street between a giant Fed seal and an
  oil barrel, Treasury notes caught in the middle"; "a traffic light over Wall Street with red,
  amber and green all lit at once"; "a gleaming cloud-shaped data centre held down by ropes tied
  to a cash register". Name the companies or institutions in it so their logos or nameplates show.
  Avoid people staring at screens and avoid charts, unless a chart is itself the joke. Refer to
  people in it by role ("the Fed chair"), never by name: their names go in people.
  The mood is bright, clever and upbeat even on bad news: show tension with balance, weight, a
  race or a tug of war, never with fire, smoke, storms, cracks, ruins or sad faces.
- people: 1 or 2 public figures acting inside the concept (pulling the rope, steadying the scale,
  running the race), the most newsworthy first. Always at least one: every post covers a company,
  a central bank or a government, so take its leader. Prefer anyone the post names, then the
  leader of a company the stories name (Tesla -> Elon Musk, NVIDIA -> Jensen Huang), never the
  leader of a company the stories don't name. A central banker or minister only when a story is
  about that institution's own decision or that person's own words. Give the role as of the date
  given; if unsure who holds it, give your best guess (code checks it). People only, by full name.
  For each: role, org (the company or institution exactly as the post writes it, e.g. "NVIDIA",
  "Fed") and look = what they are doing inside the concept, with tension in their face (gritted
  teeth, furrowed brow, straining), never fear or sadness ("straining at the rope, jaw set").
- scene: 1 to 3 small background details for the other stories ("an oil tanker on the horizon",
  "a Vertiv cooling unit"). Labels are 1-3 words."""

# The art style rotates in this order, one step per cover (next_style); the gold title is the constant.
STYLES = {
    "photo": "Photo-real editorial photograph in bright, clear morning light under a blue sky: crisp, "
    "optimistic, navy and warm amber accents, shallow depth of field.",
    "illustration": "Bold editorial magazine-cover illustration: flat colour shapes, clean confident "
    "lines on a light cream background, a cheerful palette of navy, sky blue, amber and teal, subtle "
    "paper grain.",
    "poster": "1930s art deco travel-poster lithograph: strong geometry, sunlit sunburst rays, "
    "screen-printed texture, a bright palette of sky blue, gold, cream and navy.",
    "papercut": "Layered paper-cut diorama photographed in a studio: cut card in cream, sky blue, "
    "navy and amber, soft daylight shadows between the layers, shallow depth of field.",
}

STYLE = """A 16:9 cover image for a financial markets newsletter. {style} The mood is light and
upbeat: a bright, open background, no fire, smoke, storm clouds or gloom.
The idea: {concept}. {scene}
{people} No other recognisable real person appears: never draw Jerome Powell or anyone who looks
like him, as he is no longer Fed chair (Kevin Warsh is). Add no other people; if the idea needs a
crowd, it is small generic figures. Large gold serif capital letters across the lower third read
"{title}", spelled exactly, with a thin gold rule beneath. No other words except short labels,
logos and nameplates, and no numbers, prices or percentages anywhere in the image."""

PEOPLE = """In the foreground, large and in sharp focus, {who}: recognisable likenesses in their
public roles, in business suits, faces tense with effort and focus, dignified, never a caricature."""

GENERIC = """Anyone the idea needs is a generic businessperson in a dark suit, face tense with
effort, who must not resemble any real, recognisable person."""


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


def prompt(brief: CoverBrief, text: str, *, people: bool = True, style: str = "photo") -> str:
    """The image prompt. Code keeps only people tied to the post's `text`: named in it, or leading
    a company or institution it names (its CEO for NVIDIA), by full name (so a company listed as a
    person can't become a face), and clamps the title so a chatty brief can't fill the cover."""
    tied = [p for p in brief.people if p.name in text or (p.org.strip() and p.org in text)]
    named = [p for p in tied if len(p.name.split()) >= 2][:2] if people else []
    who = "; ".join(f"{p.name} ({p.role}), {p.look}" for p in named)
    title = " ".join(brief.title.upper().split()[:3])[:28]
    return STYLE.format(
        style=STYLES[style],
        concept=brief.concept.strip().rstrip("."),
        scene=f"In the background: {'; '.join(brief.scene[:3])}." if brief.scene else "",
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


def next_style(key: str) -> str:
    """The style after the previous cover's (`key`'s own row doesn't count, so a redraw keeps the
    rotation); rows from before the rotation were all photo."""
    rows = [r for r in _rows() if r["key"] != key]
    names = list(STYLES)
    last = rows[-1].get("style", "photo") if rows else None
    return names[(names.index(last) + 1) % len(names)] if last in names else names[0]


def _remember(key: str, people: list[str], style: str = "photo") -> None:
    from castelino.agents.update.fsio import atomic_write_text

    rows = [r for r in _rows() if r["key"] != key] + [
        {"key": key, "people": people, "style": style}
    ]
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
        style = next_style(path.name)
        try:
            draw(prompt(brief, text, style=style), path)
        except Exception:  # e.g. the image model refused a real person: redraw with generic people
            if not brief.people:
                raise
            log.warning("cover: %s with people failed; redrawing without", path.name, exc_info=True)
            draw(prompt(brief, text, people=False, style=style), path)
        log.info(
            "cover: %s drew %r (%s) with %s",
            path.name,
            brief.title,
            style,
            [p.name for p in brief.people],
        )
        _remember(path.name, [p.name for p in brief.people], style)
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
