import json
from pathlib import Path

from castelino.substack import build_doc

REC = {
    "date": "2026-10-07",
    "note": {
        "headline": "H",
        "takeaways": ["t1", "t2", "t3"],
        "items": [
            {"rank": 2, "title": "Second", "body": "b2", "chart": None},
            {"rank": 1, "title": "First", "body": "b1", "chart": "macro-1"},
        ],
    },
    "exhibits": [{"finding_id": "macro-1", "file": "exhibit_1.png", "title": "Exhibit 1: DGS10"}],
}


def test_build_doc_orders_items_attaches_charts_without_a_site_link():
    doc = build_doc(
        REC, {"exhibit_1.png": {"url": "https://substackcdn.com/x.png", "imageWidth": 10}}
    )
    kinds = [n["type"] for n in doc["content"]]
    assert kinds == [
        "bullet_list",
        "heading",
        "paragraph",
        "captionedImage",
        "heading",
        "paragraph",
        "paragraph",
    ]
    assert len(doc["content"][0]["content"]) == 3
    assert doc["content"][1]["content"][0]["text"] == "1. First"
    assert doc["content"][3]["content"][0]["attrs"]["src"] == "https://substackcdn.com/x.png"
    assert "arcresearch.markets" not in str(doc)  # Substack is the only place a note is read
    assert "investment advice" in doc["content"][-1]["content"][0]["text"]


def test_chart_missing_upload_is_skipped():
    doc = build_doc(REC, {})
    assert "captionedImage" not in [n["type"] for n in doc["content"]]


def test_real_record_builds_if_present():
    p = Path("data/updates/2026-10-07.json")
    if p.exists():
        json.dumps(build_doc(json.loads(p.read_text()), {}))


def test_bold_markers_become_strong_marks():
    rec = {
        **REC,
        "note": {
            **REC["note"],
            "items": [
                {
                    "rank": 1,
                    "title": "T",
                    "body": "**Wages rose 0.13%** in Sep. **What to watch:** CPI.",
                    "chart": None,
                }
            ],
        },
    }
    body = [n for n in build_doc(rec, {})["content"] if n["type"] == "paragraph"][0]["content"]
    assert [(n["text"], n.get("marks")) for n in body] == [
        ("Wages rose 0.13%", [{"type": "strong"}]),
        (" in Sep. ", None),
        ("What to watch:", [{"type": "strong"}]),
        (" CPI.", None),
    ]


def test_a_note_is_paragraphs_with_its_attachments():
    from castelino.substack import note_payload

    p = note_payload("Lead line.\n\nSource: https://x.com/a", ["att-1"])
    assert p["bodyJson"]["type"] == "doc" and p["bodyJson"]["attrs"] == {"schemaVersion": "v1"}
    texts = [c["content"][0]["text"] for c in p["bodyJson"]["content"]]
    assert texts == ["Lead line.", "Source: https://x.com/a"]
    assert p["attachmentIds"] == ["att-1"] and p["replyMinimumRole"] == "everyone"
    assert "attachmentIds" not in note_payload("Text only.", [])


def test_post_note_uploads_attaches_then_posts(monkeypatch, tmp_path):
    import httpx

    from castelino import substack

    png = tmp_path / "card.png"
    png.write_bytes(b"\x89PNG")
    calls = []

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append((req.method, req.url.path, json.loads(req.content or b"{}"), req.headers))
        if req.url.path == "/api/v1/image":
            return httpx.Response(200, json={"id": 1, "url": "https://img/card.png"})
        if req.url.path == "/api/v1/comment/attachment":
            return httpx.Response(200, json={"id": "att-9", "type": "image"})
        return httpx.Response(200, json={"id": 365})

    real = httpx.Client
    monkeypatch.setattr(
        substack.httpx, "Client", lambda **kw: real(transport=httpx.MockTransport(handler), **kw)
    )
    monkeypatch.setenv("SUBSTACK_SID", "s")
    assert substack.post_note("$SPCX beat forecasts.", png) == "365"
    paths = [c[1] for c in calls]
    assert paths == ["/api/v1/image", "/api/v1/comment/attachment", "/api/v1/comment/feed"]
    assert calls[1][2] == {"url": "https://img/card.png", "type": "image"}
    assert calls[2][2]["attachmentIds"] == ["att-9"]
    note = json.dumps(calls[2][2])
    assert "SPCX beat forecasts." in note and "$SPCX" not in note  # cashtags are for X only
    # without a browser's Origin, Substack answers the Note with a 403 (2026-10-19)
    assert calls[2][3]["origin"] == "https://substack.com" and calls[2][3]["referer"]


def test_view_renders_as_blockquote_after_item():
    rec = json.loads(json.dumps(REC))
    rec["note"]["items"][1]["view"] = {
        "consultant": "ai",
        "topic": "AI models and chips",
        "text": "The squeeze is moving to financing.",
        "fact_ids": [],
    }
    doc = build_doc(rec, {"exhibit_1.png": {"url": "u", "imageWidth": 10}})
    kinds = [n["type"] for n in doc["content"]]
    assert kinds[1:5] == ["heading", "paragraph", "captionedImage", "blockquote"]
    bq = doc["content"][4]
    assert bq["content"][0]["content"][0]["text"] == "ARC view · AI models and chips"
    assert bq["content"][1]["content"][0]["text"] == "The squeeze is moving to financing."


def test_series_title_puts_the_series_name_first_once():
    from castelino.substack import series_title

    assert series_title("Daily Chart", "Fed hold looms") == "Daily Chart | Fed hold looms"
    assert (
        series_title("Daily Chart", "Daily Chart | Fed hold looms")
        == "Daily Chart | Fed hold looms"
    )
    assert (
        series_title("Daily Chart", "Daily Chart | Fed hold looms", 3)
        == "Daily Chart #3 | Fed hold looms"
    )


def test_next_number_follows_the_highest_published_number(monkeypatch):
    from castelino import substack
    from castelino.dashboard.endpoints import videos

    titles = [
        "Special Topic #2 | B",
        "Special Topic #4 | D",
        "Special Topic | old",
        "AI Update #9 | X",
    ]
    monkeypatch.setattr(videos, "archive_json", lambda: [{"title": t} for t in titles])
    assert substack.next_number("Special Topic") == 5  # a deleted #3 leaves no repeat
    assert substack.next_number("Weekly Deep Dive") == 1


def test_plain_title_drops_only_a_series_name():
    from castelino.substack import plain_title

    assert plain_title("Daily Update | Oil eased") == "Oil eased"
    assert plain_title("Daily Chart #12 | Oil eased") == "Oil eased"
    assert plain_title("AI Update #3 | Neolabs and Neoclouds") == "Neolabs and Neoclouds"
    assert plain_title("Special Topic | Brazil 2026: the runoff") == "Brazil 2026: the runoff"
    assert plain_title("Money for Machines") == "Money for Machines"
    assert plain_title("Brazil | a note") == "Brazil | a note"


def test_note_number_counts_earlier_published_drafts(tmp_path):
    import httpx

    from castelino.substack import note_number

    for day, did in (("2026-10-08", 1), ("2026-10-09", 2), ("2026-10-13", 3), ("2026-11-05", 4)):
        (tmp_path / f"{day}.json").write_text(json.dumps({"draft_id": did}))
    (tmp_path / "._2026-10-07.json").write_bytes(b"\xa3 macOS metadata")
    seen = []

    def handler(req):
        did = int(req.url.path.rsplit("/", 1)[-1])
        seen.append(did)
        return httpx.Response(200, json={"is_published": did != 2})  # draft 2 was never published

    http = httpx.Client(base_url="https://pub.test/api/v1", transport=httpx.MockTransport(handler))
    assert note_number("2026-11-05", tmp_path, http) == 3  # drafts 1 and 3 published before it
    assert json.loads((tmp_path / "2026-10-08.json").read_text())["published"] is True
    seen.clear()
    assert note_number("2026-11-05", tmp_path, http) == 3
    assert seen == [2]  # a marker known published isn't asked again
