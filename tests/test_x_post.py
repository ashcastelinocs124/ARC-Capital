import json

from fastapi.testclient import TestClient

from castelino import x_post
from castelino.dashboard.endpoints import admin_desk

URL = "https://archresearch.substack.com/p/saudi-strikes-lifted-oil"


def test_signature_matches_xs_documented_example():
    # https://developer.x.com/en/docs/authentication/oauth-1-0a/creating-a-signature
    params = {
        "status": "Hello Ladies + Gentlemen, a signed OAuth request!",
        "include_entities": "true",
        "oauth_consumer_key": "xvz1evFS4wEEPTGEFPHBog",
        "oauth_nonce": "kYjzVBB8Y0ZFabxSWbWovY3uYSQ2pTgmZeNu2VS4cg",
        "oauth_signature_method": "HMAC-SHA1",
        "oauth_timestamp": "1318622958",
        "oauth_token": "370773112-GmHxMAgYyLbNEtIKZeRNFsMKPR9EyMZeS9weJAEb",
        "oauth_version": "1.0",
    }
    sig = x_post.signature(
        "POST",
        "https://api.twitter.com/1.1/statuses/update.json",
        params,
        "kAcSOqF21Fu85e7zjz7ZN2U4ZRhfV3WpwPAoE3Z7kBw",
        "LswwdoUaIvS8ltyTt5jkRh4J50vUPVVHtR2YPi5kE",
    )
    assert sig == "hCtSmYh+iHYCEqBWrE7C7hYmtUk="


def test_xlen_counts_links_as_23_and_emoji_as_2():
    assert x_post.xlen("see " + URL) == 4 + 23
    assert x_post.xlen("ab 🧵") == 5


def test_no_emoji_drops_emoji_but_keeps_text_symbols():
    assert (
        x_post.no_emoji("🗓️ WEEK AHEAD · Oil 📈 up 2% → 4.1σ 🇺🇸") == "WEEK AHEAD · Oil up 2% → 4.1σ "
    )
    assert x_post.no_emoji("Nasdaq −3.4% today…") == "Nasdaq −3.4% today…"
    doc = json.dumps({"text": "🚨 CPI: 0.4%"}, ensure_ascii=False)
    assert json.loads(x_post.no_emoji(doc)) == {"text": "CPI: 0.4%"}  # what substack.push() sends


def test_drafts_are_threads_for_daily_and_weekly():
    d = x_post.drafts("daily", "Oil up", ["a", "b", "c"], URL)
    assert d == ["Oil up", "1/ a", "2/ b", "3/ c", f"Full note on Substack → {URL}"]
    w = x_post.drafts("weekly", "Week 41", [str(i) for i in range(12)], URL)
    assert w[0] == "Week 41" and w[1] == "1/ 0" and len(w) == 7 and URL in w[-1]


def _setup(tmp_path, monkeypatch, fail_at=None):
    from castelino.dashboard.main import app

    rows = [
        {
            "kind": "daily",
            "when": "2026-10-12",
            "title": "Oil up",
            "takeaways": ["a"],
            "url": URL,
            "slug": "saudi-strikes-lifted-oil",
            "image": "/thumbs/fed-officials-another-hike.jpg",
        }
    ]
    monkeypatch.setattr(admin_desk, "_published", lambda: rows)
    monkeypatch.setattr(admin_desk, "_x_dir", lambda: tmp_path)
    for k in x_post.KEYS:
        monkeypatch.setenv(k, "k")
    sent = []

    def fake_post(text, reply_to=None, media_id=None):
        if fail_at is not None and len(sent) == fail_at:
            raise RuntimeError("X said 503")
        sent.append((text, reply_to) if media_id is None else (text, reply_to, media_id))
        return f"id{len(sent)}"

    monkeypatch.setattr(x_post, "post", fake_post)
    return TestClient(app), sent


def test_post_chain_replies_in_order_and_never_twice(tmp_path, monkeypatch):
    c, sent = _setup(tmp_path, monkeypatch)
    texts = ["Oil up\n\n• a", f"Full note → {URL}"]
    r = c.post("/admin/desk/x/saudi-strikes-lifted-oil", json={"texts": texts})
    assert r.json() == {"posted_ids": ["id1", "id2"], "total": 2, "error": None}
    assert sent == [(texts[0], None), (texts[1], "id1")]
    assert (
        c.post("/admin/desk/x/saudi-strikes-lifted-oil", json={"texts": texts}).status_code == 409
    )
    assert c.get("/admin/desk/x").json()["posts"][0]["posted_ids"] == ["id1", "id2"]


def test_failed_reply_keeps_first_and_retry_continues(tmp_path, monkeypatch):
    c, sent = _setup(tmp_path, monkeypatch, fail_at=1)
    texts = ["Oil up", f"Full note → {URL}"]
    r = c.post("/admin/desk/x/saudi-strikes-lifted-oil", json={"texts": texts}).json()
    assert r["posted_ids"] == ["id1"] and "503" in r["error"]
    monkeypatch.setattr(
        x_post, "post", lambda t, reply_to=None, media_id=None: sent.append((t, reply_to)) or "id9"
    )
    r = c.post("/admin/desk/x/saudi-strikes-lifted-oil", json={"texts": ["edited"]}).json()
    assert r["posted_ids"] == ["id1", "id9"] and sent[-1] == (
        texts[1],
        "id1",
    )  # resumed the original chain


def test_rejects_long_posts_missing_link_and_unknown_slugs(tmp_path, monkeypatch):
    c, _ = _setup(tmp_path, monkeypatch)
    assert (
        c.post(
            "/admin/desk/x/saudi-strikes-lifted-oil", json={"texts": ["x" * 281, URL]}
        ).status_code
        == 400
    )
    assert (
        c.post("/admin/desk/x/saudi-strikes-lifted-oil", json={"texts": ["no link"]}).status_code
        == 400
    )
    assert c.post("/admin/desk/x/other-post", json={"texts": [URL]}).status_code == 404


def test_cover_goes_on_the_first_post_only(tmp_path, monkeypatch):
    c, sent = _setup(tmp_path, monkeypatch)
    uploads = []
    monkeypatch.setattr(x_post, "upload_image", lambda data: uploads.append(len(data)) or "m1")
    texts = ["Oil up 🧵", f"Full note → {URL}"]
    r = c.post("/admin/desk/x/saudi-strikes-lifted-oil", json={"texts": texts, "image": True})
    assert r.json()["posted_ids"] == ["id1", "id2"]
    assert sent == [(texts[0], None, "m1"), (texts[1], "id1")]
    assert uploads and uploads[0] > 10_000  # read the real /thumbs/ cover from the repo


def test_failed_upload_posts_nothing(tmp_path, monkeypatch):
    c, sent = _setup(tmp_path, monkeypatch)

    def boom(data):
        raise RuntimeError("X image upload said 400")

    monkeypatch.setattr(x_post, "upload_image", boom)
    r = c.post(
        "/admin/desk/x/saudi-strikes-lifted-oil",
        json={"texts": ["Oil up", f"Full note → {URL}"], "image": True},
    )
    assert r.status_code == 502 and "couldn't attach the cover" in r.json()["detail"]
    assert sent == [] and c.get("/admin/desk/x").json()["posts"][0]["posted_ids"] == []


def test_as_jpeg_shrinks_wide_images():
    import io

    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGBA", (3000, 1500), (0, 135, 68, 255)).save(buf, "PNG")
    out = Image.open(io.BytesIO(x_post.as_jpeg(buf.getvalue())))
    assert out.format == "JPEG" and out.size == (1600, 800)


def test_stocks_go_out_on_x_as_cashtags_only():
    ok = {"SPCX", "TSM", "NVDA", "XLE", "SPY"}.__contains__
    assert (
        x_post.cashtags("SpaceX (SPCX) beat; Nvidia (NVDA) fell.", ok) == "$SPCX beat; NVDA fell."
    )
    assert (
        x_post.cashtags("Taiwan Semiconductor (TSMC) rose.", ok)
        == "Taiwan Semiconductor (TSMC) rose."
    )
    assert (
        x_post.cashtags("Energy stocks (XLE) and the S&P 500 (SPY)", ok)
        == "Energy stocks $XLE and the S&P 500 SPY"
    )
    assert (
        x_post.cashtags("Consumer prices (CPI) rose.", lambda t: True)
        == "Consumer prices (CPI) rose."
    )


def test_a_post_carries_one_cashtag_because_x_refuses_more():
    # X answers 403 "Posts are limited to a maximum of one cashtag" (seen 2026-10-21 and 22)
    ok = {"TSLA", "XLY"}.__contains__
    assert (
        x_post.cashtags("$TSLA fell 3% while $XLY rose; $TSLA leads.", ok)
        == "$TSLA fell 3% while XLY rose; TSLA leads."
    )
    assert x_post.cashtags("Spend hit $2.5 billion, $3,637.292B by 2027.", ok) == (
        "Spend hit $2.5 billion, $3,637.292B by 2027."
    )


def test_a_post_can_carry_up_to_four_images(monkeypatch):
    sent = {}
    monkeypatch.setattr(x_post, "_auth_header", lambda *a: "OAuth x")
    monkeypatch.setattr(
        x_post.httpx,
        "post",
        lambda url, json, **k: (
            sent.update(json)
            or type("R", (), {"status_code": 201, "json": lambda self: {"data": {"id": "7"}}})()
        ),
    )
    assert x_post.post("hi", media_id=["a", "b", "c", "d", "e"]) == "7"
    assert sent["media"] == {"media_ids": ["a", "b", "c", "d"]}
    x_post.post("hi", media_id="a")
    assert sent["media"] == {"media_ids": ["a"]}
