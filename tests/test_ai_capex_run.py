import json
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pytest

from castelino.adoption.sources.edgar import Filing, Release
from castelino.adoption.store import AdoptionStore
from castelino.dashboards.ai_capex import run as ai_run
from castelino.dashboards.ai_capex.cited import Items
from castelino.dashboards.ai_capex.releases import KpiTable
from tests.test_ai_capex_census import NATIONAL, SIZE
from tests.test_ai_capex_market import rows as ramp_rows

NOW = datetime(2026, 10, 28, 21, 0, tzinfo=UTC)
SILICON = (Path(__file__).parent / "fixtures" / "ai_capex" / "silicon_index.html").read_text()
QUARTERS = [  # (start, end) of calendar quarters 2025Q3 .. 2026Q3
    ("2025-07-01", "2025-09-30"), ("2025-10-01", "2025-12-31"), ("2026-01-01", "2026-03-31"),
    ("2026-04-01", "2026-06-30"), ("2026-07-01", "2026-09-30"),
]  # fmt: skip


def company_facts(last: int, capex: float = 10.0) -> dict:
    """Quarterly 3-month facts through QUARTERS[last - 1]."""

    def q(v):
        return [
            {"start": s, "end": e, "val": v * 1e9, "filed": "2026-10-28"}
            for s, e in QUARTERS[:last]
        ]

    tags = {
        "PaymentsToAcquirePropertyPlantAndEquipment": q(capex),
        "RevenueFromContractWithCustomerExcludingAssessedTax": q(50.0),
        "NetCashProvidedByUsedInOperatingActivities": q(20.0),
        "ProceedsFromIssuanceOfLongTermDebt": q(2.0),
    }
    return {"facts": {"us-gaap": {t: {"units": {"USD": r}} for t, r in tags.items()}}}


class FakeEdgar:
    def __init__(self, short: set[str] = frozenset()):
        self.short = short  # tickers whose newest quarter isn't filed yet

    def company_facts(self, t):
        return company_facts(4 if t in self.short else 5)

    def latest_filing(self, t):
        return Filing(t, f"10q-{t}", "10-Q", "u")

    def earnings_releases(self, t, n=1):
        return [
            Release(t, f"8k-{t}-{i}", "8-K", "2026-10-28", f"https://sec.gov/{t}/{i}.htm")
            for i in range(n)
        ]

    def release_text(self, r):
        return "release text"


class Counter:
    def __init__(self):
        self.reads = 0
        self.searches = 0

    def release_reader(self):
        counter = self

        class R:
            def __call__(self, **ctx):
                counter.reads += 1
                return KpiTable(period="q", kpis=[])

        return R

    def cited_reader(self):
        class R:
            def __call__(self, **ctx):
                return Items(items=[])

        return R

    def search(self, system, user):
        self.searches += 1
        return "", []


def fred(sid):
    return pd.Series([4.2 if sid == "DGS10" else 6.8], index=pd.to_datetime(["2026-10-27"]))


class Resp:
    def __init__(self, content):
        self.content = content

    def raise_for_status(self):
        pass


def census_get(url, **kw):
    return Resp(SIZE if "Size" in url else NATIONAL)


def deps(tmp_path, counter=None, edgar=None, **over):
    c = counter or Counter()
    base = dict(
        edgar=edgar or FakeEdgar(),
        search=c.search,
        release_reader=c.release_reader(),
        cited_reader=c.cited_reader(),
        fetch_fred=fred,
        ramp_rows=ramp_rows,
        get_text=lambda url: SILICON if "silicondata" in url else (_ for _ in ()).throw(RuntimeError("openrouter down ?key=SECRET")),
        census_get=census_get,
        adoption_store=AdoptionStore(tmp_path / "adoption.db"),
        names={},
    )  # fmt: skip
    return ai_run.Deps(**(base | over))


def test_run_writes_contract_with_fakes(tmp_path):
    out = tmp_path / "ai_capex.json"
    ai_run.run(NOW, out=out, deps=deps(tmp_path))
    doc = json.loads(out.read_text())
    for key in ("generated_at", "as_of", "companies", "private", "totals", "nvidia", "rates", "gpu", "ramp",
                "openrouter", "census", "adoption", "sentences", "gaps"):  # fmt: skip
        assert key in doc, key
    msft = next(c for c in doc["companies"] if c["ticker"] == "MSFT")
    assert sum(msft["mix"].values()) == 100 and msft["kind"] == "hyperscaler"
    assert msft["quarters"][-1]["q"] == "2026Q3" and msft["cents_per_dollar"] == 20
    assert doc["rates"]["treasury_10y"]["value"] == 4.2
    assert doc["gpu"]["rows"][0]["gpu"] == "H100"
    assert doc["census"]["overall_pct"] == 24.6
    assert doc["ramp"]["sizes"][0]["size"] == "large"


def test_failed_lane_keeps_previous_and_logs_gap(tmp_path):
    out = tmp_path / "ai_capex.json"
    out.write_text(json.dumps({"openrouter": {"labs": ["from yesterday"]}}))
    ai_run.run(NOW, out=out, deps=deps(tmp_path))
    doc = json.loads(out.read_text())
    assert doc["openrouter"] == {"labs": ["from yesterday"]}
    gap = next(g for g in doc["gaps"] if g["lane"] == "openrouter")
    assert "SECRET" not in gap["error"] and "openrouter down" in gap["error"]


def test_all_lanes_fail_raises_and_keeps_file(tmp_path):
    out = tmp_path / "ai_capex.json"
    out.write_text('{"kept": true}')

    def boom(*a, **k):
        raise RuntimeError("down")

    class DeadEdgar:
        def __getattr__(self, name):
            return boom

    d = deps(tmp_path, edgar=DeadEdgar(), fetch_fred=boom, ramp_rows=boom, get_text=boom, census_get=boom, search=boom)  # fmt: skip
    d.adoption_store = DeadEdgar()
    with pytest.raises(RuntimeError, match="every lane failed"):
        ai_run.run(NOW, out=out, deps=d)
    assert json.loads(out.read_text()) == {"kept": True}


def test_quarter_totals_mark_missing_companies(tmp_path):
    out = tmp_path / "ai_capex.json"
    ai_run.run(NOW, out=out, deps=deps(tmp_path, edgar=FakeEdgar(short={"GOOGL"})))
    totals = json.loads(out.read_text())["totals"]["quarters"]
    q3 = next(q for q in totals if q["q"] == "2026Q3")
    assert (q3["reported"], q3["of"], q3["capex"]) == (4, 5, 40.0)
    q2 = next(q for q in totals if q["q"] == "2026Q2")
    assert (q2["reported"], q2["capex"]) == (5, 50.0)


def test_paid_reads_gated_by_accession(tmp_path):
    out, c = tmp_path / "ai_capex.json", Counter()
    ai_run.run(NOW, out=out, deps=deps(tmp_path, counter=c))
    first = (c.reads, c.searches)
    assert first[0] > 0 and first[1] > 0
    ai_run.run(NOW, out=out, deps=deps(tmp_path, counter=c))
    assert (c.reads, c.searches) == first  # same filings, same week: nothing paid again


def test_sentence_omitted_when_numbers_missing():
    assert ai_run.sentences({"companies": [], "totals": {}}) == {}
    s = ai_run.sentences(
        {
            "companies": [
                {"ticker": "AMZN", "name": "Amazon", "kind": "hyperscaler", "quarters": [{"q": "2026Q2", "capex": 50.0}], "yoy_pct": 56},
                {"ticker": "ORCL", "name": "Oracle", "kind": "hyperscaler", "quarters": [{"q": "2026Q2", "capex": 17.0}], "yoy_pct": 105},
            ],
            "totals": {"quarters": [{"q": "2026Q2", "capex": 181.2, "reported": 5, "of": 5}], "yoy_pct": 74, "ttm_capex": 611.0},
        }
    )  # fmt: skip
    assert s["spending"].startswith("The five spent **$181bn** in Q2 2026, up 74% from a year ago")
    assert "**$611bn** over the last four quarters" in s["spending"]
    assert "Amazon spends the most" in s["spending"] and "Oracle" in s["spending"]
    assert "compute" not in s


def test_endpoint_serves_file(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from castelino.dashboard.main import app

    f = tmp_path / "ai_capex.json"
    f.write_text('{"companies": []}')
    monkeypatch.setattr(ai_run, "out_path", lambda: f)
    assert TestClient(app).get("/dashboards/ai-capex").json() == {"companies": []}
    assert TestClient(app).get("/dashboards/ai-capex/card.png").status_code == 404


def test_card_drawn_and_a_card_failure_is_only_a_gap(tmp_path, monkeypatch):
    out = tmp_path / "ai_capex.json"
    ai_run.run(NOW, out=out, deps=deps(tmp_path))
    assert (tmp_path / "ai_capex" / "card.png").exists()

    from castelino.dashboards.ai_capex import card

    def boom(doc, path):
        raise RuntimeError("no fonts")

    monkeypatch.setattr(card, "draw", boom)
    ai_run.run(NOW, out=out, deps=deps(tmp_path))
    assert any(g["lane"] == "card" for g in json.loads(out.read_text())["gaps"])


def test_release_quarter_from_filing_date():
    # Nvidia files ~4 weeks after its quarter ends, Nebius ~6, so filed - 70 days sits mid-quarter
    assert ai_run._rel_label("2026-08-26") == "2026Q2"  # Nvidia, quarter to Jul 26
    assert ai_run._rel_label("2026-08-12") == "2026Q2"  # Nebius Q2
    assert ai_run._rel_label("2026-05-13") == "2026Q1"
    assert ai_run._rel_label("2026-10-28") == "2026Q3"  # Microsoft, quarter to Sep 30


def item(label, value, unit="billions", period="2026", high=None, date="2026-10"):
    return {"label": label, "value": value, "value_high": high, "unit": unit, "period": period,
            "date": date, "fact_id": "W1", "source": {"title": "t", "url": "u", "line": "l"}}  # fmt: skip


def test_stale_calendar_guidance_is_dropped():
    q = [{"q": "2026Q1", "capex": 35.7}, {"q": "2026Q2", "capex": 44.9}]  # $80.6bn spent in H1
    stale = [item("guidance", 91, period="full year 2026", high=93)]
    assert ai_run._guidance(stale, q) is None
    ok = ai_run._guidance([item("guidance", 175, period="calendar year 2026", high=185)], q)
    assert (ok["low"], ok["high"], ok["label"]) == (175, 185, "calendar year 2026")
    fiscal = ai_run._guidance([item("guidance", 35, period="fiscal 2027")], q)  # another year: kept
    assert fiscal["low"] == 35
    # a past year's guidance (Nebius came back with "2025") is no guidance at all
    assert (
        ai_run._guidance([item("guidance", None, unit="none", period="2025")], q, year=2026) is None
    )
    # several lines: the newest wins, whatever order the reader returned them in
    two = [item("guidance", 175, date="2026-02"), item("guidance", 190, date="2026-10")]
    assert ai_run._guidance(two, q)["low"] == 190


def test_borrowing_keeps_rates_not_spreads():
    items = [item("coupon, notes due 2036", 5.25, "percent"), item("SOFR spread", 0.44, "percent"),
             item("interest margin", 0.625, "percent"), item("convertible notes coupon", 1.75, "percent")]  # fmt: skip
    assert [b["label"] for b in ai_run._borrowing(items)] == [
        "coupon, notes due 2036",
        "convertible notes coupon",
    ]
    many = [item(f"notes {i}", 4 + i / 10, "percent") for i in range(6)]
    assert len(ai_run._borrowing(many)) == 3  # three a company keeps the chart readable


def test_off_balance_one_per_kind_at_least_a_billion():
    items = [item("leases not yet commenced", 329.1), item("Leases not yet commenced", 92.7),
             item("maximum exposure to loss", 45.95), item("power commitments", 0.006), item("x", 5, "percent")]  # fmt: skip
    got = ai_run._off_balance(items)
    assert [(o["label"], o["value"]) for o in got] == [
        ("leases not yet commenced", 329.1),
        ("maximum exposure to loss", 45.95),
    ]


def test_funding_sentence_gives_the_range_of_new_debt_rates():
    c = {"ticker": "ORCL", "name": "Oracle", "kind": "hyperscaler", "quarters": [],
         "mix": {"own_cash": 45, "debt": 35, "convertible": 0, "shares": 20, "cash_on_hand": 0},
         "borrowing": [{"label": "coupon", "rate_pct": r} for r in (4.55, 5.7)] + [{"label": "convertible notes coupon", "rate_pct": 1.0}]}  # fmt: skip
    s = ai_run.sentences({"companies": [c], "totals": {}})["funding"]
    assert "Oracle borrows **35%** of it; its new bonds and loans this year pay **4.55–5.7%**." in s
    assert "bp" not in s
