import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from castelino.agents.research.deep import store as research_store
from castelino.agents.trade import store as trade_store
from castelino.agents.update import desk
from castelino.dashboard.endpoints import admin_overview as ov

DAY = "2026-10-24"


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setattr(ov, "_today", lambda: DAY)
    monkeypatch.setattr(ov, "_data", lambda: tmp_path / "data")
    monkeypatch.setattr(desk, "_dirs", lambda: (tmp_path, tmp_path / "updates"))
    monkeypatch.setattr(trade_store, "all", lambda: [])
    monkeypatch.setattr(research_store, "all", lambda: [])
    from castelino.dashboard.main import app

    return TestClient(app)


def job(state, step="research", at="2026-10-24T17:05"):
    return SimpleNamespace(state=state, step=step, message="", at=at)


def idea(status, j=None, title="Long India (INDA) vs EM (EEM)"):
    return SimpleNamespace(
        idea="india",
        frame=SimpleNamespace(title=title),
        status=status,
        job=j,
        cost_usd=1.12,
        updated_at="2026-10-24T15:00",
    )


def test_overview_is_not_taken_by_the_day_route(client):
    r = client.get("/admin/desk/overview")
    assert r.status_code == 200
    assert {"needs_you", "running", "went_out", "spend", "counts", "errors"} <= set(r.json())


def test_trade_ideas_split_into_waiting_and_running(client, monkeypatch):
    monkeypatch.setattr(
        trade_store,
        "all",
        lambda: [
            idea("awaiting_view"),
            idea("researching", job("running"), title="Short regional banks"),
            idea("writing", job("failed", step="write"), title="Long copper"),
            idea("draft_ready", job("done"), title="Done one"),
        ],
    )
    j = client.get("/admin/desk/overview").json()
    assert [(i["title"], i["action"]) for i in j["needs_you"]] == [
        ("Long India (INDA) vs EM (EEM)", "Give your view"),
        ("Long copper", "Retry"),
    ]
    assert [i["title"] for i in j["running"]] == ["Short regional banks"]
    assert j["running"][0]["cost_usd"] == 1.12 and j["running"][0]["href"] == "/admin/trade-lab"
    assert j["counts"]["trade-lab"] == {"waiting": 2, "running": 1}


def test_research_rewrites_to_approve_wait_for_the_admin(client, monkeypatch):
    s = SimpleNamespace(
        topic="Continual learning",
        report=SimpleNamespace(title="Continual learning in frontier models"),
        status="complete",
        job=job("done"),
        proposals=[
            SimpleNamespace(status="pending"),
            SimpleNamespace(status="pending"),
            SimpleNamespace(status="approved"),
        ],
        additions=[],
        cost_usd=3.1,
        updated_at="2026-10-24T12:00",
    )
    monkeypatch.setattr(research_store, "all", lambda: [s])
    j = client.get("/admin/desk/overview").json()
    assert j["needs_you"][0]["detail"] == "Research · 2 point rewrites to approve"
    assert j["counts"]["research"] == {"waiting": 1, "running": 0}


def test_went_out_lists_sent_posts_and_skips_dry_runs(client, tmp_path):
    scout = tmp_path / "data" / "x_posts" / "scout"
    scout.mkdir(parents=True)
    (scout / f"{DAY}.json").write_text(
        json.dumps(
            {
                "posts": [
                    {
                        "at": "2026-10-24T18:15",
                        "headline": "SpaceX's 13 GW compute plan",
                        "ids": ["1", "2", "3", "4"],
                    },
                    {"at": "2026-10-24T19:15", "headline": "dry", "ids": [], "dry_run": True},
                ]
            }
        )
    )
    j = client.get("/admin/desk/overview").json()
    assert [i["title"] for i in j["went_out"]] == ["X Scout · SpaceX's 13 GW compute plan"]
    assert j["went_out"][0]["detail"] == "X thread · 4 posts"
    assert j["went_out"][0]["url"].endswith("/status/1")


def test_one_broken_section_never_blanks_the_page(client, monkeypatch):
    def boom():
        raise RuntimeError("disk full")

    monkeypatch.setattr(trade_store, "all", boom)
    j = client.get("/admin/desk/overview").json()
    assert j["errors"] == ["trade-lab: disk full"] and "research" in j["counts"]
