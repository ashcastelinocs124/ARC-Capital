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


@dataclass(frozen=True)
class Release:
    """An earnings release: exhibit 99.1 of an 8-K with item 2.02, or of a 6-K (foreign filers)."""

    ticker: str
    accession: str
    form: str
    filed: str
    url: str


_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
_SUBS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
_FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
_SIX_K_SCAN = (
    30  # foreign filers send many 6-Ks (deals, meetings, offerings); look at this many at most
)
# A 6-K earnings release says so in its headline ("second quarter 2026 financial results",
# "results for the third quarter")
_RESULTS_HEAD = re.compile(
    r"financial results|results for the (first|second|third|fourth) quarter|quarter (\d{4} )?results",
    re.I,
)
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
        self._texts: dict[
            str, str
        ] = {}  # exhibit url -> text, so a 6-K checked once isn't refetched

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
                if url := self._exhibit_url(cik, recent, i):
                    return self._text(url), url
        return None

    def _exhibit_url(self, cik: int, recent: dict, i: int) -> str | None:
        """Exhibit 99.1 of filing i (else its largest attached page)."""
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
        return _DOC_URL.format(cik=cik, acc=acc, doc=ex["name"]) if ex else None

    def _text(self, url: str) -> str:
        if url not in self._texts:
            self._texts[url] = _html_to_text(self._get(url).text)
        return self._texts[url]

    def company_facts(self, ticker: str) -> dict | None:
        """SEC's XBRL company facts (every tagged value the company has filed); None if unknown."""
        cik = self._cik(ticker)
        if cik is None:
            return None
        try:
            return self._get(_FACTS_URL.format(cik=cik)).json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            raise

    def earnings_releases(self, ticker: str, n: int = 1) -> list[Release]:
        """The newest n earnings releases, newest first: 8-Ks with item 2.02, and 6-Ks whose exhibit
        reports a quarter's results (foreign filers such as Nebius file no 8-K or 10-Q)."""
        cik = self._cik(ticker)
        if cik is None:
            return []
        recent = self._get(_SUBS_URL.format(cik=cik)).json()["filings"]["recent"]
        out: list[Release] = []
        six_k = 0
        for i, form in enumerate(recent["form"]):
            if len(out) >= n:
                break
            url = None
            if form.startswith("8-K") and "2.02" in recent["items"][i]:
                url = self._exhibit_url(cik, recent, i)
            elif form.startswith("6-K") and six_k < _SIX_K_SCAN:
                six_k += 1
                url = self._exhibit_url(cik, recent, i)
                if url and not _RESULTS_HEAD.search(self._text(url)[:600]):
                    url = None  # a deal, an AGM, a note offering: not a quarter's results
            if url:
                out.append(
                    Release(
                        ticker.upper(),
                        recent["accessionNumber"][i],
                        form,
                        recent["filingDate"][i],
                        url,
                    )
                )
        return out

    def release_text(self, r: Release) -> str:
        return self._text(r.url)
