"""The link card for /dashboards/ai-capex (the dark look the user picked) and the page copy that carries
its preview tags. X, LinkedIn and Slack cache a card per image URL, so the image is published under a
dated name and each day's new posts show that day's numbers."""

from __future__ import annotations

import html as h
import json
import re
from datetime import date
from pathlib import Path

from castelino.dashboards.ai_capex.run import _qname, _usd

SITE = "https://arcresearch.markets"
BG, TEXT, TEXT2, MUTED, GRID, RULE, ACCENT, UP = (
    "#1a221f", "#f2f5f3", "#d6dcd9", "#a8b0ac", "#222b27", "#35403b", "#5fcf97", "#4ade80",
)  # fmt: skip
COLORS = {
    "MSFT": "#339af0",
    "GOOGL": "#2fa36e",
    "AMZN": "#e8590c",
    "META": "#9775fa",
    "ORCL": "#fbbf24",
}
W, H = 1200, 630


def _latest_full(doc: dict) -> dict | None:
    full = [q for q in (doc.get("totals") or {}).get("quarters", []) if q["reported"] == q["of"]]
    return full[-1] if full else None


def chart_quarters(doc: dict) -> list[dict]:
    """The card's bars: up to the latest quarter every company has filed. A partial one (3 of 5)
    would read as capex collapsing on the most-shared image; the page marks it, the card leaves it out."""
    qs = (doc.get("totals") or {}).get("quarters", [])
    last = _latest_full(doc)
    return [q for q in qs if last and q["q"] <= last["q"]][-10:]


def _kpis(doc: dict) -> list[tuple[str, str, str | None]]:
    tot, out = doc.get("totals") or {}, []
    if q := _latest_full(doc):
        yoy = tot.get("yoy_pct")
        out.append(
            (
                _usd(q["capex"]),
                f"capex in {_qname(q['q'])}",
                f"▲ {yoy}%" if yoy is not None else None,
            )
        )
    if tot.get("backlog"):
        g = tot.get("backlog_growth_pct")
        out.append(
            (_usd(tot["backlog"]), "contracted backlog", f"▲ {g}%" if g is not None else None)
        )
    if tot.get("ttm_capex"):
        g = tot.get("ttm_yoy_pct")
        out.append(
            (
                _usd(tot["ttm_capex"]),
                "capex, last four quarters",
                f"▲ {g}%" if g is not None else None,
            )
        )
    return out


def _updated(doc: dict) -> str:
    d = date.fromisoformat(doc["as_of"])
    return f"{d:%b} {d.day}, {d.year}"


def draw(doc: dict, path: Path) -> Path:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.image as mpimg
    import matplotlib.pyplot as plt
    from matplotlib.patches import FancyBboxPatch

    from castelino.config import get_settings

    fig = plt.figure(figsize=(W / 100, H / 100), dpi=100, facecolor=BG)
    px = lambda x, y: (x / W, 1 - y / H)  # noqa: E731 - pixel coordinates from the top left
    logo = get_settings().root / "frontend" / "public" / "arc-logo.png"
    if logo.exists():
        fig.patches.append(FancyBboxPatch(px(56, 100), 62 / W, 56 / H, boxstyle="round,pad=0,rounding_size=0.012",
                                          transform=fig.transFigure, facecolor="white", edgecolor="none"))  # fmt: skip
        ax = fig.add_axes([*px(60, 97), 54 / W, 50 / H], zorder=3)  # above its white tile
        ax.imshow(mpimg.imread(logo))
        ax.axis("off")
    fig.text(*px(140, 58), "ARC RESEARCH · DASHBOARD", color=ACCENT, fontsize=12, fontweight="bold")
    fig.text(
        *px(140, 104),
        "AI Demand & Capex",
        color=TEXT,
        fontsize=31,
        fontweight="bold",
        family="serif",
    )
    renderer = fig.canvas.get_renderer()
    for i, (value, label, change) in enumerate(_kpis(doc)):
        y = 225 + i * 110
        fig.text(*px(56, y), value, color=TEXT, fontsize=38, fontweight="bold")
        t = fig.text(*px(56, y + 34), label, color=TEXT2, fontsize=14)
        if (
            change
        ):  # measured, so it never overlaps the label (Fly's DejaVu runs wider than Helvetica)
            right = t.get_window_extent(renderer).x1
            fig.text(
                right / W + 10 / W,
                1 - (y + 34) / H,
                change,
                color=UP,
                fontsize=14,
                fontweight="bold",
            )
    tot = chart_quarters(doc)
    if tot:
        ax = fig.add_axes([560 / W, 1 - 520 / H, 600 / W, 330 / H], facecolor=BG)
        labels = [q["q"] for q in tot]
        base = [0.0] * len(labels)
        for c in doc.get("companies") or []:
            if c["kind"] != "hyperscaler":
                continue
            by = {q["q"]: q.get("capex") or 0.0 for q in c["quarters"]}
            vals = [by.get(lab, 0.0) for lab in labels]
            ax.bar(range(len(labels)), vals, bottom=base, width=0.72, color=COLORS.get(c["ticker"], MUTED),
                   edgecolor=BG, linewidth=1.2, label=c["name"])  # fmt: skip
            base = [b + v for b, v in zip(base, vals, strict=True)]
        ax.text(len(labels) - 1, base[-1] * 1.03, f"{base[-1]:.0f}", ha="center", va="bottom",
                color=TEXT, fontsize=13, fontweight="bold")  # fmt: skip
        ax.set_xticks([i for i in range(len(labels)) if i % 3 == 0 or i == len(labels) - 1])
        ax.set_xticklabels(
            [f"Q{labels[i][5]} '{labels[i][2:4]}" for i in ax.get_xticks()],
            color=MUTED,
            fontsize=11,
        )
        ax.tick_params(axis="y", colors=MUTED, labelsize=11, length=0)
        ax.tick_params(axis="x", length=0)
        ax.grid(axis="y", color=GRID, linewidth=1.5)
        ax.set_axisbelow(True)
        for s in ax.spines.values():
            s.set_visible(False)
        ax.set_ylim(0, base[-1] * 1.18 if base[-1] else 1)
        fig.text(*px(560, 146), "Quarterly capex, $bn", color=TEXT2, fontsize=13, fontweight="bold")
        ax.legend(loc="lower left", frameon=False, fontsize=10, labelcolor=MUTED, ncol=5,
                  bbox_to_anchor=(-0.01, 1.01), handlelength=0.9, columnspacing=1.0)  # fmt: skip
    fig.add_artist(
        matplotlib.lines.Line2D([56 / W, 1 - 56 / W], [1 - 574 / H] * 2, color=RULE, linewidth=1.5)
    )
    fig.text(*px(56, 607), f"Hyperscalers and neoclouds: spending, funding, demand and compute · Updated {_updated(doc)}",
             color=MUTED, fontsize=12)  # fmt: skip
    fig.text(
        *px(W - 56, 607),
        "arcresearch.markets",
        color=ACCENT,
        fontsize=12,
        fontweight="bold",
        ha="right",
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=100, facecolor=BG)
    plt.close(fig)
    return path


def description(doc: dict) -> str:
    tot, parts = doc.get("totals") or {}, []
    if q := _latest_full(doc):
        s = f"Hyperscalers spent {_usd(q['capex'])} on capex in {_qname(q['q'])}"
        parts.append(
            s
            + (
                f", up {tot['yoy_pct']}% from a year ago."
                if tot.get("yoy_pct") is not None
                else "."
            )
        )
    if tot.get("backlog"):
        parts.append(f"Contracted backlog: {_usd(tot['backlog'])}.")
    parts.append(f"Updated {_updated(doc)}.")
    return " ".join(parts)


def og_page(index_html: str, doc: dict) -> str:
    """The built index.html with this dashboard's title and preview tags in place of the site's."""
    tags = {
        "og:title": "AI Demand & Capex · ARC Research",
        "og:description": description(doc),
        "og:image": f"{SITE}/api/dashboards/ai-capex/card-{doc['as_of']}.png",
        "og:url": f"{SITE}/dashboards/ai-capex",
        "og:type": "website",
    }
    out = re.sub(r"<title>.*?</title>", "", index_html, flags=re.S)
    out = re.sub(r'\s*<meta (property|name)="(og:[^"]+|twitter:[^"]+|description)"[^>]*>', "", out)
    head = [f"<title>{h.escape(tags['og:title'])}</title>",
            f'<meta name="description" content="{h.escape(tags["og:description"])}" />']  # fmt: skip
    head += [f'<meta property="{k}" content="{h.escape(v)}" />' for k, v in tags.items()]
    head += [
        '<meta name="twitter:card" content="summary_large_image" />',
        f'<meta name="twitter:image" content="{h.escape(tags["og:image"])}" />',
    ]
    return out.replace("</head>", "    " + "\n    ".join(head) + "\n  </head>", 1)


def write_og(static_dir: Path, snapshot: Path) -> Path | None:
    """Write <static>/dashboards/ai-capex.html; nothing without a snapshot."""
    if not snapshot.exists():
        return None
    doc = json.loads(snapshot.read_text())
    if not doc.get("as_of"):
        return None
    out = static_dir / "dashboards" / "ai-capex.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(og_page((static_dir / "index.html").read_text(), doc))
    return out
