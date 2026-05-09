"""Unit tests for TudorJonesScraper — mocks _fetch_transcript."""
import asyncio

import castelino.agents.personas.scrapers.tudor_jones as mod
from castelino.agents.personas.scrapers.tudor_jones import (
    KNOWN_INTERVIEWS,
    TudorJonesScraper,
)


def test_tudor_jones_persona_id():
    assert TudorJonesScraper.persona_id == "tudor_jones"


def test_known_interviews_has_at_least_two_entries():
    assert len(KNOWN_INTERVIEWS) >= 2


def test_known_interviews_have_required_fields():
    for iv in KNOWN_INTERVIEWS:
        assert iv.video_id
        assert iv.title
        assert iv.venue
        assert iv.date.tzinfo is not None  # timezone-aware


def test_builds_doc_per_interview(monkeypatch):
    """Each interview with a non-empty transcript becomes one CorpusDoc."""
    scraper = TudorJonesScraper()
    canned_segments = [{"text": "We see a macro regime shift. " * 15}]
    monkeypatch.setattr(scraper, "_fetch_transcript", lambda vid: canned_segments)
    monkeypatch.setattr(mod, "fetch_persona_via_sonar", lambda **kw: [])

    docs = asyncio.run(scraper.fetch())
    assert len(docs) == len(scraper._known_interviews())
    d = docs[0]
    assert d.url.startswith("https://www.youtube.com/watch?v=")
    assert len(d.text) >= 50
    assert "tudor_jones_" in d.source


def test_skips_interviews_with_empty_transcript(monkeypatch):
    scraper = TudorJonesScraper()
    monkeypatch.setattr(scraper, "_fetch_transcript", lambda vid: [])
    monkeypatch.setattr(mod, "fetch_persona_via_sonar", lambda **kw: [])

    docs = asyncio.run(scraper.fetch())
    assert docs == []


def test_transcript_exception_skips_interview(monkeypatch):
    """If _fetch_transcript raises (e.g. transcript disabled), that interview is skipped."""
    scraper = TudorJonesScraper()
    monkeypatch.setattr(scraper, "_fetch_transcript",
                        lambda vid: (_ for _ in ()).throw(RuntimeError("no transcript")))
    monkeypatch.setattr(mod, "fetch_persona_via_sonar", lambda **kw: [])

    docs = asyncio.run(scraper.fetch())
    assert docs == []


def test_sonar_fallback_fires_when_below_threshold(monkeypatch):
    from castelino.agents.personas.corpus import CorpusDoc
    from datetime import UTC, datetime

    scraper = TudorJonesScraper()
    monkeypatch.setattr(scraper, "_fetch_transcript", lambda vid: [])

    fake_sonar_doc = CorpusDoc(
        source="sonar_tudor_jones",
        date=datetime.now(UTC),
        title="Sonar result",
        text="PTJ sonar summary. " * 10,
        url="https://sonar.example.com",
    )
    monkeypatch.setattr(mod, "fetch_persona_via_sonar", lambda **kw: [fake_sonar_doc])

    docs = asyncio.run(scraper.fetch())
    assert len(docs) == 1
    assert docs[0].source == "sonar_tudor_jones"
