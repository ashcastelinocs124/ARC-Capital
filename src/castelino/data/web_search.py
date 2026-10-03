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


def search(system: str, user: str) -> tuple[str, list[tuple[str, str]]]:
    """Run one web-search-grounded call -> (answer text, [(title, url)] cited).

    Raises on any API failure; callers decide how to degrade.
    """
    from openai import OpenAI

    cfg = get_settings()
    client = OpenAI(api_key=cfg.openai_api_key, timeout=cfg.openai.request_timeout_s)
    resp = client.responses.create(
        model=cfg.web_search.model,
        instructions=system,
        input=user,
        tools=[{"type": "web_search"}],
    )
    sources: list[tuple[str, str]] = []
    seen: set[str] = set()
    for item in resp.output:
        for part in getattr(item, "content", None) or []:
            for ann in getattr(part, "annotations", None) or []:
                url = getattr(ann, "url", None)
                if getattr(ann, "type", "") == "url_citation" and url and url not in seen:
                    seen.add(url)
                    sources.append((getattr(ann, "title", None) or url, url))
    return (resp.output_text or "").strip(), sources
