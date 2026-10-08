"""Search-grounded LLM calls via OpenAI's Responses API `web_search` tool.

Replaces the Perplexity Sonar calls (Deep Research sub-agents, persona
corpus fallback, non-US calendar, Trump backtest archive). Uses the same
OPENAI_API_KEY as every agent; the model is `web_search.model` in config.yaml.
"""

from __future__ import annotations

import os

from castelino.config import get_settings


def has_key() -> bool:
    return bool(os.environ.get("OPENAI_API_KEY", "").strip())


def search_cited(
    system: str, user: str, model: str | None = None
) -> tuple[str, list[tuple[str, str, int, int]]]:
    """One web-search call -> (raw answer text, [(title, url, start, end)] per citation).

    start/end index into the returned text (not stripped). Raises on API failure.
    """
    from openai import OpenAI

    cfg = get_settings()
    # a reasoning model + live search often runs past the 60 s default; a timeout just wastes the call
    client = OpenAI(api_key=cfg.openai_api_key, timeout=max(cfg.openai.request_timeout_s, 180))
    resp = client.responses.create(
        model=model or cfg.web_search.model,
        instructions=system,
        input=user,
        tools=[{"type": "web_search"}],
    )
    cites: list[tuple[str, str, int, int]] = []
    for item in resp.output:
        for part in getattr(item, "content", None) or []:
            for ann in getattr(part, "annotations", None) or []:
                url = getattr(ann, "url", None)
                if getattr(ann, "type", "") == "url_citation" and url:
                    cites.append(
                        (
                            getattr(ann, "title", None) or url,
                            url,
                            int(getattr(ann, "start_index", 0) or 0),
                            int(getattr(ann, "end_index", 0) or 0),
                        )
                    )
    return resp.output_text or "", cites


def search(system: str, user: str, model: str | None = None) -> tuple[str, list[tuple[str, str]]]:
    """Run one web-search-grounded call -> (answer text, [(title, url)] cited).

    Raises on any API failure; callers decide how to degrade.
    """
    text, cites = search_cited(system, user, model)
    sources: list[tuple[str, str]] = []
    seen: set[str] = set()
    for title, url, _, _ in cites:
        if url not in seen:
            seen.add(url)
            sources.append((title, url))
    return text.strip(), sources
