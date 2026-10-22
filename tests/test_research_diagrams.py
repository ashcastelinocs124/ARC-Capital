from castelino.agents.research.deep import charts, diagrams, visuals
from castelino.agents.research.deep.models import DiagramBox, DiagramDraft, Point, PointChart
from castelino.agents.trade import llm
from castelino.agents.update.models import Fact

FACT = Fact(id="A1", text="About half of answers stayed stale (50%) in StaleBench", numbers=[50.0],
            provenance="reported", source_title="arXiv", source_url="https://arxiv.org/x")  # fmt: skip
BY = {"A1": FACT}


def point(pid: str) -> Point:
    return Point(id=pid, agent="A", headline=f"{pid} headline", body="body", fact_ids=["A1"])


def branches(pid="p1", stale="about half stay stale (50%)", k=3) -> DiagramDraft:
    boxes = [DiagramBox(title="Weight update", lines=["Changes: the model's parameters"], note="Cost up front"),
             DiagramBox(title="Retrieval refresh", lines=[f"Catch: {stale}"], note=""),
             DiagramBox(title="Test-time learning", lines=["Changes: memory and context"], note=""),
             DiagramBox(title="Editing", lines=["A narrow weight update"], note="")][:k]  # fmt: skip
    return DiagramDraft(point_id=pid, layout="branches", title="Three kinds of update",
                        root="Continual learning", root_note="keeping a model current", boxes=boxes, caption="")  # fmt: skip


def test_the_analysts_words_pick_the_visual_and_a_plain_visual_leaves_it_to_the_decision():
    assert visuals.wanted("a point at the start, with a diagram") == "diagram"
    assert visuals.wanted("chart the GPU spend") == "chart"
    assert visuals.wanted("explain it, with a visual") is None


def test_a_diagram_keeps_its_box_counts_and_only_cited_figures():
    assert diagrams.diagram_errors(branches(), point("p1"), BY) == []
    assert (
        "branches needs 2 to 4 boxes" in diagrams.diagram_errors(branches(k=1), point("p1"), BY)[0]
    )
    bad = diagrams.diagram_errors(branches(stale="60% stay stale"), point("p1"), BY)
    assert bad == ["p1: 60% is not in the point's cited facts"]


def test_visualize_gives_each_point_a_diagram_or_a_chart(monkeypatch):
    calls = []
    monkeypatch.setattr(visuals, "_picks_diagram", lambda p, m: calls.append(p.id) or p.id == "p1")
    monkeypatch.setattr(
        diagrams, "diagram_points", lambda pts, by, m: {p.id: branches(p.id) for p in pts}
    )
    chart = PointChart(form="bars", title="t", values=[])
    monkeypatch.setattr(charts, "chart_points", lambda pts, by, m: {p.id: chart for p in pts})

    out = visuals.visualize([point("p1"), point("p2")], BY, llm.Meter())
    assert [(p.id, bool(p.diagram), bool(p.chart)) for p in out] == [
        ("p1", True, False),
        ("p2", False, True),
    ]
    assert sorted(calls) == ["p1", "p2"]  # one decision per point

    calls.clear()  # the analyst said "diagram": no decision is asked
    out = visuals.visualize([point("p1"), point("p2")], BY, llm.Meter(), ask="add a diagram")
    assert all(p.diagram and not p.chart for p in out) and calls == []

    monkeypatch.setattr(
        diagrams, "diagram_points", lambda pts, by, m: {}
    )  # the diagram failed twice
    out = visuals.visualize([point("p1")], BY, llm.Meter(), ask="add a diagram")
    assert out[0].chart and not out[0].diagram  # falls back to a chart


def test_both_layouts_draw_a_png(tmp_path):
    flow = DiagramDraft(point_id="p1", layout="flow", title="The weight-update pipeline", root="", root_note="",
                        boxes=[DiagramBox(title=t, lines=["Needs: GPUs"], note="") for t in
                               ("Continual pre-training", "Fine-tuning", "Alignment", "Serving")],
                        caption="Each step needs a training cycle.")  # fmt: skip
    for name, d in (("b.png", branches()), ("f.png", flow)):
        diagrams.render_png(1, d, "arxiv.org", tmp_path / name)
        assert (tmp_path / name).stat().st_size > 10_000


def test_a_long_note_wraps_and_every_box_line_fits_its_width_in_flys_font():
    b = DiagramBox(title="Guard each update", lines=["Evaluate and guard before deployment"] * 3,
                   note="Repeated edits can degrade capabilities over time")  # fmt: skip
    w = (1 - 0.025 * 3) / 4  # one of four branches
    size, title, body, note = diagrams._fit(b, w, 0.7)
    assert "\n" in note  # the note no longer runs into the next box (Substack PNG, 2026-10-21)
    inner = w * diagrams.AX_W - 16
    for text, k, s in (
        (title, diagrams.BOLD, size + 1.2),
        (body, diagrams.CHAR, size),
        (note, diagrams.BOLD, size),
    ):
        assert max(len(line) for line in text.split("\n")) * s * k <= inner
