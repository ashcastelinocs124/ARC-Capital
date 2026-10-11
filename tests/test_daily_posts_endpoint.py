from castelino.dashboard.endpoints.daily_posts import parse_daily_posts

FEED = """<rss xmlns:content="http://purl.org/rss/1.0/modules/content/"><channel>
<item><title>Fed pause expectations rose</title><description>ARC Daily Note &#183; Thursday, October 8, 2026</description>
<link>https://archresearch.substack.com/p/fed-pause</link><enclosure url="https://cdn/x.png" type="image/jpeg"/>
<content:encoded><![CDATA[<p>intro</p><ul><li><p>Waller left room for a pause.</p></li><li><p>Auction pressure.</p></li></ul>]]></content:encoded></item>
<item><title>Neolabs</title><description>In this video I walk</description><link>https://archresearch.substack.com/p/neolabs</link></item>
<item><title>Off-site</title><description>ARC Daily Note &#183; Friday, October 9, 2026</description><link>javascript:alert(1)</link></item>
</channel></rss>"""


def test_parse_daily_posts_keeps_only_daily_notes_on_the_substack():
    posts = parse_daily_posts(FEED)
    assert len(posts) == 1
    p = posts[0]
    assert p["date"] == "2026-10-08" and p["image"] == "https://cdn/x.png"
    assert p["takeaways"] == ["Waller left room for a pause.", "Auction pressure."]
