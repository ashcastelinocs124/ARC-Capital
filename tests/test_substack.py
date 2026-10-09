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


def test_build_doc_orders_items_attaches_charts_and_links_back():
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
        "paragraph",
    ]
    assert len(doc["content"][0]["content"]) == 3
    assert doc["content"][1]["content"][0]["text"] == "1. First"
    assert doc["content"][3]["content"][0]["attrs"]["src"] == "https://substackcdn.com/x.png"
    link = doc["content"][-2]["content"][1]["marks"][0]["attrs"]["href"]
    assert link == "https://arcresearch.markets/updates?date=2026-10-07"
    assert "investment advice" in doc["content"][-1]["content"][0]["text"]


def test_chart_missing_upload_is_skipped():
    doc = build_doc(REC, {})
    assert "captionedImage" not in [n["type"] for n in doc["content"]]


def test_real_record_builds_if_present():
    p = Path("data/updates/2026-10-07.json")
    if p.exists():
        json.dumps(build_doc(json.loads(p.read_text()), {}))
