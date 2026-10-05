import pytest

from castelino.adoption.score import company_score, hire_raw, pillar_scores, spend_raw, talk_raw


def test_talk_raw():
    assert talk_raw([1, 2, 3], 2000) == pytest.approx(3.0)
    assert talk_raw([], 1000) == 0.0          # no AI claims is a valid zero
    assert talk_raw([2], 0) is None           # no text is missing, not zero


def test_hire_raw():
    assert hire_raw(5, 100) == pytest.approx(0.05)
    assert hire_raw(0, 0) is None


def test_spend_raw():
    assert spend_raw(10, 5, 100) == pytest.approx(0.15)
    assert spend_raw(None, 5, 50) == pytest.approx(0.1)
    assert spend_raw(None, None, 100) is None
    assert spend_raw(10, 5, None) is None
    assert spend_raw(10, 5, 0) is None


def test_pillar_scores_golden():
    raw = {
        "A": {"talk": 1.0, "hire": None, "spend": None},
        "B": {"talk": 3.0, "hire": None, "spend": None},
    }
    s = pillar_scores(raw)
    assert s["A"]["talk"] == pytest.approx(50 - 50 / 3)   # z = -1
    assert s["B"]["talk"] == pytest.approx(50 + 50 / 3)   # z = +1
    assert s["A"]["hire"] is None


def test_pillar_scores_clip_at_three_sigma():
    raw = {f"T{i}": {"talk": 0.0, "hire": None, "spend": None} for i in range(19)}
    raw["OUT"] = {"talk": 100.0, "hire": None, "spend": None}
    s = pillar_scores(raw)
    assert s["OUT"]["talk"] == pytest.approx(100.0)       # z ~ 4.4 clipped to 3


def test_pillar_scores_zero_variance_and_single_company():
    same = {t: {"talk": 2.0, "hire": None, "spend": None} for t in "AB"}
    assert pillar_scores(same)["A"]["talk"] == pytest.approx(50.0)
    one = {"A": {"talk": 9.0, "hire": None, "spend": None}}
    assert pillar_scores(one)["A"]["talk"] == pytest.approx(50.0)


def test_company_score_needs_two_pillars():
    assert company_score({"talk": 30.0, "hire": 60.0, "spend": 90.0}) == (pytest.approx(60.0), 3)
    assert company_score({"talk": 30.0, "hire": None, "spend": 70.0}) == (pytest.approx(50.0), 2)
    assert company_score({"talk": 30.0, "hire": None, "spend": None}) == (None, 1)
    assert company_score({"talk": None, "hire": None, "spend": None}) == (None, 0)
