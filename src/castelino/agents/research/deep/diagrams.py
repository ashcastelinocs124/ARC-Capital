"""Point diagrams: for a point understood best as a picture of how its ideas relate (a definition, the kinds
of something, a pipeline), not as a chart of its numbers. visuals.py decides which a point gets.

One call draws the diagrams of several points (DiagramSet). Code checks the box counts and that any figure
in the diagram is one of the point's cited facts' numbers, with one retry told what failed; a point that
still fails gets no diagram. The Research tab draws a diagram as SVG and render_png() draws it for the
Substack draft, both from the same data, so the model never draws anything itself.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

from castelino.agents.research.deep.models import DiagramDraft, DiagramSet, Fact, Point
from castelino.agents.trade import llm
from castelino.agents.update.guard import unsupported
from castelino.config import get_settings

BOXES = {"branches": (2, 4), "flow": (2, 5)}
LINES, CHARS = 4, 40  # per box: at most 4 lines of at most 40 characters

SYSTEM = f"""You draw diagrams for points of an ARC Research report, one per point you are given. A diagram
shows how a point's ideas relate, in the point's own words, so a reader grasps it at a glance.
- layout "branches": one idea split into its kinds or parts (root = the idea, 2 to 4 boxes, one per kind);
  layout "flow": steps in order, left to right (2 to 5 boxes, root and root_note empty).
- Each box: a title of 1 to 4 words; up to {LINES} lines of at most {CHARS} characters ("Changes: the
  model's parameters", "Needs: a training cycle"); note = one short bottom line (a cost, a catch) or "".
- title: the diagram's title, a short phrase with no figures. caption: one short line or "".
- Use only what the point and its facts say. A figure may appear only if it is in a cited fact, written
  as that fact gives it. Plain words, no dashes as punctuation."""


def _brief(points: list[Point], by: dict[str, Fact]) -> str:
    out = []
    for p in points:
        facts = "\n".join(f"  [{i}] {by[i].text}" for i in p.fact_ids if i in by)
        out.append(f"Point {p.id}: {p.headline}\n{p.body}\nCited facts:\n{facts}")
    return "\n\n".join(out)


def _texts(d: DiagramDraft) -> list[str]:
    return [d.title, d.root, d.root_note, d.caption] + [
        t for b in d.boxes for t in (b.title, b.note, *b.lines)
    ]


def diagram_errors(d: DiagramDraft, point: Point, by: dict[str, Fact]) -> list[str]:
    lo, hi = BOXES[d.layout]
    errs = [] if lo <= len(d.boxes) <= hi else [f"{point.id}: {d.layout} needs {lo} to {hi} boxes"]
    if d.layout == "branches" and not d.root.strip():
        errs.append(f"{point.id}: branches needs the root idea")
    for b in d.boxes:
        if len(b.lines) > LINES or any(len(t) > CHARS for t in b.lines):
            errs.append(
                f"{point.id}: box {b.title!r} has over {LINES} lines or a line over {CHARS} characters"
            )
    nums = {n for i in point.fact_ids if i in by for n in by[i].numbers}
    errs += [
        f"{point.id}: {f} is not in the point's cited facts" for f in unsupported(_texts(d), nums)
    ]
    return errs


def _ask(msgs: list[dict], meter: llm.Meter) -> DiagramSet:
    try:
        model = get_settings().deep_research.chart_model
        return llm.structured("research_diagrammer", model, msgs, DiagramSet, meter)
    except Exception:  # noqa: BLE001 - a visual is never load-bearing; the point goes without one
        return DiagramSet(diagrams=[])


def diagram_points(
    points: list[Point], by: dict[str, Fact], meter: llm.Meter
) -> dict[str, DiagramDraft]:
    """A diagram per point id; a point whose diagram fails twice is missing from the result."""
    if not points:
        return {}
    msgs = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": _brief(points, by)}]
    done: dict[str, DiagramDraft] = {}
    for attempt in range(2):
        out, errs = _ask(msgs, meter), []
        for p in points:
            if p.id in done:
                continue
            d = next((x for x in out.diagrams if x.point_id == p.id), None)
            e = diagram_errors(d, p, by) if d else [f"{p.id}: no diagram returned"]
            if e:
                errs += e
            else:
                done[p.id] = d
        if not errs or attempt:
            break
        msgs += [
            {"role": "assistant", "content": out.model_dump_json()},
            {
                "role": "user",
                "content": "Fix only these diagrams and return them:\n" + "\n".join(errs),
            },
        ]
    return done


GREEN, GREEN_SOFT = "#047857", "#E6F4EC"
AMBER, AMBER_SOFT = "#B45309", "#FEF3C7"
SLATE, SLATE_SOFT = "#475569", "#F1F5F9"
TONES = [(GREEN, GREEN_SOFT), (AMBER, AMBER_SOFT), (SLATE, SLATE_SOFT), ("#1D4ED8", "#DBEAFE")]


AX_W, AX_H = 0.82 * 6.4 * 72, 0.63 * 3.9 * 72  # the frame's plot area in points (_frame, left=0.06)
# average glyph width per point of font size: Fly draws in DejaVu Sans, wider than the Mac's Helvetica,
# so the PNG is sized for DejaVu (bold wider still) or a long line runs out of its box on Substack
CHAR, BOLD = 0.6, 0.66


def _wrap(text: str, width_pt: float, size: float, k: float) -> str:
    return textwrap.fill(text, max(8, int(width_pt / (size * k))), break_on_hyphens=False)


def _lines(text: str) -> int:
    return text.count("\n") + 1 if text else 0


def _fit(b, w: float, room: float) -> tuple[float, str, str, str]:
    """(font size, wrapped title, body and note) so a box's text fits its width and height."""
    inner = w * AX_W - 16
    for size in (8.2, 7.8, 7.4, 7.0, 6.6, 6.2):
        title = _wrap(b.title, inner, size + 1.2, BOLD)
        body = "\n".join(_wrap(t, inner, size, CHAR) for t in b.lines)
        note = _wrap(b.note, inner, size, BOLD) if b.note else ""
        need = (
            _lines(title) * (size + 1.6) * 1.3
            + (_lines(body) + _lines(note)) * size * 1.35
            + size * 2
        )
        if need <= room * AX_H:
            break
    return size, title, body, note


def render_png(n: int, d: DiagramDraft, data: str, path: Path) -> None:
    """The diagram in the house frame (Exhibit n, title, Source line, logo), for the Substack draft."""
    from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

    from castelino.agents.update.charts import INK, INK2
    from castelino.agents.weekly.charts import _frame

    def box(ax, x, y, w, h, b, edge, fill):
        size, title, body, note = _fit(b, w, h - 0.06)
        ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0,rounding_size=0.02",
                                    fc=fill, ec=edge, lw=1.3))  # fmt: skip
        ax.text(x + w / 2, y + h - 0.04, title, ha="center", va="top", fontsize=size + 1.2,
                fontweight="bold", color=edge, linespacing=1.15)  # fmt: skip
        top = y + h - 0.06 - (title.count("\n") + 1) * (size + 1.6) * 1.3 / AX_H - 0.03
        ax.text(
            x + 0.018, top, body, ha="left", va="top", fontsize=size, color=INK, linespacing=1.35
        )
        if note:
            ax.text(x + 0.018, y + 0.025, note, ha="left", va="bottom", fontsize=size,
                    fontweight="bold", color=edge, linespacing=1.3)  # fmt: skip

    def draw(ax):
        ax.set_xlim(-0.006, 1.006)
        ax.set_ylim(0, 1)
        ax.axis("off")
        k = len(d.boxes)
        if d.layout == "branches":
            gap = 0.025
            w = (1 - gap * (k - 1)) / k
            ax.add_patch(FancyBboxPatch((0.35, 0.84), 0.3, 0.15, boxstyle="round,pad=0,rounding_size=0.025",
                                        fc=INK, ec=INK))  # fmt: skip
            ax.text(
                0.5,
                0.94 if d.root_note else 0.915,  # centred in its box when it has no sub-line
                d.root,
                ha="center",
                va="center",
                color="white",
                fontsize=10.5,
                fontweight="bold",
            )
            if d.root_note:
                ax.text(
                    0.5, 0.875, d.root_note, ha="center", va="center", color="#CBD5E1", fontsize=7.5
                )
            xs = [i * (w + gap) for i in range(k)]
            ax.plot([0.5, 0.5], [0.84, 0.8], color=INK2, lw=1.2)
            ax.plot([xs[0] + w / 2, xs[-1] + w / 2], [0.8, 0.8], color=INK2, lw=1.2)
            for i, b in enumerate(d.boxes):
                ax.plot([xs[i] + w / 2] * 2, [0.8, 0.76], color=INK2, lw=1.2)
                edge, fill = TONES[i % len(TONES)]
                box(ax, xs[i], 0.0, w, 0.76, b, edge, fill)
        else:
            gap = 0.055
            w = (1 - gap * (k - 1)) / k
            for i, b in enumerate(d.boxes):
                x = i * (w + gap)
                edge, fill = TONES[0] if i < k - 1 else TONES[2]
                box(ax, x, 0.24, w, 0.62, b, edge, fill)
                if i < k - 1:
                    ax.add_patch(FancyArrowPatch((x + w + 0.006, 0.55), (x + w + gap - 0.006, 0.55),
                                                 arrowstyle="-|>", mutation_scale=13, color=INK2, lw=1.6))  # fmt: skip
            if d.caption:
                ax.text(0, 0.08, d.caption, fontsize=8, color=INK2)

    _frame(n, d.title, "Diagram from the point's cited sources", data, path, draw, left=0.06,
           bottom=0.13, kicker="DEEP RESEARCH")  # fmt: skip
