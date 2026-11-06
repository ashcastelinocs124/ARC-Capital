from castelino.dashboard.endpoints.videos import parse_videos

FEED = """<rss xmlns:content="http://purl.org/rss/1.0/modules/content/"><channel>
<item><title>Neolabs</title><description>d</description><link>https://archresearch.substack.com/p/neolabs</link>
<pubDate>Wed, 07 Oct 2026 05:03:30 GMT</pubDate><enclosure url="https://x/a.mp3" type="audio/mpeg"/>
<content:encoded><![CDATA[<p>hi</p>]]></content:encoded></item>
<item><title>Weekly</title><link>https://archresearch.substack.com/p/weekly</link>
<pubDate>Sun, 20 Sep 2026 02:12:06 GMT</pubDate><enclosure url="https://x/a.png" type="image/jpeg"/>
<content:encoded><![CDATA[<div class="native-video-embed" data-attrs="{&quot;mediaUploadId&quot;:&quot;d1cb62d4-8d08-4de3-916a-018778d8122b&quot;}"></div><img src="https://cdn/x.png">]]></content:encoded></item>
<item><title>Text post</title><link>https://archresearch.substack.com/p/text</link>
<pubDate>Sun, 20 Sep 2026 02:12:06 GMT</pubDate><content:encoded><![CDATA[<p>no video</p>]]></content:encoded></item>
<item><title>Off-site link</title><link>javascript:alert(1)</link>
<pubDate>Sun, 20 Sep 2026 02:12:06 GMT</pubDate><enclosure url="https://x/a.mp3" type="audio/mpeg"/></item>
</channel></rss>"""


def test_parse_videos_keeps_only_video_posts_on_the_substack():
    cover = "https://substack-video.s3.amazonaws.com/v/transcoded-00001.png"
    vids = parse_videos(
        FEED,
        [
            {"slug": "neolabs", "cover_image": cover, "podcast_duration": 2170.6},
            {"slug": "weekly", "id": 7},
        ],
    )
    assert [v["title"] for v in vids] == ["Neolabs", "Weekly"]
    assert (
        vids[0]["date"] == "2026-10-07"
        and vids[0]["thumbnail"] == cover
        and vids[0]["duration"] == 2171
    )
    assert (
        vids[1]["thumbnail"].endswith(
            "/post/7/d1cb62d4-8d08-4de3-916a-018778d8122b/transcoded-00001.png"
        )
        and vids[1]["duration"] is None
    )


def test_feed_fetch_asks_for_a_fresh_build(monkeypatch):
    """Substack's servers keep old feed builds for a while: on 2026-10-15 Fly got one from 40 minutes
    before the day's post, so the publish missed it. A query string gets a fresh build."""
    from castelino.dashboard.endpoints import videos

    seen = []

    class Reply:
        text = "<rss/>"

        def raise_for_status(self):
            pass

    monkeypatch.setattr(videos, "_feed", (0.0, ""))
    monkeypatch.setattr(videos.httpx, "get", lambda url, **kw: seen.append(kw) or Reply())
    videos.feed_xml()
    assert "t" in (seen[0].get("params") or {})


def test_archive_pages_by_cursor_until_the_end(monkeypatch):
    """Since 2026-11-05 Substack pages the archive by ?cursor= and refuses offset (400)."""
    from castelino.dashboard.endpoints import videos

    pages = {
        None: {"posts": [{"id": 3}, {"id": 2}], "nextCursor": "a"},
        "a": {"posts": [{"id": 2}, {"id": 1}], "nextCursor": "b"},
        "b": {"posts": [{"id": 0}], "nextCursor": None},
    }

    class Reply:
        def __init__(self, body):
            self.body = body

        def raise_for_status(self):
            pass

        def json(self):
            return self.body

    monkeypatch.setattr(videos, "_archive", (0.0, []))
    monkeypatch.setattr(
        videos.httpx,
        "get",
        lambda url, params, **kw: (
            Reply(pages[params.get("cursor")])
            if "offset" not in params and params["limit"] <= 25
            else None
        ),
    )
    assert [p["id"] for p in videos.archive_json()] == [3, 2, 1, 0]


def test_archive_videos_lists_old_videos_once():
    from castelino.dashboard.endpoints.videos import archive_videos

    post = "https://archresearch.substack.com/p/"
    archive = [
        {"type": "podcast", "videoUpload": {}, "canonical_url": post + "a", "slug": "a",
         "post_date": "2026-10-07T12:00:00Z", "title": "Neolabs", "podcast_duration": 2170.6},
        {"type": "newsletter", "canonical_url": post + "b", "slug": "b", "post_date": "2026-10-06"},
        {"type": "newsletter", "canonical_url": post + "weekly-market-update-1",
         "slug": "weekly-market-update-1", "post_date": "2026-09-20"},
        {"type": "podcast", "canonical_url": post + "c", "slug": "c", "post_date": "2026-09-01"},
    ]  # fmt: skip
    vids = archive_videos(archive, seen={post + "c"})
    assert [v["url"].rsplit("/", 1)[-1] for v in vids] == ["a", "weekly-market-update-1"]
    assert vids[0]["duration"] == 2171 and vids[0]["date"] == "2026-10-07"
