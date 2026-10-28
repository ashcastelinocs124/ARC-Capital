import pandas as pd

from castelino.dashboards.ai_capex import market

SIZES = [
    {"date_month": "2026-08-01", "business_size": "Large businesses", "adoption_rate_pct": 64.0},
    {"date_month": "2026-09-01", "business_size": "Large businesses", "adoption_rate_pct": 65.71},
    {
        "date_month": "2026-09-01",
        "business_size": "Medium-sized businesses",
        "adoption_rate_pct": 62.49,
    },
    {"date_month": "2026-09-01", "business_size": "Small businesses", "adoption_rate_pct": 50.0},
]
VENDORS = [{"date_month": "2026-09-01", "vendor": "Anthropic", "adoption_rate_pct": 43.8}]
INDUSTRIES = [
    {"date_month": "2026-09-01", "naics_sector": "Information", "adoption_rate_pct": 79.9}
]


def rows(key):
    return {"adoptionSize": SIZES, "adoptionVendor": VENDORS, "adoptionIndustry": INDUSTRIES}[key]


def test_ramp_maps_medium_to_mid():
    got = market.ramp(rows)
    assert got["month"] == "2026-09"
    assert got["sizes"] == [
        {"size": "large", "label": "Large businesses", "pct": 65.7},
        {"size": "mid", "label": "Medium-sized businesses", "pct": 62.5},
        {"size": "small", "label": "Small businesses", "pct": 50.0},
    ]
    assert got["vendors"] == [{"vendor": "Anthropic", "pct": 43.8}]
    assert got["industries"] == [{"industry": "Information", "pct": 79.9}]


def test_rates_latest_non_null():
    def fred(sid):
        idx = pd.to_datetime(["2026-10-26", "2026-10-27", "2026-10-28"])
        return pd.Series(
            {"DGS10": [4.1, 4.2, None], "BAMLH0A0HYM2EY": [6.7, 6.8, None]}[sid], index=idx
        )

    got = market.rates(fred)
    assert got == {
        "treasury_10y": {"value": 4.2, "date": "2026-10-27"},
        "high_yield": {"value": 6.8, "date": "2026-10-27"},
    }
