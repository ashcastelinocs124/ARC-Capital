"""The free reads: bond yields (FRED), who pays for AI (Ramp) and which models businesses use
(OpenRouter). Code only."""

from __future__ import annotations

from castelino.agents.research.deep import sources
from castelino.week_ahead import spend

RATES = {
    "treasury_10y": "DGS10",
    "high_yield": "BAMLH0A0HYM2EY",
}  # the 10-yr; ICE BofA HY effective yield
SIZES = {"Large businesses": "large", "Medium-sized businesses": "mid", "Small businesses": "small"}


def rates(fetch_fred=spend.default_fred) -> dict:
    out = {}
    for key, sid in RATES.items():
        s = fetch_fred(sid).dropna()
        out[key] = {"value": round(float(s.iloc[-1]), 2), "date": f"{s.index[-1]:%Y-%m-%d}"}
    return out


def _latest(rows: list[dict]) -> list[dict]:
    last = max(r["date_month"] for r in rows)
    return [r for r in rows if r["date_month"] == last]


def ramp(rows=sources.ramp_rows) -> dict:
    sizes = _latest(rows("adoptionSize"))
    vendors = _latest(rows("adoptionVendor"))
    industries = _latest(rows("adoptionIndustry"))
    by_size = {r["business_size"]: r["adoption_rate_pct"] for r in sizes}
    return {
        "month": max(r["date_month"] for r in sizes)[:7],
        "sizes": [
            {"size": key, "label": label, "pct": round(by_size[label], 1)}
            for label, key in SIZES.items()
            if label in by_size
        ],
        "vendors": sorted(
            ({"vendor": r["vendor"], "pct": round(r["adoption_rate_pct"], 1)} for r in vendors),
            key=lambda v: -v["pct"],
        ),
        "industries": sorted(
            (
                {"industry": r["naics_sector"], "pct": round(r["adoption_rate_pct"], 1)}
                for r in industries
            ),
            key=lambda v: -v["pct"],
        ),
    }


def openrouter(get_text=spend.get_text) -> dict:
    return spend.openrouter_share(get_text(spend.RANKINGS_URL))
