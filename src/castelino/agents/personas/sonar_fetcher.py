"""Perplexity Sonar fallback for persona corpus building.

Used when a primary scraper (RSS / YouTube / PDF) returns thin results.
Sonar does web search with citations — we ask it to find recent
commentary by the persona and return summaries grounded in real sources.

Cached aggressively (24h TTL) since Sonar calls cost money. Cache lives
under data/cache/sonar_personas/<persona_id>.json.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

from openai import OpenAI

from castelino.agents.personas.corpus import CorpusDoc
from castelino.config import get_settings

log = logging.getLogger(__name__)


_CACHE_TTL_HOURS = 24


_PROMPT_TEMPLATE = """\
Find {max_items} recent (within the last 12 months) opinion pieces,
columns, speeches, interviews, or commentary published by {persona_name}.

For EACH item return a JSON object with these exact keys:
  - "title": the piece's title
  - "date": ISO 8601 date (YYYY-MM-DD), best estimate if exact unknown
  - "source_url": canonical URL where the piece can be found
  - "summary": 2-3 paragraphs (about 150-250 words) capturing {persona_name}'s
               core argument in their own voice. Stay close to what they
               actually said. Quote where appropriate. Do NOT paraphrase
               into generic summary-speak.

Return ONLY a JSON array of these objects. No prefatory text, no markdown
fences. If you cannot find {max_items} items, return as many as you can.
"""


def _cache_dir() -> Path:
    return get_settings().resolved_paths.cache / "sonar_personas"


def _cache_path(persona_id: str) -> Path:
    return _cache_dir() / f"{persona_id}.json"


def _read_cache(persona_id: str) -> list[CorpusDoc] | None:
    p = _cache_path(persona_id)
    if not p.exists():
        return None
    mtime = datetime.fromtimestamp(p.stat().st_mtime, tz=UTC)
    if (datetime.now(UTC) - mtime) > timedelta(hours=_CACHE_TTL_HOURS):
        return None
    try:
        raw = json.loads(p.read_text())
        return [
            CorpusDoc(
                source=d["source"],
                date=datetime.fromisoformat(d["date"]),
                title=d["title"],
                text=d["text"],
                url=d["url"],
            )
            for d in raw
        ]
    except Exception as e:
        log.warning("sonar persona cache for %s corrupt: %s", persona_id, e)
        return None


def _write_cache(persona_id: str, docs: list[CorpusDoc]) -> None:
    d = _cache_dir()
    d.mkdir(parents=True, exist_ok=True)
    payload = [
        {
            "source": doc.source,
            "date": doc.date.isoformat(),
            "title": doc.title,
            "text": doc.text,
            "url": doc.url,
        }
        for doc in docs
    ]
    _cache_path(persona_id).write_text(json.dumps(payload, indent=2))


_JSON_FENCE_RX = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def _parse_sonar_response(raw: str) -> list[dict]:
    """Sonar sometimes wraps JSON in markdown fences; tolerate both."""
    text = raw.strip()
    m = _JSON_FENCE_RX.search(text)
    if m:
        text = m.group(1).strip()
    # Find the first '[' and matching final ']' to be tolerant of preamble
    start = text.find("[")
    end = text.rfind("]")
    if start == -1 or end == -1:
        raise ValueError(f"no JSON array in Sonar response: {raw[:200]}")
    return json.loads(text[start : end + 1])


def fetch_persona_via_sonar(
    *,
    persona_id: str,
    persona_name: str,
    max_items: int = 10,
) -> list[CorpusDoc]:
    """Ask Sonar for recent persona commentary. Cached. Returns [] on failure."""
    cached = _read_cache(persona_id)
    if cached is not None:
        log.info("sonar persona cache hit: %s (%d docs)", persona_id, len(cached))
        return cached

    cfg = get_settings()
    api_key = cfg.perplexity_api_key
    if not api_key:
        log.debug("PERPLEXITY_API_KEY not set — skipping Sonar persona fallback")
        return []

    prompt = _PROMPT_TEMPLATE.format(
        persona_name=persona_name, max_items=max_items,
    )
    try:
        client = OpenAI(api_key=api_key, base_url="https://api.perplexity.ai")
        resp = client.chat.completions.create(
            model=cfg.sonar.model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a research assistant who finds and summarizes "
                        "real published commentary by named public figures. "
                        "Stay grounded in actual sources you can cite. Return "
                        "JSON only."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.0,
        )
        raw = (resp.choices[0].message.content or "").strip()
        items = _parse_sonar_response(raw)
    except Exception as e:
        log.warning("Sonar persona fetch failed for %s: %s", persona_id, e)
        return []

    docs: list[CorpusDoc] = []
    for it in items:
        try:
            date_str = it.get("date", "")
            try:
                date = datetime.fromisoformat(date_str).replace(tzinfo=UTC)
            except Exception:
                date = datetime.now(UTC)
            url = it.get("source_url") or ""
            text = (it.get("summary") or "").strip()
            if len(text) < 100:
                continue
            slug = (
                url.rsplit("/", 1)[-1]
                or it.get("title", "piece").lower().replace(" ", "_")[:40]
            )
            docs.append(CorpusDoc(
                source=f"sonar_{persona_id}_{slug}",
                date=date,
                title=it.get("title", "(untitled)"),
                text=text,
                url=url,
            ))
        except Exception as e:
            log.warning("skipping malformed sonar item for %s: %s", persona_id, e)
            continue

    log.info("sonar persona fetch %s → %d docs", persona_id, len(docs))
    if docs:
        _write_cache(persona_id, docs)
    return docs
