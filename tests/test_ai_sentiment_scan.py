from datetime import date

from castelino.ai_sentiment import scan

OEMBED = {
    "url": "https://x.com/dev_a/status/111",
    "author_url": "https://x.com/Dev_A",
    "html": '<blockquote class="twitter-tweet"><p lang="en" dir="ltr">Claude is &amp; '
    'was <a href="https://t.co/x">fast</a></p>&mdash; Dev A (@Dev_A) <a href="https://x.com/dev_a/'
    'status/111?ref_src=twsrc">October 12, 2026</a></blockquote>\n',
}


def test_status_urls_from_text_and_citations_normalised_and_deduped():
    text = "See https://twitter.com/dev_a/status/111?s=20 and x.com/indie/status/222."
    cites = [
        "https://x.com/dev_a/status/111",
        "https://example.com/blog",
        "https://x.com/indie/status/333/photo/1",
    ]
    assert scan.status_urls(text, cites) == [
        "https://x.com/dev_a/status/111",
        "https://x.com/indie/status/222",
        "https://x.com/indie/status/333",
    ]


def test_parse_oembed():
    assert scan.parse_oembed(OEMBED) == ("dev_a", "Claude is & was fast")


def test_fetch_posts_keeps_only_listed_authors_and_skips_failures():
    replies = {
        "https://x.com/dev_a/status/111": OEMBED,
        "https://x.com/bot/status/9": {**OEMBED, "author_url": "https://x.com/bot"},
    }

    def get(url):
        if url not in replies:
            raise RuntimeError("404")
        return replies[url]

    urls = [
        "https://x.com/dev_a/status/111",
        "https://x.com/bot/status/9",
        "https://x.com/gone/status/1",
    ]
    posts = scan.fetch_posts(urls, {"dev_a": ""}, get=get)
    assert posts == [
        {"url": "https://x.com/dev_a/status/111", "author": "dev_a", "text": "Claude is & was fast"}
    ]


def test_find_posts_builds_x_search_call():
    seen = {}

    def call(tools, prompt):
        seen["tools"], seen["prompt"] = tools, prompt
        return "https://x.com/dev_a/status/111", []

    urls = scan.find_posts(["dev_a", "indie"], date(2026, 10, 12), call=call)
    assert urls == ["https://x.com/dev_a/status/111"]
    t = seen["tools"][0]
    assert t["type"] == "x_search" and t["allowed_x_handles"] == ["dev_a", "indie"]
    assert t["from_date"] == "2026-10-12" and t["to_date"] == "2026-10-12"
