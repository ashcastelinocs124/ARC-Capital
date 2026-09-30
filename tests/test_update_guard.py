from castelino.agents.update.guard import find_unsupported
from tests.update_fixtures import make_snapshot, make_update


def test_grounded_update_passes():
    assert find_unsupported(make_update(), make_snapshot()) == []


def test_invented_bp_move_is_flagged():
    upd = make_update()
    upd.asset_classes = "2y +17bp, SPY -0.4%."
    assert find_unsupported(upd, make_snapshot()) == ["+17bp"]


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


# ── final-review regressions ──────────────────────────────────────────────


def test_spelled_out_units_are_checked():
    upd = make_update()
    upd.asset_classes = "Core PCE 3.7 percent, up 17 basis points."
    assert find_unsupported(upd, make_snapshot()) == ["17 basis points"]


def test_explicit_sign_must_match():
    upd = make_update()
    upd.asset_classes = "SPY +0.4% on the day."          # snapshot has -0.4
    assert find_unsupported(upd, make_snapshot()) == ["+0.4%"]


def test_times_100_only_applies_to_predictions():
    upd = make_update()
    upd.economy = "SPY moved 40% of its range."          # only SPY -0.4 ×100 could match; it is not a probability
    assert find_unsupported(upd, make_snapshot()) == ["40%"]


def test_tolerance_follows_displayed_precision():
    upd = make_update()
    upd.economy = "Core PCE 3.74% vs 3.5% prior."        # snapshot 3.7: 3.74 is a different number
    assert find_unsupported(upd, make_snapshot()) == ["3.74%"]
