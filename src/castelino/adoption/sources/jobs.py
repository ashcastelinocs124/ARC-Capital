"""Open AI/ML engineer postings from Greenhouse and Lever public boards.

v1 covers the two ATS vendors with public JSON APIs. Companies on other systems get no Hire pillar
(missing, not zero); the career-page fallback is deferred.
"""

from __future__ import annotations

import csv
import logging
import re
from dataclasses import dataclass
from pathlib import Path

import httpx

log = logging.getLogger(__name__)

_AI_TERM = re.compile(
    r"\bmachine learning\b|\bML\b|\bAI\b|\bartificial intelligence\b|\bdeep learning\b|\bNLP\b|\bLLM\b"
    r"|\bapplied scientist\b|\bresearch scientist\b|\bdata scientist\b",
    re.I,
)
_ROLE_TERM = re.compile(r"\b(engineer|scientist|researcher|developer)\b", re.I)


def is_ai_ml_role(title: str) -> bool:
    return bool(_AI_TERM.search(title) and _ROLE_TERM.search(title))


@dataclass(frozen=True)
class JobCounts:
    ai: int
    total: int


def load_boards(path: Path) -> dict[str, tuple[str, str]]:
    with open(path, newline="") as f:
        return {
            r["ticker"].strip().upper(): (r["ats"].strip().lower(), r["token"].strip())
            for r in csv.DictReader(f)
        }


class JobsFetcher:
    def __init__(self, boards: dict[str, tuple[str, str]], http: httpx.Client | None = None):
        self._boards = boards
        self._http = http or httpx.Client(timeout=30, follow_redirects=True)

    def _titles(self, ats: str, token: str) -> list[str] | None:
        if ats == "greenhouse":
            r = self._http.get(f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs")
            r.raise_for_status()
            return [j["title"] for j in r.json()["jobs"]]
        if ats == "lever":
            r = self._http.get(f"https://api.lever.co/v0/postings/{token}", params={"mode": "json"})
            r.raise_for_status()
            return [p["text"] for p in r.json()]
        log.warning("unsupported ATS %r for board %s", ats, token)
        return None

    def counts(self, ticker: str) -> JobCounts | None:
        board = self._boards.get(ticker.upper())
        if board is None:
            return None
        try:
            titles = self._titles(*board)
        except (httpx.HTTPError, ValueError, KeyError) as e:
            log.warning("job board fetch failed for %s: %s", ticker, e)
            return None
        if titles is None:
            return None
        return JobCounts(ai=sum(is_ai_ml_role(t) for t in titles), total=len(titles))
