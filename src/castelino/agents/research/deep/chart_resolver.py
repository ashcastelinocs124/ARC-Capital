from __future__ import annotations

import logging
import re

import pandas as pd

from castelino.agents.research.deep.models import (
    ChartPoint,
    ChartSeries,
    ChartSpec,
    ChartType,
    ResolvedChart,
)
from castelino.config import get_settings
from castelino.data.openbb_adapter import get_adapter

log = logging.getLogger(__name__)

_TICKER_RE = re.compile(r"^[A-Z.\-]{1,6}$")


def _clean_symbols(raw: list[str]) -> list[str]:
    out = []
    for s in raw or []:
        t = (s or "").strip().upper()
        if _TICKER_RE.match(t):
            out.append(t)
    return out


def _fmt_x(idx) -> str:
    return idx.strftime("%Y-%m-%d") if hasattr(idx, "strftime") else str(idx)


def _series_from_close(name: str, df: pd.DataFrame) -> ChartSeries:
    pts = [
        ChartPoint(x=_fmt_x(idx), y=float(val))
        for idx, val in df["close"].dropna().items()
    ]
    return ChartSeries(name=name, points=pts)


class ChartResolver:
    """Deterministic spec -> OpenBB data. No LLM. Drops any chart that fails.

    A chart is never load-bearing: any fetch failure (bad ticker, OpenBB down,
    empty frame) drops just that chart and is logged; the report always
    completes.
    """

    def __init__(self, *, adapter=None):
        self._adapter = adapter or get_adapter()

    def resolve_all(self, specs: list[ChartSpec]) -> list[ResolvedChart]:
        cfg = get_settings().deep_research
        out: list[ResolvedChart] = []
        for spec in (specs or [])[: cfg.max_charts]:
            try:
                chart = self._resolve_one(spec)
            except Exception as e:  # never raise — a chart is never load-bearing
                log.warning("chart dropped: %s (%s)", spec.title, e)
                continue
            if chart and chart.series and any(s.points for s in chart.series):
                out.append(chart)
            else:
                log.info("chart dropped (no data): %s", spec.title)
        return out

    def _resolve_one(self, spec: ChartSpec) -> ResolvedChart | None:
        cfg = get_settings().deep_research
        lookback = spec.lookback_days or cfg.chart_lookback_days_default

        if spec.type == ChartType.PRICE_HISTORY:
            syms = _clean_symbols(spec.symbols)
            if not syms:
                return None
            df = self._adapter.history(syms[0], lookback_days=lookback)
            return ResolvedChart(
                type=spec.type, title=spec.title, rationale=spec.rationale,
                series=[_series_from_close(syms[0], df)], y_label="Price",
            )

        if spec.type == ChartType.COMPARISON:
            syms = _clean_symbols(spec.symbols)
            if not syms:
                return None
            series: list[ChartSeries] = []
            for sym in syms:
                df = self._adapter.history(sym, lookback_days=lookback)
                close = df["close"].dropna()
                if close.empty:
                    continue
                base = float(close.iloc[0])
                if base == 0:
                    continue
                pts = [
                    ChartPoint(x=_fmt_x(idx), y=round(float(val) / base * 100.0, 4))
                    for idx, val in close.items()
                ]
                series.append(ChartSeries(name=sym, points=pts))
            return ResolvedChart(
                type=spec.type, title=spec.title, rationale=spec.rationale,
                series=series, y_label="Indexed to 100",
            )

        if spec.type == ChartType.ECON_INDICATOR:
            sid = (spec.series_id or "").strip().upper()
            if not sid:
                return None
            df = self._adapter.economic_indicators([sid])
            col = df[sid] if sid in df.columns else df.iloc[:, 0]
            pts = [
                ChartPoint(x=_fmt_x(idx), y=float(val))
                for idx, val in col.dropna().items()
            ]
            return ResolvedChart(
                type=spec.type, title=spec.title, rationale=spec.rationale,
                series=[ChartSeries(name=sid, points=pts)], y_label=sid,
            )

        if spec.type == ChartType.YIELD_CURVE:
            df = self._adapter.yield_curve()
            row = df.iloc[0]
            pts = [
                ChartPoint(x=str(label), y=float(val))
                for label, val in row.items() if pd.notna(val)
            ]
            return ResolvedChart(
                type=spec.type, title=spec.title, rationale=spec.rationale,
                series=[ChartSeries(name="UST yield", points=pts)], y_label="Yield %",
            )

        return None
