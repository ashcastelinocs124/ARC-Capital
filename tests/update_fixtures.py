from castelino.agents.update.models import (
    DailyUpdate,
    MarketSnapshot,
    NewTheme,
    PredictionDelta,
    Release,
    SectorRead,
    SectorTrend,
    ThemeEdit,
)
from castelino.forecast.regime import (
    GrowthForecast,
    InflationForecast,
    RegimeForecast,
    _ModelMetrics,
)


def make_forecast(
    g_prob=0.76, g_brier=0.236, i_prob=0.87, i_brier=0.189, feature_month="2026-08-01"
) -> RegimeForecast:
    def mk(cls, tid, prob, brier):
        return cls(
            target_id=tid,
            target_name=tid,
            feature_month=feature_month,
            target_month="2026-09-01",
            up=prob >= 0.5,
            prob_up=prob,
            indicators_used=[tid],
            train_metrics=_ModelMetrics(accuracy=0.65, brier=brier, n_test=100),
            history_start="2000-01-01",
            n_obs=300,
        )

    return RegimeForecast(
        growth=mk(GrowthForecast, "INDPRO", g_prob, g_brier),
        inflation=mk(InflationForecast, "PCEPILFE", i_prob, i_brier),
    )


def make_snapshot() -> MarketSnapshot:
    row = lambda a, b, c: {"1d": a, "1w": b, "1m": c}  # noqa: E731
    return MarketSnapshot(
        date="2026-09-30",
        releases=[
            Release(series="PCEPILFE", name="Core PCE y/y", latest=3.7, prior=3.5, change=0.2)
        ],
        asset_returns={
            "rates_credit": {"DGS2": row(8.0, 12.0, 30.0), "TLT": row(-0.6, -1.0, -4.0)},
            "equities": {"SPY": row(-0.4, -0.5, 1.0)},
        },
        sectors=[
            SectorTrend(
                sector="XLE",
                r1w=2.1,
                r1m=6.8,
                r3m=11.2,
                r6m=7.5,
                r12m=-2.0,
                rel1m=5.9,
                rel12m=-20.0,
                short_label="accelerating",
                long_label="bottoming, turning up",
            )
        ],
        prediction={
            "growth": PredictionDelta(old=0.76, new=0.71, gate="promoted"),
            "inflation": PredictionDelta(old=0.87, new=0.87, gate="kept"),
        },
        data_gaps=["BCOM (empty)"],
    )


def make_update() -> DailyUpdate:
    return DailyUpdate(
        headline="Hot Core PCE extends the inflation theme; growth odds slip.",
        economy="Core PCE 3.7% vs 3.5% prior.",
        asset_classes="2y +8bp, SPY -0.4%.",
        predictions_changed="Growth P(up) 76% → 71%. Inflation held at 87%.",
        themes_touched=[
            ThemeEdit(title="Inflation re-accelerating", text="Core PCE 3.7%, fourth hot print.")
        ],
        new_themes=[
            NewTheme(title="Energy leadership", text="XLE +6.8% over a month.", importance=3)
        ],
        sector_reads=[SectorRead(sector="XLE", text="Leading on oil supply.")],
    )
