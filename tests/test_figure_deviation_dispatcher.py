"""Wave 3 Task 3.4 — multi-lexicon dispatcher.

A single FigurePost from a tracked figure must fan out across every lexicon
configured on that figure. Each lexicon scores independently, updates its
own rolling window, and can emit a `FigureDeviationTrigger` independently
of the others. Cooldown is per (figure_id, lexicon, event_id) triple so a
single tweet that hits two lexicons emits exactly two triggers (one per
lexicon), but a re-feed of the same post emits zero.
"""
from __future__ import annotations

import textwrap
from datetime import UTC, datetime
from pathlib import Path

import pytest

from castelino.triggers.figure_deviation.models import (
    FigureBaseline,
    FigureDeviationTrigger,
    FigurePost,
    LexiconScore,
)


# ────────────────────────── helpers / fixtures ─────────────────────────────


def _post(text: str, *, event_id: str, figure_id: str = "trump") -> FigurePost:
    return FigurePost(
        figure_id=figure_id,
        text=text,
        ts=datetime.now(UTC),
        source="x_api",
        event_id=event_id,
    )


def _build_lexicon(lex_dir: Path, name: str, terms: dict[str, float]) -> None:
    hot_terms_yaml = "\n".join(
        f'  - {{ term: "{t}", weight: {w} }}' for t, w in terms.items()
    )
    yaml_body = (
        f"name: {name}\n"
        f"version: 1\n"
        f"axis: test\n"
        f"hot_terms:\n"
        f"{hot_terms_yaml}\n"
        f"cold_terms: []\n"
        f"modifiers:\n"
        f"  intensifiers: []\n"
        f"  hedges: []\n"
    )
    (lex_dir / f"{name}.yaml").write_text(yaml_body)


def _build_baseline(
    base_dir: Path, *, figure_id: str, lexicon: str, mean: float, std: float,
) -> None:
    fig_dir = base_dir / figure_id
    fig_dir.mkdir(parents=True, exist_ok=True)
    base = FigureBaseline(
        figure_id=figure_id, lexicon_name=lexicon, lexicon_version=1,
        mean=mean, std=std, n_samples=100,
        last_refreshed=datetime.now(UTC),
    )
    (fig_dir / f"{lexicon}.json").write_text(base.model_dump_json(indent=2))


class _FakeStageB:
    """Stage B stand-in for Wave 3. Always confirms; records every call.
    Real Stage B (LLM gate with FigureProfile retrieval) lands in Wave 7."""

    def __init__(self, *, confirm: bool = True) -> None:
        self.confirm = confirm
        self.calls: list[dict] = []

    async def confirm_deviation(self, **kwargs):
        self.calls.append(kwargs)
        return self.confirm


# ────────────────────────── fan-out ────────────────────────────────────────


@pytest.mark.asyncio
async def test_single_post_fans_across_all_configured_lexicons(tmp_path):
    """One post that scores positive on TWO lexicons emits TWO triggers."""
    from castelino.triggers.figure_deviation.dispatcher import (
        FigureDeviationDispatcher,
        LexiconBinding,
    )

    lex_dir = tmp_path / "lexicons"
    lex_dir.mkdir()
    _build_lexicon(lex_dir, "trade_protectionist_v1", {"tariff": 1.0})
    _build_lexicon(lex_dir, "fed_pressure_v1", {"powell": 1.0})

    base_dir = tmp_path / "baselines"
    base_dir.mkdir()
    _build_baseline(base_dir, figure_id="trump",
                    lexicon="trade_protectionist_v1", mean=0.0, std=0.1)
    _build_baseline(base_dir, figure_id="trump",
                    lexicon="fed_pressure_v1", mean=0.0, std=0.1)

    captured: list[FigureDeviationTrigger] = []
    dispatcher = FigureDeviationDispatcher(
        figure_id="trump",
        lexicon_bindings=[
            LexiconBinding(
                name="trade_protectionist_v1",
                threshold_sigma=1.5,
                window_size=3,
                directional_tags_positive=["usd_up", "em_equity_down"],
                directional_tags_negative=[],
            ),
            LexiconBinding(
                name="fed_pressure_v1",
                threshold_sigma=1.5,
                window_size=3,
                directional_tags_positive=["rates_down", "gold_up"],
                directional_tags_negative=[],
            ),
        ],
        lexicon_dir=lex_dir,
        baseline_dir=base_dir,
        stage_b=_FakeStageB(confirm=True),
        emitter=captured.append,
    )

    # Seed 2 prior posts that hit both lexicons to fill the rolling windows
    await dispatcher.handle_post(
        _post("tariff and powell", event_id="t1"),
    )
    await dispatcher.handle_post(
        _post("tariff and powell", event_id="t2"),
    )
    # Third post (window now full) should trigger both
    await dispatcher.handle_post(
        _post("tariff and powell", event_id="t3"),
    )

    emitted_lexicons = {t.lexicon for t in captured}
    assert "trade_protectionist_v1" in emitted_lexicons
    assert "fed_pressure_v1" in emitted_lexicons


# ────────────────────────── single-lexicon emission ────────────────────────


@pytest.mark.asyncio
async def test_post_hitting_one_lexicon_emits_one_trigger(tmp_path):
    """A post that hits trade-protectionism but not Fed-pressure produces
    exactly ONE trigger (not two)."""
    from castelino.triggers.figure_deviation.dispatcher import (
        FigureDeviationDispatcher,
        LexiconBinding,
    )

    lex_dir = tmp_path / "lexicons"
    lex_dir.mkdir()
    _build_lexicon(lex_dir, "trade_protectionist_v1", {"tariff": 1.0})
    _build_lexicon(lex_dir, "fed_pressure_v1", {"powell": 1.0})

    base_dir = tmp_path / "baselines"
    base_dir.mkdir()
    _build_baseline(base_dir, figure_id="trump",
                    lexicon="trade_protectionist_v1", mean=0.0, std=0.1)
    _build_baseline(base_dir, figure_id="trump",
                    lexicon="fed_pressure_v1", mean=0.0, std=0.1)

    captured: list[FigureDeviationTrigger] = []
    dispatcher = FigureDeviationDispatcher(
        figure_id="trump",
        lexicon_bindings=[
            LexiconBinding(name="trade_protectionist_v1", threshold_sigma=1.5,
                           window_size=3,
                           directional_tags_positive=["usd_up"],
                           directional_tags_negative=[]),
            LexiconBinding(name="fed_pressure_v1", threshold_sigma=1.5,
                           window_size=3,
                           directional_tags_positive=["gold_up"],
                           directional_tags_negative=[]),
        ],
        lexicon_dir=lex_dir,
        baseline_dir=base_dir,
        stage_b=_FakeStageB(confirm=True),
        emitter=captured.append,
    )
    for ev in ("t1", "t2", "t3"):
        await dispatcher.handle_post(
            _post("tariff (no fed mention here)", event_id=ev),
        )
    emitted_lexicons = {t.lexicon for t in captured}
    assert emitted_lexicons == {"trade_protectionist_v1"}


# ────────────────────────── directional tags wired into trigger ────────────


@pytest.mark.asyncio
async def test_emitted_trigger_carries_lexicon_directional_tags(tmp_path):
    from castelino.triggers.figure_deviation.dispatcher import (
        FigureDeviationDispatcher,
        LexiconBinding,
    )

    lex_dir = tmp_path / "lexicons"
    lex_dir.mkdir()
    _build_lexicon(lex_dir, "trade_protectionist_v1", {"tariff": 1.0})

    base_dir = tmp_path / "baselines"
    base_dir.mkdir()
    _build_baseline(base_dir, figure_id="trump",
                    lexicon="trade_protectionist_v1", mean=0.0, std=0.1)

    captured: list[FigureDeviationTrigger] = []
    dispatcher = FigureDeviationDispatcher(
        figure_id="trump",
        lexicon_bindings=[LexiconBinding(
            name="trade_protectionist_v1", threshold_sigma=1.5, window_size=3,
            directional_tags_positive=["usd_up", "em_equity_down", "semis_down"],
            directional_tags_negative=[],
        )],
        lexicon_dir=lex_dir,
        baseline_dir=base_dir,
        stage_b=_FakeStageB(confirm=True),
        emitter=captured.append,
    )
    for ev in ("t1", "t2", "t3"):
        await dispatcher.handle_post(_post("tariff", event_id=ev))

    assert len(captured) >= 1
    trigger = captured[0]
    assert "usd_up" in trigger.directional_tags
    assert "em_equity_down" in trigger.directional_tags
    assert "semis_down" in trigger.directional_tags
    assert trigger.direction == "positive"


# ────────────────────────── cooldown ───────────────────────────────────────


@pytest.mark.asyncio
async def test_cooldown_skips_duplicate_event_ids(tmp_path):
    """Re-feeding the same post (same event_id) does not emit twice on the
    same lexicon."""
    from castelino.triggers.figure_deviation.dispatcher import (
        FigureDeviationDispatcher,
        LexiconBinding,
    )

    lex_dir = tmp_path / "lexicons"
    lex_dir.mkdir()
    _build_lexicon(lex_dir, "trade_protectionist_v1", {"tariff": 1.0})

    base_dir = tmp_path / "baselines"
    base_dir.mkdir()
    _build_baseline(base_dir, figure_id="trump",
                    lexicon="trade_protectionist_v1", mean=0.0, std=0.1)

    captured: list[FigureDeviationTrigger] = []
    dispatcher = FigureDeviationDispatcher(
        figure_id="trump",
        lexicon_bindings=[LexiconBinding(
            name="trade_protectionist_v1", threshold_sigma=1.5, window_size=3,
            directional_tags_positive=["usd_up"],
            directional_tags_negative=[],
        )],
        lexicon_dir=lex_dir,
        baseline_dir=base_dir,
        stage_b=_FakeStageB(confirm=True),
        emitter=captured.append,
    )
    for ev in ("t1", "t2", "t3"):
        await dispatcher.handle_post(_post("tariff", event_id=ev))
    n_first = len(captured)
    # Re-feed t3 — must NOT emit again
    await dispatcher.handle_post(_post("tariff", event_id="t3"))
    assert len(captured) == n_first


# ────────────────────────── Stage B veto blocks emission ───────────────────


@pytest.mark.asyncio
async def test_stage_b_veto_blocks_emission(tmp_path):
    """Stage A passes but Stage B says 'not confirmed' — no trigger."""
    from castelino.triggers.figure_deviation.dispatcher import (
        FigureDeviationDispatcher,
        LexiconBinding,
    )

    lex_dir = tmp_path / "lexicons"
    lex_dir.mkdir()
    _build_lexicon(lex_dir, "trade_protectionist_v1", {"tariff": 1.0})

    base_dir = tmp_path / "baselines"
    base_dir.mkdir()
    _build_baseline(base_dir, figure_id="trump",
                    lexicon="trade_protectionist_v1", mean=0.0, std=0.1)

    captured: list[FigureDeviationTrigger] = []
    dispatcher = FigureDeviationDispatcher(
        figure_id="trump",
        lexicon_bindings=[LexiconBinding(
            name="trade_protectionist_v1", threshold_sigma=1.5, window_size=3,
            directional_tags_positive=["usd_up"],
            directional_tags_negative=[],
        )],
        lexicon_dir=lex_dir,
        baseline_dir=base_dir,
        stage_b=_FakeStageB(confirm=False),  # vetoes
        emitter=captured.append,
    )
    for ev in ("t1", "t2", "t3"):
        await dispatcher.handle_post(_post("tariff", event_id=ev))
    assert captured == []
