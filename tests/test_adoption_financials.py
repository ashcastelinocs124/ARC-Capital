from types import SimpleNamespace

import pandas as pd
import pytest

from castelino.adoption.sources.financials import fetch_financials

DATES = pd.to_datetime(["2026-06-30", "2026-03-31", "2025-12-31", "2025-09-30", "2025-06-30"])


def fake_yf(cashflow, financials):
    return SimpleNamespace(
        Ticker=lambda t: SimpleNamespace(
            quarterly_cashflow=cashflow, quarterly_financials=financials
        )
    )


def frame(rows):
    return pd.DataFrame(rows, index=DATES).T


def test_ttm_uses_newest_four_quarters_and_capex_magnitude():
    cf = frame({"Capital Expenditure": [-10, -10, -10, -10, -99]})
    fin = frame(
        {"Research And Development": [5, 5, 5, 5, 50], "Total Revenue": [100, 100, 100, 100, 999]}
    )
    capex, rnd, rev = fetch_financials("ACME", yf=fake_yf(cf, fin))
    assert (capex, rnd, rev) == (pytest.approx(40.0), pytest.approx(20.0), pytest.approx(400.0))


def test_missing_row_or_too_few_quarters_is_none():
    cf = frame({"Other": [1, 1, 1, 1, 1]})
    fin = pd.DataFrame(
        {DATES[0]: [5.0, 100.0], DATES[1]: [5.0, 100.0]},
        index=["Research And Development", "Total Revenue"],
    )
    assert fetch_financials("ACME", yf=fake_yf(cf, fin)) == (None, None, None)
