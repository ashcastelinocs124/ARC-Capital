import pytest
from fastapi.testclient import TestClient

from castelino.agents.consultants import planner, runner, store
from castelino.agents.consultants.models import Company, Watchlist

WL = {"companies": [{"name": "NVIDIA", "ticker": "NVDA"}], "series": [], "queries": ["AI chips"]}


@pytest.fixture
def client(monkeypatch):
    started: list = []
    monkeypatch.setattr(runner, "submit_start", lambda slug: started.append(slug))
    from castelino.dashboard.main import app

    c = TestClient(app)
    c.started = started
    return c


def test_router_before_admin_desk(client):
    r = client.get("/admin/desk/consultants")
    assert r.status_code == 200 and r.json() == {"consultants": []}


def test_plan_returns_the_planners_watchlist(client, monkeypatch):
    wl = Watchlist(companies=[Company(name="NVIDIA", ticker="NVDA")], series=[], queries=["q"])
    monkeypatch.setattr(planner, "suggest", lambda topic, meter: wl)
    r = client.post("/admin/desk/consultants/plan", json={"topic": "AI chips"})
    assert r.status_code == 200 and r.json()["watchlist"]["companies"][0]["ticker"] == "NVDA"


def test_create_list_get(client):
    r = client.post(
        "/admin/desk/consultants", json={"topic": "AI models and chips", "watchlist": WL}
    )
    assert r.status_code == 200
    row = r.json()
    assert (row["slug"], row["code"], row["status"]) == ("ai-models-and-chips", "K1", "building")
    assert client.started == ["ai-models-and-chips"]
    rows = client.get("/admin/desk/consultants").json()["consultants"]
    assert [x["slug"] for x in rows] == ["ai-models-and-chips"]
    d = client.get("/admin/desk/consultants/ai-models-and-chips").json()
    assert d["consultant"]["topic"] == "AI models and chips"
    assert d["thesis"] is None and d["history"] == [] and d["memory"] == {"short": [], "long": []}
    assert d["today"]["facts"] == []


def test_pause_resume_build_and_delete(client):
    client.post("/admin/desk/consultants", json={"topic": "India", "watchlist": WL})
    base = "/admin/desk/consultants/india"
    assert client.post(f"{base}/pause").json()["status"] == "paused"
    assert client.post(f"{base}/resume").json()["status"] == "active"
    assert client.post(f"{base}/build").status_code == 200 and client.started == ["india", "india"]
    assert client.delete(base).status_code == 200
    assert client.get("/admin/desk/consultants").json()["consultants"] == []
    assert any((store.root() / "hidden").iterdir())


def test_unknown_slug_is_404(client):
    assert client.get("/admin/desk/consultants/nope").status_code == 404
    assert client.post("/admin/desk/consultants/nope/pause").status_code == 404


def test_get_returns_todays_log_notes(client):
    from datetime import date

    client.post("/admin/desk/consultants", json={"topic": "India", "watchlist": WL})
    with store.edit_day("india", date.today().isoformat()) as d:
        d.notes.append("cost cap: skipped build")
    log = client.get("/admin/desk/consultants/india").json()["log"]
    assert log["notes"] == ["cost cap: skipped build"]


def test_build_now_shows_building(client):
    client.post("/admin/desk/consultants", json={"topic": "India", "watchlist": WL})
    with store.edit("india") as x:
        x.status = "failed"
    assert client.post("/admin/desk/consultants/india/build").json()["status"] == "building"


def test_short_topic_is_422(client):
    r = client.post("/admin/desk/consultants", json={"topic": "AI", "watchlist": WL})
    assert r.status_code == 422


def test_check_returns_the_chip_or_422(client, monkeypatch):
    def company(t):
        if t == "ZZZZ":
            raise ValueError("ZZZZ has no prices on Yahoo Finance.")
        return Company(name="Broadcom", ticker="AVGO")

    monkeypatch.setattr(planner, "check_company", company)
    monkeypatch.setattr(planner, "check_series", lambda s: "fred:DGS10")
    url = "/admin/desk/consultants/check"
    r = client.post(url, json={"kind": "company", "value": "avgo"})
    assert r.json() == {"company": {"name": "Broadcom", "ticker": "AVGO"}}
    r = client.post(url, json={"kind": "company", "value": "ZZZZ"})
    assert r.status_code == 422 and r.json()["detail"] == "ZZZZ has no prices on Yahoo Finance."
    assert client.post(url, json={"kind": "series", "value": "fred:dgs10"}).json() == {
        "series": "fred:DGS10"
    }


def test_put_watchlist_saves_and_validates(client):
    client.post("/admin/desk/consultants", json={"topic": "India", "watchlist": WL})
    url = "/admin/desk/consultants/india/watchlist"
    new = {**WL, "series": ["yahoo:INDA"]}
    assert client.put(url, json=new).json() == {"watchlist": new}
    assert store.load("india").watchlist.series == ["yahoo:INDA"]
    assert client.put(url, json={**WL, "series": ["bloomberg:X"]}).status_code == 422
    many = [{"name": f"C{i}", "ticker": f"T{i}"} for i in range(planner.MAX_HAND + 1)]
    assert client.put(url, json={**WL, "companies": many}).status_code == 422
    assert store.load("india").watchlist.series == ["yahoo:INDA"]  # a refused edit saves nothing
    assert client.put("/admin/desk/consultants/nope/watchlist", json=WL).status_code == 404


def test_create_refuses_a_malformed_series(client):
    r = client.post(
        "/admin/desk/consultants",
        json={"topic": "India", "watchlist": {**WL, "series": ["INDA"]}},
    )
    assert r.status_code == 422 and client.started == []


def test_post_knob_and_chart(client):
    client.post("/admin/desk/consultants", json={"topic": "India", "watchlist": WL})
    base = "/admin/desk/consultants/india"
    assert client.get(base).json()["consultant"]["post_to_x"] is False  # Off by default
    assert client.post(f"{base}/x", json={"on": True}).json()["post_to_x"] is True
    assert store.load("india").post_to_x is True
    assert client.post(f"{base}/x", json={"on": False}).json()["post_to_x"] is False
    assert client.get(f"{base}/posts/2026-10-22.png").status_code == 404
    png = store.cdir("india") / "posts" / "2026-10-22.png"
    png.parent.mkdir(parents=True)
    png.write_bytes(b"\x89PNG")
    r = client.get(f"{base}/posts/2026-10-22.png")
    assert r.status_code == 200 and r.headers["content-type"] == "image/png"
    assert client.get(f"{base}/posts/..%2Fconsultant.png").status_code == 404
