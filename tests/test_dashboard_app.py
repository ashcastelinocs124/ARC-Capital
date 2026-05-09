"""Tests for the OpenBB dashboard skeleton."""
from fastapi.testclient import TestClient
import pytest


@pytest.fixture
def client():
    from castelino.dashboard.main import app
    return TestClient(app)


def test_root(client):
    r = client.get("/")
    assert r.status_code == 200
    assert r.json()["name"] == "CKM Capital"


def test_widgets_json_is_dict(client):
    r = client.get("/widgets.json")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, dict)
    assert "nav_metrics" in data
    assert "positions_table" in data


def test_apps_json_is_array(client):
    r = client.get("/apps.json")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["name"] == "CKM Capital"
    assert "tabs" in data[0]
    assert len(data[0]["tabs"]) == 6
