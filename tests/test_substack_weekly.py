from castelino.substack_weekly import build_weekly_doc, table_png

SECTION = {
    "title": "The long end",
    "agent": "Rates desk",
    "paragraphs": ["p1", "p2"],
    "fact_ids": ["A1"],
    "exhibits": [{"fact_id": "A1", "window_days": 90}],
    "challenges": [{"question": "Growth?", "answer": "No.", "verdict": "Accepted"}],
}
REC = {
    "week": "2026-W41",
    "start": "2026-10-05",
    "end": "2026-10-09",
    "report": {
        "title": "Long end reprices",
        "subtitle": "Term premium returns",
        "watch": "CPI Wednesday.",
        "bullets": [{"lead": "Yields jumped.", "body": "Up 28bp.", "fact_ids": ["A1"]}],
        "sections": [SECTION],
    },
    "exhibits": [
        {
            "n": 1,
            "section": 0,
            "fact_id": "A1",
            "title": "Exhibit 1: DGS10",
            "subtitle": "s",
            "file": "exhibit_1.png",
        }
    ],
    "facts": [
        {
            "id": "A1",
            "source_title": "FRED DGS10",
            "source_url": "https://fred.stlouisfed.org/series/DGS10",
        }
    ],
    "regime": {"pulse": 64, "pressure": 38},
    "plan": {"agents": [{"name": "Rates desk", "description": "US rates"}]},
    "scorecard": [],
    "counts": {"notes": 5, "agents": 1, "data_pulls": 9},
}
UP = {n: {"url": f"https://cdn/{n}"} for n in ("exhibit_1.png", "scorecard.png", "counts.png")}


def text_of(node):
    return "".join(c.get("text", "") for c in node.get("content", []))


def test_doc_has_every_part_of_the_report_in_order():
    doc = build_weekly_doc(REC, UP)
    joined = " | ".join(text_of(n) for n in doc["content"])
    order = [
        "The week at a glance",
        "What to watch",
        "ARC regime read",
        "Research desk",
        "1. The long end",
        "p1",
        "Editor challenged",
        "Method and sources",
        "Not investment advice",
    ]
    pos = [joined.index(s) for s in order]
    assert pos == sorted(pos)
    srcs = [
        n["content"][0]["attrs"]["src"] for n in doc["content"] if n["type"] == "captionedImage"
    ]
    assert srcs == [
        "https://cdn/scorecard.png",
        "https://cdn/counts.png",
        "https://cdn/exhibit_1.png",
    ]
    assert "https://arcresearch.markets/deep-research?week=2026-W41" in str(doc)


def test_missing_upload_is_skipped_not_fatal():
    doc = build_weekly_doc(REC, {})
    assert not [n for n in doc["content"] if n["type"] == "captionedImage"]


def test_existing_draft_is_not_overwritten_unless_the_record_is_newer(tmp_path, monkeypatch):
    import json
    import os

    from castelino import substack_weekly as sw

    deep = tmp_path / "data" / "deep"
    (deep / "substack").mkdir(parents=True)
    rec_path = deep / "2026-W41.json"
    rec_path.write_text(json.dumps(REC | {"generated_at": "2026-10-11T06:40:00"}))
    marker = deep / "substack" / "2026-W41.json"
    marker.write_text(json.dumps({"draft_id": 1}))
    os.utime(rec_path, (1_000, 1_000))
    os.utime(marker, (2_000, 2_000))

    class Cfg:
        root = tmp_path

        class deep_dive:  # noqa: N801
            data_dir = "data/deep"

    monkeypatch.setattr(sw, "get_settings", lambda: Cfg)
    monkeypatch.setattr(sw, "push", lambda **kw: "pushed")
    assert sw.push_weekly_draft("2026-W41").startswith("skipped: draft already up to date")
    os.utime(rec_path, (3_000, 3_000))  # rebuilt after the draft was made
    assert sw.push_weekly_draft("2026-W41") == "pushed"


def test_table_png_writes_an_image(tmp_path):
    p = table_png(["Asset", "1w"], [["S&P 500", "+0.9%"]], tmp_path / "t.png", "The week")
    assert p.stat().st_size > 1000
