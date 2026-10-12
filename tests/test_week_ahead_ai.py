from datetime import UTC, date, datetime

from castelino.week_ahead import ai


def ts(y, m, d):
    return int(datetime(y, m, d, 12, tzinfo=UTC).timestamp())


MODELS = {
    "data": [
        {
            "id": "anthropic/claude-haiku-5.5",
            "canonical_slug": "anthropic/claude-haiku-5.5-20261008",
            "name": "Anthropic: Claude Haiku 5.5",
            "created": ts(2026, 10, 8),
        },
        {
            "id": "anthropic/claude-haiku-5.5:batch",
            "canonical_slug": "anthropic/claude-haiku-5.5-20261008",
            "name": "Anthropic: Claude Haiku 5.5 (batch)",
            "created": ts(2026, 10, 8),
        },
        {"id": "foo/bar:free", "name": "Foo: Bar (free)", "created": ts(2026, 10, 9)},
        {
            "id": "mistralai/mistral-large-4",
            "name": "Mistral: Mistral Large 4",
            "created": ts(2026, 10, 14),
        },
        {"id": "old/model", "name": "Old: Model", "created": ts(2026, 9, 1)},
        {"id": "x-ai/nameless", "name": "Nameless", "created": ts(2026, 10, 13)},
    ]
}


def test_launched_window_and_dedupe():
    evs = ai.launched(date(2026, 10, 12), date(2026, 10, 16), get_json=lambda url: MODELS)
    assert [(e["name"], e["lab"], e["date"]) for e in evs] == [
        ("Claude Haiku 5.5", "Anthropic", "2026-10-08"),
        ("Nameless", "x-ai", "2026-10-13"),
        ("Mistral Large 4", "Mistral", "2026-10-14"),
    ]
    assert evs[0]["status"] == "launched"
    assert evs[0]["source_url"] == "https://openrouter.ai/anthropic/claude-haiku-5.5"


def test_reported_keeps_only_cited_well_formed_lines():
    text = (
        "Google | Gemini 4 Pro | 2026-10-15\n"
        "Some Lab | Rumoured Model | late October\n"
        "not a release line\n"
        "OpenAI | GPT-7 | November ([theinformation.com](https://theinformation.com/x))\n"
    )
    a = text.index("Google")
    c = text.index("OpenAI")
    cites = [
        ("Google blog", "https://blog.google/g4", a, a + 10),
        ("The Information", "https://theinformation.com/x", c, c + 10),
    ]
    evs = ai.reported(date(2026, 10, 12), search=lambda s, u: (text, cites))
    assert [(e["lab"], e["name"], e["when"], e["date"]) for e in evs] == [
        ("Google", "Gemini 4 Pro", "2026-10-15", "2026-10-15"),
        ("OpenAI", "GPT-7", "November", None),
    ]
    assert evs[0]["status"] == "reported" and evs[0]["source_url"] == "https://blog.google/g4"


def test_reported_none():
    assert ai.reported(date(2026, 10, 12), search=lambda s, u: ("NONE", [])) == []
