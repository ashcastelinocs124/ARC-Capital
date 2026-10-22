"""Charts on X release posts (the user's ask, 2026-10-22). An earnings post carries up to three: where
its sales came from and where its profit came from (treemaps of the company's business segments), and
its beat or miss against estimates. A data release carries one: actual against forecast and previous.

The segments come from the earnings release the company files with the SEC (exhibit 99.1 of an 8-K
with item 2.02), usually minutes after it reports. The Segment Reader only copies that release's
segment table; code keeps a number only if the release prints it, and draws every chart. A chart that
can't be made is left out: a post never waits for one."""

from __future__ import annotations

import re
import textwrap
from datetime import date
from pathlib import Path
from typing import Literal

from matplotlib.patches import Rectangle
from pydantic import BaseModel

from castelino.agents.base import StructuredAgent
from castelino.agents.update.facts import numbers_in
from castelino.agents.weekly import charts as wc
from castelino.config import get_settings

KICKER = "EARNINGS"
MAX_BOXES = 8  # past this the boxes get too small to read; the rest fold into "Other"
DOMINANT = 0.9  # one box this big is the whole chart (a one-dot chart), so it isn't drawn
READ = """You read a company's quarterly earnings release, as filed with the SEC, and copy its table of
results by business segment for the quarter just reported; with no segment table, its revenue by
business line or source (automotive, energy, services ...). A table with several quarters side by side:
use only the column of the quarter just reported. For each segment or line: its name, its
net sales (revenue), and its change against a year ago in percent if the table gives one; its profit
(operating income, segment income or earnings before income taxes, whichever the table reports) and
that profit's change in percent if given. Copy every number exactly as the table prints it, in the
table's unit; a number in brackets is negative. Leave out corporate, eliminations, other reconciling
lines and the total. profit_label names the profit measure as the table does. period: the quarter as
the release names it ("Q1 fiscal 2027", "third quarter 2026"). No segment table: no segments."""


class Segment(BaseModel):  # LLM output (closed schema: no defaults)
    name: str
    sales: float
    sales_change_pct: float | None
    profit: float | None
    profit_change_pct: float | None


class SegmentTable(BaseModel):  # LLM output (closed schema: no defaults)
    period: str
    unit: Literal["thousands", "millions", "billions"]
    profit_label: str
    segments: list[Segment]


class SegmentReader(StructuredAgent[SegmentTable]):
    name = "x_segment_reader"
    output_schema = SegmentTable
    tier = "fast"

    def __init__(self) -> None:
        self.model = get_settings().x_scout.writer_model

    def system_prompt(self) -> str:
        return READ

    def user_prompt(self, *, company: str, text: str) -> str:
        return f"Company: {company}\n\nEarnings release:\n{text[:60_000]}"


def checked(table: SegmentTable, text: str) -> SegmentTable:
    """Only numbers the release prints: a segment whose sales aren't in it is dropped, any other
    number that isn't becomes None."""
    printed = {round(abs(n), 6) for n in numbers_in(text)}

    def ok(v: float | None) -> float | None:
        return v if v is not None and round(abs(v), 6) in printed else None

    segs = [
        s.model_copy(
            update={
                "sales_change_pct": ok(s.sales_change_pct),
                "profit": ok(s.profit),
                "profit_change_pct": ok(s.profit_change_pct),
            }
        )
        for s in table.segments
        if s.sales > 0 and ok(s.sales) is not None
    ]
    return table.model_copy(update={"segments": segs})


def segments(company: str, ticker: str, day: date) -> tuple[SegmentTable, str] | None:
    """The checked segment table of the release filed for `day` and its address; None when there is
    no release yet or fewer than 2 segments survive the check."""
    from castelino.adoption.sources.edgar import EdgarClient

    found = EdgarClient(get_settings().adoption.sec_user_agent).earnings_release(ticker, day)
    if not found:
        return None
    text, url = found
    table = checked(SegmentReader()(company=company, text=text), text)
    return (table, url) if len(table.segments) >= 2 else None


def _money(v: float, unit: str) -> str:
    b = v * {"thousands": 1e-6, "millions": 1e-3, "billions": 1.0}[unit]
    return f"\\${b:,.2f}B" if b < 10 else f"\\${b:,.1f}B" if b < 1000 else f"\\${b / 1000:,.2f}T"


def _shade(change: float | None) -> tuple[str, str]:
    """(fill, text): one green hue, darker for faster growth; red for a fall; light when unknown."""
    if change is None:
        return "#A7F3D0", wc.INK
    if change < 0:
        return "#FCA5A5", wc.INK
    if change < 3:
        return "#6EE7B7", wc.INK
    return ("#10B981", wc.INK) if change < 6 else (wc.GREEN, "white")


def squarify(vals: list[float], x: float, y: float, w: float, h: float) -> list[tuple]:
    """Squarified treemap: (x, y, w, h) per value, values sorted large to small."""
    out, areas = [], [v * w * h / sum(vals) for v in vals]

    def worst(row: list[float], side: float) -> float:
        s = sum(row)
        return max(max(side * side * r / (s * s), s * s / (side * side * r)) for r in row)

    while areas:
        side, row = min(w, h), [areas.pop(0)]
        while areas and worst([*row, areas[0]], side) <= worst(row, side):
            row.append(areas.pop(0))
        s = sum(row)
        if w >= h:  # a column down the left
            cw, cy = s / h, y
            for r in row:
                out.append((x, cy, cw, r / cw))
                cy += r / cw
            x, w = x + cw, w - cw
        else:  # a row along the bottom
            rh, cx = s / w, x
            for r in row:
                out.append((cx, y, r / rh, rh))
                cx += r / rh
            y, h = y + rh, h - rh
    return out


def treemap(items: list[tuple[str, float, float | None]], unit: str, title: str, sub: str,
            data: str, path: Path) -> None:  # fmt: skip
    """Boxes sized by value, shaded by change; past MAX_BOXES the smallest fold into "Other"."""
    items = sorted(items, key=lambda t: -t[1])
    if len(items) > MAX_BOXES:
        rest = items[MAX_BOXES - 1 :]
        items = [*items[: MAX_BOXES - 1], ("Other", sum(v for _, v, _ in rest), None)]
    total = sum(v for _, v, _ in items)

    def draw(ax):
        for (name, v, chg), (x, y, w, h) in zip(items, squarify([v for _, v, _ in items], 0, 0, 100, 60), strict=True):  # fmt: skip
            fill, ink = _shade(chg)
            ax.add_patch(Rectangle((x, y), w, h, facecolor=fill, edgecolor="white", lw=2.5))
            if w < 9 or h < 9:
                continue  # too small for a label
            small = w < 20 or h < 16
            wrap = max(8, int(w * (0.8 if small else 0.62)))  # characters a line of the box holds
            ax.text(x + 1.5, y + h - 2.2, textwrap.fill(name, wrap), va="top",
                    fontsize=7.5 if small else 9.5, fontweight="bold", color=ink)  # fmt: skip
            sign = (
                ""
                if chg is None
                else ("+" if chg > 0 else "−" if chg < 0 else "") + f"{abs(chg):g}% y/y"
            )
            ax.text(x + 1.5, y + 2, f"{_money(v, unit)} · {v / total * 100:.0f}%" + (f"\n{sign}" if sign else ""),
                    va="bottom", fontsize=7.5 if small else 9, color=ink)  # fmt: skip
        ax.set_xlim(0, 100)
        ax.set_ylim(0, 60)
        ax.axis("off")

    wc._frame(
        1, title, sub, data, path, draw, kicker=KICKER, left=0.06, bottom=0.12, numbered=False
    )


def segment_charts(
    company: str, table: SegmentTable, url: str, out: Path, ticker: str
) -> list[Path]:
    """Where the sales came from and, when every segment reports a profit, where the profit came from.
    A treemap needs 2 boxes and none of them DOMINANT: one box is no chart."""
    data = f"{company} earnings release (SEC 8-K, exhibit 99.1): {url.split('/')[-1]}"
    whose = company + ("'" if company.endswith("s") else "'s")
    paths = []

    def draw(kind: str, items: list, measure: str, note: str = "") -> None:
        total = sum(v for _, v, _ in items)
        if len(items) < 2 or max(v for _, v, _ in items) >= DOMINANT * total:
            print(f"  {ticker}: no {kind} treemap: {len(items)} segment(s), one is most of it")
            return
        legend = (
            " · darker = faster growth, red = down" if any(c is not None for *_, c in items) else ""
        )
        p = out / f"{ticker}-{kind}.png"
        treemap(items, table.unit, f"Where {whose} {kind} came from",
                f"{measure} by segment, {table.period}{legend}", data + note, p)  # fmt: skip
        paths.append(p)

    draw("sales", [(_short(s.name), s.sales, s.sales_change_pct) for s in table.segments], "Sales")
    profits = [(_short(s.name), s.profit, s.profit_change_pct) for s in table.segments]
    if all(v is not None for _, v, _ in profits):
        lost = [f"{n} ({_money(abs(v), table.unit)} loss)" for n, v, _ in profits if v <= 0]
        note = f"; not shown: {', '.join(lost)}" if lost else ""
        draw("profit", [t for t in profits if t[1] > 0], table.profit_label, note)
    return paths


def _short(name: str) -> str:
    """'Total automotive revenues' -> 'Automotive': the table's filler words off a box's name."""
    s = re.sub(r"^total\s+|\s+(revenues?|net sales|sales|segment)$", "", name.strip(), flags=re.I)
    return s[:1].upper() + s[1:] if s else name


_EPS = re.compile(r"EPS (-?)\$?(-?[\d.,]+)( cents)? vs (-?)\$?(-?[\d.,]+)( cents)? expected", re.I)
_REV = re.compile(
    r"revenue \$?([\d.,]+) (billion|million) vs \$?([\d.,]+) (billion|million) expected", re.I
)


def _num(sign: str, s: str, cents: str | None = None) -> float:
    v = float(s.replace(",", "")) * (-1 if sign else 1)
    return v / 100 if cents else v


def beat_miss(line: str, company: str, path: Path) -> bool:
    """EPS and revenue against estimates, from the post's own numbers line; False when it gives neither."""
    rows = []
    if m := _EPS.search(line):
        a, e = _num(m[1], m[2], m[3]), _num(m[4], m[5], m[6])
        if e > 0:
            rows.append(("EPS", f"\\${a:.2f} vs \\${e:.2f}", a, e))
    if m := _REV.search(line):
        a = _num("", m[1]) * (1 if m[2].lower() == "billion" else 1e-3)
        e = _num("", m[3]) * (1 if m[4].lower() == "billion" else 1e-3)
        rows.append(("Revenue", f"\\${a:,.2f}B vs \\${e:,.2f}B", a, e))
    if not rows:
        return False
    pct = [(n, lab, (a / e - 1) * 100) for n, lab, a, e in rows]
    beats = {p >= 0 for *_, p in pct}
    what = " and ".join({"EPS": "earnings", "Revenue": "revenue"}[n] for n, *_ in pct)
    title = (
        f"{company} {'beat' if beats == {True} else 'missed'} on {what}"
        if len(beats) == 1
        else f"{company}: "
        + ", ".join(
            f"{n.replace('Revenue', 'revenue')} {'beat' if p >= 0 else 'missed'}" for n, _, p in pct
        )  # fmt: skip
    )
    lo, hi = min(0, *(p for *_, p in pct)), max(0, *(p for *_, p in pct))
    span = (hi - lo) or 1
    xmin, xmax = lo - span * 0.05, hi + span * (0.6 if hi > 0 else 0.5)

    def draw(ax):
        ys = list(range(len(pct)))[::-1]
        for y, (_, _, p) in zip(ys, pct, strict=True):
            ax.barh(y, p, height=0.5, color=wc.GREEN if p >= 0 else wc.RED)
            words = f"{'beat' if p >= 0 else 'missed'} by {abs(p):.1f}%"
            if p >= 0:
                ax.text(p, y, f"  {words}", va="center", ha="left", fontsize=11, fontweight="bold")
            elif -p > 0.38 * (xmax - xmin):  # long enough to hold its label, clear of the axis
                ax.text(p, y, f"  {words}", va="center", ha="left", fontsize=11, fontweight="bold", color="white")  # fmt: skip
            else:  # a short miss: the label right of zero
                ax.text(0, y, f"  {words}", va="center", ha="left", fontsize=11, fontweight="bold")
        ax.set_yticks(ys)
        ax.set_yticklabels([f"{n}\n{lab}" for n, lab, _ in pct], fontsize=9.5)
        ax.axvline(0, color=wc.INK2, lw=1)
        ax.set_xlim(xmin, xmax)
        ax.set_xlabel("% against the analysts' estimate", fontsize=8.5)

    wc._frame(1, title, "Reported against the analysts' estimate", "Results and estimates as cited in the post",
              path, draw, kicker=KICKER, left=0.27, numbered=False)  # fmt: skip
    return True


def data_chart(label: str, e: dict, day: date, path: Path) -> bool:
    """Actual against forecast and previous, from Nasdaq's calendar row; False without an actual."""
    rows = [
        (n, e.get(k))
        for n, k in (("Previous", "previous"), ("Forecast", "consensus"), ("Actual", "actual"))
    ]
    rows = [(n, v) for n, v in rows if v is not None]
    if not rows or rows[-1][0] != "Actual":
        return False
    unit, act, cons = e.get("unit") or "", rows[-1][1], e.get("consensus")
    verb = "" if cons is None else " came in above forecast" if act > cons else " came in below forecast" if act < cons else " came in at forecast"  # fmt: skip

    def draw(ax):
        for i, (n, v) in enumerate(rows):
            filled = n == "Actual"
            ax.bar(i, v, width=0.55, color=wc.GREEN if filled else "white", edgecolor=wc.GREEN if filled else wc.INK2,
                   ls="-" if filled else "--", lw=1.4)  # fmt: skip
            ax.text(
                i,
                v,
                f"{v:g}{unit}",
                ha="center",
                va="bottom" if v >= 0 else "top",
                fontsize=11,
                fontweight="bold",
            )
        ax.set_xticks(range(len(rows)))
        ax.set_xticklabels([n for n, _ in rows], fontsize=9.5)
        ax.axhline(0, color=wc.INK2, lw=1)
        lo, hi = min(0, *(v for _, v in rows)), max(0, *(v for _, v in rows))
        ax.set_ylim(lo * 1.18, hi * 1.18 or 1)

    wc._frame(1, f"{label}{verb}", f"Released {day:%b %-d, %Y}", "Nasdaq economic calendar", path, draw,
              kicker="DATA RELEASE", left=0.12, numbered=False)  # fmt: skip
    return True


def earnings_charts(company: str, ticker: str, line: str, day: date, out: Path) -> list[Path]:
    """Up to three charts for an earnings post; whatever fails is left out (and logged)."""
    out.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    try:
        if found := segments(company, ticker, day):
            paths += segment_charts(company, *found, out, ticker)
        else:
            print(
                f"  {ticker}: no segment table in an SEC filing yet; posting the beat or miss alone"
            )
    except Exception as e:  # noqa: BLE001 - a chart never holds up the news
        print(f"  {ticker}: segment charts failed: {e}")
    try:
        if beat_miss(line, company, p := out / f"{ticker}-vs-estimates.png"):
            paths.append(p)
    except Exception as e:  # noqa: BLE001
        print(f"  {ticker}: beat-or-miss chart failed: {e}")
    return paths
