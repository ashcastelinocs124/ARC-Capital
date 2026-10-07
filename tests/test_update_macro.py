from castelino.agents import base
from castelino.agents.update import bls, macro
from castelino.agents.update.models import FindingDraft, FindingDrafts, MarketSnapshot, Release
from tests.update_fixtures import make_snapshot


def test_bls_facts_compute_mom_from_index_levels():
    data = {"CUSR0000SAH1": [("Aug 2026", 404.0), ("Jul 2026", 402.0), ("Jun 2026", 401.0)]}
    facts = bls.bls_facts(fetch_fn=lambda ids: data)
    f = facts[0]
    assert f.id == "B1" and f.provenance == "data"
    latest, prior = round((404 / 402 - 1) * 100, 2), round((402 / 401 - 1) * 100, 2)
    assert f.numbers == [latest, prior, round(latest - prior, 2)]
    assert [p.label for p in f.series.points] == ["Jul 2026 data", "Aug 2026 data"]


def test_bls_fetch_parses_monthly_rows_and_skips_annual():
    body = {
        "status": "REQUEST_SUCCEEDED",
        "Results": {
            "series": [
                {
                    "seriesID": "X",
                    "data": [
                        {"year": "2026", "period": "M13", "periodName": "Annual", "value": "1"},
                        {"year": "2026", "period": "M08", "periodName": "August", "value": "404.0"},
                        {"year": "2026", "period": "M07", "periodName": "July", "value": "-"},
                    ],
                }
            ]
        },
    }

    class R:
        def raise_for_status(self):
            pass

        def json(self):
            return body

    assert bls.fetch(["X"], post=lambda *a, **k: R()) == {"X": [("Aug 2026", 404.0)]}


def test_gather_facts_builds_release_and_market_facts():
    snap = make_snapshot()
    snap.releases[0].latest_period, snap.releases[0].prior_period = "Aug 2026", "Jul 2026"
    facts, got = macro.gather_facts(
        collect_fn=lambda **k: snap, bls_fn=lambda: [], claims_fn=lambda: None, today="2026-10-07"
    )
    assert got is snap
    rel = next(f for f in facts if "Core PCE" in f.text)
    assert rel.numbers == [3.7, 3.5, 0.2] and rel.series.kind == "release"
    assert rel.series.points[-1].label == "Aug 2026 data"
    dgs2 = next(f for f in facts if f.text.startswith("DGS2"))
    assert "bp" in dgs2.text and dgs2.series.provider == "fred" and dgs2.series.kind == "daily"


def test_gather_facts_records_a_gap_when_a_source_fails():
    def boom():
        raise RuntimeError("BLS down")

    snap = make_snapshot()
    facts, got = macro.gather_facts(
        collect_fn=lambda **k: snap, bls_fn=boom, claims_fn=lambda: None, today="2026-10-07"
    )
    assert facts and any("BLS" in g for g in got.data_gaps)


def test_run_uses_agent_model_and_returns_findings(monkeypatch):
    fake = base.FakeLLMClient()
    fake.register(
        "FindingDrafts",
        lambda s, u: FindingDrafts(
            findings=[FindingDraft(claim="Core PCE hotter", figure=3.7, unit="%", fact_ids=["M1"])]
        ),
    )
    monkeypatch.setattr(base, "_LIVE_CLIENT_SINGLETON", fake)
    snap = MarketSnapshot(
        date="2026-10-07",
        releases=[
            Release(
                series="PCEPILFE",
                name="Core PCE y/y",
                latest=3.7,
                prior=3.5,
                change=0.2,
                latest_period="Aug 2026",
                prior_period="Jul 2026",
            )
        ],
    )
    monkeypatch.setattr(macro, "gather_facts", lambda **k: (macro.release_facts(snap), snap))
    out = macro.run("focus on inflation")
    assert out.findings[0].id == "macro-1" and out.snapshot is snap
    assert fake.call_log[-1][1] == "gpt-6-luna"
