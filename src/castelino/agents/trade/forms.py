"""Trade Lab's chart catalog. The chart agent names a form, its series and a window; code fetches the data,
computes every plotted number and draws it in the house frame (weekly/charts._frame). Each form returns the
numbers it shows, which become C facts the editor may cite. Twelve forms; line, compare and bars are the
"plain" ones the variety rule limits. Reference drawings from real data: the spec's forms/forms.py."""

from __future__ import annotations

import re
import textwrap
from collections.abc import Callable
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from matplotlib.colors import LinearSegmentedColormap, TwoSlopeNorm
from matplotlib.patches import Rectangle, Wedge

from castelino.agents.trade.models import ChartSpec
from castelino.agents.update.charts import GREEN, INK, INK2, SLATE
from castelino.agents.weekly.charts import COMPARE, DARK, RED, _frame

KICKER = "TRADE LAB"
DIV = LinearSegmentedColormap.from_list("div", [RED, "#FFFFFF", GREEN])
TRAIL_LIGHT = "#CBD5E1"
SERIES = re.compile(r"^(fred|yahoo):([A-Za-z0-9^=._-]{1,20})$")
NICE = {
    "financial_services": "Financials",
    "consumer_cyclical": "Consumer",
    "technology": "Technology",
    "industrials": "Industrials",
    "basic_materials": "Materials",
    "energy": "Energy",
    "healthcare": "Health care",
    "communication_services": "Communication",
    "consumer_defensive": "Staples",
    "utilities": "Utilities",
    "realestate": "Real estate",
}
SHORT = {"Communication": "Comms", "Health care": "Health", "Real estate": "Property"}


@dataclass
class Sources:
    yahoo: Callable[[str], pd.Series]
    fred: Callable[[str], pd.Series]
    sectors: Callable[[str], dict[str, float]]

    @staticmethod
    def live() -> Sources:
        from castelino.forecast import regime

        def sectors(t: str) -> dict[str, float]:
            import yfinance as yf

            return dict(yf.Ticker(t).funds_data.sector_weightings)

        return Sources(regime._fetch_yf_close, regime._fetch_fred_series, sectors)


@dataclass
class Form:
    description: str
    plain: bool
    min_series: int
    max_series: int
    draw: Callable


_NAMES: ContextVar[dict[str, str] | None] = ContextVar("names", default=None)  # set by render


def _ticker(sid: str) -> str:
    return sid.split(":", 1)[1]


def _name(sid: str) -> str:
    """ "iShares MSCI India ETF (INDA)" when the spec named the series, else the bare ticker. A label, never
    a data key: fetch with _ticker."""
    full = (_NAMES.get() or {}).get(sid)
    return f"{full} ({_ticker(sid)})" if full else _ticker(sid)


def _wrap(label: str, width: int = 20) -> str:
    """Full names run long: break them onto lines for tick labels."""
    return textwrap.fill(label, width)


def _sign(v: float, unit: str = "%") -> str:
    return (f"+{v:.1f}" if v > 0 else f"−{-v:.1f}") + unit


def _xdates(ax, idx, fmt="%b %Y"):
    x = np.arange(len(idx))
    step = max(1, len(x) // 6)
    ax.set_xticks(x[::step])
    ax.set_xticklabels([d.strftime(fmt) for d in idx[::step]], fontsize=8)
    return x


def _window(s: pd.Series, days: int) -> pd.Series:
    s = s.dropna()
    return s[s.index >= s.index[-1] - pd.Timedelta(days=days)]


def _chg(s: pd.Series) -> float:
    return float(s.iloc[-1] / s.iloc[0] - 1) * 100


# ── plain forms ──────────────────────────────────────────────────────────────
def _line(spec, data, src):
    s = _window(data[spec.series[0]], spec.window_days)
    chg = _chg(s)

    def draw(ax):
        x = _xdates(ax, s.index, "%b %d" if spec.window_days <= 120 else "%b %Y")
        ax.plot(x, s.values, color=GREEN, lw=2)
        ax.annotate(f"{s.iloc[-1]:,.2f}", (x[-1], s.iloc[-1]), xytext=(4, 0),
                    textcoords="offset points", fontsize=8.5, color=GREEN, fontweight="bold",
                    va="center")  # fmt: skip

    name = _name(spec.series[0])
    nums = [(f"{name} change", round(chg, 1)), ("last", round(float(s.iloc[-1]), 2))]
    return draw, f"{name}, {_sign(chg)} over the window", nums, {}


def _compare(spec, data, src):
    df = pd.concat({_name(k): _window(data[k], spec.window_days) for k in spec.series}, axis=1)
    df = df.dropna()
    reb = df / df.iloc[0] * 100

    def draw(ax):
        x = _xdates(ax, reb.index)
        for i, c in enumerate(reb.columns):
            col = COMPARE[i % 4]
            ax.plot(
                x, reb[c], color=col, lw=2.4 if i == 0 else 1.6, label=c, zorder=3 if i == 0 else 2
            )
            ax.annotate(f"{reb[c].iloc[-1]:,.0f}", (x[-1], reb[c].iloc[-1]), xytext=(4, 0),
                        textcoords="offset points", fontsize=8.5, color=col, fontweight="bold",
                        va="center")  # fmt: skip
        ax.axhline(100, color=SLATE, lw=0.8, ls="--")
        ax.legend(fontsize=8, frameon=False, loc="upper left")

    nums = [(f"{c} change", round(float(reb[c].iloc[-1] - 100), 1)) for c in reb.columns]
    return draw, f"Start = 100 on {reb.index[0]:%b %-d, %Y}", nums, {}


def _bars(spec, data, src):
    vals = {_name(k): _chg(_window(data[k], spec.window_days)) for k in spec.series}
    names = list(vals)

    def draw(ax):
        y = list(range(len(names)))[::-1]
        colors = [GREEN if vals[n] >= 0 else RED for n in names]
        ax.barh(y, [vals[n] for n in names], color=colors, height=0.6)
        for yi, n in zip(y, names, strict=True):
            ax.text(vals[n], yi, " " + _sign(vals[n]) + " ", va="center",
                    ha="left" if vals[n] >= 0 else "right", fontsize=8.5, fontweight="bold")  # fmt: skip
        ax.set_yticks(y)
        ax.set_yticklabels([_wrap(n) for n in names], fontsize=8.5)
        ax.axvline(0, color=INK2, lw=1)
        ax.set_xticks([])
        ax.margins(x=0.25)

    nums = [(f"{n} change", round(v, 1)) for n, v in vals.items()]
    return draw, f"Change over the last {spec.window_days} days", nums, {"left": 0.25}


# ── creative forms ───────────────────────────────────────────────────────────
def _scatter(spec, data, src):
    a, b = (_window(data[k], spec.window_days).resample("W-FRI").last() for k in spec.series[:2])
    w = pd.concat([a, b], axis=1).dropna()
    xs, ys = w.iloc[:, 1].to_numpy(), w.iloc[:, 0].to_numpy()
    r = float(w.pct_change().dropna().corr().iloc[0, 1])

    def draw(ax):
        alphas = np.linspace(0.15, 1, len(xs))
        ax.plot(xs, ys, color=TRAIL_LIGHT, lw=1.2, zorder=1)
        ax.scatter(xs, ys, c=[(0.02, 0.47, 0.34, a_) for a_ in alphas], s=22, zorder=2)
        ax.scatter([xs[-1]], [ys[-1]], s=110, color=GREEN, edgecolor="white", lw=1.5, zorder=3)
        ax.annotate(f"{w.index[-1]:%b %d}", (xs[-1], ys[-1]), xytext=(7, 5),
                    textcoords="offset points", fontsize=8.5, color=GREEN, fontweight="bold")  # fmt: skip
        ax.set_xlabel(_name(spec.series[1]), fontsize=8.5, color=INK2)
        ax.set_ylabel(_name(spec.series[0]), fontsize=8.5, color=INK2)
        ax.grid(color="#E2E8F0", lw=0.7)

    sub = f"Weekly closes; weekly moves correlate {r:+.2f}"
    return draw, sub, [("weekly correlation", round(r, 2))], {"left": 0.12}


def _squarify(vals, x, y, w, h):
    """Squarified treemap layout (Bruls et al.): one (x, y, w, h) per value, in order."""
    out, vals = [], [v * w * h / sum(vals) for v in vals]

    def worst(row, side):
        s = sum(row)
        return max(max(side * side * r / (s * s), (s * s) / (side * side * r)) for r in row)

    while vals:
        side, row = min(w, h), [vals.pop(0)]
        while vals and worst(row + [vals[0]], side) <= worst(row, side):
            row.append(vals.pop(0))
        s = sum(row)
        if w >= h:
            cw, cy = s / h, y
            for r in row:
                out.append((x, cy, cw, r / cw))
                cy += r / cw
            x, w = x + cw, w - cw
        else:
            rh, cx = s / w, x
            for r in row:
                out.append((cx, y, r / rh, rh))
                cx += r / rh
            y, h = y + rh, h - rh
    return out


def _treemap(spec, data, src):
    funds = [_name(k) for k in spec.series]
    weights = {
        f: {NICE.get(k, k): float(v) for k, v in src.sectors(_ticker(sid)).items() if v > 0.004}
        for f, sid in zip(funds, spec.series, strict=True)
    }

    def draw(ax):
        ax.set_xlim(0, 1.08 * len(funds))
        ax.set_ylim(0, 1)
        ax.axis("off")
        for i, f in enumerate(funds):
            items = sorted(weights[f].items(), key=lambda kv: -kv[1])
            rects = _squarify([v for _, v in items], i * 1.08, 0, 1.0, 0.9)
            for (lab, v), (x, y, w, h) in zip(items, rects, strict=True):
                c = (
                    GREEN
                    if lab == "Technology"
                    else (SLATE if lab == "Financials" else TRAIL_LIGHT)
                )
                ax.add_patch(Rectangle((x, y), w, h, facecolor=c, edgecolor="white", lw=2))
                if w * h > 0.035 and w > 0.12:
                    label = SHORT.get(lab, lab) if w < 0.22 else lab
                    white = lab in ("Technology", "Financials")
                    ax.text(x + 0.012, y + h - 0.02, f"{label}\n{v * 100:.1f}%", va="top",
                            fontsize=7.5 if w < 0.22 else 9, fontweight="bold",
                            color="white" if white else INK)  # fmt: skip
            ax.text(i * 1.08, 0.93, _wrap(f, 34), fontsize=10, fontweight="bold", color=INK)

    nums = [
        (f"{f} technology weight", round(weights[f].get("Technology", 0.0) * 100, 1)) for f in funds
    ]
    layout = {"left": 0.05, "bottom": 0.14}
    return draw, "Fund weight by sector; technology in green", nums, layout


def _weekly_corr(a: pd.Series, b: pd.Series, weeks: int = 52) -> float:
    w = pd.concat([a, b], axis=1).ffill().resample("W-FRI").last().pct_change().dropna()
    return float(w.iloc[-weeks:].corr().iloc[0, 1])


def _ytd(s: pd.Series) -> float:
    before = s[s.index.year < s.index[-1].year]
    return float(s.iloc[-1] / before.iloc[-1] - 1) * 100 if len(before) else 0.0


def _quadrant(spec, data, src):
    bench, markets = spec.series[0], spec.series[1:]
    rows = []
    for k in markets:
        t = _name(k)
        tech = float(src.sectors(_ticker(k)).get("technology", 0.0)) * 100
        s = data[k].dropna()
        rows.append((t, tech, _weekly_corr(s, data[bench]), _ytd(s)))

    def draw(ax):
        xs, ys, cs = (np.array([r[i] for r in rows]) for i in (1, 2, 3))
        ax.axvspan(-1, 20, ymax=0.5, color=GREEN, alpha=0.07)
        ax.axvline(20, color=SLATE, lw=0.8, ls="--")
        ax.axhline(0.5, color=SLATE, lw=0.8, ls="--")
        lim = max(30.0, float(abs(cs).max()))
        sizes = [220 if i == 0 else 90 for i in range(len(rows))]
        edges = [DARK if i == 0 else "white" for i in range(len(rows))]
        sc = ax.scatter(xs, ys, s=sizes, c=cs, cmap=DIV, norm=TwoSlopeNorm(0, -lim, lim),
                        edgecolor=edges, lw=1.5, zorder=3)  # fmt: skip
        right = max(68.0, float(xs.max()) + 8) / 2
        for i, (t, x, y, _) in enumerate(rows):  # names past the middle sit left of their dot
            off, ha = (11 if i == 0 else 7), "left"
            if x > right:
                off, ha = -off, "right"
            ax.annotate(_wrap(t, 26), (x, y), xytext=(off, -3), textcoords="offset points", ha=ha,
                        fontsize=8.5, fontweight="bold" if i == 0 else "normal", color=INK)  # fmt: skip
        ax.text(19.5, 0.46, "AI HEDGE ZONE", fontsize=7.5, color=GREEN, fontweight="bold",
                ha="right", va="top")  # fmt: skip
        ax.set_xlim(-1, max(68.0, float(xs.max()) + 8))
        ax.set_ylim(min(0.0, float(ys.min()) - 0.05), 1)
        ax.set_xlabel("Technology weight in the fund (%)", fontsize=8.5, color=INK2)
        ax.set_ylabel(
            _wrap(f"Weekly correlation with {_name(bench)}", 34), fontsize=8.5, color=INK2
        )
        cb = ax.figure.colorbar(sc, ax=ax, fraction=0.03, pad=0.02, shrink=0.8)
        cb.set_label("Return this year (%)", fontsize=7.5)
        cb.ax.tick_params(labelsize=7)

    nums = [
        n
        for t, x, y, z in rows
        for n in (
            (f"{t} tech weight", round(x, 1)),
            (f"{t} correlation", round(y, 2)),
            (f"{t} this year", round(z, 1)),
        )
    ]
    sub = f"Tech weight against weekly correlation with {_name(bench)} (52 weeks); colour = return this year"
    return draw, sub, nums, {"left": 0.11}


def _underwater(spec, data, src):
    df = pd.concat({_name(k): _window(data[k], spec.window_days) for k in spec.series}, axis=1)
    df = df.dropna()
    dd = (df / df.cummax() - 1) * 100

    def draw(ax):
        x = _xdates(ax, dd.index)
        for i, c in enumerate(dd.columns):
            col = GREEN if i == 0 else DARK
            ax.fill_between(x, dd[c], 0, color=col, alpha=0.35 if i == 0 else 0.18, lw=0)
            ax.plot(x, dd[c], color=col, lw=1.8 if i == 0 else 1.2, label=c)
            j = int(np.argmin(dd[c].values))
            ax.annotate(_sign(float(dd[c].iloc[j])), (j, dd[c].iloc[j]), xytext=(6, -2),
                        textcoords="offset points", fontsize=8, color=col, fontweight="bold",
                        va="center")  # fmt: skip
        ax.axhline(0, color=INK2, lw=0.8)
        ax.set_ylabel("Below its last peak (%)", fontsize=8.5, color=INK2)
        ax.legend(fontsize=8, frameon=False, loc="lower left")

    nums = [(f"{c} now below peak", round(float(dd[c].iloc[-1]), 1)) for c in dd.columns]
    nums += [(f"{c} worst", round(float(dd[c].min()), 1)) for c in dd.columns]
    return (
        draw,
        f"Drawdown from the previous high since {dd.index[0]:%b %-d, %Y}",
        nums,
        {"left": 0.11},
    )


def _slope(spec, data, src):
    bench, subj = _name(spec.series[0]), _name(spec.series[1])
    both = {
        bench: _window(data[spec.series[0]], spec.window_days),
        subj: _window(data[spec.series[1]], spec.window_days),
    }
    d = pd.concat(both, axis=1).pct_change().dropna() * 100
    pair = d.loc[d[bench].nsmallest(20).index]

    def draw(ax):
        for _, r in pair.iterrows():
            ax.plot([0, 1], [r[bench], r[subj]], color=TRAIL_LIGHT, lw=1, zorder=1)
        for xpos, col, c in ((0, RED, bench), (1, GREEN, subj)):
            ax.scatter([xpos] * len(pair), pair[c], color=col, s=26, zorder=2)
            m = float(pair[c].mean())
            ax.plot([xpos - 0.08, xpos + 0.08], [m, m], color=col, lw=3)
            ax.text(xpos + (-0.12 if xpos == 0 else 0.12), m, f"avg {_sign(m)}",
                    ha="right" if xpos == 0 else "left", va="center", fontsize=8.5, color=col,
                    fontweight="bold")  # fmt: skip
        ax.set_xticks([0, 1])
        ax.set_xticklabels([_wrap(bench, 30), _wrap(f"{subj}, same day", 30)], fontsize=9)
        ax.set_xlim(-0.45, 1.45)
        ax.axhline(0, color=INK2, lw=0.8)
        ax.set_ylabel("Daily move (%)", fontsize=8.5, color=INK2)

    nums = [
        (f"{bench} average on its 20 worst days", round(float(pair[bench].mean()), 2)),
        (f"{subj} average those days", round(float(pair[subj].mean()), 2)),
        (f"{subj} down days of 20", float((pair[subj] < 0).sum())),
    ]
    sub = f"{bench}'s 20 worst days in the window, each joined to {subj}'s move that day"
    return draw, sub, nums, {"left": 0.12}


def _waterfall(spec, data, src):
    a = _window(data[spec.series[0]].dropna(), spec.window_days)
    f = data[spec.series[1]].dropna().reindex(a.index).ffill().bfill()
    usd = float(a.iloc[-1] / a.iloc[0] - 1)
    fxr = float(f.iloc[0] / f.iloc[-1] - 1)  # the local currency's change against the dollar
    local = (1 + usd) / (1 + fxr) - 1
    steps = [("Local stocks", local * 100), ("Currency", (usd - local) * 100)]

    def draw(ax):
        run = 0.0
        for i, (_, v) in enumerate(steps):
            ax.bar(i, v, bottom=run, color=RED if v < 0 else GREEN, width=0.55)
            ax.text(i, run + v, f" {_sign(v, ' pts')} ", ha="center",
                    va="top" if v < 0 else "bottom", fontsize=9, fontweight="bold")  # fmt: skip
            ax.plot([i + 0.28, i + 0.72], [run + v, run + v], color=SLATE, lw=0.8, ls="--")
            run += v
        ax.bar(2, run, color=DARK, width=0.55)
        ax.text(2, run, f" {_sign(run)} ", ha="center", va="top" if run < 0 else "bottom",
                fontsize=9.5, fontweight="bold")  # fmt: skip
        ax.set_xticks([0, 1, 2])
        labels = ["Local stocks", "Currency", f"{_name(spec.series[0])} in dollars"]
        ax.set_xticklabels([_wrap(lab, 26) for lab in labels], fontsize=8.5)
        ax.axhline(0, color=INK2, lw=1)
        ax.set_ylabel("Change (%)", fontsize=8.5, color=INK2)
        ax.margins(y=0.2)

    nums = [
        ("local stocks", round(local * 100, 1)),
        ("currency part", round((usd - local) * 100, 1)),
        ("dollar return", round(usd * 100, 1)),
        ("currency vs dollar", round(fxr * 100, 1)),
    ]
    sub = f"{_name(spec.series[0])}'s dollar return since {a.index[0]:%b %-d, %Y}, split into stocks and currency"
    return draw, sub, nums, {"left": 0.12}


def _threshold_band(spec, data, src):
    both = pd.concat([data[k] for k in spec.series[:2]], axis=1).ffill()
    w = both.resample("W-FRI").last().pct_change().dropna()
    rc = w.iloc[:, 0].rolling(26).corr(w.iloc[:, 1]).dropna()
    rc = rc[rc.index >= rc.index[-1] - pd.Timedelta(days=max(spec.window_days, 365))]
    th = float(spec.threshold)

    def draw(ax):
        x = _xdates(ax, rc.index)
        ax.axhspan(th, 1.0, color=RED, alpha=0.08)
        ax.axhline(th, color=RED, lw=0.9, ls="--")
        ax.text(len(rc) - 1, 0.95, f"thesis breaks above {th:g}", fontsize=8, color=RED,
                fontweight="bold", ha="right", va="top")  # fmt: skip
        ax.fill_between(x, rc, 0, color=GREEN, alpha=0.15, lw=0)
        ax.plot(x, rc, color=GREEN, lw=2)
        ax.annotate(f"now {rc.iloc[-1]:.2f}", (x[-1], rc.iloc[-1]), xytext=(4, 0),
                    textcoords="offset points", fontsize=8.5, color=GREEN, fontweight="bold",
                    va="center")  # fmt: skip
        ax.set_ylim(min(-0.2, float(rc.min()) - 0.05), 1.0)
        ax.axhline(0, color=INK2, lw=0.8)

    nums = [
        ("correlation now", round(float(rc.iloc[-1]), 2)),
        ("peak correlation", round(float(rc.max()), 2)),
        ("weeks above threshold", float((rc > th).sum())),
    ]
    sub = f"26-week correlation of {_name(spec.series[0])} and {_name(spec.series[1])} weekly moves"
    return draw, sub, nums, {"left": 0.1}


def _dial(spec, data, src):
    from castelino.agents.trade.tools import technical_numbers

    keys = spec.series[:2]
    names = [_name(k) for k in keys]
    tech = {n: technical_numbers(data[k], None) for n, k in zip(names, keys, strict=True)}

    def draw(ax):
        fig, p = ax.figure, ax.get_position()
        ax.set_position([0.04, p.y0, 0.42, p.height])
        ax.set_aspect("equal")
        ax.axis("off")
        for a0, a1, c in ((0, 54, RED), (54, 126, "#E2E8F0"), (126, 180, GREEN)):
            ax.add_patch(Wedge((0, 0), 1, a0, a1, width=0.28, color=c))
        for i, n in enumerate(names):
            ang = np.deg2rad(180 - tech[n]["rsi14"] * 1.8)
            ax.plot([0, 0.82 * np.cos(ang)], [0, 0.82 * np.sin(ang)], color=GREEN if i == 0 else DARK,
                    lw=3 if i == 0 else 2, solid_capstyle="round")  # fmt: skip
        ax.text(-0.86, -0.12, "oversold < 30", fontsize=7.5, color=INK2, ha="center", va="top")
        ax.text(0.86, -0.12, "overbought > 70", fontsize=7.5, color=INK2, ha="center", va="top")
        rsi = "\n".join(f"{n}  {tech[n]['rsi14']:.0f}" for n in names)
        ax.text(
            0, -0.3, f"14-day RSI\n{rsi}", ha="center", fontsize=8.5, fontweight="bold", va="top"
        )
        ax.set_xlim(-1.2, 1.2)
        ax.set_ylim(-0.5, 1.1)
        ax2 = fig.add_axes([0.66, p.y0 + 0.08, 0.2, p.height - 0.16])
        for i, n in enumerate(names):
            col = GREEN if i == 0 else DARK
            pos = tech[n]["range_pos"]
            ax2.plot([0, 100], [i, i], color="#E2E8F0", lw=6, solid_capstyle="round")
            ax2.scatter([pos], [i], s=120, color=col, zorder=3, edgecolor="white", lw=1.5)
            ax2.text(
                pos,
                i + 0.28,
                f"{pos:.0f}%",
                ha="center",
                fontsize=8.5,
                fontweight="bold",
                color=col,
            )
            if "vs_sma200" in tech[n]:
                ax2.text(104, i, f"{_sign(tech[n]['vs_sma200'])} vs\n200-day avg", va="center",
                         fontsize=7.5, color=INK2)  # fmt: skip
        ax2.set_yticks(range(len(names)))
        ax2.set_yticklabels([_wrap(n) for n in names], fontsize=8.5)
        ax2.set_ylim(-0.6, len(names) - 0.3)
        ax2.set_xticks([0, 100])
        ax2.set_xticklabels(["52-week low", "high"], fontsize=8)
        for side in ("top", "right", "left"):
            ax2.spines[side].set_visible(False)
        ax2.tick_params(axis="y", length=0)

    nums = [
        (f"{n} {k}", float(tech[n][k]))
        for n in names
        for k in ("rsi14", "range_pos", "vs_sma200")
        if k in tech[n]
    ]
    return draw, "Momentum (RSI) and where each sits in its 52-week range", nums, {"left": 0.05}


def _calendar(spec, data, src):
    a, b = (data[k].dropna() for k in spec.series[:2])
    d = (pd.concat([a, b], axis=1).dropna().pct_change().dropna() * 100).iloc[-130:]
    diff = d.iloc[:, 0] - d.iloc[:, 1]
    ahead = int((diff > 0).sum())

    def draw(ax):
        wk = ((diff.index - diff.index[0]).days + diff.index[0].weekday()) // 7
        grid = np.full((5, int(wk.max()) + 1), np.nan)
        for (dt, v), c in zip(diff.items(), wk, strict=True):
            if dt.weekday() < 5:
                grid[dt.weekday(), c] = v
        lim = max(1.0, float(np.nanpercentile(abs(diff), 95)))
        im = ax.imshow(grid, cmap=DIV, norm=TwoSlopeNorm(0, -lim, lim), aspect="auto")
        ax.set_yticks(range(5))
        ax.set_yticklabels(["Mon", "Tue", "Wed", "Thu", "Fri"], fontsize=8)
        months: dict[str, int] = {}
        for dt, c in zip(diff.index, wk, strict=True):
            months.setdefault(dt.strftime("%b"), int(c))
        ax.set_xticks(list(months.values()))
        ax.set_xticklabels(list(months), fontsize=8)
        ax.tick_params(length=0)
        for side in ax.spines.values():
            side.set_visible(False)
        cb = ax.figure.colorbar(im, ax=ax, fraction=0.03, pad=0.02)
        cb.set_label("difference, pts", fontsize=7.5)
        cb.ax.tick_params(labelsize=7)

    first, second = _name(spec.series[0]), _name(spec.series[1])
    sub = f"{first} beat {second} on {ahead} of {len(diff)} days; green = {first} ahead"
    return (
        draw,
        sub,
        [("days ahead", float(ahead)), ("trading days", float(len(diff)))],
        {"left": 0.08},
    )


FORMS: dict[str, Form] = {
    "line": Form("One series over the window.", True, 1, 1, _line),
    "compare": Form("2 to 4 series rebased to 100 at the window start.", True, 2, 4, _compare),
    "bars": Form("Each series' % change over the window, as bars.", True, 1, 8, _bars),
    "scatter": Form(
        "Two series week by week with a fading trail; shows whether they move together.",
        False,
        2,
        2,
        _scatter,
    ),  # fmt: skip
    "treemap": Form(
        "What a fund holds: sector weights of 1 or 2 ETFs side by side (yahoo: ETF tickers).",
        False,
        1,
        2,
        _treemap,
    ),  # fmt: skip
    "quadrant": Form(
        "Markets placed by tech weight (x) and weekly correlation with a benchmark (y); "
        "series = [benchmark, subject ETF, then up to 10 more ETFs].",
        False,
        3,
        12,
        _quadrant,
    ),  # fmt: skip
    "underwater": Form(
        "How far each series sits below its previous peak (drawdown), filled.",
        False,
        1,
        3,
        _underwater,
    ),
    "slope": Form(
        "A benchmark's 20 worst days in the window, each joined to the subject's same-day move; "
        "series = [benchmark, subject].",
        False,
        2,
        2,
        _slope,
    ),  # fmt: skip
    "waterfall": Form(
        "A USD asset's return split into local stocks and currency; "
        "series = [asset, local currency per USD e.g. yahoo:INR=X].",
        False,
        2,
        2,
        _waterfall,
    ),  # fmt: skip
    "threshold_band": Form(
        "26-week rolling correlation of two series against a threshold line "
        "(the 'proves it wrong' test); needs threshold.",
        False,
        2,
        2,
        _threshold_band,
    ),  # fmt: skip
    "dial": Form(
        "RSI gauge plus each series' place in its 52-week range (1 or 2 series).",
        False,
        1,
        2,
        _dial,
    ),
    "calendar": Form(
        "One square per trading day for 130 days: series 1's move minus series 2's.",
        False,
        2,
        2,
        _calendar,
    ),  # fmt: skip
}
PLAIN = {name for name, f in FORMS.items() if f.plain}


def catalog_text() -> str:
    return "\n".join(
        f"- {n}{' (plain)' if f.plain else ''}: {f.description} "
        f"Series: {f.min_series} to {f.max_series}."
        for n, f in FORMS.items()
    )


def spec_errors(spec: ChartSpec) -> list[str]:
    f = FORMS.get(spec.form)
    if f is None:
        return [f"unknown form {spec.form}"]
    errs = [
        f"bad series {s} (use fred:ID or yahoo:TICKER)" for s in spec.series if not SERIES.match(s)
    ]
    if not f.min_series <= len(spec.series) <= f.max_series:
        errs.append(
            f"{spec.form} needs {f.min_series} to {f.max_series} series, got {len(spec.series)}"
        )
    if spec.form == "threshold_band" and spec.threshold is None:
        errs.append("threshold_band needs a threshold")
    if not 30 <= spec.window_days <= 3650:
        errs.append("window_days must be 30 to 3650")
    if len(spec.title) > 60:  # the frame cuts "Exhibit n: <title>" at 72 characters
        errs.append(
            "title is over 60 characters and would be cut off; shorten the claim, keep the full names"
        )
    return errs


def render(spec: ChartSpec, src: Sources, out: Path, n: int) -> list[tuple[str, float]]:
    if errs := spec_errors(spec):
        raise ValueError("; ".join(errs))
    data = {}
    for sid in spec.series:
        provider, name = sid.split(":", 1)
        data[sid] = (src.fred if provider == "fred" else src.yahoo)(name)
    _NAMES.set(dict(zip(spec.series, spec.names or [], strict=False)))
    draw, sub, nums, layout = FORMS[spec.form].draw(spec, data, src)
    feeds = ", ".join(
        sorted({"FRED" if s.startswith("fred:") else "Yahoo Finance" for s in spec.series})
    )
    source = f"{feeds} ({', '.join(_ticker(s) for s in spec.series)}); computed by ARC."
    _frame(n, spec.title, _wrap(sub, 72), source, out, draw, kicker=KICKER, **layout)
    return nums
