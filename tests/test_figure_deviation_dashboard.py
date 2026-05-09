"""Wave 8 Task 8.1 — /figures dashboard endpoint tests."""
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from castelino.config import (
    FigureDeviationCfg,
    LexiconCfg,
    Settings,
    TrackedFigureBaselineCfg,
    TrackedFigureCfg,
    TrackedFigureSourceCfg,
)


@pytest.fixture
def fake_settings(tmp_path) -> Settings:
    """Build a Settings object with two figures + isolated paths."""
    real = __import__(
        "castelino.config", fromlist=["get_settings"],
    ).get_settings()
    real.figure_deviation = FigureDeviationCfg(
        enabled=True,
        figures=[
            TrackedFigureCfg(
                id="powell",
                display_name="Jerome H. Powell",
                sources=[TrackedFigureSourceCfg(
                    type="audio", provider="deepgram",
                    stream_resolver="fed_event_calendar",
                )],
                lexicons=[LexiconCfg(
                    name="hawkish_dovish_v1", threshold_sigma=1.5,
                    window_size=5,
                    directional_tags_positive=["rates_up", "usd_up"],
                )],
                baseline=TrackedFigureBaselineCfg(),
            ),
            TrackedFigureCfg(
                id="trump",
                display_name="Donald J. Trump",
                sources=[TrackedFigureSourceCfg(
                    type="x_api", username="realdonaldtrump",
                    poll_interval_min=5,
                )],
                lexicons=[
                    LexiconCfg(name="trade_protectionist_v1",
                               threshold_sigma=1.5, window_size=3),
                    LexiconCfg(name="fed_pressure_v1",
                               threshold_sigma=1.5, window_size=3),
                ],
                baseline=TrackedFigureBaselineCfg(),
            ),
        ],
    )
    real.paths.data_dir = str(tmp_path)
    return real


def test_list_figures_returns_all_configured(fake_settings, tmp_path):
    from castelino.dashboard.main import app

    with patch(
        "castelino.dashboard.endpoints.figures.get_settings",
        return_value=fake_settings,
    ):
        client = TestClient(app)
        resp = client.get("/figures")
    assert resp.status_code == 200
    figures = {f["id"]: f for f in resp.json()}
    assert "powell" in figures
    assert "trump" in figures


def test_list_figures_carries_lexicons_and_source_types(
    fake_settings, tmp_path,
):
    from castelino.dashboard.main import app

    with patch(
        "castelino.dashboard.endpoints.figures.get_settings",
        return_value=fake_settings,
    ):
        client = TestClient(app)
        figures = {f["id"]: f for f in client.get("/figures").json()}
    assert figures["trump"]["lexicons"] == [
        "trade_protectionist_v1", "fed_pressure_v1",
    ]
    assert figures["trump"]["source_types"] == ["x_api"]
    assert figures["powell"]["source_types"] == ["audio"]


def test_get_figure_detail_includes_baseline_status(fake_settings, tmp_path):
    from castelino.dashboard.main import app
    from castelino.triggers.figure_deviation.models import FigureBaseline

    # Seed a baseline for trump × trade_protectionist_v1
    base_dir = tmp_path / "figure_baselines" / "trump"
    base_dir.mkdir(parents=True)
    (base_dir / "trade_protectionist_v1.json").write_text(
        FigureBaseline(
            figure_id="trump", lexicon_name="trade_protectionist_v1",
            lexicon_version=1, mean=0.12, std=0.18, n_samples=480,
            last_refreshed=datetime.now(UTC),
        ).model_dump_json(indent=2),
    )

    with patch(
        "castelino.dashboard.endpoints.figures.get_settings",
        return_value=fake_settings,
    ):
        client = TestClient(app)
        resp = client.get("/figures/trump")
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == "trump"
    lex_by_name = {lex["name"]: lex for lex in body["lexicons"]}
    assert lex_by_name["trade_protectionist_v1"]["baseline_present"] is True
    assert lex_by_name["trade_protectionist_v1"]["baseline_mean"] == 0.12
    assert lex_by_name["fed_pressure_v1"]["baseline_present"] is False


def test_get_unknown_figure_returns_404(fake_settings, tmp_path):
    from castelino.dashboard.main import app

    with patch(
        "castelino.dashboard.endpoints.figures.get_settings",
        return_value=fake_settings,
    ):
        client = TestClient(app)
        resp = client.get("/figures/nonexistent")
    assert resp.status_code == 404
