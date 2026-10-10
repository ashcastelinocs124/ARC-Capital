# ruff: noqa: N803, N806 - X/Z are the usual design-matrix names
import numpy as np
import pandas as pd
import pytest

from castelino.cross_asset import model as m


def _data(asset="gld", n=170, seed=0):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2023-01-06", periods=n, freq="W-FRI")
    cols = m.columns_for(asset)
    X = pd.DataFrame(rng.normal(size=(n, len(cols))), index=idx, columns=cols)
    true = pd.Series(0.0, index=cols)
    true["ry"] = -0.5
    if "usd" in cols:
        true["usd"] = -0.8
    y = X @ true + rng.normal(scale=0.3, size=n)
    return X, y, true


def test_factor_map_respected():
    assert "usd" not in m.columns_for("ief") and "be" not in m.columns_for("spx")
    assert "pos_gld" in m.columns_for("gld") and "pos" not in m.columns_for("gld")


@pytest.mark.parametrize("asset", ["spx", "ief", "gld"])
def test_contributions_plus_unexplained_equal_move(asset):
    X, y, _ = _data(asset)
    out = m.explain(asset, X, y)
    for w, k in (("1w", 1), ("1m", 4), ("3m", 13)):
        win = out["windows"][w]
        total = sum(c["contribution"] for c in win["contributions"]) + win["unexplained"]
        assert total == pytest.approx(win["move"], abs=1e-9)
        assert win["move"] == pytest.approx(y.iloc[-k:].sum())
        g = sum(gr["contribution"] for gr in win["groups"]) + win["unexplained"]
        assert g == pytest.approx(win["move"], abs=1e-9)


def test_recovers_planted_betas():
    X, y, _ = _data("gld", n=400)
    f = m.fit(X.iloc[-104:], y.iloc[-104:])
    assert f.beta["ry"] == pytest.approx(-0.5, abs=0.1)
    assert f.beta["usd"] == pytest.approx(-0.8, abs=0.1)


def test_constant_column_gets_zero_beta():
    X, y, _ = _data("spx")
    X["inflation"] = 0.0  # no releases in the window
    f = m.fit(X.iloc[-104:], y.iloc[-104:])
    assert f.beta["inflation"] == 0


def test_walk_forward_r2_high_for_explainable_asset():
    X, y, _ = _data("gld", n=200)
    assert m.walk_forward_r2(X, y) > 0.7


def test_groups_and_summary():
    X, y, _ = _data("gld")
    out = m.explain("gld", X, y)
    rates = next(g for g in out["windows"]["1w"]["groups"] if g["group"] == "rates")
    assert {c["factor"] for c in rates["members"]} == {"y2", "ry", "be"}
    assert 0 <= rates["max_pairwise_corr"] <= 1
    line = m.summary_line(out)
    assert line.startswith("Biggest drivers:") and "pts" in line
