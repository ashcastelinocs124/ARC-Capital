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
