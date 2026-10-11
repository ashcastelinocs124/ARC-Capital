import json
from datetime import date

import pytest

from castelino.agents.weekly.inputs import (
    due_week,
    load_week,
    week_bounds,
    week_id,
    week_markdown,
)


def note(day, headline="H"):
    return {
        "version": 2,
        "date": day,
        "note": {
            "headline": headline,
            "takeaways": ["t1"],
            "items": [
                {
                    "rank": 1,
                    "title": "Yields jump",
                    "body": "b",
                    "finding_ids": ["macro-1"],
                    "chart": None,
                }
            ],
        },
        "findings": [{"id": "macro-1", "claim": "10y rose 12bp"}],
    }


def write_notes(d, days):
    for day in days:
        (d / f"{day}.json").write_text(json.dumps(note(day, f"Headline {day}")))


def test_week_id_and_bounds():
    assert week_id(date(2026, 10, 9)) == "2026-W41"
    assert week_bounds("2026-W41") == (date(2026, 10, 5), date(2026, 10, 9))


def test_due_on_weekend_is_this_week_on_weekday_last_week(tmp_path):
    assert due_week(date(2026, 10, 10), tmp_path) == "2026-W41"  # Saturday
    assert due_week(date(2026, 10, 11), tmp_path) == "2026-W41"  # Sunday
    assert due_week(date(2026, 10, 12), tmp_path) == "2026-W41"  # Monday: last week still missing
    (tmp_path / "2026-W41.json").write_text("{}")
    assert due_week(date(2026, 10, 12), tmp_path) is None
    assert due_week(date(2026, 10, 14), tmp_path) is None  # Wed: W41 done, W42 not over yet


def test_load_week_lists_missing_days_as_gaps(tmp_path):
    write_notes(tmp_path, ["2026-10-05", "2026-10-06", "2026-10-08"])
    inp = load_week(tmp_path, "2026-W41", min_notes=3)
    assert inp.days == ["2026-10-05", "2026-10-06", "2026-10-08"]
    assert inp.gaps == ["2026-10-07: no Morning Note", "2026-10-09: no Morning Note"]


def test_holiday_week_with_two_notes_fails(tmp_path):
    write_notes(tmp_path, ["2026-10-05", "2026-10-06"])
    with pytest.raises(RuntimeError, match="only 2 Morning Notes"):
        load_week(tmp_path, "2026-W41", min_notes=3)


def test_v1_note_is_a_gap_not_input(tmp_path):
    write_notes(tmp_path, ["2026-10-05", "2026-10-06", "2026-10-07"])
    (tmp_path / "2026-10-08.json").write_text(json.dumps({"date": "2026-10-08", "update": {}}))
    inp = load_week(tmp_path, "2026-W41", min_notes=3)
    assert "2026-10-08: not a v2 Morning Note" in inp.gaps


def test_markdown_carries_headlines_items_and_finding_claims(tmp_path):
    write_notes(tmp_path, ["2026-10-05", "2026-10-06", "2026-10-07"])
    md = week_markdown(load_week(tmp_path, "2026-W41", min_notes=3))
    assert "## 2026-10-05: Headline 2026-10-05" in md
    assert "item 1: Yields jump" in md and "finding: 10y rose 12bp" in md
