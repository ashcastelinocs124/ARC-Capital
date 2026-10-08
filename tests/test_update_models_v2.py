import pandas as pd

from castelino.agents.update.collector import _release
from castelino.agents.update.models import DailyRecordV2, MorningNote, NoteItem, Stage
from castelino.config import get_settings


def test_release_carries_data_periods():
    idx = pd.date_range("2025-06-01", periods=15, freq="MS")
    r = _release("CPIAUCSL", "CPI y/y", "yoy", pd.Series(range(100, 115), index=idx, dtype=float))
    assert r.latest_period == idx[-1].strftime("%b %Y")
    assert r.prior_period == idx[-2].strftime("%b %Y")


def test_v2_record_roundtrip():
    note = MorningNote(
        headline="h",
        takeaways=["a", "b", "c"],
        items=[NoteItem(rank=1, title="t", body="b", finding_ids=["macro-1"], chart=None)],
        themes_touched=[],
        new_themes=[],
    )
    rec = DailyRecordV2(
        date="2026-10-07",
        generated_at="2026-10-07T07:00:00",
        findings=[],
        note=note,
        exhibits=[],
        releases=[],
        rounds=0,
        data_gaps=[],
    )
    back = DailyRecordV2.model_validate_json(rec.model_dump_json())
    assert back.version == 2 and back.note.takeaways == ["a", "b", "c"]


def test_new_stages_and_config():
    assert [s.value for s in Stage] == [
        "idle",
        "planning",
        "researching",
        "reviewing",
        "writing",
        "guarding",
        "charting",
        "done",
        "failed",
    ]
    ua = get_settings().update_agent
    assert (ua.orchestrator_model, ua.editor_model, ua.agent_model, ua.search_model) == (
        "gpt-6-sol",
        "gpt-6-sol",
        "gpt-6-luna",
        "gpt-6-luna",
    )
    assert (ua.max_rounds, ua.items) == (2, 5)


def test_backfilled_defaults_false_and_round_trips():
    note = MorningNote(
        headline="h", takeaways=["a", "b", "c"], items=[], themes_touched=[], new_themes=[]
    )
    base = dict(
        date="2026-10-03",
        generated_at="2026-10-07T20:00:00",
        findings=[],
        note=note,
        exhibits=[],
        releases=[],
        rounds=0,
        data_gaps=[],
    )
    assert DailyRecordV2(**base).backfilled is False
    assert DailyRecordV2.model_validate_json(
        DailyRecordV2(**base, backfilled=True).model_dump_json()
    ).backfilled
