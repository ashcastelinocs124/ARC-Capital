from castelino.dashboard.endpoints.daily_posts import parse_daily_posts

FEED = """<rss xmlns:content="http://purl.org/rss/1.0/modules/content/"><channel>
<item><title>Fed pause expectations rose</title><description>ARC Daily Note &#183; Thursday, October 8, 2026</description>
<link>https://archresearch.substack.com/p/fed-pause</link><enclosure url="https://cdn/x.png" type="image/jpeg"/>
<content:encoded><![CDATA[<p>intro</p><ul><li><p>Waller left room for a pause.</p></li><li><p>Auction pressure.</p></li></ul>]]></content:encoded></item>
<item><title>Saudi strikes</title><description>ARC Morning Note &#183; Monday, October 12, 2026</description>
<link>https://archresearch.substack.com/p/saudi-strikes</link></item>
<item><title>Oil supply fears</title><description>ARC Theme Charts &#183; Tuesday, October 20, 2026</description>
<link>https://archresearch.substack.com/p/oil-supply-fears</link>
<content:encoded><![CDATA[<p>why</p><ul><li><p><strong>News &amp; X: </strong>Oil leads.</p></li></ul>]]></content:encoded></item>
<item><title>Tesla and Meta</title><description>ARC Daily Update &#183; Wednesday, October 21, 2026</description>
<link>https://archresearch.substack.com/p/tesla-and-meta</link></item>
<item><title>Hand-renamed</title><description>ARC Note &#183; Saturday, October 10, 2026</description>
<link>https://archresearch.substack.com/p/hand-renamed</link></item>
<item><title>Neolabs</title><description>In this video I walk</description><link>https://archresearch.substack.com/p/neolabs</link></item>
<item><title>Off-site</title><description>ARC Daily Note &#183; Friday, October 9, 2026</description><link>javascript:alert(1)</link></item>
</channel></rss>"""


def test_parse_daily_posts_keeps_only_daily_notes_and_theme_charts_on_the_substack():
    posts = parse_daily_posts(FEED)
    assert [(p["date"], p["kind"]) for p in posts] == [
        ("2026-10-21", "note"),  # the name since 2026-10-21
        ("2026-10-20", "charts"),
        ("2026-10-12", "note"),
        ("2026-10-10", "note"),  # renamed "ARC Note" by hand (the Oct 21 post)
        ("2026-10-08", "note"),
    ]  # newest first
    assert posts[1]["takeaways"] == ["News & X: Oil leads."]
    p = posts[4]
    assert p["date"] == "2026-10-08" and p["image"] == "https://cdn/x.png"
    assert p["takeaways"] == ["Waller left room for a pause.", "Auction pressure."]


def test_archive_adds_the_posts_the_feed_dropped():
    from castelino.dashboard.endpoints.daily_posts import archive_daily_posts

    archive = [
        {
            "title": "Saudi strikes",
            "subtitle": "ARC Morning Note · Monday, October 12, 2026",
            "canonical_url": "https://archresearch.substack.com/p/saudi-strikes",
        },
        {
            "title": "Fed pause",
            "subtitle": "ARC Daily Note · Thursday, October 8, 2026",
            "canonical_url": "https://archresearch.substack.com/p/fed-pause",
            "cover_image": "https://cdn/c.png",
        },
        {
            "title": "Neolabs",
            "subtitle": "AI",
            "canonical_url": "https://archresearch.substack.com/p/n",
        },
    ]
    seen = {"https://archresearch.substack.com/p/saudi-strikes"}
    (p,) = archive_daily_posts(archive, seen)
    assert (p["date"], p["kind"], p["image"], p["takeaways"]) == (
        "2026-10-08",
        "note",
        "https://cdn/c.png",
        [],
    )
