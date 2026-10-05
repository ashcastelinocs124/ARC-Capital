"""SEC EDGAR: latest 10-K / 10-Q text for a ticker. SEC requires a contact User-Agent and <= 10 req/s."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass

import httpx
from bs4 import BeautifulSoup


class EdgarError(RuntimeError):
    pass


@dataclass(frozen=True)
class Filing:
    ticker: str
    accession: str
    form: str
    url: str  # primary document; fetched only when the filing is not cached yet


_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
_SUBS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
_DOC_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/{doc}"
_FORMS = {"10-K", "10-Q"}


def _html_to_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "ix:header"]):
        tag.decompose()
    return re.sub(r"\s+", " ", soup.get_text(" ")).strip()


class EdgarClient:
    def __init__(
        self,
        user_agent: str,
        http: httpx.Client | None = None,
        min_interval: float = 0.12,
        sleep=time.sleep,
    ):
        if not user_agent.strip():
            raise EdgarError(
                "adoption.sec_user_agent is empty: SEC requires a contact string such as "
                "'ARC Research you@example.com'. Set it in config.yaml."
            )
        self._http = http or httpx.Client(
            headers={"User-Agent": user_agent}, timeout=30, follow_redirects=True
        )
        self._min_interval = min_interval
        self._sleep = sleep
        self._ciks: dict[str, int] | None = None

    def _get(self, url: str) -> httpx.Response:
        self._sleep(self._min_interval)
        r = self._http.get(url)
        r.raise_for_status()
        return r

    def _cik(self, ticker: str) -> int | None:
        if self._ciks is None:
            data = self._get(_TICKERS_URL).json()
            self._ciks = {row["ticker"].upper(): int(row["cik_str"]) for row in data.values()}
        return self._ciks.get(ticker.upper())

    def latest_filing(self, ticker: str) -> Filing | None:
        cik = self._cik(ticker)
        if cik is None:
            return None
        recent = self._get(_SUBS_URL.format(cik=cik)).json()["filings"]["recent"]
        for i, form in enumerate(recent["form"]):
            if form in _FORMS:
                accession = recent["accessionNumber"][i]
                url = _DOC_URL.format(
                    cik=cik, acc=accession.replace("-", ""), doc=recent["primaryDocument"][i]
                )
                return Filing(ticker.upper(), accession, form, url)
        return None

    def filing_text(self, filing: Filing) -> str:
        return _html_to_text(self._get(filing.url).text)
