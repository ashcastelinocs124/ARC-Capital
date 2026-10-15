"""Cover art for the Morning Note and Weekly Deep Dive Substack drafts.

The Cover Artist (fast tier) turns the finished post into a 2-3 word title, the public figures
it names (Fed officials, CEOs) and a few things to draw; code keeps only people whose name is in
the post, wraps it all in one fixed style (the look of the hand-made covers of October 2026) and
the image model draws it once. If the image model refuses a real person, it redraws once with
generic people. The PNG is cached next to the post's data, so a rerun never pays
twice. substack.push() asks for a cover only when the draft has none, so a cover set by hand in
Substack is never replaced. The site and X read Substack's cover, so nothing else changes.

Redo one: `uv run python -m castelino.cover <YYYY-MM-DD | YYYY-Www>` redraws it and replaces
the draft's cover (an unpublished draft only).
"""

from __future__ import annotations

import base64
import json
import logging
import sys
import time
from pathlib import Path

from pydantic import BaseModel

from castelino.agents.base import StructuredAgent
from castelino.config import get_settings

log = logging.getLogger(__name__)


class Person(BaseModel):
    name: str  # exactly as the post writes it
    role: str  # "San Francisco Fed President", "Nvidia CEO"
    look: str  # "thoughtful, studying a report"


class CoverBrief(BaseModel):
    title: str
    people: list[Person]
    scene: list[str]


BRIEF = """You design the cover image for an ARC Research markets newsletter post.
From its headline and stories, return:
- title: 2 or 3 punchy words naming the main story, like a magazine cover ("INFLATION HEATS UP",
  "MIXED SIGNALS", "PRICE PRESSURE"). No numbers, tickers or punctuation.
- people: up to 3 public figures at the centre of the main stories (Fed officials, central
  bankers, CEOs, finance ministers), the most newsworthy first. Only people the post names: copy
  each name exactly as written there, never add one from your own knowledge. Give their public
  role and a dignified, newsroom look ("thoughtful, hand on chin", "studying a report",
  "speaking at a podium"). Empty if the post names nobody.
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

    def user_prompt(self, *, headline: str, stories: list[str]) -> str:
        return f"Headline: {headline}\n\nStories:\n\n" + "\n\n".join(stories)


def prompt(brief: CoverBrief, text: str, *, people: bool = True) -> str:
    """The image prompt. Code keeps only people the post's `text` names (so the model can't add
    someone) and clamps the title so a chatty brief can't fill the cover with words."""
    named = [p for p in brief.people if p.name.strip() and p.name in text][:3] if people else []
    who = "; ".join(f"{p.name} ({p.role}), {p.look}" for p in named)
    title = " ".join(brief.title.upper().split()[:3])[:28]
    return STYLE.format(
        scene="; ".join(brief.scene[:5]),
        people=PEOPLE.format(who=who) if named else GENERIC,
        title=title,
    )


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


def make(path: Path, headline: str, stories: list[str], *, force: bool = False) -> Path | None:
    """The cover PNG at `path`, drawn if missing (or `force`). None on any failure: a draft
    without a cover is today's behaviour, so the cover must never break the draft."""
    if path.exists() and not force:
        return path
    try:
        brief = CoverArtist()(headline=headline, stories=stories)
        text = "\n".join([headline, *stories])
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
        return path
    except Exception:
        log.warning("cover: %s failed; the draft goes out without one", path.name, exc_info=True)
        return None


def for_note(day: str, *, force: bool = False) -> Path | None:
    cfg = get_settings()
    updates = cfg.root / cfg.update_agent.updates_dir
    note = json.loads((updates / f"{day}.json").read_text())["note"]
    stories = [f"{i['title']}\n{i['body']}" for i in note.get("items", [])]
    return make(updates / "covers" / f"{day}.png", note["headline"], stories, force=force)


def for_week(week: str, *, force: bool = False) -> Path | None:
    cfg = get_settings()
    deep = cfg.root / cfg.deep_dive.data_dir
    report = json.loads((deep / f"{week}.json").read_text())["report"]
    stories = [f"{s['title']}\n" + " ".join(s.get("what_happened", [])) for s in report["sections"]]
    return make(deep / "covers" / f"{week}.png", report["title"], stories, force=force)


if __name__ == "__main__":
    from castelino import substack

    logging.basicConfig(level=logging.INFO)
    key = sys.argv[1]
    weekly = "-W" in key
    png = (for_week if weekly else for_note)(key, force=True)
    if not png:
        sys.exit("cover: failed (see the log above)")
    cfg = get_settings()
    base = cfg.root / (cfg.deep_dive.data_dir if weekly else cfg.update_agent.updates_dir)
    print("cover:", png)
    print("substack:", substack.set_cover(base / "substack" / f"{key}.json", png))
