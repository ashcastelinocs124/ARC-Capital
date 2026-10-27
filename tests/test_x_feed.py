import json

from castelino import x_post
from castelino.dashboard.endpoints import x_feed

REPLY = {
    "data": [
        {
            "id": "2112639309052334156",
            "created_at": "2026-10-20T20:15:03.000Z",
            "text": "📊 MACRO · Starts fell &amp; permits too https://t.co/pic1 via https://t.co/lnk",
            "attachments": {"media_keys": ["3_1"]},
            "entities": {
                "urls": [
                    {"url": "https://t.co/pic1", "media_key": "3_1"},
                    {"url": "https://t.co/lnk", "display_url": "aba.com/news"},
                ]
            },
        },
        {"id": "javascript:alert(1)", "text": "bad id"},
        {"id": "8", "text": "the X Scout reply", "in_reply_to_user_id": "1702425364474044416"},
        {"id": "7", "text": "hand-typed", "attachments": {"media_keys": ["3_2"]}},
    ],
    "includes": {
        "media": [
            {"media_key": "3_1", "type": "photo", "url": "https://pbs.twimg.com/media/a.png"},
            {"media_key": "3_2", "type": "photo", "url": "https://evil.example/a.png"},
        ]
    },
}


def test_parse_keeps_the_text_the_photo_and_a_safe_link():
    a, b = x_feed.parse(REPLY)
    assert a["text"] == "MACRO · Starts fell & permits too via aba.com/news"
    assert a["image"] == "https://pbs.twimg.com/media/a.png"
    assert a["url"] == "https://x.com/AshleynCas46131/status/2112639309052334156"
    assert (b["id"], b["image"]) == ("7", None)  # an image off X's CDN is never rendered


class Reply:
    def __init__(self, body):
        self.body = body

    def raise_for_status(self):
        pass

    def json(self):
        return self.body


def test_refresh_asks_only_for_newer_posts_and_not_twice_in_ten_minutes(tmp_path, monkeypatch):
    monkeypatch.setattr(x_feed, "_path", lambda: tmp_path / "x_feed.json")
    for k in x_post.KEYS:
        monkeypatch.setenv(k, "k")
    asked = []

    def get(url, params, headers, timeout):
        asked.append(params)
        n = len(asked)
        return Reply({"data": [{"id": str(100 + n), "text": f"post {n}"}]})

    assert [p["id"] for p in x_feed.refresh(now=1000, get=get)] == ["101"]
    assert "since_id" not in asked[0] and asked[0]["exclude"] == "replies,retweets"
    assert [p["id"] for p in x_feed.refresh(now=1300, get=get)] == ["101"]  # cached
    assert [p["id"] for p in x_feed.refresh(now=1700, get=get)] == ["102", "101"]
    assert asked[1]["since_id"] == "101" and len(asked) == 2

    monkeypatch.delenv("X_API_KEY")  # the Mac: no keys, serve the file
    assert [p["id"] for p in x_feed.refresh(now=9999, get=get)] == ["102", "101"]
    assert len(asked) == 2


ME = "1702425364474044416"
REPORT = "https://archresearch.substack.com/p/the-squeeze-moves-to-financing"
THREAD = {
    "data": [
        # newest first, as X sends them; the thread's own posts reply to the lead (same conversation)
        {
            "id": "903",
            "text": "4/ What to watch: cloud budgets. Full report: https://t.co/rep",
            "conversation_id": "900",
            "in_reply_to_user_id": ME,
            "entities": {
                "urls": [
                    {
                        "url": "https://t.co/rep",
                        "expanded_url": REPORT + "?utm_source=x",
                        "display_url": "archresearch.substack.com/p/the-squ…",
                        "title": "The squeeze moves to financing",
                    }
                ]
            },
        },
        {
            "id": "901",
            "text": "2/ What happened",
            "conversation_id": "900",
            "in_reply_to_user_id": ME,
        },
        {
            "id": "950",
            "text": "@someone thanks!",
            "conversation_id": "777",
            "in_reply_to_user_id": "42",
        },
        {
            "id": "902",
            "text": "3/ Why it matters",
            "conversation_id": "900",
            "in_reply_to_user_id": ME,
            "attachments": {"media_keys": ["3_9"]},
        },
        {
            "id": "900",
            "created_at": "2026-10-22T14:00:00.000Z",
            "text": "AI funding is the new squeeze",
            "conversation_id": "900",
        },
    ],
    "includes": {"media": [{"media_key": "3_9", "url": "https://pbs.twimg.com/media/c.png"}]},
}


def test_parse_groups_own_thread_posts_under_their_lead():
    (lead,) = x_feed.parse(THREAD)  # a reply to someone else never shows
    assert lead["id"] == "900" and lead["text"] == "AI funding is the new squeeze"
    assert [t["id"] for t in lead["thread"]] == ["901", "902", "903"]  # in thread order
    assert lead["thread"][1]["image"] == "https://pbs.twimg.com/media/c.png"
    assert lead["thread"][0]["url"] == "https://x.com/AshleynCas46131/status/901"


def test_a_substack_report_link_becomes_the_posts_report_card():
    (lead,) = x_feed.parse(THREAD)
    assert lead["report"] == {"url": REPORT, "title": "The squeeze moves to financing"}
    assert lead["thread"][2]["text"] == "4/ What to watch: cloud budgets. Full report:"


def test_a_report_link_off_substack_is_not_a_card():
    bad = {
        "data": [
            {
                "id": "5",
                "text": "see https://t.co/x",
                "entities": {
                    "urls": [
                        {
                            "url": "https://t.co/x",
                            "expanded_url": "https://evil.example/p/a",
                            "display_url": "evil.example/p/a",
                        }
                    ]
                },
            }
        ]
    }
    (p,) = x_feed.parse(bad)
    assert p["report"] is None and p["text"] == "see evil.example/p/a"


def test_new_thread_posts_attach_to_a_cached_lead():
    cached = [
        {
            "id": "900",
            "at": "",
            "text": "lead",
            "image": None,
            "url": "u",
            "thread": [],
            "report": None,
        }
    ]
    later = {
        "data": [
            {
                "id": "904",
                "text": "5/ one more",
                "conversation_id": "900",
                "in_reply_to_user_id": ME,
            }
        ]
    }
    (lead,) = x_feed.parse(later, cached)
    assert [t["id"] for t in lead["thread"]] == ["904"]


def test_an_old_cache_is_rebuilt_once_with_threads(tmp_path, monkeypatch):
    p = tmp_path / "x_feed.json"
    p.write_text('{"posts": [{"id": "900", "text": "lead"}], "checked": 0}')  # before threads
    monkeypatch.setattr(x_feed, "_path", lambda: p)
    for k in x_post.KEYS:
        monkeypatch.setenv(k, "k")
    asked = []

    def get(url, params, headers, timeout):
        asked.append(params)
        return Reply(THREAD)

    posts = x_feed.refresh(now=1000, get=get)
    assert "since_id" not in asked[0]  # refetch the threads it never kept
    assert [t["id"] for t in posts[0]["thread"]] == ["901", "902", "903"]
    x_feed.refresh(now=2000, get=get)
    assert asked[1]["since_id"] == "950"  # the newest post seen, replies included


def test_a_check_time_in_the_future_does_not_freeze_the_feed(tmp_path, monkeypatch):
    p = tmp_path / "x_feed.json"
    p.write_text('{"v": 3, "posts": [], "checked": 1000000000000, "newest": "900"}')
    monkeypatch.setattr(x_feed, "_path", lambda: p)
    for k in x_post.KEYS:
        monkeypatch.setenv(k, "k")
    asked = []

    def get(url, params, headers, timeout):
        asked.append(params)
        return Reply(THREAD)

    x_feed.refresh(now=1000, get=get)
    assert asked  # it asked X instead of serving the file forever


def test_only_market_posts_show_and_each_is_asked_once(tmp_path, monkeypatch):
    p = tmp_path / "x_feed.json"
    p.write_text('{"v": 3, "posts": [], "checked": 0, "newest": "1"}')
    monkeypatch.setattr(x_feed, "_path", lambda: p)
    for k in x_post.KEYS:
        monkeypatch.setenv(k, "k")
    asked = []

    def ask(text, q, meter, agent):
        asked.append(text)
        return {"market": 0.1 if "kane" in text else 0.9}

    monkeypatch.setattr(x_feed, "predicates", ask)
    body = {
        "data": [{"id": "11", "text": "well deserved harry kane"}, {"id": "10", "text": "CPI rose"}]
    }
    assert [x["id"] for x in x_feed.refresh(now=1000, get=lambda *a, **k: Reply(body))] == ["10"]
    x_feed.refresh(now=2000, get=lambda *a, **k: Reply({"data": []}))
    assert len(asked) == 2  # the kept post carries its answer; the dropped one is gone


def test_a_rebuild_keeps_the_threads_of_posts_it_did_not_reach(tmp_path, monkeypatch):
    p = tmp_path / "x_feed.json"
    old = {"id": "5", "text": "CPI rose", "thread": [{"id": "6"}], "report": {"url": "r"}}
    p.write_text(json.dumps({"v": 2, "posts": [old], "checked": 0, "newest": "6"}))
    monkeypatch.setattr(x_feed, "_path", lambda: p)
    for k in x_post.KEYS:
        monkeypatch.setenv(k, "k")
    posts = x_feed.refresh(
        now=1000, get=lambda *a, **k: Reply({"data": [{"id": "10", "text": "PPI"}]})
    )
    assert [x["id"] for x in posts] == ["10", "5"]
    assert posts[1]["thread"] == [{"id": "6"}] and posts[1]["report"] == {"url": "r"}
