from castelino.dashboard.endpoints.videos import parse_videos

FEED = """<rss xmlns:content="http://purl.org/rss/1.0/modules/content/"><channel>
<item><title>Neolabs</title><description>d</description><link>https://archresearch.substack.com/p/neolabs</link>
<pubDate>Wed, 07 Oct 2026 05:03:30 GMT</pubDate><enclosure url="https://x/a.mp3" type="audio/mpeg"/>
<content:encoded><![CDATA[<p>hi</p>]]></content:encoded></item>
<item><title>Weekly</title><link>https://archresearch.substack.com/p/weekly</link>
<pubDate>Sun, 20 Sep 2026 02:12:06 GMT</pubDate><enclosure url="https://x/a.png" type="image/jpeg"/>
<content:encoded><![CDATA[<div class="native-video-embed"></div><img src="https://cdn/x.png">]]></content:encoded></item>
<item><title>Text post</title><link>https://archresearch.substack.com/p/text</link>
<pubDate>Sun, 20 Sep 2026 02:12:06 GMT</pubDate><content:encoded><![CDATA[<p>no video</p>]]></content:encoded></item>
<item><title>Off-site link</title><link>javascript:alert(1)</link>
<pubDate>Sun, 20 Sep 2026 02:12:06 GMT</pubDate><enclosure url="https://x/a.mp3" type="audio/mpeg"/></item>
</channel></rss>"""


def test_parse_videos_keeps_only_video_posts_on_the_substack():
    cover = "https://substack-video.s3.amazonaws.com/v/transcoded-00001.png"
    vids = parse_videos(
        FEED, [{"slug": "neolabs", "cover_image": cover, "podcast_duration": 2170.6}]
    )
    assert [v["title"] for v in vids] == ["Neolabs", "Weekly"]
    assert (
        vids[0]["date"] == "2026-10-07"
        and vids[0]["thumbnail"] == cover
        and vids[0]["duration"] == 2171
    )
    assert vids[1]["thumbnail"] is None and vids[1]["duration"] is None
