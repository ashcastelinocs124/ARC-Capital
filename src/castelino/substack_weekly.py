"""Push a Weekly Deep Dive to Substack as a draft: the full report, every page and exhibit.

Run: `uv run python -m castelino.substack_weekly [YYYY-Www]` (default: the newest week)."""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import httpx
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from castelino import cover  # noqa: E402
from castelino.config import get_settings  # noqa: E402
from castelino.substack import (  # noqa: E402
    SITE,
    CookieExpiredError,
    _bold,
    _heading,
    _image,
    _p,
    _text,
    push,
    series_title,
)

INK = "#0F172A"


def table_png(header: list[str], rows: list[list[str]], path: Path, title: str) -> Path:
    """Substack's editor has no table block: render a table as an image."""
    if not rows:  # every source down: matplotlib can't draw an empty table
        rows = [["No data this week", *([""] * (len(header) - 1))]]
    fig, ax = plt.subplots(figsize=(7.2, 0.5 + 0.32 * (len(rows) + 1)))
    ax.axis("off")
    fig.text(0.02, 0.97, title, fontsize=11, fontweight="bold", color=INK, va="top")
    t = ax.table(cellText=rows, colLabels=header, loc="center", cellLoc="right", colLoc="right")
    t.auto_set_font_size(False)
    t.set_fontsize(9)
    for (r, c), cell in t.get_celld().items():
        cell.set_edgecolor("#e5e5e7")
        if r == 0:
            cell.set_facecolor("#1f2937")
            cell.get_text().set_color("white")
        if c == 0:
            cell.get_text().set_ha("left")
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=200, bbox_inches="tight")
    plt.close(fig)
    return path


def _fmt(v, unit: str) -> str:
    if v is None:
        return "–"
    return f"{v:+.0f}bp" if unit == "bp" else f"{v:+.1f}%"


def _level(r: dict) -> str:
    if r["unit"] == "%":
        return f"{r['level']:.2f}%"
    if r["unit"] == "$":
        return f"${r['level']:,.2f}"
    return f"{r['level']:,.2f}"


def scorecard_rows(rec: dict) -> list[list[str]]:
    return [
        [r["asset"], _level(r), *(_fmt(r[k], r["change_unit"]) for k in ("w1", "m1", "m3", "ytd"))]
        for r in rec.get("scorecard", [])
    ]


PARTS = [  # each trend: the high level from our notes, then the desk's deep research
    ("what_happened", "What happened"),
    ("why", "Why it happened"),
    ("under_the_surface", "Under the surface"),
    ("market_impact", "What it means for markets"),
    ("watch", "What to watch"),
]

COUNT_LABELS = [
    ("notes", "Daily Updates read"),
    ("agents", "Specialist agents"),
    ("data_pulls", "Data pulls"),
    ("board_posts", "Board posts shared"),
    ("grill_rounds", "Grill rounds"),
    ("figures_checked", "Figures checked"),
    ("exhibits", "Exhibits"),
]


def _bullets(items: list[list[dict]]) -> dict:
    return {
        "type": "bullet_list",
        "content": [{"type": "list_item", "content": [_p(*i)]} for i in items],
    }


def build_weekly_doc(record: dict, uploaded: dict[str, dict]) -> dict:
    rep, week = record["report"], record["week"]
    url = f"{SITE}/deep-research?week={week}"
    c: list[dict] = [_heading("The week at a glance", 2)]
    c.append(_bullets([[_bold(b["lead"] + " "), _text(b["body"])] for b in rep["bullets"]]))
    c.append(_p(_bold("What to watch: "), _text(rep["watch"])))
    reg = record.get("regime") or {}
    if reg.get("pulse") is not None:
        read = f"Pulse P(expansion) {reg['pulse']:.0f}% · Pressure P(CPI accelerates) {reg['pressure']:.0f}%"
        c.append(_p(_bold("ARC regime read: "), _text(read)))
    agents = record.get("plan", {}).get("agents", [])
    desks = "; ".join(
        f"{a['name']} ({', '.join(a['trends']) if a.get('trends') else a['description']})"
        for a in agents
    )
    c.append(_p(_bold("Research desk: "), _text(desks)))
    for name in ("scorecard.png", "counts.png"):
        if name in uploaded:
            c.append(_image(uploaded[name], name.removesuffix(".png")))
    by_section: dict[int, list[dict]] = {}
    for ex in record.get("exhibits", []):
        by_section.setdefault(ex["section"], []).append(ex)
    for i, s in enumerate(rep["sections"]):
        c.append(_heading(f"{i + 1}. {s['title']}", 2))
        c.append(_p(_text(s["agent"].upper())))
        if "what_happened" not in s:  # reports written before the two-tier sections
            c += [_p(_text(t)) for t in s.get("paragraphs", [])]
        for key, heading in PARTS:
            if s.get(key):
                c.append(_heading(heading, 4))
                c += [_p(_text(t)) for t in s[key]]
        for ch in s["challenges"]:
            said = f"“{ch['question']}” {ch['answer']} "
            c.append(_p(_bold("Editor challenged: "), _text(said), _bold(ch["verdict"])))
        for ex in by_section.get(i, []):
            if ex["file"] in uploaded:
                c.append(_image(uploaded[ex["file"]], ex["title"]))
    c.append(_heading("Method and sources", 2))
    c.append(
        _p(
            _text(
                "A Lead agent read the week's Daily Updates and staffed specialist desks that "
                "pulled their own data; an editor (Claude Opus 5.5) challenged every finding "
                "before writing. Every figure is checked against the cited data."
            )
        )
    )
    cited = {i for s in rep["sections"] for i in s["fact_ids"]}
    cited |= {i for b in rep["bullets"] for i in b["fact_ids"]}
    seen: dict[str, str] = {}
    for f in record.get("facts", []):
        if f["id"] in cited:
            seen.setdefault(f["source_url"], f["source_title"])
    if seen:
        c.append(_bullets([[_text(t, u)] for u, t in seen.items()]))
    c.append(
        _p(
            _text("Interactive version with every source: "),
            _text(url.removeprefix("https://"), url),
        )
    )
    c.append(_p(_text("Not investment advice.")))
    return {"type": "doc", "content": c}


def push_weekly_draft(week: str | None = None) -> str:
    cfg = get_settings()
    deep = cfg.root / cfg.deep_dive.data_dir
    weeks = sorted((p.stem for p in deep.glob("????-W??.json")), reverse=True)
    week = week or (weeks[0] if weeks else None)
    if not week or not (deep / f"{week}.json").exists():
        return f"skipped: no Weekly Deep Dive for {week or 'any week'}"
    record, marker = deep / f"{week}.json", deep / "substack" / f"{week}.json"
    # Re-pushing an unchanged report would overwrite edits made by hand in the Substack editor.
    if marker.exists() and marker.stat().st_mtime >= record.stat().st_mtime:
        return f"skipped: draft already up to date for {week} (report unchanged since)"
    rec = json.loads(record.read_text())
    charts = deep / "charts" / week
    head = ["Asset", "Level", "1w", "1m", "3m", "YTD"]
    table_png(head, scorecard_rows(rec), charts / "scorecard.png", "The week in markets")
    counts = rec.get("counts", {})
    rows = [[label, str(counts.get(k, 0))] for k, label in COUNT_LABELS]
    table_png(["Item", "Count"], rows, charts / "counts.png", "How this report was made")
    pngs = {"scorecard.png": charts / "scorecard.png", "counts.png": charts / "counts.png"}
    pngs |= {ex["file"]: charts / ex["file"] for ex in rec.get("exhibits", [])}
    start, end = date.fromisoformat(rec["start"]), date.fromisoformat(rec["end"])
    return push(
        marker=deep / "substack" / f"{week}.json",
        title=series_title("Weekly Deep Dive", rec["report"]["title"]),
        subtitle=f"ARC Weekly Deep Dive · {start:%b %-d}–{end:%b %-d, %Y}",
        pngs=pngs,
        body=lambda up: build_weekly_doc(rec, up),
        label=week,
        cover=lambda: cover.for_week(week),
    )


if __name__ == "__main__":
    try:
        print("substack weekly:", push_weekly_draft(sys.argv[1] if len(sys.argv) > 1 else None))
    except (CookieExpiredError, httpx.HTTPError) as e:
        print("substack weekly: FAILED:", e, file=sys.stderr)
        sys.exit(1)
