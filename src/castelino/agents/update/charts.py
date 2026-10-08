"""Chart agent (code, no LLM): one institutional-style exhibit per chart the Editor asked for.

Style follows the institutional-financial-chart skill: emerald primary, slate previous, ARC logo,
"Exhibit N" title, subtitle computed from the plotted numbers, "Source: ARC Research" footer.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from castelino.agents.update.models import Exhibit, Finding, SeriesRef  # noqa: E402

log = logging.getLogger(__name__)

GREEN, SLATE, INK, INK2 = "#047857", "#94A3B8", "#0F172A", "#334155"
KICKER = {"macro": "MACRO", "news": "NEWS", "alt": "ALT DATA", "ai": "AI & CHIPS"}
WINDOW = 7


def default_fetch(ref: SeriesRef) -> list[tuple[str, float]]:
    if ref.provider == "polymarket":
        from castelino.agents.update.sources import polymarket

        by_day: dict[str, float] = {}  # the feed adds an intraday point; keep each day's last
        for t, p in polymarket.price_history(ref.id):
            by_day[datetime.fromtimestamp(t, UTC).strftime("%b %d")] = p * 100
        return list(by_day.items())[-WINDOW:]
    from castelino.forecast import regime

    fn = regime._fetch_fred_series if ref.provider == "fred" else regime._fetch_yf_close
    s = fn(ref.id).dropna().tail(WINDOW)
    return [(pd.Timestamp(i).strftime("%b %d"), float(v)) for i, v in s.items()]


def subtitle(ref: SeriesRef, pts: list[tuple[str, float]]) -> str:
    a, b = pts[0][1], pts[-1][1]
    if ref.kind == "release":
        return f"{b - a:+.2f}pp vs previous release"
    if ref.provider == "polymarket":
        return f"{b - a:+.1f}pp over the window"
    if ref.id.startswith("DGS"):
        return f"{(b - a) * 100:+.0f}bp over the window"
    return f"{(b / a - 1) * 100:+.1f}% over the window"


def _end_label(ref: SeriesRef, v: float) -> str:
    if ref.kind == "release" or ref.id.startswith("DGS"):
        return f"{v:.2f}%"
    if ref.provider == "polymarket":
        return f"{v:.0f}%"
    return f"{v:,.2f}"


TITLE_MAX = 60  # wider titles run under the logo


def title_for(n: int, ref: SeriesRef, n_pts: int) -> str:
    suffix = "" if ref.kind == "release" else f" · last {n_pts} obs"
    head = f"Exhibit {n}: "
    room = TITLE_MAX - len(head) - len(suffix)
    label = ref.label if len(ref.label) <= room else ref.label[: room - 1].rstrip() + "…"
    return head + label + suffix


def footer_lines(f: Finding) -> tuple[str, str]:
    return "Source: ARC Research", f"Data: {f.source_title}."


LOGO = Path(__file__).resolve().parents[4] / "frontend" / "public" / "arc-logo.png"


def _logo():
    if not LOGO.is_file():
        return None  # a chart without the logo beats no chart
    img = plt.imread(LOGO)
    if img.shape[2] == 3:
        return img
    # Composite onto white: imshow resampling of the transparent-black background left a grey box.
    a = np.where(img[..., 3:4] < 0.2, 0.0, img[..., 3:4])  # background carries ~1-15% alpha noise
    return img[..., :3] * a + (1 - a)


def _render(n: int, f: Finding, pts: list[tuple[str, float]], path: Path) -> Exhibit:
    ref = f.series
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
    title = title_for(n, ref, len(pts))
    sub = subtitle(ref, pts)
    fig, ax = plt.subplots(figsize=(6.4, 3.9))
    fig.subplots_adjust(left=0.1, right=0.88, top=0.76, bottom=0.2)
    labels, vals = [p[0] for p in pts], [p[1] for p in pts]
    if ref.kind == "release":
        bars = ax.bar(labels, vals, color=[SLATE] * (len(vals) - 1) + [GREEN], width=0.5)
        for b, v in zip(bars, vals, strict=True):
            ax.text(
                b.get_x() + b.get_width() / 2,
                v,
                _end_label(ref, v),
                ha="center",
                va="bottom",
                fontsize=11,
                fontweight="bold",
            )
        ax.axhline(0, color=INK2, lw=1)
    else:
        x = list(range(len(vals)))
        ax.plot(x, vals, color=GREEN, lw=2)
        ax.scatter([x[-1]], [vals[-1]], color=GREEN, zorder=3)
        ax.annotate(
            _end_label(ref, vals[-1]),
            (x[-1], vals[-1]),
            xytext=(6, 0),
            textcoords="offset points",
            va="center",
            fontsize=10,
            fontweight="bold",
            color=GREEN,
        )
        ax.set_xticks(x)
        ax.set_xticklabels(labels, fontsize=8.5)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.tick_params(labelsize=8.5)
    fig.text(
        0.06,
        0.965,
        f"ARC RESEARCH | {KICKER[f.agent]}",
        fontsize=8.5,
        fontweight="bold",
        color="#475569",
    )
    fig.text(0.06, 0.905, title, fontsize=13, fontweight="bold")
    fig.text(0.06, 0.855, sub, fontsize=10, color=INK2)
    src, data = footer_lines(f)
    fig.text(0.06, 0.055, src, fontsize=9, fontweight="bold")
    fig.text(0.06, 0.02, data, fontsize=8, color=INK2)
    logo = _logo()
    if logo is not None:
        logo_ax = fig.add_axes((0.84, 0.83, 0.12, 0.15))
        logo_ax.imshow(logo)
        logo_ax.axis("off")
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path)
    plt.close(fig)
    return Exhibit(n=n, finding_id=f.id, title=title, subtitle=sub, file=path.name)


def make_exhibits(findings: list[Finding], out_dir: Path, fetch=default_fetch) -> list[Exhibit]:
    out: list[Exhibit] = []
    for f in findings:
        ref = f.series
        try:
            if ref is None:
                raise ValueError("no series")
            pts = [(p.label, p.value) for p in ref.points] if ref.kind == "release" else fetch(ref)
            if len(pts) < 2:
                raise ValueError(f"only {len(pts)} point(s)")
            n = len(out) + 1
            out.append(_render(n, f, pts, Path(out_dir) / f"exhibit_{n}.png"))
        except Exception as exc:  # noqa: BLE001 — a chart is never load-bearing
            log.warning("chart for %s dropped: %s", f.id, exc)
    return out
