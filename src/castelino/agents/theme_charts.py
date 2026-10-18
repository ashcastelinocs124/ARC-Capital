"""Theme Charts' own chart forms, beyond the Weekly Deep Dive's lines and bars.

heatmap: each series' 1d/1w/1m/3m move, shaded by how unusual it is (σ of the same-length moves
over 2 years) · together: how often two series moved the same way (the share of the last 13 weeks),
one line coloured by zone · range: where each series sits between its 1-year low and high, with a ring where
it was a month ago. Every number is computed here from the fetched daily series, never the LLM's;
moves use the same bar counts as the Morning Note's market facts (1d=1, 1w=5, 1m=21, 3m=63), so a
cell matches the M fact the picker quotes. Plugged into `make_weekly_exhibits(forms=FORMS)`.
`chart_data` hands the same numbers (plus a year of daily points for the range buttons) to the
browser, which draws Radar's theme card (/macro#theme) interactively; the PNGs remain for older runs and the download link.
"""

from __future__ import annotations

import math

import matplotlib.dates as mdates
import numpy as np
import pandas as pd
from matplotlib.collections import LineCollection
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.lines import Line2D

from castelino.agents.update.charts import GREEN, INK, INK2, SLATE, is_rate
from castelino.agents.update.collector import BARS
from castelino.agents.update.models import Fact
from castelino.agents.weekly.charts import RED, window_label

HORIZONS = ("1d", "1w", "1m", "3m")
SIZES = {"heatmap": (2, 8), "together": (2, 2), "range": (2, 6)}
SIGMA = LinearSegmentedColormap.from_list("sigma", [RED, "#FFFFFF", GREEN])
ROLL, TOGETHER, APART = 13, 60, 40  # weeks per share; the "move together" / "move opposite" bands


def form_errors(ch, by: dict[str, Fact]) -> list[str]:
    lo, hi = SIZES[ch.kind]
    errs = [] if lo <= len(ch.fact_ids) <= hi else [f"{ch.kind} needs {lo}-{hi} series"]
    if any(
        (f := by.get(i)) is None or f.series is None or f.series.provider not in ("fred", "yahoo")
        for i in ch.fact_ids
    ):
        errs.append(f"{ch.kind} takes only FRED or Yahoo series")
    if ch.kind == "together" and not 180 <= ch.window_days <= 3650:
        errs.append(f"together window {ch.window_days} days is out of range (180-3650)")
    return errs


def _rate(f: Fact) -> bool:
    return f.series.provider == "fred" and is_rate(f.series.id)


def _daily(f: Fact, series, days: int) -> pd.Series:
    s = series(f.series, days).dropna()
    if len(s) < 30 or s.index.to_series().diff().median() > pd.Timedelta(days=5):
        raise ValueError(f"{f.series.id}: needs a daily series")
    return s


def _stamp(names: list[str], lasts: list[pd.Timestamp]) -> list[str]:
    """A row whose data ends before the others' (FRED lags Yahoo by a day or more) says when."""
    return [n if d == max(lasts) else f"{n} · {d:%b %d}" for n, d in zip(names, lasts, strict=True)]


def _move(v: float, rate: bool) -> str:
    return f"{v:+.0f}bp" if rate else f"{v:+.1f}%"


def heat_rows(cited: list[Fact], series) -> list[dict]:
    """Per series: its 1d/1w/1m/3m move and that move in σ of the same-length moves over 2 years."""
    rows, lasts = [], []
    for f in cited:
        s, rate = _daily(f, series, 1100), _rate(f)  # ~3 years: 2 for σ plus the 3m lookback
        cells = []
        for h in HORIZONS:
            chg = (s.diff(BARS[h]) * 100 if rate else s.pct_change(BARS[h]) * 100).dropna()
            sd = chg.iloc[-505:-1].std()
            cells.append((float(chg.iloc[-1]), float(chg.iloc[-1] / sd) if sd > 0 else 0.0))
        rows.append({"name": f.series.label or f.series.id, "rate": rate, "cells": cells})
        lasts.append(s.index[-1])
    for r, name in zip(rows, _stamp([r["name"] for r in rows], lasts), strict=True):
        r["name"] = name
    return rows


def heatmap(pick, cited: list[Fact], series):
    rows = heat_rows(cited, series)
    names, cells = [r["name"] for r in rows], [(r["cells"], r["rate"]) for r in rows]

    def draw(ax):
        z = np.array([[c[1] for c in row] for row, _ in cells])
        ax.imshow(np.clip(z, -3, 3), cmap=SIGMA, vmin=-3, vmax=3, aspect="auto")
        for i, (row, rate) in enumerate(cells):
            for j, (v, sig) in enumerate(row):
                ax.text(j, i, _move(v, rate), ha="center", va="center", fontsize=9.5,
                        fontweight="bold", color="white" if abs(sig) > 1.8 else INK)  # fmt: skip
        ax.set_xticks(range(len(HORIZONS)), [h.upper() for h in HORIZONS], fontweight="bold")
        ax.set_yticks(range(len(names)), names)
        ax.xaxis.tick_top()
        ax.set_xticks(np.arange(-0.5, len(HORIZONS)), minor=True)
        ax.set_yticks(np.arange(-0.5, len(names)), minor=True)
        ax.grid(which="minor", color="white", lw=3)
        ax.tick_params(which="both", length=0)
        for sp in ax.spines.values():
            sp.set_visible(False)
        ax.text(0, -0.07, "Shade = size of the move in standard deviations vs the last 2 years",
                transform=ax.transAxes, fontsize=7.5, color=INK2, va="top")  # fmt: skip

    i, j = max(
        ((i, j) for i in range(len(cells)) for j in range(len(HORIZONS))),
        key=lambda ij: abs(cells[ij[0]][0][ij[1]][1]),
    )
    v, sig = cells[i][0][j]
    name = names[i].split(" · ")[0]
    sub = f"Most unusual: {name} {_move(v, cells[i][1])} over {HORIZONS[j]} ({sig:+.1f}σ)"
    return draw, sub, {"left": 0.24, "bottom": 0.17}


def weekly(cited: list[Fact], series, days: int) -> pd.DataFrame:
    """Two series' closes, one row per week (its last close, on its own date)."""
    fx, fy = cited
    df = pd.concat([_daily(fx, series, days), _daily(fy, series, days)], axis=1, join="inner")
    w = df.groupby(df.index.to_period("W-FRI")).tail(1)
    if len(w) < 4:
        raise ValueError("together: fewer than 4 weeks overlap")
    return w


def together_share(cited: list[Fact], series, days: int) -> pd.Series:
    """% of the last ROLL weeks in which both series moved the same way, one point a week over `days`
    (a flat week counts as not the same way)."""
    w = weekly(cited, series, days + (ROLL + 2) * 7)
    share = (w.diff().dropna().prod(axis=1) > 0).rolling(ROLL).mean().dropna() * 100
    share = share[share.index >= share.index[-1] - pd.Timedelta(days=days)]
    if len(share) < 4:
        raise ValueError("together: fewer than 4 weeks of shares")
    return share


def _zone(v: float) -> str:
    return GREEN if v >= TOGETHER else RED if v <= APART else SLATE


def together(pick, cited: list[Fact], series):
    s = together_share(cited, series, pick.window_days)
    last, same = s.iloc[-1], round(s.iloc[-1] * ROLL / 100)
    hi, lo = math.ceil(ROLL * TOGETHER / 100), math.floor(ROLL * APART / 100)

    def draw(ax):
        ax.axhspan(TOGETHER, 100, color=GREEN, alpha=0.07, lw=0)
        ax.axhspan(0, APART, color=RED, alpha=0.06, lw=0)
        # ponytail: densified so the colour switches close to where the line crosses a band edge
        x = mdates.date2num(s.index)
        xs = np.linspace(x[0], x[-1], len(s) * 24)
        ys = np.interp(xs, x, s.to_numpy())
        segs = np.stack([np.column_stack([xs[:-1], ys[:-1]]), np.column_stack([xs[1:], ys[1:]])], 1)
        colors = [_zone(v) for v in (ys[:-1] + ys[1:]) / 2]
        ax.add_collection(LineCollection(segs, colors=colors, lw=2.2, capstyle="round", zorder=2))
        ax.scatter([x[-1]], [last], s=90, color=_zone(last), edgecolor="white", lw=1.5, zorder=3,
                   clip_on=False)  # fmt: skip
        ax.annotate(f"{last:.0f}%", (x[-1], last), xytext=(9, 0), textcoords="offset points",
                    fontsize=9, color=INK2 if _zone(last) == SLATE else _zone(last), fontweight="bold", va="center",
                    annotation_clip=False)  # fmt: skip
        keys = ((GREEN, f"Move together ({hi}+ of {ROLL} weeks)"), (SLATE, "No steady link"),
                (RED, f"Move opposite ({lo} or fewer)"))  # fmt: skip
        ax.legend([Line2D([], [], color=c, lw=2.2) for c, _ in keys], [t for _, t in keys],
                  loc="lower left", bbox_to_anchor=(0, 1.0), ncol=3, frameon=False, fontsize=8,
                  handlelength=1.6, borderaxespad=0.2)  # fmt: skip
        ax.set_xlim(x[0], x[-1])
        ax.set_ylim(0, 100)
        ax.xaxis_date()
        ax.xaxis.set_major_formatter(
            mdates.DateFormatter("%b %Y" if pick.window_days > 400 else "%b")
        )
        ax.set_ylabel(f"% of the last {ROLL} weeks\nmoving the same way", fontsize=9, color=INK2)
        ax.grid(axis="y", color="#E2E8F0", lw=0.7)

    sub = (
        f"Moved the same way in {same} of the last {ROLL} weeks · {window_label(pick.window_days)}"
    )
    return draw, sub, {"left": 0.13}


def range_rows(cited: list[Fact], series) -> list[dict]:
    """Per series: its 1-year low and high, latest value and the value a month ago."""
    rows, lasts = [], []
    for f in cited:
        s = _daily(f, series, 365)
        rows.append(
            {
                "name": f.series.label or f.series.id,
                "lo": float(s.min()),
                "hi": float(s.max()),
                "last": float(s.iloc[-1]),
                "ago": float(s.iloc[-1 - BARS["1m"]]),
                "rate": _rate(f),
            }
        )
        lasts.append(s.index[-1])
    for r, name in zip(rows, _stamp([r["name"] for r in rows], lasts), strict=True):
        r["name"] = name
    return rows


def range_(pick, cited: list[Fact], series):
    rr = range_rows(cited, series)
    rows = [(r["name"], r["lo"], r["hi"], r["last"], r["ago"], r["rate"]) for r in rr]
    labels = [r[0] for r in rows]

    def pos(v, lo, hi):
        return (v - lo) / (hi - lo) * 100 if hi > lo else 50.0

    def draw(ax):
        for k, (_, lo, hi, last, ago, rate) in enumerate(rows):
            y = len(rows) - 1 - k
            p, pa = pos(last, lo, hi), pos(ago, lo, hi)
            up = GREEN if last >= ago else RED
            unit = "%" if rate else ""
            ax.plot([0, 100], [y, y], color="#E2E8F0", lw=9, solid_capstyle="round", zorder=1)
            ax.scatter([pa], [y], s=70, facecolor="white", edgecolor=SLATE, lw=1.6, zorder=2)
            if abs(p - pa) > 4:
                ax.annotate("", (p, y), (pa, y), zorder=2,
                            arrowprops={"arrowstyle": "-|>", "color": up, "lw": 1.6,
                                        "shrinkA": 5, "shrinkB": 7})  # fmt: skip
            ax.scatter([p], [y], s=120, color=up, edgecolor="white", lw=1.5, zorder=3)
            ax.text(p, y + 0.3, f"{last:,.2f}{unit}", ha="center", fontsize=8.5,
                    fontweight="bold", color=up)  # fmt: skip
            for x, v, ha in ((0, lo, "left"), (100, hi, "right")):
                ax.text(x, y - 0.38, f"{v:,.2f}{unit}", ha=ha, fontsize=7.5, color=INK2)
        ax.set_yticks(range(len(rows)), labels[::-1])
        ax.set_xticks([0, 50, 100], ["1-year low", "midpoint", "1-year high"], color=INK2)
        ax.set_xlim(-4, 104)
        ax.set_ylim(-0.7, len(rows) - 0.3)
        ax.tick_params(length=0)
        for sp in ax.spines.values():
            sp.set_visible(False)

    name, lo, hi, last, *_ = max(rows, key=lambda r: abs(pos(r[3], r[1], r[2]) - 50))
    sub = f"{name}: {pos(last, lo, hi):.0f}% of its 1-year range · ring = a month ago"
    return draw, sub, {"left": 0.24, "bottom": 0.16}


FORMS = {"heatmap": heatmap, "together": together, "range": range_}

YEAR = 370  # days of daily points sent for the 1M-1Y range buttons


def _pts(s: pd.Series) -> list[list]:
    return [[d.strftime("%Y-%m-%d"), round(float(v), 4)] for d, v in s.items()]


def chart_data(ch, cited: list[Fact], series, fetch) -> dict:
    """What the browser draws for one chart: the same numbers as the PNG, computed by the same code.
    Line and compare carry a year of daily points (or the fact's own points for a Polymarket market
    or a release) and the picker's window as the default range."""
    if ch.kind == "movers":
        pts = sorted(ch.points, key=lambda p: p.value, reverse=True)
        return {"bars": [{"label": p.label, "value": p.value} for p in pts], "unit": ch.unit}
    if ch.kind == "heatmap":
        return {"rows": heat_rows(cited, series)}
    if ch.kind == "range":
        return {"rows": range_rows(cited, series)}
    if ch.kind == "together":
        return {
            "names": [f.series.label or f.series.id for f in cited],
            "window": ch.window_days,
            "points": _pts(together_share(cited, series, ch.window_days)),
        }
    out, dated = [], True
    for f in cited[:1] if ch.kind == "line" else cited:
        ref = f.series
        if ref.provider == "polymarket" or ref.kind == "release":
            dated = False  # a short run of labelled points ("Oct 14", "Sep 2026"): no range buttons
            pts = (
                [(p.label, p.value) for p in ref.points]
                if ref.kind == "release"
                else fetch(ref, ch.window_days)
            )
            points = [[label, round(float(v), 4)] for label, v in pts]
        else:
            points = _pts(series(ref, max(ch.window_days, YEAR)).dropna())
        if len(points) < 2:
            raise ValueError(f"{ref.id}: only {len(points)} point(s)")
        unit = "%" if ref.provider == "polymarket" or _rate(f) else ""
        out.append({"name": ref.label or ref.id, "unit": unit, "points": points})
    rebase = ch.kind == "compare" and not all(s["unit"] == "%" for s in out)
    return {"series": out, "dated": dated, "window": ch.window_days, "rebase": rebase}
