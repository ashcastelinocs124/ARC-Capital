import httpx
import pytest

from castelino.adoption.sources.edgar import EdgarClient, EdgarError


def handler(request: httpx.Request) -> httpx.Response:
    u = str(request.url)
    if u.endswith("company_tickers.json"):
        return httpx.Response(200, json={"0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple"},
                                         "1": {"cik_str": 111, "ticker": "NOFORM", "title": "NoForm"}})
    if "CIK0000320193.json" in u:
        return httpx.Response(200, json={"filings": {"recent": {
            "form": ["8-K", "10-Q", "10-K"],
            "accessionNumber": ["0000320193-26-000001", "0000320193-26-000010", "0000320193-25-000099"],
            "primaryDocument": ["a8k.htm", "a10q.htm", "a10k.htm"]}}})
    if "CIK0000000111.json" in u:
        return httpx.Response(200, json={"filings": {"recent": {
            "form": ["8-K"], "accessionNumber": ["x"], "primaryDocument": ["x.htm"]}}})
    if u.endswith("/320193/000032019326000010/a10q.htm"):
        return httpx.Response(200, text="<html><script>var x=1;</script><body><p>We use  machine\nlearning.</p></body></html>")
    return httpx.Response(404)


def client():
    http = httpx.Client(transport=httpx.MockTransport(handler), headers={"User-Agent": "test"})
    return EdgarClient("ARC Research test@example.com", http=http, min_interval=0, sleep=lambda s: None)


def test_latest_filing_picks_newest_10q_without_downloading_it():
    seen = []

    def spy(request):
        seen.append(str(request.url))
        return handler(request)

    http = httpx.Client(transport=httpx.MockTransport(spy), headers={"User-Agent": "test"})
    c = EdgarClient("ARC Research test@example.com", http=http, min_interval=0, sleep=lambda s: None)
    f = c.latest_filing("aapl")
    assert f is not None
    assert (f.ticker, f.form, f.accession) == ("AAPL", "10-Q", "0000320193-26-000010")
    assert not any(u.endswith(".htm") for u in seen)          # metadata only; the document is fetched on demand
    assert c.filing_text(f) == "We use machine learning."


def test_unknown_ticker_and_no_annual_or_quarterly_filing():
    c = client()
    assert c.latest_filing("ZZZZ") is None
    assert c.latest_filing("NOFORM") is None


def test_blank_user_agent_fails_fast():
    with pytest.raises(EdgarError, match="sec_user_agent"):
        EdgarClient("  ")
