"""Wave 7 Task 7.3 — conviction-ledger dual feed tests."""
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from castelino.triggers.figure_deviation.conviction_feed import (
    _translate_tags,
    feed_conviction_ledger,
)
from castelino.triggers.figure_deviation.dispatcher import PostScoredEvent
from castelino.triggers.figure_deviation.models import FigurePost


# ────────────────────────── tag translation table ──────────────────────────


def test_translate_usd_up_to_growth_up():
    g, i = _translate_tags(["usd_up"])
    assert g == "up"
    assert i == "neutral"


def test_translate_em_equity_down_to_growth_down():
    g, i = _translate_tags(["em_equity_down", "semis_down"])
    assert g == "down"
    assert i == "neutral"


def test_translate_gold_up_to_inflation_up():
    g, i = _translate_tags(["gold_up"])
    assert g == "neutral"
    assert i == "up"


def test_translate_combined_growth_and_inflation():
    g, i = _translate_tags(["usd_up", "em_equity_down", "gold_up"])
    # usd_up=up + em_down=down → tie → neutral
    assert g == "neutral"
    assert i == "up"


def test_translate_unmapped_tag_drops_silently():
    g, i = _translate_tags(["ibit_up"])  # crypto — no growth/inflation signal
    assert g == "neutral"
    assert i == "neutral"


# ────────────────────────── feed integration ───────────────────────────────


def _post() -> FigurePost:
    return FigurePost(
        figure_id="trump",
        text="50% tariffs on China starting Monday",
        ts=datetime.now(UTC),
        source="x_api",
        event_id="t1",
    )


def test_feed_appends_to_conviction_ledger(tmp_path, monkeypatch):
    """A scored post with mappable tags should append to the ledger."""
    appended = []
    monkeypatch.setattr(
        "castelino.triggers.figure_deviation.conviction_feed.conviction.append",
        lambda scores: appended.extend(scores) or len(scores),
    )
    event = PostScoredEvent(
        figure_id="trump", post=_post(), lexicon="trade_protectionist_v1",
        score_value=0.84,
        directional_tags=["usd_up", "em_equity_down", "semis_down"],
    )
    feed_conviction_ledger(event)
    assert len(appended) == 1
    record = appended[0]
    assert record.materiality > 0.3
    assert record.headline_id.startswith("figure_deviation:trump:")


def test_feed_skips_below_noise_floor(monkeypatch):
    """Score < 0.05 in absolute terms is noise — don't pollute the ledger."""
    appended = []
    monkeypatch.setattr(
        "castelino.triggers.figure_deviation.conviction_feed.conviction.append",
        lambda scores: appended.extend(scores) or len(scores),
    )
    event = PostScoredEvent(
        figure_id="trump", post=_post(), lexicon="trade_protectionist_v1",
        score_value=0.02,
        directional_tags=["usd_up"],
    )
    feed_conviction_ledger(event)
    assert appended == []


def test_feed_skips_when_tags_have_no_growth_or_inflation_signal(monkeypatch):
    """A tweet that only fires regulatory_stance crypto sub-axis shouldn't
    contribute to growth/inflation ledger at all."""
    appended = []
    monkeypatch.setattr(
        "castelino.triggers.figure_deviation.conviction_feed.conviction.append",
        lambda scores: appended.extend(scores) or len(scores),
    )
    event = PostScoredEvent(
        figure_id="trump", post=_post(), lexicon="regulatory_stance_v1",
        score_value=0.7,
        directional_tags=["ibit_up", "btc_up"],
    )
    feed_conviction_ledger(event)
    assert appended == []


def test_feed_isolates_failures_in_ledger_append(monkeypatch):
    """If conviction.append raises, the feed must not propagate the
    error — the dispatcher's main path is more important."""
    def boom(scores):
        raise RuntimeError("ledger broken")
    monkeypatch.setattr(
        "castelino.triggers.figure_deviation.conviction_feed.conviction.append",
        boom,
    )
    event = PostScoredEvent(
        figure_id="trump", post=_post(), lexicon="x",
        score_value=0.5, directional_tags=["usd_up"],
    )
    # Must NOT raise
    feed_conviction_ledger(event)


# ────────────────────────── dispatcher hook integration ────────────────────


@pytest.mark.asyncio
async def test_dispatcher_invokes_on_post_scored_for_every_scored_post(
    tmp_path,
):
    """Wire the dispatcher with on_post_scored and confirm it fires on
    every scored post (regardless of Stage A outcome)."""
    from castelino.triggers.figure_deviation.dispatcher import (
        FigureDeviationDispatcher,
        LexiconBinding,
    )
    from castelino.triggers.figure_deviation.models import FigureBaseline

    lex_dir = tmp_path / "lexicons"
    lex_dir.mkdir()
    (lex_dir / "trade_protectionist_v1.yaml").write_text(
        'name: trade_protectionist_v1\nversion: 1\nhot_terms:\n'
        '  - { term: "tariff", weight: 1.0 }\ncold_terms: []\n'
        'modifiers:\n  intensifiers: []\n  hedges: []\n'
    )
    base_dir = tmp_path / "baselines"
    (base_dir / "trump").mkdir(parents=True)
    (base_dir / "trump" / "trade_protectionist_v1.json").write_text(
        FigureBaseline(
            figure_id="trump", lexicon_name="trade_protectionist_v1",
            lexicon_version=1, mean=0.0, std=0.1, n_samples=100,
            last_refreshed=datetime.now(UTC),
        ).model_dump_json()
    )

    class StubStageB:
        async def confirm_deviation(self, **kw):
            return True

    captured_events: list[PostScoredEvent] = []
    dispatcher = FigureDeviationDispatcher(
        figure_id="trump",
        lexicon_bindings=[LexiconBinding(
            name="trade_protectionist_v1", threshold_sigma=99.0,  # never crosses
            window_size=3,
            directional_tags_positive=["usd_up", "em_equity_down"],
            directional_tags_negative=[],
        )],
        lexicon_dir=lex_dir,
        baseline_dir=base_dir,
        stage_b=StubStageB(),
        emitter=lambda t: None,
        on_post_scored=captured_events.append,
    )
    # Stage A will NOT fire (threshold 99σ) — but on_post_scored should
    # still be called for every scored post.
    for ev in ("t1", "t2", "t3"):
        await dispatcher.handle_post(FigurePost(
            figure_id="trump", text="tariff",
            ts=datetime.now(UTC), source="x_api", event_id=ev,
        ))
    assert len(captured_events) == 3
    assert all(e.lexicon == "trade_protectionist_v1" for e in captured_events)
    assert all(e.score_value > 0 for e in captured_events)
    assert "usd_up" in captured_events[0].directional_tags
