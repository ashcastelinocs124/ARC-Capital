import httpx
import pytest

from castelino.adoption.sources.edgar import EdgarClient, EdgarError


def handler(request: httpx.Request) -> httpx.Response:
    u = str(request.url)
    if u.endswith("company_tickers.json"):
        return httpx.Response(
            200,
            json={
                "0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple"},
                "1": {"cik_str": 111, "ticker": "NOFORM", "title": "NoForm"},
            },
        )
    if "CIK0000320193.json" in u:
        return httpx.Response(
            200,
            json={
                "filings": {
                    "recent": {
                        "form": ["8-K", "10-Q", "10-K"],
                        "accessionNumber": [
                            "0000320193-26-000001",
                            "0000320193-26-000010",
                            "0000320193-25-000099",
                        ],
                        "primaryDocument": ["a8k.htm", "a10q.htm", "a10k.htm"],
                    }
                }
            },
        )
    if "CIK0000000111.json" in u:
        return httpx.Response(
            200,
            json={
                "filings": {
                    "recent": {
                        "form": ["8-K"],
                        "accessionNumber": ["x"],
                        "primaryDocument": ["x.htm"],
                    }
                }
            },
        )
    if u.endswith("/320193/000032019326000010/a10q.htm"):
        return httpx.Response(
            200,
            text="<html><script>var x=1;</script><body><p>We use  machine\nlearning.</p></body></html>",
        )
    return httpx.Response(404)


def client():
    http = httpx.Client(transport=httpx.MockTransport(handler), headers={"User-Agent": "test"})
    return EdgarClient(
        "ARC Research test@example.com", http=http, min_interval=0, sleep=lambda s: None
    )


def test_latest_filing_picks_newest_10q_without_downloading_it():
    seen = []

    def spy(request):
        seen.append(str(request.url))
        return handler(request)

    http = httpx.Client(transport=httpx.MockTransport(spy), headers={"User-Agent": "test"})
    c = EdgarClient(
        "ARC Research test@example.com", http=http, min_interval=0, sleep=lambda s: None
    )
    f = c.latest_filing("aapl")
    assert f is not None
    assert (f.ticker, f.form, f.accession) == ("AAPL", "10-Q", "0000320193-26-000010")
    assert not any(
        u.endswith(".htm") for u in seen
    )  # metadata only; the document is fetched on demand
    assert c.filing_text(f) == "We use machine learning."


def test_unknown_ticker_and_no_annual_or_quarterly_filing():
    c = client()
    assert c.latest_filing("ZZZZ") is None
    assert c.latest_filing("NOFORM") is None


def test_blank_user_agent_fails_fast():
    with pytest.raises(EdgarError, match="sec_user_agent"):
        EdgarClient("  ")


# ── company facts and recent earnings releases (AI Demand & Capex dashboard) ──

_REL_SUBS = {
    "filings": {
        "recent": {
            "form": ["8-K", "10-Q", "6-K", "6-K", "8-K"],
            "items": ["2.02,9.01", "", "", "", "7.01"],
            "filingDate": ["2026-10-22", "2026-10-20", "2026-10-15", "2026-09-01", "2026-08-01"],
            "accessionNumber": ["0001-26-5", "0001-26-4", "0001-26-3", "0001-26-2", "0001-26-1"],
            "primaryDocument": ["k5.htm", "q4.htm", "f3.htm", "f2.htm", "k1.htm"],
        }
    }
}
_REL_EX = {  # accession without dashes -> exhibit 99.1 body
    "0001265": "<p>Results for the third quarter 2026</p>",
    "0001263": "<p>Nebius reports results for the third quarter of 2026</p>",
    # mentions "results" and "quarter" but is no earnings release
    "0001262": "<p>Nebius announces results of its Annual General Meeting held this quarter</p>",
    "0001261": "<p>Regulation FD disclosure</p>",
}


def rel_handler(request: httpx.Request) -> httpx.Response:
    u = str(request.url)
    if u.endswith("company_tickers.json"):
        return httpx.Response(200, json={"0": {"cik_str": 1, "ticker": "NEO", "title": "Neo"}})
    if u.endswith("/submissions/CIK0000000001.json"):
        return httpx.Response(200, json=_REL_SUBS)
    if u.endswith("/api/xbrl/companyfacts/CIK0000000001.json"):
        return httpx.Response(200, json={"cik": 1, "facts": {"us-gaap": {}}})
    for acc, body in _REL_EX.items():
        if u.endswith(f"/1/{acc}/index.json"):
            return httpx.Response(
                200, json={"directory": {"item": [{"name": "ex99-1.htm", "size": "10"}]}}
            )
        if u.endswith(f"/1/{acc}/ex99-1.htm"):
            return httpx.Response(200, text=f"<html><body>{body}</body></html>")
    return httpx.Response(404)


def rel_client(handler=rel_handler):
    http = httpx.Client(transport=httpx.MockTransport(handler), headers={"User-Agent": "test"})
    return EdgarClient(
        "ARC Research test@example.com", http=http, min_interval=0, sleep=lambda s: None
    )


def test_company_facts_fetches_by_cik():
    seen = []

    def spy(request):
        seen.append(str(request.url))
        return rel_handler(request)

    assert rel_client(spy).company_facts("neo") == {"cik": 1, "facts": {"us-gaap": {}}}
    assert any(u.endswith("companyfacts/CIK0000000001.json") for u in seen)


def test_company_facts_unknown_ticker_is_none():
    assert rel_client().company_facts("ZZZZ") is None


def test_earnings_releases_8k_and_6k():
    c = rel_client()
    got = c.earnings_releases("NEO", n=5)
    assert [(r.form, r.filed, r.accession) for r in got] == [
        ("8-K", "2026-10-22", "0001-26-5"),
        ("6-K", "2026-10-15", "0001-26-3"),
    ]
    assert c.release_text(got[1]) == "Nebius reports results for the third quarter of 2026"
    assert [r.accession for r in c.earnings_releases("NEO")] == ["0001-26-5"]
