"""Weekly exhibits: the Editor picks a chart form per exhibit; code draws it from the facts' data.

Forms: line (one series), compare (2-4 series, prices rebased to 100, rates as levels), release
(a release history), breakdown and movers (bars, one fact number per bar) and dumbbell (before ->
after). Every plotted number is a fact's data: series are fetched from the fact's SeriesRef, bar
values must be one of the fact's numbers (checked by the guard). Same house style as the Morning
Note exhibits: ARC green, slate for context, the logo, "Exhibit N" and a source footer."""

from __future__ import annotations

import logging
from pathlib import Path
from types import SimpleNamespace

import matplotlib.pyplot as plt
import pandas as pd

from castelino.agents.update.charts import (
    GREEN,
    INK,
    INK2,
    SLATE,
    _logo,
    _render,
    default_fetch,
    is_rate,
)
from castelino.agents.update.models import Fact
from castelino.agents.weekly.models import ExhibitPick, WeeklyExhibit, WeeklyReport

log = logging.getLogger(__name__)

RED = "#B91C1C"
DARK = "#0F172A"
COMPARE = [GREEN, DARK, SLATE, "#6EE7B7"]  # 4 series max, all within the ARC palette

_LABELS = (
    (10, "last week"),
    (35, "last month"),
    (100, "last 3 months"),
    (200, "last 6 months"),
    (400, "last year"),
)


def window_label(days: int) -> str:
    for limit, label in _LABELS:
        if days <= limit:
            return label
    return f"last {round(days / 365)} years"


def default_series(ref, window_days: int) -> pd.Series:
    """The fact's full daily series over the window (compare charts)."""
    from castelino.forecast import regime

    fn = regime._fetch_fred_series if ref.provider == "fred" else regime._fetch_yf_close
    s = fn(ref.id).dropna()
    return s[s.index >= s.index[-1] - pd.Timedelta(days=window_days)]


def compare_frame(facts: list[Fact], window_days: int, series=default_series) -> pd.DataFrame:
    """Aligned columns per fact; prices rebased to 100 at the first common date, FRED rates
    kept as levels (all rates) so a yield chart reads in %."""
    names = [f.series.label or f.series.id for f in facts]
    if len(set(names)) < len(names):  # duplicate labels would overwrite each other's column
        names = [f.series.id for f in facts]
    if len(set(names)) < len(names):
        raise ValueError("compare: the same series twice")
    df = pd.DataFrame({n: series(f.series, window_days) for n, f in zip(names, facts, strict=True)})
    df = df.dropna()
    if len(df) < 2:
        raise ValueError("compare: series don't overlap")
    if all(f.series.provider == "fred" and is_rate(f.series.id) for f in facts):
        return df
    return df / df.iloc[0] * 100


def _num(v: float) -> str:
    """The value as the data wrote it (up to 2 decimals, no padding): 62.89, 0.4, 197,000."""
    return f"{v:,.2f}".rstrip("0").rstrip(".")


def _fmt(v: float, unit: str, signed: bool = True) -> str:
    sign = "+" if signed and v > 0 else ""
    if unit == "$":
        return f"${v:,.2f}"  # money always shows cents
    return f"{sign}{_num(v)}{unit if unit != 'level' else ''}"


def _frame(
    n: int,
    title: str,
    sub: str,
    data: str,
    path: Path,
    draw,
    left=0.1,
    bottom=0.2,
    kicker: str = "WEEKLY DEEP DIVE",
) -> None:
    plt.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.sans-serif": ["Helvetica", "Arial", "DejaVu Sans"],
            "text.color": INK,
            "axes.edgecolor": "#475569",
            "xtick.color": INK,
            "ytick.color": INK,
            "savefig.dpi": 240,
        }
    )
    fig, ax = plt.subplots(figsize=(6.4, 3.9))
    fig.subplots_adjust(left=left, right=0.88, top=0.76, bottom=bottom)
    draw(ax)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.tick_params(labelsize=8.5)
    fig.text(
        0.06,
        0.965,
        f"ARC RESEARCH | {kicker}",
        fontsize=8.5,
        fontweight="bold",
        color="#475569",
    )
    head = f"Exhibit {n}: {title}"[:72]
    # shrink a long title so it stops short of the logo (13pt fits ~52 characters)
    fig.text(0.06, 0.905, head, fontsize=min(13, 13 * 52 / len(head)), fontweight="bold")
    if "\n" in sub:  # a wrapped subtitle hangs from under the title instead of growing up into it
        fig.text(0.06, 0.885, sub, fontsize=10, color=INK2, va="top")
    else:
        fig.text(0.06, 0.855, sub, fontsize=10, color=INK2)
    fig.text(0.06, 0.055, "Source: ARC Research", fontsize=9, fontweight="bold")
    fig.text(0.06, 0.02, f"Data: {data}"[:110], fontsize=8, color=INK2)
    logo = _logo()
    if logo is not None:
        logo_ax = fig.add_axes((0.84, 0.83, 0.12, 0.15))
        logo_ax.imshow(logo)
        logo_ax.axis("off")
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path)
    plt.close(fig)


def _bars(ex: ExhibitPick, diverging: bool, keep_order: bool = False, signed: bool = True):
    pts = list(ex.points) if keep_order else sorted(ex.points, key=lambda p: p.value, reverse=True)
    labels, vals = [p.label for p in pts], [p.value for p in pts]

    def draw(ax):
        colors = [GREEN if v >= 0 else RED for v in vals]
        if diverging:
            x = range(len(vals))
            bars = ax.bar(x, vals, color=colors, width=0.6)
            ax.set_xticks(list(x))
            ax.set_xticklabels(
                [lb if len(lb) <= 16 else lb[:15] + "…" for lb in labels], fontsize=8
            )
            ax.axhline(0, color=INK2, lw=1)
            span = max(vals) - min(min(vals), 0) or 1  # headroom so end labels clear the axes
            ax.set_ylim(min(min(vals), 0) - 0.18 * span, max(max(vals), 0) + 0.18 * span)
            for b, v in zip(bars, vals, strict=True):
                ax.text(
                    b.get_x() + b.get_width() / 2,
                    v,
                    _fmt(v, ex.unit, signed),
                    ha="center",
                    va="bottom" if v >= 0 else "top",
                    fontsize=8.5,
                    fontweight="bold",
                )
        else:
            y = list(range(len(vals)))[::-1]
            ax.barh(y, vals, color=colors, height=0.6)
            ax.set_yticks(y)
            ax.set_yticklabels(labels, fontsize=8.5)
            ax.axvline(0, color=INK2, lw=1)
            span = max(vals) - min(min(vals), 0) or 1
            for yi, v in zip(y, vals, strict=True):  # label just outside the bar's end
                ax.text(
                    v + (0.02 if v >= 0 else -0.02) * span,
                    yi,
                    _fmt(v, ex.unit, signed),
                    va="center",
                    ha="left" if v >= 0 else "right",
                    fontsize=8.5,
                    fontweight="bold",
                )
            ax.set_xlim(min(min(vals), 0) - 0.25 * span, max(max(vals), 0) + 0.25 * span)

    top = max(pts, key=lambda p: p.value)
    sub = f"Highest: {top.label} {_fmt(top.value, ex.unit, signed)}"
    return draw, sub


def _dumbbell(ex: ExhibitPick):
    a, b = ex.points

    def draw(ax):
        ax.plot([0, 1], [a.value, b.value], color=SLATE, lw=3, zorder=1)
        ax.scatter([0], [a.value], s=120, color=SLATE, zorder=2)
        ax.scatter([1], [b.value], s=120, color=GREEN, zorder=2)
        for x, p, c in ((0, a, INK2), (1, b, GREEN)):
            ax.annotate(
                _fmt(p.value, ex.unit, signed=False),
                (x, p.value),
                xytext=(0, 10),
                textcoords="offset points",
                ha="center",
                fontsize=10,
                fontweight="bold",
                color=c,
            )
        ax.set_xticks([0, 1])
        ax.set_xticklabels([a.label, b.label], fontsize=9)
        ax.set_xlim(-0.4, 1.4)
        lo, hi = sorted((a.value, b.value))
        pad = (hi - lo) * 0.4 or abs(hi) * 0.1 or 1
        ax.set_ylim(lo - pad, hi + pad)

    return draw, f"{a.label} to {b.label}"


def _compare(df: pd.DataFrame, rebased: bool):
    def draw(ax):
        x = list(range(len(df)))
        for i, col in enumerate(df.columns):
            ax.plot(x, df[col], color=COMPARE[i % 4], lw=2, label=col)
            ax.annotate(
                f"{df[col].iloc[-1]:,.1f}",
                (x[-1], df[col].iloc[-1]),
                xytext=(4, 0),
                textcoords="offset points",
                va="center",
                fontsize=8.5,
                color=COMPARE[i % 4],
                fontweight="bold",
            )
        step = max(1, len(x) // 6)
        ax.set_xticks(x[::step])
        ax.set_xticklabels(
            [pd.Timestamp(i).strftime("%b %d") for i in df.index[::step]], fontsize=8.5
        )
        if rebased:
            ax.axhline(100, color=SLATE, lw=0.8, ls="--")
        ax.legend(fontsize=8, frameon=False, loc="upper left")

    last = df.iloc[-1]
    lead = last.idxmax()
    sub = f"{lead} leads, {last[lead]:,.1f}" + (" (start = 100)" if rebased else "%")
    return draw, sub


def _data_line(facts: list[Fact]) -> str:
    return ", ".join(dict.fromkeys(f.source_title for f in facts)) + "."


def make_weekly_exhibits(
    report: WeeklyReport,
    facts: list[Fact],
    out_dir: Path,
    fetch=default_fetch,
    series=default_series,
    kicker: str = "WEEKLY DEEP DIVE",
    forms: dict | None = None,  # extra kind -> fn(pick, facts, series) -> (draw, sub, frame kw)
) -> list[WeeklyExhibit]:
    by = {f.id: f for f in facts}
    out: list[WeeklyExhibit] = []
    for si, sec in enumerate(report.sections):
        for pick in sec.exhibits:
            n = len(out) + 1
            path = Path(out_dir) / f"exhibit_{n}.png"
            try:
                cited = [
                    by[i] for i in dict.fromkeys(pick.fact_ids + [p.fact_id for p in pick.points])
                ]
                if not cited:
                    raise ValueError("no facts")
                title, sub = pick.title, ""
                if pick.kind in ("line", "release"):
                    fact = cited[0]
                    if fact.series is None:
                        raise ValueError("no chartable series")
                    ref = fact.series
                    release = ref.kind == "release"
                    pts = (
                        [(p.label, p.value) for p in ref.points]
                        if release
                        else fetch(ref, pick.window_days)
                    )
                    if len(pts) < 2:
                        raise ValueError(f"only {len(pts)} point(s)")
                    label = (
                        None
                        if release
                        else (
                            "last 7 days"
                            if ref.provider == "polymarket"
                            else window_label(pick.window_days)
                        )
                    )
                    shim = SimpleNamespace(
                        id=fact.id, agent="", series=ref, source_title=fact.source_title
                    )
                    ex = _render(n, shim, pts, path, kicker=kicker, window_label=label)
                    title, sub = ex.title.removeprefix(f"Exhibit {n}: "), ex.subtitle
                elif pick.kind == "compare":
                    if not 2 <= len(cited) <= 4 or any(f.series is None for f in cited):
                        raise ValueError("compare needs 2-4 series")
                    df = compare_frame(cited, pick.window_days, series)
                    rebased = not all(
                        f.series.provider == "fred" and is_rate(f.series.id) for f in cited
                    )
                    draw, sub = _compare(df, rebased)
                    sub = f"{sub} · {window_label(pick.window_days)}"
                    _frame(n, title, sub, _data_line(cited), path, draw, kicker=kicker)
                elif pick.kind in ("breakdown", "movers"):
                    if len(pick.points) < 2:
                        raise ValueError("needs 2+ points")
                    draw, sub = _bars(pick, diverging=pick.kind == "movers")
                    left = 0.1 if pick.kind == "movers" else 0.32  # room for category labels
                    _frame(
                        n,
                        title,
                        sub,
                        _data_line(cited),
                        path,
                        draw,
                        left=left,
                        bottom=0.24,
                        kicker=kicker,
                    )
                elif pick.kind == "dumbbell":
                    if len(pick.points) != 2:
                        raise ValueError("needs 2 points")
                    draw, sub = _dumbbell(pick)
                    _frame(n, title, sub, _data_line(cited), path, draw, kicker=kicker)
                elif pick.kind in (forms or {}):
                    draw, sub, kw = forms[pick.kind](pick, cited, series)
                    _frame(n, title, sub, _data_line(cited), path, draw, kicker=kicker, **kw)
                else:
                    raise ValueError(f"unknown form {pick.kind}")
                out.append(
                    WeeklyExhibit(
                        n=n,
                        section=si,
                        fact_id=cited[0].id,
                        kind=pick.kind,
                        title=f"Exhibit {n}: {title}",
                        subtitle=sub,
                        file=path.name,
                    )
                )
            except Exception as exc:  # noqa: BLE001 — a chart is never load-bearing
                log.warning("weekly exhibit %s (%s) dropped: %s", pick.fact_ids, pick.kind, exc)
    return out
