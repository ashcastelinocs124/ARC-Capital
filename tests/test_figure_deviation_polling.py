"""Wave 5 Task 5.2 — polling orchestrator tests."""
from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from castelino.config import (
    FigureDeviationCfg,
    LexiconCfg,
    TrackedFigureBaselineCfg,
    TrackedFigureCfg,
    TrackedFigureSourceCfg,
)
from castelino.triggers.figure_deviation.models import (
    FigureBaseline,
    FigurePost,
)
from castelino.triggers.figure_deviation.source.base import FigurePostSource


# ────────────────────────── helpers ────────────────────────────────────────


class _FakeSource(FigurePostSource):
    """Test source that records each stream() call and emits canned posts."""

    def __init__(self, posts: list[FigurePost]) -> None:
        self._posts = posts
        self.call_count = 0

    async def stream(self, figure, source_cfg) -> AsyncIterator[FigurePost]:
        self.call_count += 1
        for p in self._posts:
            yield p


class _StubStageB:
    async def confirm_deviation(self, **kw):
        return True


def _setup_lex_and_baseline(tmp_path: Path) -> tuple[Path, Path]:
    lex_dir = tmp_path / "lexicons"
    lex_dir.mkdir()
    (lex_dir / "trade_protectionist_v1.yaml").write_text(
        'name: trade_protectionist_v1\nversion: 1\nhot_terms:\n'
        '  - { term: "tariff", weight: 1.0 }\ncold_terms: []\n'
        'modifiers:\n  intensifiers: []\n  hedges: []\n'
    )
    base_dir = tmp_path / "baselines"
    base_dir.mkdir()
    (base_dir / "trump").mkdir()
    (base_dir / "trump" / "trade_protectionist_v1.json").write_text(
        FigureBaseline(
            figure_id="trump", lexicon_name="trade_protectionist_v1",
            lexicon_version=1, mean=0.0, std=0.1, n_samples=100,
            last_refreshed=datetime.now(UTC),
        ).model_dump_json(indent=2),
    )
    return lex_dir, base_dir


def _trump_cfg() -> FigureDeviationCfg:
    return FigureDeviationCfg(
        enabled=True,
        poll_interval_min=30,
        figures=[TrackedFigureCfg(
            id="trump",
            display_name="Donald J. Trump",
            sources=[TrackedFigureSourceCfg(
                type="x_api", username="realdonaldtrump", poll_interval_min=5,
            )],
            lexicons=[LexiconCfg(
                name="trade_protectionist_v1",
                threshold_sigma=1.5, window_size=3,
                directional_tags_positive=["usd_up"],
                directional_tags_negative=[],
            )],
            baseline=TrackedFigureBaselineCfg(),
        )],
    )


# ────────────────────────── tests ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_tick_polls_due_sources(tmp_path):
    from castelino.triggers.figure_deviation.polling import (
        FigureDeviationPollingOrchestrator,
    )
    lex_dir, base_dir = _setup_lex_and_baseline(tmp_path)

    fake_source = _FakeSource([])

    orch = FigureDeviationPollingOrchestrator(
        cfg=_trump_cfg(),
        source_factory=lambda src_cfg: fake_source,
        baseline_dir=base_dir,
        lexicon_dir=lex_dir,
        stage_b=_StubStageB(),
        emitter=lambda t: None,
    )
    polled = await orch.tick()
    assert polled == 1
    assert fake_source.call_count == 1


@pytest.mark.asyncio
async def test_tick_skips_sources_not_yet_due(tmp_path):
    from castelino.triggers.figure_deviation.polling import (
        FigureDeviationPollingOrchestrator,
    )
    lex_dir, base_dir = _setup_lex_and_baseline(tmp_path)
    fake_source = _FakeSource([])

    orch = FigureDeviationPollingOrchestrator(
        cfg=_trump_cfg(),
        source_factory=lambda src_cfg: fake_source,
        baseline_dir=base_dir,
        lexicon_dir=lex_dir,
        stage_b=_StubStageB(),
        emitter=lambda t: None,
    )
    # Initial poll
    now = datetime.now(UTC)
    await orch.tick(now=now)
    # Tick 1 minute later — interval is 5 min, so should NOT poll
    polled_2 = await orch.tick(now=now + timedelta(minutes=1))
    assert polled_2 == 0
    # Tick 6 minutes later — should poll
    polled_3 = await orch.tick(now=now + timedelta(minutes=6))
    assert polled_3 == 1


@pytest.mark.asyncio
async def test_tick_routes_emitted_posts_through_dispatcher(tmp_path):
    from castelino.triggers.figure_deviation.polling import (
        FigureDeviationPollingOrchestrator,
    )
    lex_dir, base_dir = _setup_lex_and_baseline(tmp_path)
    posts = [
        FigurePost(
            figure_id="trump", text="tariff",
            ts=datetime.now(UTC), source="x_api", event_id=f"t{i}",
        )
        for i in range(3)
    ]
    fake_source = _FakeSource(posts)
    captured = []

    orch = FigureDeviationPollingOrchestrator(
        cfg=_trump_cfg(),
        source_factory=lambda src_cfg: fake_source,
        baseline_dir=base_dir,
        lexicon_dir=lex_dir,
        stage_b=_StubStageB(),
        emitter=captured.append,
    )
    await orch.tick()
    # Three identical 'tariff' posts → window full + Stage A passes →
    # Stage B confirms → at least one trigger emitted
    assert len(captured) >= 1
    assert captured[0].lexicon == "trade_protectionist_v1"


@pytest.mark.asyncio
async def test_tick_isolates_failures_per_source(tmp_path):
    """A source that raises during stream() must not crash the orchestrator."""
    from castelino.triggers.figure_deviation.polling import (
        FigureDeviationPollingOrchestrator,
    )
    lex_dir, base_dir = _setup_lex_and_baseline(tmp_path)

    class ExplodingSource(FigurePostSource):
        async def stream(self, figure, source_cfg):
            raise RuntimeError("boom")
            yield  # pragma: no cover — make this an async gen

    orch = FigureDeviationPollingOrchestrator(
        cfg=_trump_cfg(),
        source_factory=lambda src_cfg: ExplodingSource(),
        baseline_dir=base_dir,
        lexicon_dir=lex_dir,
        stage_b=_StubStageB(),
        emitter=lambda t: None,
    )
    # Must NOT raise
    polled = await orch.tick()
    assert polled == 1


@pytest.mark.asyncio
async def test_tick_skips_audio_sources(tmp_path):
    """Audio sources are event-driven — the polling orchestrator must not
    poll them."""
    from castelino.triggers.figure_deviation.polling import (
        FigureDeviationPollingOrchestrator,
    )
    lex_dir, base_dir = _setup_lex_and_baseline(tmp_path)
    audio_cfg = FigureDeviationCfg(
        enabled=True,
        poll_interval_min=30,
        figures=[TrackedFigureCfg(
            id="powell",
            display_name="Jerome H. Powell",
            sources=[TrackedFigureSourceCfg(
                type="audio", provider="deepgram",
                stream_resolver="fed_event_calendar",
            )],
            lexicons=[LexiconCfg(name="hawkish_dovish_v1")],
        )],
    )

    factory_called = [False]
    def factory(src_cfg):
        factory_called[0] = True
        raise AssertionError("audio source should not be instantiated by poller")

    orch = FigureDeviationPollingOrchestrator(
        cfg=audio_cfg,
        source_factory=factory,
        baseline_dir=base_dir,
        lexicon_dir=lex_dir,
        stage_b=_StubStageB(),
        emitter=lambda t: None,
    )
    polled = await orch.tick()
    assert polled == 0
    assert factory_called[0] is False


@pytest.mark.asyncio
async def test_tick_disabled_cfg_does_nothing(tmp_path):
    from castelino.triggers.figure_deviation.polling import (
        FigureDeviationPollingOrchestrator,
    )
    lex_dir, base_dir = _setup_lex_and_baseline(tmp_path)
    cfg = _trump_cfg()
    cfg.enabled = False
    orch = FigureDeviationPollingOrchestrator(
        cfg=cfg,
        source_factory=lambda src_cfg: _FakeSource([]),
        baseline_dir=base_dir,
        lexicon_dir=lex_dir,
        stage_b=_StubStageB(),
        emitter=lambda t: None,
    )
    polled = await orch.tick()
    assert polled == 0
