from castelino.agents.update.guard import find_unsupported
from tests.update_fixtures import make_snapshot, make_update


def test_grounded_update_passes():
    assert find_unsupported(make_update(), make_snapshot()) == []


def test_invented_bp_move_is_flagged():
    upd = make_update()
    upd.asset_classes = "2y +12bp, SPY -0.4%."
    assert find_unsupported(upd, make_snapshot()) == ["+12bp"]


def test_invented_percent_is_flagged():
    upd = make_update()
    upd.economy = "Core PCE 9.9% vs 3.5% prior."
    assert find_unsupported(upd, make_snapshot()) == ["9.9%"]


def test_probability_formats_are_accepted():
    upd = make_update()
    upd.predictions_changed = "Growth P(up) 76.0% → 71% and inflation 87%."
    assert find_unsupported(upd, make_snapshot()) == []


def test_plain_counts_without_units_are_ignored():
    upd = make_update()
    upd.headline = "Day 10 of outperformance, the 4th upside surprise in 2026."
    assert find_unsupported(upd, make_snapshot()) == []


def test_sector_reads_and_theme_text_are_checked():
    upd = make_update()
    upd.sector_reads[0].text = "Up 42% in a week."
    upd.themes_touched[0].text = "Core PCE 3.7%."
    assert find_unsupported(upd, make_snapshot()) == ["42%"]
