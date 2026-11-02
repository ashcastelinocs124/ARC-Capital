import json

import pytest

from castelino import substack
from castelino.agents.trade import publish, store
from castelino.agents.trade.models import ChartOption, ChartSpec, StepError
from tests.test_trade_editor import idea as base_idea
from tests.test_trade_editor import report


@pytest.fixture
def an_idea(monkeypatch, tmp_path):
    monkeypatch.setenv("ARC_TRADE_DIR", str(tmp_path / "trades"))
    monkeypatch.setenv("SUBSTACK_PUBLICATION_URL", "https://pub.example")
    monkeypatch.setattr(publish, "_set_section", lambda draft_id: None)
    monkeypatch.setattr(publish, "_get", lambda draft_id: {"draft_body": "{}"})
    i = base_idea().model_copy(update={"report": report()})
    spec = ChartSpec(
        section="intro",
        form="quadrant",
        series=["yahoo:SMH", "yahoo:INDA", "yahoo:EWZ"],
        window_days=365,
        threshold=None,
        title="Where India sits",
        why="w",
        agent_pick=True,
    )
    opt = ChartOption(id="intro-1-1", spec=spec, file="intro-1-1.png", chosen=True)
    i.current().options.append(opt)
    store.charts_dir(i.id).mkdir(parents=True, exist_ok=True)
    store.save(i)
    return i


def test_doc_order_intro_takeaways_cover_sections_watch_sources(an_idea):
    up = {
        "intro-1-1.png": {"url": "https://img/cover"},
        "bear-1-1.png": {"url": "https://img/bear"},
    }
    d = publish.doc(an_idea, up)
    kinds = [n["type"] for n in d["content"]]
    assert kinds[:2] == ["paragraph", "paragraph"]  # the introduction comes first
    assert kinds[2:5] == ["heading", "bullet_list", "captionedImage"]  # takeaways, then the cover
    text = json.dumps(d)
    assert "What to watch:" in text and "Not investment advice." in text
    assert text.index("https://img/cover") < text.index("https://img/bear")


def test_the_draft_uses_the_editors_headings_not_internal_labels(an_idea):
    """Substack readers saw "1. The bull case" / "2. The bear case": labels for us, not for them
    (user feedback, 2026-10-16). The editor writes a heading that says what the section finds."""
    secs = [
        s.model_copy(update={"heading": "India keeps lagging emerging markets"})
        if s.key == "bear"
        else s
        for s in an_idea.report.sections
    ]
    an_idea.report = an_idea.report.model_copy(update={"sections": secs})
    heads = [
        n["content"][0]["text"]
        for n in publish.doc(an_idea, {})["content"]
        if n["type"] == "heading"
    ]
    assert "India keeps lagging emerging markets" in heads
    assert not any("bull case" in h or "bear case" in h for h in heads)


def test_push_returns_the_draft_link(an_idea, monkeypatch):
    def fake_push(*, marker, title, subtitle, pngs, body, label):
        assert title == f"Special Topic #5 | {an_idea.report.title}"
        assert subtitle.startswith("ARC Special Topics · India ·") and "intro-1-1.png" in pngs
        marker.write_text(json.dumps({"draft_id": 42}))
        return "created draft 42"

    monkeypatch.setattr(substack, "push", fake_push)
    monkeypatch.setattr(substack, "next_number", lambda series: 5)
    assert publish.push(an_idea) == {
        "draft_id": 42,
        "url": "https://pub.example/publish/post/42",
        "sha": publish.sha(None),  # of the text read back, so a later hand edit shows
    }


def test_publish_published_draft_fails_clearly(an_idea, monkeypatch):
    def published(**kw):
        return "skipped: Trade Lab i1 is already published on Substack (draft 42)"

    monkeypatch.setattr(substack, "push", published)
    monkeypatch.setattr(substack, "next_number", lambda series: 5)
    with pytest.raises(StepError, match="already published"):
        publish.push(an_idea)


def test_current_text_reads_the_drafts_paragraphs(an_idea):
    body = {
        "type": "doc",
        "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": "My edit."}]},
            {"type": "heading", "content": [{"type": "text", "text": "The bear case"}]},
        ],
    }
    i = an_idea.model_copy(update={"substack": {"draft_id": 42, "url": "u"}})
    got = publish.current_text(i, get=lambda draft_id: {"draft_body": json.dumps(body)})
    assert got == "My edit.\n\nThe bear case"
