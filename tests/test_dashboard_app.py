"""Tests for the OpenBB dashboard skeleton."""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from castelino.dashboard.main import app

    return TestClient(app)


def test_root(client):
    r = client.get("/")
    assert r.status_code == 200
    assert r.json()["name"] == "ARC Research"


def test_widgets_json_is_dict(client):
    r = client.get("/widgets.json")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, dict)
    assert set(data) == {"macro_indicators", "yield_curve_chart", "news_feed", "econ_calendar"}


def test_apps_json_is_array(client):
    r = client.get("/apps.json")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["name"] == "ARC Research"
    assert "tabs" in data[0]
    assert list(data[0]["tabs"]) == ["macro"]
