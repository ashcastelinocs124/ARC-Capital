from datetime import date, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from castelino import benchmark, costs, x_post
from castelino.dashboard.endpoints import admin_desk


def test_prices_tokens_adds_search_fee_and_leaves_unknown_models_unpriced():
    benchmark.record_call("update_editor", "gpt-6-sol", {}, started=0, tokens=(1_000_000, 100_000))
    benchmark.record_call("web_search", "gpt-6-luna", {}, started=0, tokens=(50_000, 2_000))
    benchmark.record_call("web_search", "gpt-6-luna", {}, started=0, error="timeout")  # no fee
    benchmark.record_call("weekly_editor", "claude-opus-5-5", {}, started=0, tokens=(10_000, 1_000))
    benchmark.record_call("mystery", "gpt-9-nova", {}, started=0, tokens=(5, 5))

    rows = {r["agent"]: r for r in costs.summary(1)["rows"] if r["provider"] != "fly"}
    assert rows["update_editor"]["usd"] == pytest.approx(2.0 + 1.0)
    search = rows["web_search"]
    assert (search["calls"], search["tokens_in"]) == (2, 50_000)
    assert search["usd"] == pytest.approx((50_000 * 0.10 + 2_000 * 0.50) / 1e6 + 0.01)
    assert rows["weekly_editor"]["provider"] == "anthropic"
    assert rows["weekly_editor"]["usd"] == pytest.approx(0.04 + 0.02)
    assert rows["mystery"]["usd"] is None  # unpriced, never $0


def test_range_skips_days_without_logs_and_sees_new_calls_today():
    today = date.fromisoformat(f"{datetime.now():%Y-%m-%d}")

    def calls():
        return [r for r in costs.summary(7, today)["rows"] if r["provider"] != "fly"]

    assert calls() == []
    benchmark.record_call("theme_picker", "gpt-6-sol", {}, started=0, tokens=(1000, 0))
    assert calls()[0]["calls"] == 1
    benchmark.record_call("theme_picker", "gpt-6-sol", {}, started=0, tokens=(1000, 0))
    assert calls()[0]["calls"] == 2  # the grown file is re-read


def test_fly_server_is_one_row_a_day_from_the_day_billing_began():
    fly = [r for r in costs.summary(5, date(2026, 10, 15))["rows"] if r["provider"] == "fly"]
    assert [r["day"] for r in fly] == ["2026-10-13", "2026-10-14", "2026-10-15"]
    assert fly[0]["usd"] == pytest.approx((13.39 + 0.45) / 30)


def test_costs_endpoint_is_not_taken_by_the_day_route():
    app = FastAPI()
    app.include_router(admin_desk.router)
    r = TestClient(app).get("/admin/desk/costs?days=7")
    assert r.status_code == 200 and r.json()["days"] == 7
    assert costs.provider("deepseek/deepseek-v4-pro") == "openrouter"


def test_x_posts_and_reads_are_priced_per_call(monkeypatch):
    monkeypatch.setattr(x_post, "_auth_header", lambda *a: "OAuth x")
    monkeypatch.setattr(
        x_post.httpx,
        "post",
        lambda url, json, **k: type(
            "R", (), {"status_code": 201, "json": lambda self: {"data": {"id": "7"}}}
        )(),
    )
    x_post.post("CPI beat forecasts.")
    x_post.post("CPI cooled.")
    x_post.post(
        "The full note: https://archresearch.substack.com/p/note"
    )  # X bills a link at $0.200
    benchmark.record_x("read", 12)  # the About feed: X bills each post a read returns
    rows = {r["model"]: r for r in costs.summary(1)["rows"] if r["provider"] == "x"}
    assert (rows["x-post"]["calls"], rows["x-post"]["usd"]) == (2, pytest.approx(0.03))
    assert rows["x-post-link"]["usd"] == pytest.approx(0.2)
    assert (rows["x-read"]["calls"], rows["x-read"]["usd"]) == (12, pytest.approx(0.06))
    assert costs.summary(1)["x_fees"]["x-post-link"] == 0.2
