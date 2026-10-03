"""Web search client for Deep Research sub-agents. Real impl is OpenAI's
Responses API `web_search` tool (data/web_search.py); FakeSonarClient is for
tests. (Sonar* names kept from the Perplexity version so callers/tests are
unchanged.)
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod

from castelino.agents.research.deep.models import SourceRef
from castelino.data import web_search

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


class OpenAIWebSearchClient(SonarClient):
    """Real impl. Returns an empty result (no raise) when the key is unset
    or the call fails — matches the codebase 'returns [] on failure' rule."""

    def search(self, query: str) -> SonarResult:
        if not web_search.has_key():
            log.debug("OPENAI_API_KEY not set — web search skipped")
            return SonarResult(content="", sources=[])
        try:
            content, cited = web_search.search(_SONAR_SYSTEM, query)
            sources = [SourceRef(title=t, url=u, snippet="") for t, u in cited]
            return SonarResult(content=content, sources=sources)
        except Exception as e:  # noqa: BLE001
            log.warning("web search failed for %r: %s", query[:80], e)
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
