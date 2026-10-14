"""Theme Charts' own chart forms, beyond the Weekly Deep Dive's lines and bars.

heatmap: each series' 1d/1w/1m/3m move, shaded by how unusual it is (σ of the same-length moves
over 2 years) · scatter: two series against each other, week by week, so a trail shows whether they
move together · range: where each series sits between its 1-year low and high, with a ring where
it was a month ago. Every number is computed here from the fetched daily series, never the LLM's;
moves use the same bar counts as the Morning Note's market facts (1d=1, 1w=5, 1m=21, 3m=63), so a
cell matches the M fact the picker quotes. Plugged into `make_weekly_exhibits(forms=FORMS)`.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from matplotlib.collections import LineCollection
from matplotlib.colors import LinearSegmentedColormap

from castelino.agents.update.charts import GREEN, INK, INK2, SLATE, is_rate
from castelino.agents.update.collector import BARS
from castelino.agents.update.models import Fact
from castelino.agents.weekly.charts import RED, window_label

HORIZONS = ("1d", "1w", "1m", "3m")
SIZES = {"heatmap": (2, 8), "scatter": (2, 2), "range": (2, 6)}
SIGMA = LinearSegmentedColormap.from_list("sigma", [RED, "#FFFFFF", GREEN])
TRAIL = LinearSegmentedColormap.from_list("trail", ["#CBD5E1", GREEN])


def form_errors(ch, by: dict[str, Fact]) -> list[str]:
    lo, hi = SIZES[ch.kind]
    errs = [] if lo <= len(ch.fact_ids) <= hi else [f"{ch.kind} needs {lo}-{hi} series"]
    if any(
        (f := by.get(i)) is None or f.series is None or f.series.provider not in ("fred", "yahoo")
        for i in ch.fact_ids
    ):
        errs.append(f"{ch.kind} takes only FRED or Yahoo series")
    if ch.kind == "scatter" and not 30 <= ch.window_days <= 3650:
        errs.append(f"scatter window {ch.window_days} days is out of range")
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


def heatmap(pick, cited: list[Fact], series):
    names, cells, lasts = [], [], []  # cells[row][col] = (move, sigma)
    for f in cited:
        s, rate = _daily(f, series, 1100), _rate(f)  # ~3 years: 2 for σ plus the 3m lookback
        row = []
        for h in HORIZONS:
            chg = (s.diff(BARS[h]) * 100 if rate else s.pct_change(BARS[h]) * 100).dropna()
            sd = chg.iloc[-505:-1].std()
            row.append((float(chg.iloc[-1]), float(chg.iloc[-1] / sd) if sd > 0 else 0.0))
        names.append(f.series.label or f.series.id)
        cells.append((row, rate))
        lasts.append(s.index[-1])
    names = _stamp(names, lasts)

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


def scatter(pick, cited: list[Fact], series):
    fx, fy = cited
    df = pd.concat(
        [_daily(fx, series, pick.window_days), _daily(fy, series, pick.window_days)],
        axis=1,
        join="inner",
    )
    w = df.groupby(df.index.to_period("W-FRI")).tail(1)  # each week's last close, on its own date
    if len(w) < 4:
        raise ValueError("scatter: fewer than 4 weeks overlap")
    xs, ys = w.iloc[:, 0].to_numpy(), w.iloc[:, 1].to_numpy()
    r = w.diff().dropna().corr().iloc[0, 1]
    names = [f.series.label or f.series.id for f in (fx, fy)]

    def draw(ax):
        t = np.linspace(0, 1, len(xs))
        segs = np.stack([np.column_stack([xs[:-1], ys[:-1]]), np.column_stack([xs[1:], ys[1:]])], 1)
        ax.add_collection(LineCollection(segs, colors=TRAIL(t[1:]), lw=2.2, zorder=1))
        ax.scatter(xs[:-1], ys[:-1], c=TRAIL(t[:-1]), s=18, zorder=2)
        ax.annotate("", (xs[-1], ys[-1]), (xs[-2], ys[-2]),
                    arrowprops={"arrowstyle": "-|>", "color": GREEN, "lw": 2.2, "shrinkB": 6})  # fmt: skip
        ax.scatter([xs[-1]], [ys[-1]], s=110, color=GREEN, edgecolor="white", lw=1.5, zorder=3)
        ax.scatter([xs[0]], [ys[0]], s=60, facecolor="white", edgecolor=SLATE, lw=1.5, zorder=3)
        for k, color, weight in ((0, INK2, "normal"), (-1, GREEN, "bold")):
            ax.annotate(f"{w.index[k]:%b %d}", (xs[k], ys[k]), xytext=(7, 5),
                        textcoords="offset points", fontsize=8.5, color=color, fontweight=weight)  # fmt: skip
        for setter, name, f in ((ax.set_xlabel, names[0], fx), (ax.set_ylabel, names[1], fy)):
            setter(name + (" (%)" if _rate(f) else ""), fontsize=9, color=INK2)
        ax.grid(color="#E2E8F0", lw=0.7)
        ax.margins(0.12)

    sub = f"Weekly closes, {window_label(pick.window_days)} · weekly moves correlate {r:+.2f}"
    return draw, sub, {"left": 0.13, "bottom": 0.24}


def range_(pick, cited: list[Fact], series):
    rows, lasts = [], []  # (name, lo, hi, last, month ago, rate)
    for f in cited:
        s = _daily(f, series, 365)
        ago = float(s.iloc[-1 - BARS["1m"]])
        lo, hi, last = float(s.min()), float(s.max()), float(s.iloc[-1])
        rows.append((f.series.label or f.series.id, lo, hi, last, ago, _rate(f)))
        lasts.append(s.index[-1])
    labels = _stamp([r[0] for r in rows], lasts)

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


FORMS = {"heatmap": heatmap, "scatter": scatter, "range": range_}
