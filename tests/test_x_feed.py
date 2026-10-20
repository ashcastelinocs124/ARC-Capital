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
