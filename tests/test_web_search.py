"""data/web_search.py: Responses API call -> (text, deduped url citations)."""

from types import SimpleNamespace as Ns

import openai

from castelino.data import web_search


def test_search_returns_text_and_deduped_citations(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    calls = {}

    def ann(url, title):
        return Ns(type="url_citation", url=url, title=title)

    resp = Ns(
        output_text=" CPI rose 3.1%. ",
        output=[
            Ns(type="web_search_call"),  # no content
            Ns(
                type="message",
                content=[
                    Ns(annotations=[ann("https://bls.gov", "BLS"), ann("https://bls.gov", "BLS")]),
                    Ns(annotations=[ann("https://fred.org", None), Ns(type="file_citation")]),
                ],
            ),
        ],
    )

    class FakeOpenAI:
        def __init__(self, **kw):
            self.responses = Ns(create=lambda **kw: calls.update(kw) or resp)

    monkeypatch.setattr(openai, "OpenAI", FakeOpenAI)

    text, sources = web_search.search("sys", "what is CPI")

    assert text == "CPI rose 3.1%."
    assert sources == [("BLS", "https://bls.gov"), ("https://fred.org", "https://fred.org")]
    assert calls["tools"] == [{"type": "web_search"}] and calls["instructions"] == "sys"


def test_has_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert not web_search.has_key()
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    assert web_search.has_key()
