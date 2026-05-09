"""Wave 5 Task 5.1 — XApiTweetSource tests with httpx.MockTransport.

Real X API calls require a Basic-tier subscription + bearer token, so the
tests inject a MockTransport via monkeypatching the source's `_client()`
method. The implementation's behaviour around since_id, dedup, 429 backoff,
and state persistence are the things we test — actual HTTP transport is
mocked.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

import httpx
import pytest

from castelino.config import (
    LexiconCfg,
    TrackedFigureCfg,
    TrackedFigureSourceCfg,
)
from castelino.triggers.figure_deviation.models import FigurePost


# ────────────────────────── helpers ────────────────────────────────────────


def _trump_cfg() -> TrackedFigureCfg:
    return TrackedFigureCfg(
        id="trump",
        display_name="Donald J. Trump",
        sources=[TrackedFigureSourceCfg(
            type="x_api", username="realdonaldtrump", poll_interval_min=5,
        )],
        lexicons=[LexiconCfg(
            name="trade_protectionist_v1",
            threshold_sigma=1.5, window_size=3,
        )],
    )


def _patch_client(monkeypatch, handler: Callable[[httpx.Request], httpx.Response]):
    """Replace XApiTweetSource._client to inject a MockTransport-backed client."""
    from castelino.triggers.figure_deviation.source import x_api as x_api_mod

    requests_seen: list[httpx.Request] = []

    def capturing_handler(request: httpx.Request) -> httpx.Response:
        requests_seen.append(request)
        return handler(request)

    transport = httpx.MockTransport(capturing_handler)

    def fake_client(self):
        return httpx.AsyncClient(
            transport=transport,
            headers={"Authorization": f"Bearer {self._bearer}"},
            timeout=self._timeout,
        )

    monkeypatch.setattr(x_api_mod.XApiTweetSource, "_client", fake_client)
    return requests_seen


# ────────────────────────── tests ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_x_api_source_resolves_user_id_then_polls_timeline(
    monkeypatch, tmp_path,
):
    def handler(request: httpx.Request) -> httpx.Response:
        if "users/by/username" in str(request.url):
            return httpx.Response(
                200,
                json={"data": {"id": "25073877", "username": "realdonaldtrump"}},
            )
        if "/users/25073877/tweets" in str(request.url):
            return httpx.Response(200, json={"data": [
                {
                    "id": "1900000000000000001",
                    "text": "50% tariff on Chinese steel starting Monday",
                    "created_at": "2026-05-08T13:30:00Z",
                    "referenced_tweets": [],
                    "public_metrics": {"like_count": 5000},
                },
                {
                    "id": "1900000000000000002",
                    "text": "Powell is late as always, hurting the economy",
                    "created_at": "2026-05-08T13:35:00Z",
                    "referenced_tweets": [],
                    "public_metrics": {"like_count": 3000},
                },
            ]})
        return httpx.Response(404)

    _patch_client(monkeypatch, handler)
    from castelino.triggers.figure_deviation.source.x_api import XApiTweetSource

    src = XApiTweetSource(
        bearer_token="fake_token",
        state_path=tmp_path / "x_api_state.json",
    )
    figure = _trump_cfg()
    posts: list[FigurePost] = []
    async for p in src.stream(figure, figure.sources[0]):
        posts.append(p)

    assert len(posts) == 2
    assert posts[0].source == "x_api"
    assert posts[0].text.startswith("50% tariff")
    assert posts[0].figure_id == "trump"
    assert {p.event_id for p in posts} == {
        "1900000000000000001", "1900000000000000002",
    }
    assert "x.com/realdonaldtrump/status/" in posts[0].source_url


@pytest.mark.asyncio
async def test_x_api_source_uses_since_id_to_avoid_replay(
    monkeypatch, tmp_path,
):
    """Second poll passes since_id from the first cycle's last tweet."""
    state_path = tmp_path / "x_api_state.json"
    state_path.write_text(json.dumps({
        "25073877": {
            "since_id": "1900000000000000002",
            "username": "realdonaldtrump",
        },
    }))

    def handler(request):
        if "users/by/username" in str(request.url):
            return httpx.Response(200, json={"data": {"id": "25073877"}})
        return httpx.Response(200, json={"data": []})

    requests_seen = _patch_client(monkeypatch, handler)
    from castelino.triggers.figure_deviation.source.x_api import XApiTweetSource

    src = XApiTweetSource(bearer_token="fake_token", state_path=state_path)
    figure = _trump_cfg()
    posts = [p async for p in src.stream(figure, figure.sources[0])]
    assert posts == []
    # Confirm the timeline request carried the since_id query param
    timeline_req = next(r for r in requests_seen if "tweets" in str(r.url))
    assert "since_id=1900000000000000002" in str(timeline_req.url)


@pytest.mark.asyncio
async def test_x_api_source_handles_429_with_backoff(monkeypatch, tmp_path):
    def handler(request):
        if "users/by/username" in str(request.url):
            return httpx.Response(200, json={"data": {"id": "25073877"}})
        return httpx.Response(
            429,
            headers={"Retry-After": "30"},
            json={"title": "Too Many Requests"},
        )

    _patch_client(monkeypatch, handler)
    from castelino.triggers.figure_deviation.source.x_api import XApiTweetSource

    src = XApiTweetSource(
        bearer_token="fake_token", state_path=tmp_path / "state.json",
    )
    figure = _trump_cfg()
    posts = [p async for p in src.stream(figure, figure.sources[0])]
    assert posts == []
    assert src.last_backoff_sec >= 30


@pytest.mark.asyncio
async def test_x_api_source_advances_since_id_only_on_success(
    monkeypatch, tmp_path,
):
    """On a 5xx error, since_id must NOT advance — replay is preferred to
    silently dropping tweets."""
    def handler(request):
        if "users/by/username" in str(request.url):
            return httpx.Response(200, json={"data": {"id": "25073877"}})
        return httpx.Response(503, json={"title": "Service Unavailable"})

    _patch_client(monkeypatch, handler)
    from castelino.triggers.figure_deviation.source.x_api import XApiTweetSource

    state_path = tmp_path / "state.json"
    src = XApiTweetSource(bearer_token="fake", state_path=state_path)
    figure = _trump_cfg()
    posts = [p async for p in src.stream(figure, figure.sources[0])]
    assert posts == []
    assert not state_path.exists()


def test_x_api_source_rejects_empty_token(tmp_path):
    from castelino.triggers.figure_deviation.source.x_api import XApiTweetSource
    with pytest.raises(ValueError, match="bearer token"):
        XApiTweetSource(bearer_token="", state_path=tmp_path / "x.json")


@pytest.mark.asyncio
async def test_x_api_source_passes_referenced_tweets_in_raw_meta(
    monkeypatch, tmp_path,
):
    """Stage B uses raw_meta.referenced_tweets to detect quoted-tweet
    contexts (so 'Biden's tariff was bad' doesn't fire on TARIFF positively
    despite the term being present)."""
    def handler(request):
        if "users/by/username" in str(request.url):
            return httpx.Response(200, json={"data": {"id": "25073877"}})
        return httpx.Response(200, json={"data": [{
            "id": "1900000000000000001",
            "text": "tariffs",
            "created_at": "2026-05-08T13:30:00Z",
            "referenced_tweets": [
                {"type": "quoted", "id": "1234567890"},
            ],
            "public_metrics": {},
        }]})

    _patch_client(monkeypatch, handler)
    from castelino.triggers.figure_deviation.source.x_api import XApiTweetSource

    src = XApiTweetSource(bearer_token="fake", state_path=tmp_path / "s.json")
    figure = _trump_cfg()
    posts = [p async for p in src.stream(figure, figure.sources[0])]
    assert len(posts) == 1
    assert posts[0].raw_meta["referenced_tweets"][0]["type"] == "quoted"
