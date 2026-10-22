"""SEC EDGAR: latest 10-K / 10-Q text for a ticker. SEC requires a contact User-Agent and <= 10 req/s."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from datetime import date

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

    def earnings_release(self, ticker: str, day: date) -> tuple[str, str] | None:
        """(text, address) of the earnings release filed on or after `day`: exhibit 99.1 of an 8-K
        with item 2.02 (results of operations). None until it's filed. One filed after 17:30 ET gets
        the next business day's date, hence "on or after"."""
        cik = self._cik(ticker)
        if cik is None:
            return None
        recent = self._get(_SUBS_URL.format(cik=cik)).json()["filings"]["recent"]
        for i, form in enumerate(recent["form"]):
            if recent["filingDate"][i] < day.isoformat():
                return None  # newest first: nothing filed since the report day
            if form.startswith("8-K") and "2.02" in recent["items"][i]:
                acc = recent["accessionNumber"][i].replace("-", "")
                index = f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/index.json"
                docs = self._get(index).json()["directory"]["item"]
                pages = [
                    d
                    for d in docs
                    if d["name"].endswith((".htm", ".html"))
                    and d["name"] != recent["primaryDocument"][i]
                    and not re.fullmatch(r"R\d+\.htm|.*index.*", d["name"])
                ]
                ex = next((d for d in pages if re.search(r"99[._-]?0?1", d["name"])), None)
                ex = ex or max(pages, key=lambda d: int(d.get("size") or 0), default=None)
                if ex:
                    url = _DOC_URL.format(cik=cik, acc=acc, doc=ex["name"])
                    return _html_to_text(self._get(url).text), url
        return None
