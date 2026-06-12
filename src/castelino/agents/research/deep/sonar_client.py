"""Sonar search client. Real impl hits Perplexity via the OpenAI SDK
(base_url=https://api.perplexity.ai); FakeSonarClient is for tests.

Perplexity returns the answer text in choices[0].message.content and a
top-level `citations` list of URLs on the response object.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod

from castelino.agents.research.deep.models import SourceRef
from castelino.config import get_settings

log = logging.getLogger(__name__)


class SonarResult:
    def __init__(self, *, content: str, sources: list[SourceRef]):
        self.content = content
        self.sources = sources


class SonarClient(ABC):
    @abstractmethod
    def search(self, query: str) -> SonarResult: ...


_SONAR_SYSTEM = (
    "You are a meticulous web research assistant. Answer the question using "
    "current, real web sources. Be specific and factual. Cite figures and "
    "dates. If you are unsure, say so rather than guessing."
)


class PerplexitySonarClient(SonarClient):
    """Real impl. Returns an empty result (no raise) when the key is unset
    or the call fails — matches the codebase 'returns [] on failure' rule."""

    def search(self, query: str) -> SonarResult:
        cfg = get_settings()
        api_key = cfg.perplexity_api_key
        if not api_key:
            log.debug("PERPLEXITY_API_KEY not set — Sonar search skipped")
            return SonarResult(content="", sources=[])
        try:
            from openai import OpenAI

            client = OpenAI(
                api_key=api_key,
                base_url="https://api.perplexity.ai",
                timeout=cfg.openai.request_timeout_s,
            )
            resp = client.chat.completions.create(
                model=cfg.sonar.model,
                messages=[
                    {"role": "system", "content": _SONAR_SYSTEM},
                    {"role": "user", "content": query},
                ],
                temperature=0.0,
            )
            content = (resp.choices[0].message.content or "").strip()
            urls = getattr(resp, "citations", None) or []
            sources = [SourceRef(title=u, url=u, snippet="") for u in urls]
            return SonarResult(content=content, sources=sources)
        except Exception as e:  # noqa: BLE001
            log.warning("Sonar search failed for %r: %s", query[:80], e)
            return SonarResult(content="", sources=[])


class FakeSonarClient(SonarClient):
    """Deterministic test double. Register substring → SonarResult."""

    def __init__(self, default: SonarResult | None = None):
        self._by_substr: list[tuple[str, SonarResult]] = []
        self._default = default
        self.call_count = 0
        self.queries: list[str] = []

    def register(self, substring: str, result: SonarResult) -> None:
        self._by_substr.append((substring.lower(), result))

    def search(self, query: str) -> SonarResult:
        self.call_count += 1
        self.queries.append(query)
        ql = query.lower()
        for sub, res in self._by_substr:
            if sub in ql:
                return res
        if self._default is not None:
            return self._default
        return SonarResult(content="", sources=[])
