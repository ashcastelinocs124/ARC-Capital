from castelino.dashboard.endpoints.section_posts import parse_section_posts

P = "https://archresearch.substack.com/p/"
ARCHIVE = [
    {
        "section_slug": "artificial-intelligence-update",
        "title": "Neolabs",
        "canonical_url": P + "neolabs",
        "post_date": "2026-10-07T04:00:00Z",
        "description": "d",
        "cover_image": "https://s3/x.png",
        "podcast_duration": 2170.6,
        "type": "podcast",
        "videoUpload": {"id": "1"},
    },
    {
        "section_slug": "special-topics",
        "title": "Note",
        "canonical_url": P + "note",
        "post_date": "2026-09-28T04:00:00Z",
        "type": "newsletter",
    },
    {
        "section_slug": "financial-markets",
        "title": "Daily",
        "canonical_url": P + "daily",
        "post_date": "2026-10-09T04:00:00Z",
    },
    {
        "section_slug": "special-topics",
        "title": "Bad link",
        "canonical_url": "javascript:alert(1)",
        "post_date": "2026-09-01",
    },
]


def test_parse_section_posts_keeps_the_two_sections_with_safe_links():
    posts = parse_section_posts(ARCHIVE)
    assert [p["title"] for p in posts] == ["Neolabs", "Note"]
    assert (
        posts[0]["video"] is True
        and posts[0]["duration"] == 2171
        and posts[0]["date"] == "2026-10-07"
    )
    assert posts[1]["video"] is False and posts[1]["thumbnail"] is None
