"""Push a day's Morning Note to Substack as a draft (you review and hit Publish yourself).

Substack has no official API: these are the internal endpoints its editor uses, as mapped by
github.com/jakub-k-slys/substack-gateway-oss, authenticated with your browser session cookies.
Run: `uv run python -m castelino.substack [YYYY-MM-DD]` (default today). publish_snapshot.sh
calls it non-fatally, so a broken push never blocks the site deploy.
"""

from __future__ import annotations

import base64
import json
import os
import sys
from datetime import date

import httpx

from castelino.agents.update.fsio import atomic_write_text
from castelino.config import get_settings

SITE = "https://arcresearch.markets"


class CookieExpiredError(RuntimeError):
    pass


def _text(s: str, href: str | None = None) -> dict:
    node: dict = {"type": "text", "text": s}
    if href:
        node["marks"] = [{"type": "link", "attrs": {"href": href, "target": "_blank"}}]
    return node


def _p(*content: dict) -> dict:
    return {"type": "paragraph", "content": list(content)}


def _image(up: dict, alt: str) -> dict:
    # Shape of Substack's captionedImage/image2 node, from the gateway's draft_body_resolver.
    return {
        "type": "captionedImage",
        "content": [
            {
                "type": "image2",
                "attrs": {
                    "src": up["url"],
                    "height": up.get("imageHeight"),
                    "width": up.get("imageWidth"),
                    "bytes": up.get("bytes"),
                    "alt": alt,
                    "type": up.get("contentType"),
                    "belowTheFold": False,
                    "topImage": False,
                    "isProcessing": False,
                    "offset": False,
                },
            }
        ],
    }


def build_doc(record: dict, uploaded: dict[str, dict]) -> dict:
    """Substack editor doc for a v2 record. `uploaded` maps exhibit file name -> image upload reply."""
    note, day = record["note"], record["date"]
    exhibits = {e["finding_id"]: e for e in record.get("exhibits", [])}
    content: list[dict] = [
        {
            "type": "bullet_list",
            "content": [
                {"type": "list_item", "content": [_p(_text(t))]} for t in note["takeaways"]
            ],
        }
    ]
    for item in sorted(note["items"], key=lambda i: i["rank"]):
        content.append(
            {
                "type": "heading",
                "attrs": {"level": 3},
                "content": [_text(f"{item['rank']}. {item['title']}")],
            }
        )
        content.append(_p(_text(item["body"])))
        ex = exhibits.get(item.get("chart") or "")
        if ex and ex["file"] in uploaded:
            content.append(_image(uploaded[ex["file"]], ex["title"]))
    url = f"{SITE}/updates?date={day}"
    content.append(
        _p(_text("Interactive charts and every source: "), _text(url.removeprefix("https://"), url))
    )
    content.append(_p(_text("Not investment advice.")))
    return {"type": "doc", "content": content}


def _subtitle(day: str) -> str:
    return f"ARC Morning Note · {date.fromisoformat(day):%A, %B %-d, %Y}"


def _check(r: httpx.Response) -> httpx.Response:
    if r.status_code in (401, 403):
        raise CookieExpiredError(
            f"{r.status_code} from Substack: session cookie expired. Copy substack.sid (and connect.sid if your "
            "browser has it) into .env (SUBSTACK_SID, SUBSTACK_CONNECT_SID), then rerun."
        )
    r.raise_for_status()
    return r


def push_draft(day: str) -> str:
    cfg = get_settings()
    updates = cfg.root / cfg.update_agent.updates_dir
    pub = os.getenv("SUBSTACK_PUBLICATION_URL", "").rstrip("/")
    sid, connect = os.getenv("SUBSTACK_SID"), os.getenv("SUBSTACK_CONNECT_SID")
    if not (pub and sid):
        return "skipped: SUBSTACK_PUBLICATION_URL / SUBSTACK_SID not set"
    path = updates / f"{day}.json"
    if not path.exists():
        return f"skipped: no Morning Note for {day}"
    record = json.loads(path.read_text())
    if record.get("version") != 2:
        return f"skipped: {day} is not a v2 Morning Note"

    marker = updates / "substack" / f"{day}.json"
    api = f"{pub}/api/v1"
    cookies = {"substack.sid": sid} | (
        {"connect.sid": connect} if connect else {}
    )  # connect.sid is optional
    with httpx.Client(cookies=cookies, timeout=60) as http:
        draft_id = json.loads(marker.read_text())["draft_id"] if marker.exists() else None
        if draft_id:
            r = http.get(f"{api}/drafts/{draft_id}")
            if r.status_code == 404:
                draft_id = None  # deleted in Substack: make a fresh one
            elif _check(r).json().get("is_published"):
                return f"skipped: {day} is already published on Substack (draft {draft_id})"

        uploaded = {}
        charts = updates / "charts" / day
        for ex in record.get("exhibits", []):
            png = charts / ex["file"]
            if png.exists():
                data_uri = "data:image/png;base64," + base64.b64encode(png.read_bytes()).decode()
                uploaded[ex["file"]] = _check(
                    http.post(f"{api}/image", json={"image": data_uri})
                ).json()

        fields = {
            "draft_title": record["note"]["headline"],
            "draft_subtitle": _subtitle(day),
            "draft_body": json.dumps(build_doc(record, uploaded), ensure_ascii=False),
        }
        if draft_id:
            _check(http.put(f"{api}/drafts/{draft_id}", json=fields))
            return f"updated draft {draft_id} for {day} ({len(uploaded)} charts)"

        settings = _check(http.get("https://substack.com/api/v1/user-settings")).json()
        user_id = settings["userSettings"][0]["user_id"]
        payload = fields | {
            "draft_bylines": [{"id": user_id, "is_guest": False}],
            "audience": "everyone",  # the gateway's default is only_paid
            "type": "newsletter",
            "section_chosen": False,
            "draft_section_id": None,
        }
        draft_id = _check(http.post(f"{api}/drafts", json=payload)).json()["id"]
    marker.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(marker, json.dumps({"draft_id": draft_id}))
    return f"created draft {draft_id} for {day} ({len(uploaded)} charts): {pub}/publish/post/{draft_id}"


if __name__ == "__main__":
    day = sys.argv[1] if len(sys.argv) > 1 else date.today().isoformat()
    try:
        print("substack:", push_draft(day))
    except (CookieExpiredError, httpx.HTTPError) as e:
        print("substack: FAILED:", e, file=sys.stderr)
        sys.exit(1)
