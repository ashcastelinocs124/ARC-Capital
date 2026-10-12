from castelino.dashboard.endpoints.weekly_posts import parse_weekly_posts

BODY = (
    "<h2>The week at a glance</h2><ul>"
    "<li><p><strong>Markets priced an October hold.</strong> After a 12-0 vote...</p></li>"
    "<li><p><strong>Wages reverted.</strong> Hourly earnings rose 0.1%.</p></li>"
    "</ul><p>What to watch: CPI.</p><ul><li>not a takeaway</li></ul>"
)
ARCHIVE = [
    {
        "slug": "hike-risk-oil-shocks-and-an-ai-reality",
        "title": "Hike Risk, Oil Shocks and an AI Reality Check Test Markets ",
        "subtitle": "ARC Weekly Deep Dive · Oct 5–Oct 9, 2026",
        "post_date": "2026-10-12T00:54:12.966Z",
        "cover_image": "https://substack-post-media.s3.amazonaws.com/public/images/x.png",
        "canonical_url": "https://archresearch.substack.com/p/hike-risk-oil-shocks-and-an-ai-reality",
        "body_html": BODY,
    },
    {  # a daily note: not a weekly
        "slug": "fed-pause",
        "title": "Fed pause",
        "subtitle": "ARC Daily Note · Thursday, October 8, 2026",
        "post_date": "2026-10-09T00:00:00Z",
        "canonical_url": "https://archresearch.substack.com/p/fed-pause",
    },
    {  # a weekly spanning two months, no cover, link off-site: dropped
        "slug": "evil",
        "title": "x",
        "subtitle": "ARC Weekly Deep Dive · Sep 28–Oct 2, 2026",
        "post_date": "2026-10-05T00:00:00Z",
        "canonical_url": "https://evil.example.com/p/x",
    },
    {
        "slug": "w40",
        "title": "Payrolls miss",
        "subtitle": "ARC Weekly Deep Dive · Sep 28–Oct 2, 2026",
        "post_date": "2026-10-04T00:00:00Z",
        "canonical_url": "https://archresearch.substack.com/p/w40",
    },
]


def test_weekly_posts_are_the_published_weekly_deep_dives_newest_first():
    posts = parse_weekly_posts(ARCHIVE, overrides={})
    assert [p["week"] for p in posts] == ["2026-W41", "2026-W40"]
    p = posts[0]
    assert p["title"] == "Hike Risk, Oil Shocks and an AI Reality Check Test Markets"
    assert (p["start"], p["end"]) == ("2026-10-05", "2026-10-09")
    assert p["takeaways"] == ["Markets priced an October hold.", "Wages reverted."]
    assert p["image"].startswith("https://substack-post-media") and p["url"].endswith("ai-reality")
    assert posts[1]["image"] is None and posts[1]["takeaways"] == []


def test_a_hand_made_cover_wins():
    posts = parse_weekly_posts(
        ARCHIVE, overrides={"hike-risk-oil-shocks-and-an-ai-reality": "/thumbs/x.jpg"}
    )
    assert posts[0]["image"] == "/thumbs/x.jpg"
