"""Instrument registry — the tradable universe and its source mapping.

Single source of truth for: what we trade, what asset class it is, and where
its prices come from. Adapters in `pricing.py` route on `source` and `symbol`.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class AssetClass(str, Enum):
    EQUITY = "equity"
    BOND_ETF = "bond_etf"
    COMMODITY_ETF = "commodity_etf"
    FUTURES = "futures"
    FX = "fx"


class PriceSource(str, Enum):
    YFINANCE = "yfinance"
    FRED = "fred"


class Instrument(BaseModel):
    """An asset we can trade, mark, or read context from."""

    instrument_id: str  # canonical name used everywhere (e.g. "TLT", "EURUSD")
    symbol: str  # provider-specific ticker (e.g. "EURUSD=X" for yfinance)
    asset_class: AssetClass
    source: PriceSource
    description: str = ""
    # Average daily volume in USD (rough). None = treat liquidity check as pass-through.
    avg_daily_volume_usd: float | None = None
    # Multiplier for futures (contract value = price * multiplier)
    contract_multiplier: float = Field(default=1.0, ge=0.0)
    # Tradeable. FRED yields are read-only context, not tradable.
    tradable: bool = True


# v1 universe — ~30 instruments per design doc §3.
# Equities: top S&P names + sector ETFs. Bonds: duration-bucket ETFs + FRED context.
# Commodities: ETFs + front-month futures. FX: 5 majors.
INSTRUMENTS: dict[str, Instrument] = {
    # ── Equities (top names + sectors) ────────────────────────────────────
    "SPY": Instrument(
        instrument_id="SPY", symbol="SPY", asset_class=AssetClass.EQUITY,
        source=PriceSource.YFINANCE, description="S&P 500 ETF",
        avg_daily_volume_usd=40_000_000_000,
    ),
    "QQQ": Instrument(
        instrument_id="QQQ", symbol="QQQ", asset_class=AssetClass.EQUITY,
        source=PriceSource.YFINANCE, description="Nasdaq-100 ETF",
        avg_daily_volume_usd=20_000_000_000,
    ),
    "AAPL": Instrument(
        instrument_id="AAPL", symbol="AAPL", asset_class=AssetClass.EQUITY,
        source=PriceSource.YFINANCE, description="Apple Inc.",
        avg_daily_volume_usd=10_000_000_000,
    ),
    "MSFT": Instrument(
        instrument_id="MSFT", symbol="MSFT", asset_class=AssetClass.EQUITY,
        source=PriceSource.YFINANCE, description="Microsoft Corp.",
        avg_daily_volume_usd=8_000_000_000,
    ),
    "NVDA": Instrument(
        instrument_id="NVDA", symbol="NVDA", asset_class=AssetClass.EQUITY,
        source=PriceSource.YFINANCE, description="Nvidia Corp.",
        avg_daily_volume_usd=30_000_000_000,
    ),
    "GOOGL": Instrument(
        instrument_id="GOOGL", symbol="GOOGL", asset_class=AssetClass.EQUITY,
        source=PriceSource.YFINANCE, description="Alphabet Class A",
        avg_daily_volume_usd=4_000_000_000,
    ),
    "AMZN": Instrument(
        instrument_id="AMZN", symbol="AMZN", asset_class=AssetClass.EQUITY,
        source=PriceSource.YFINANCE, description="Amazon.com Inc.",
        avg_daily_volume_usd=8_000_000_000,
    ),
    "META": Instrument(
        instrument_id="META", symbol="META", asset_class=AssetClass.EQUITY,
        source=PriceSource.YFINANCE, description="Meta Platforms",
        avg_daily_volume_usd=6_000_000_000,
    ),
    "XLE": Instrument(
        instrument_id="XLE", symbol="XLE", asset_class=AssetClass.EQUITY,
        source=PriceSource.YFINANCE, description="Energy Select Sector SPDR",
        avg_daily_volume_usd=1_500_000_000,
    ),
    "XLK": Instrument(
        instrument_id="XLK", symbol="XLK", asset_class=AssetClass.EQUITY,
        source=PriceSource.YFINANCE, description="Tech Select Sector SPDR",
        avg_daily_volume_usd=1_000_000_000,
    ),
    "XLF": Instrument(
        instrument_id="XLF", symbol="XLF", asset_class=AssetClass.EQUITY,
        source=PriceSource.YFINANCE, description="Financial Select Sector SPDR",
        avg_daily_volume_usd=1_500_000_000,
    ),
    "XLV": Instrument(
        instrument_id="XLV", symbol="XLV", asset_class=AssetClass.EQUITY,
        source=PriceSource.YFINANCE, description="Health Care Select Sector SPDR",
        avg_daily_volume_usd=900_000_000,
    ),
    "XLY": Instrument(
        instrument_id="XLY", symbol="XLY", asset_class=AssetClass.EQUITY,
        source=PriceSource.YFINANCE, description="Consumer Discretionary SPDR",
        avg_daily_volume_usd=800_000_000,
    ),
    "XLI": Instrument(
        instrument_id="XLI", symbol="XLI", asset_class=AssetClass.EQUITY,
        source=PriceSource.YFINANCE, description="Industrial Select Sector SPDR",
        avg_daily_volume_usd=700_000_000,
    ),
    # ── Fixed income ────────────────────────────────────────────────────────
    "TLT": Instrument(
        instrument_id="TLT", symbol="TLT", asset_class=AssetClass.BOND_ETF,
        source=PriceSource.YFINANCE, description="20+ Year Treasury Bond ETF",
        avg_daily_volume_usd=2_500_000_000,
    ),
    "IEF": Instrument(
        instrument_id="IEF", symbol="IEF", asset_class=AssetClass.BOND_ETF,
        source=PriceSource.YFINANCE, description="7-10 Year Treasury Bond ETF",
        avg_daily_volume_usd=600_000_000,
    ),
    "SHY": Instrument(
        instrument_id="SHY", symbol="SHY", asset_class=AssetClass.BOND_ETF,
        source=PriceSource.YFINANCE, description="1-3 Year Treasury Bond ETF",
        avg_daily_volume_usd=900_000_000,
    ),
    "LQD": Instrument(
        instrument_id="LQD", symbol="LQD", asset_class=AssetClass.BOND_ETF,
        source=PriceSource.YFINANCE, description="iShares iBoxx Investment Grade Corporate Bond ETF",
        avg_daily_volume_usd=600_000_000,
    ),
    "HYG": Instrument(
        instrument_id="HYG", symbol="HYG", asset_class=AssetClass.BOND_ETF,
        source=PriceSource.YFINANCE, description="iShares iBoxx High Yield Corporate Bond ETF",
        avg_daily_volume_usd=1_200_000_000,
    ),
    # FRED yields — context only, not tradable
    "DGS2": Instrument(
        instrument_id="DGS2", symbol="DGS2", asset_class=AssetClass.BOND_ETF,
        source=PriceSource.FRED, description="2-Year Treasury Constant Maturity Rate",
        tradable=False,
    ),
    "DGS10": Instrument(
        instrument_id="DGS10", symbol="DGS10", asset_class=AssetClass.BOND_ETF,
        source=PriceSource.FRED, description="10-Year Treasury Constant Maturity Rate",
        tradable=False,
    ),
    # ── Commodities ─────────────────────────────────────────────────────────
    "GLD": Instrument(
        instrument_id="GLD", symbol="GLD", asset_class=AssetClass.COMMODITY_ETF,
        source=PriceSource.YFINANCE, description="SPDR Gold Trust",
        avg_daily_volume_usd=1_500_000_000,
    ),
    "USO": Instrument(
        instrument_id="USO", symbol="USO", asset_class=AssetClass.COMMODITY_ETF,
        source=PriceSource.YFINANCE, description="United States Oil Fund",
        avg_daily_volume_usd=400_000_000,
    ),
    "UNG": Instrument(
        instrument_id="UNG", symbol="UNG", asset_class=AssetClass.COMMODITY_ETF,
        source=PriceSource.YFINANCE, description="United States Natural Gas Fund",
        avg_daily_volume_usd=200_000_000,
    ),
    "CL_F": Instrument(
        instrument_id="CL_F", symbol="CL=F", asset_class=AssetClass.FUTURES,
        source=PriceSource.YFINANCE, description="Crude Oil Front-Month Future",
        contract_multiplier=1000.0,  # 1000 barrels
    ),
    "GC_F": Instrument(
        instrument_id="GC_F", symbol="GC=F", asset_class=AssetClass.FUTURES,
        source=PriceSource.YFINANCE, description="Gold Front-Month Future",
        contract_multiplier=100.0,  # 100 troy oz
    ),
    "NG_F": Instrument(
        instrument_id="NG_F", symbol="NG=F", asset_class=AssetClass.FUTURES,
        source=PriceSource.YFINANCE, description="Natural Gas Front-Month Future",
        contract_multiplier=10000.0,  # 10000 mmbtu
    ),
    # ── FX (yfinance major-pair tickers use =X suffix) ──────────────────────
    "EURUSD": Instrument(
        instrument_id="EURUSD", symbol="EURUSD=X", asset_class=AssetClass.FX,
        source=PriceSource.YFINANCE, description="Euro / US Dollar",
    ),
    "USDJPY": Instrument(
        instrument_id="USDJPY", symbol="USDJPY=X", asset_class=AssetClass.FX,
        source=PriceSource.YFINANCE, description="US Dollar / Japanese Yen",
    ),
    "GBPUSD": Instrument(
        instrument_id="GBPUSD", symbol="GBPUSD=X", asset_class=AssetClass.FX,
        source=PriceSource.YFINANCE, description="British Pound / US Dollar",
    ),
    "AUDUSD": Instrument(
        instrument_id="AUDUSD", symbol="AUDUSD=X", asset_class=AssetClass.FX,
        source=PriceSource.YFINANCE, description="Australian Dollar / US Dollar",
    ),
    "USDCAD": Instrument(
        instrument_id="USDCAD", symbol="USDCAD=X", asset_class=AssetClass.FX,
        source=PriceSource.YFINANCE, description="US Dollar / Canadian Dollar",
    ),
    # VIX — context only (Principles Guard reads for circuit breaker)
    "VIX": Instrument(
        instrument_id="VIX", symbol="^VIX", asset_class=AssetClass.EQUITY,
        source=PriceSource.YFINANCE, description="CBOE Volatility Index",
        tradable=False,
    ),
}


def get_instrument(instrument_id: str) -> Instrument:
    """Look up an instrument; raises KeyError with a helpful message if unknown."""
    if instrument_id not in INSTRUMENTS:
        raise KeyError(
            f"Unknown instrument {instrument_id!r}. "
            f"Add it to src/castelino/data/instruments.py."
        )
    return INSTRUMENTS[instrument_id]


def tradable_universe() -> list[Instrument]:
    """All instruments flagged `tradable=True`."""
    return [i for i in INSTRUMENTS.values() if i.tradable]


def by_asset_class(cls: AssetClass) -> list[Instrument]:
    return [i for i in INSTRUMENTS.values() if i.asset_class == cls]
