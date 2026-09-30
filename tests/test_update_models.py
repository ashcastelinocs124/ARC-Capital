from castelino.agents.update.fsio import atomic_write_text
from castelino.agents.update.models import DailyRecord, MarketSnapshot, Stage
from castelino.config import get_settings
from tests.update_fixtures import make_snapshot, make_update


def test_config_defaults():
    cfg = get_settings().update_agent
    assert cfg.gate_tolerance == 0.02
    assert (cfg.short_term_notes, cfg.long_term_notes) == (5, 20)
    assert cfg.max_guard_retries == 1 and cfg.enabled is True


def test_snapshot_and_record_roundtrip():
    rec = DailyRecord(date="2026-09-30", generated_at="2026-09-30T07:30:00",
                      snapshot=make_snapshot(), update=make_update())
    again = DailyRecord.model_validate_json(rec.model_dump_json())
    assert again.snapshot.prediction["growth"].new == 0.71
    assert again.update.new_themes[0].importance == 3


def test_empty_snapshot_is_valid():
    assert MarketSnapshot(date="2026-09-30").releases == []


def test_stage_values():
    assert Stage.IDLE.value == "idle" and Stage.FAILED.value == "failed"


def test_atomic_write_creates_parents_and_leaves_no_tmp(tmp_path):
    p = tmp_path / "a" / "b.json"
    atomic_write_text(p, "{}")
    assert p.read_text() == "{}"
    assert not list(tmp_path.rglob("*.tmp"))
