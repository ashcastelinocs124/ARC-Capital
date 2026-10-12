from datetime import date, datetime
from zoneinfo import ZoneInfo

from castelino.ai_sentiment import xapi

NY = ZoneInfo("America/New_York")
FAMILIES = {"Anthropic": ["claude", "claude code"], "Google": ["gemini", "nano banana"]}


def test_queries_cover_every_handle_and_stay_under_the_limit():
    handles = [f"handle_number_{i:02d}" for i in range(40)]
    qs = xapi.build_queries(handles, FAMILIES)
    assert all(len(q) <= xapi.MAX_QUERY for q in qs) and len(qs) > 1
    joined = " ".join(qs)
    assert all(f"from:{h}" in joined for h in handles)
    assert '"claude code"' in qs[0] and "-is:retweet" in qs[0]


def test_window_is_the_ny_day_clamped_before_now():
    now = datetime(2026, 10, 12, 17, 0, tzinfo=NY)
    start, end = xapi.window(date(2026, 10, 12), now)
    assert start == "2026-10-12T04:00:00Z" and end == "2026-10-12T20:59:30Z"
    assert xapi.window(date(2026, 10, 11), now)[1] == "2026-10-12T04:00:00Z"


def test_search_paginates_maps_authors_and_prefers_long_text():
    pages = [
        {
            "data": [
                {
                    "id": "1",
                    "author_id": "u1",
                    "text": "short…",
                    "note_tweet": {"text": "Claude is fast, long version"},
                },
                {"id": "2", "author_id": "u2", "text": "Gemini is slow"},
            ],
            "includes": {
                "users": [{"id": "u1", "username": "Dev_A"}, {"id": "u2", "username": "indie"}]
            },
            "meta": {"next_token": "abc"},
        },
        {
            "data": [{"id": "3", "author_id": "u1", "text": "Claude again"}],
            "includes": {"users": [{"id": "u1", "username": "Dev_A"}]},
            "meta": {},
        },
    ]
    seen = []

    def get(params):
        seen.append(params)
        return pages[len(seen) - 1]

    posts = xapi.search("q", "s", "e", get=get)
    assert [p["url"] for p in posts] == [
        "https://x.com/dev_a/status/1",
        "https://x.com/indie/status/2",
        "https://x.com/dev_a/status/3",
    ]
    assert posts[0]["text"] == "Claude is fast, long version" and posts[0]["author"] == "dev_a"
    assert seen[1]["next_token"] == "abc" and seen[0]["max_results"] == 100


def test_search_stops_at_the_cap():
    def get(params):
        return {
            "data": [{"id": str(i), "author_id": "u", "text": "x"} for i in range(100)],
            "includes": {"users": [{"id": "u", "username": "a"}]},
            "meta": {"next_token": "more"},
        }

    assert (
        len(xapi.search("q", "s", "e", get=get, cap=250)) == 300
    )  # stops after the page that crosses it


def test_empty_result():
    assert xapi.search("q", "s", "e", get=lambda p: {"meta": {"result_count": 0}}) == []
