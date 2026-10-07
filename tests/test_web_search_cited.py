from types import SimpleNamespace as Ns

import openai

from castelino.data import web_search


def fake_openai(text, anns):
    class Fake:
        def __init__(self, **kw):
            self.responses = Ns(
                create=lambda **k: Ns(
                    output_text=text,
                    output=[
                        Ns(content=[Ns(annotations=[Ns(type="url_citation", **a) for a in anns])])
                    ],
                )
            )

    return Fake


def test_search_cited_keeps_positions_and_search_dedupes(monkeypatch):
    anns = [
        dict(url="https://a", title="A", start_index=5, end_index=9),
        dict(url="https://a", title="A", start_index=20, end_index=24),
    ]
    monkeypatch.setattr(openai, "OpenAI", fake_openai("  hello world ", anns))
    text, cites = web_search.search_cited("s", "u", model="gpt-6-luna")
    assert text == "  hello world "
    assert cites == [("A", "https://a", 5, 9), ("A", "https://a", 20, 24)]
    assert web_search.search("s", "u") == ("hello world", [("A", "https://a")])
