"""Smoke test: start dashboard, hit every endpoint, verify no 500s.
Does NOT require OPENBB_PAT — endpoints degrade gracefully.
"""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from castelino.dashboard.main import app

    return TestClient(app)


ENDPOINTS = [
    "/",
    "/widgets.json",
    "/apps.json",
    "/macro_indicators",
    "/yield_curve",
    "/news",
    "/economic_calendar",
]


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_endpoint_no_500(client, endpoint):
    r = client.get(endpoint)
    assert r.status_code == 200, f"{endpoint} returned {r.status_code}: {r.text[:200]}"
