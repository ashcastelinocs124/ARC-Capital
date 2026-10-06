"""Open AI/ML engineer postings from public job-board data APIs.

Greenhouse, Lever, Workday, Oracle Recruiting and UKG (the ATS vendors), plus Amazon's own careers
search, all expose the JSON their careers pages load. Companies on other systems get no Hire
pillar (missing, not zero) unless they have a saved recipe (sources/recipes.py), which is
replayed here the same way.
"""

from __future__ import annotations

import csv
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import httpx

from castelino.adoption.sources import recipes

log = logging.getLogger(__name__)

_AI_TERM = re.compile(
    r"\bmachine learning\b|\bML\b|\bAI\b|\bartificial intelligence\b|\bdeep learning\b|\bNLP\b|\bLLM\b"
    r"|\bapplied scientist\b|\bresearch scientist\b|\bdata scientist\b",
    re.I,
)
_ROLE_TERM = re.compile(r"\b(engineer|scientist|researcher|developer)\b", re.I)
# Paged boards are read up to Workday's own listing cap, so every company is counted on the same
# basis: at most its first 2,000 open postings.
MAX_POSTINGS = 2000


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
    def __init__(
        self,
        boards: dict[str, tuple[str, str]],
        http: httpx.Client | None = None,
        recipes_dir: Path | None = None,
    ):
        self._boards = boards
        self._recipes_dir = recipes_dir
        # No zstd: httpx fails on a second zstd reply from the same server (seen on amazon.jobs).
        self._http = http or httpx.Client(
            timeout=30, follow_redirects=True, headers={"Accept-Encoding": "gzip, deflate"}
        )

    def _titles(self, ats: str, token: str) -> list[str] | None:
        if ats == "greenhouse":
            r = self._http.get(f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs")
            r.raise_for_status()
            return [j["title"] for j in r.json()["jobs"]]
        if ats == "lever":
            r = self._http.get(f"https://api.lever.co/v0/postings/{token}", params={"mode": "json"})
            r.raise_for_status()
            return [p["text"] for p in r.json()]
        if ats == "workday":
            return self._workday_titles(token)
        if ats == "oracle":
            return self._oracle_titles(token)
        if ats == "ukg":
            return self._ukg_titles(token)
        if ats == "amazon":
            return self._amazon_titles()
        if ats == "recipe":
            return self._recipe_titles(token)
        log.warning("unsupported ATS %r for board %s", ats, token)
        return None

    @staticmethod
    def _paged(fetch_page: Callable[[int, int], list[str | None]], size: int) -> list[str]:
        """Read pages of `size` until an empty page or MAX_POSTINGS; drop postings with no title.

        Stops on empty, not short: Oracle sometimes returns 24 of 25 mid-listing.
        """
        titles: list[str] = []
        for offset in range(0, MAX_POSTINGS, size):
            page = fetch_page(offset, size)
            titles += [t for t in page if t]  # a few Workday postings have no title
            if not page:
                break
        return titles

    def _workday_titles(self, token: str) -> list[str]:
        """token = "tenant/wdN/site", from https://<tenant>.<wdN>.myworkdayjobs.com/<site>."""
        tenant, wd, site = token.split("/")
        url = f"https://{tenant}.{wd}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs"

        def page(offset: int, size: int) -> list[str | None]:
            body = {"limit": size, "offset": offset, "searchText": "", "appliedFacets": {}}
            r = self._http.post(url, json=body)
            r.raise_for_status()
            return [j.get("title") for j in r.json().get("jobPostings", [])]

        return self._paged(page, 20)

    def _oracle_titles(self, token: str) -> list[str]:
        """token = "host/siteNumber", e.g. jpmc.fa.oraclecloud.com/CX_1002 (Oracle Recruiting Cloud)."""
        host, site = token.split("/")
        url = f"https://{host}/hcmRestApi/resources/latest/recruitingCEJobRequisitions"

        def page(offset: int, size: int) -> list[str | None]:
            finder = f"findReqs;siteNumber={site},limit={size},offset={offset}"
            r = self._http.get(
                url, params={"onlyData": "true", "expand": "requisitionList", "finder": finder}
            )
            r.raise_for_status()
            return [j.get("Title") for j in r.json()["items"][0]["requisitionList"]]

        return self._paged(page, 25)

    def _ukg_titles(self, token: str) -> list[str]:
        """token = "host/tenant/boardId", from https://<host>/<tenant>/JobBoard/<boardId>/ (UKG)."""
        host, tenant, board = token.split("/")
        url = f"https://{host}/{tenant}/JobBoard/{board}/JobBoardView/LoadSearchResults"

        def page(offset: int, size: int) -> list[str | None]:
            search = {"Top": size, "Skip": offset, "QueryString": "", "Filters": []}
            r = self._http.post(url, json={"opportunitySearch": search})
            r.raise_for_status()
            return [j.get("Title") for j in r.json()["opportunities"]]

        return self._paged(page, 50)

    def _recipe_titles(self, token: str) -> list[str] | None:
        """token = recipe file stem in recipes_dir (written by the Recipe Writer, layer 3)."""
        if self._recipes_dir is None:
            return None
        try:
            return recipes.replay(recipes.load(self._recipes_dir / f"{token}.json"), self._http)
        except Exception as e:  # noqa: BLE001 - missing file, no Playwright, site changed: Hire missing
            log.warning("recipe %s failed: %s", token, e)
            return None

    def _amazon_titles(self) -> list[str]:
        def page(offset: int, size: int) -> list[str | None]:
            r = self._http.get(
                "https://www.amazon.jobs/en/search.json",
                params={"result_limit": size, "offset": offset},
            )
            r.raise_for_status()
            return [j.get("title") for j in r.json()["jobs"]]

        return self._paged(page, 100)

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
