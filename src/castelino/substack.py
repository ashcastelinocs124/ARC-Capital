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
import re
import sys
from collections.abc import Callable
from datetime import date
from pathlib import Path

import httpx

from castelino import cover
from castelino.agents.update.fsio import atomic_write_text
from castelino.config import get_settings
from castelino.x_post import no_emoji

SITE = "https://arcresearch.markets"


class CookieExpiredError(RuntimeError):
    pass


def _text(s: str, href: str | None = None) -> dict:
    node: dict = {"type": "text", "text": s}
    if href:
        node["marks"] = [{"type": "link", "attrs": {"href": href, "target": "_blank"}}]
    return node


def _rich(s: str) -> list[dict]:
    """Text with the Editor's **bold** markers as strong marks (odd split parts are bold)."""
    nodes = []
    for i, part in enumerate(s.split("**")):
        if part:  # ProseMirror rejects empty text nodes
            nodes.append(_text(part) | ({"marks": [{"type": "strong"}]} if i % 2 else {}))
    return nodes


def _p(*content: dict) -> dict:
    return {"type": "paragraph", "content": list(content)}


def _bold(s: str) -> dict:
    return {"type": "text", "text": s, "marks": [{"type": "bold"}]}


def _heading(s: str, level: int = 3) -> dict:
    return {"type": "heading", "attrs": {"level": level}, "content": [_text(s)]}


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
    all_ex = record.get("exhibits", [])
    by_item = {e["item"]: e for e in all_ex if e.get("item") is not None}
    exhibits = {} if by_item else {e["finding_id"]: e for e in all_ex}  # older notes
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
        for para in re.split(r"\n\s*\n", item["body"]):
            if para.strip():
                content.append(_p(*_rich(para.strip())))
        ex = by_item.get(item["rank"]) or exhibits.get(item.get("chart") or "")
        if ex and ex["file"] in uploaded:
            content.append(_image(uploaded[ex["file"]], ex["title"]))
    if record.get("calendar"):  # code-written: every release and earnings report of the day
        content.append(_heading("On the calendar today"))
        content.append(
            {
                "type": "bullet_list",
                "content": [
                    {"type": "list_item", "content": [_p(_text(t))]} for t in record["calendar"]
                ],
            }
        )
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


def _upload(http: httpx.Client, api: str, png: Path) -> dict:
    data_uri = "data:image/png;base64," + base64.b64encode(png.read_bytes()).decode()
    return _check(http.post(f"{api}/image", json={"image": data_uri})).json()


NOTES_API = "https://substack.com/api/v1"  # Notes belong to the account, not the publication
# Without a browser's Origin, Referer and User-Agent, Substack answers the Note itself with a 403 error
# page, though the image upload and attachment pass (seen 2026-10-19, from the Mac and from Fly)
BROWSER = {
    "Origin": "https://substack.com",
    "Referer": "https://substack.com/home",
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/141.0 Safari/537.36",
}


def can_note() -> bool:
    return bool(os.getenv("SUBSTACK_SID"))


def note_payload(text: str, attachment_ids: list[str]) -> dict:
    """A Note's body: one plain-text paragraph per blank-line block (substack-gateway-oss's shape;
    links stay plain text, as the gateway sends them)."""
    paras = [
        {"type": "paragraph", "content": [{"type": "text", "text": p.strip()}]}
        for p in text.split("\n\n")
        if p.strip()
    ]
    out = {
        "bodyJson": {"type": "doc", "attrs": {"schemaVersion": "v1"}, "content": paras},
        "tabId": "for-you",
        "surface": "feed",
        "replyMinimumRole": "everyone",
    }
    if attachment_ids:
        out["attachmentIds"] = attachment_ids
    return out


def post_note(text: str, png: Path | None = None) -> str:
    """Post a Substack Note as the session's account, `png` attached; returns the Note id. Raises
    with Substack's message on failure. Image Notes: upload, register an image attachment (checked
    against Substack on 2026-10-19), then post the Note with its id."""
    sid, connect = os.getenv("SUBSTACK_SID"), os.getenv("SUBSTACK_CONNECT_SID")
    if not sid:
        raise RuntimeError("SUBSTACK_SID not set")
    cookies = {"substack.sid": sid} | ({"connect.sid": connect} if connect else {})
    with httpx.Client(cookies=cookies, timeout=60, headers=BROWSER) as http:
        ids = []
        if png is not None:
            url = _upload(http, NOTES_API, png)["url"]
            att = http.post(f"{NOTES_API}/comment/attachment", json={"url": url, "type": "image"})
            ids.append(_check(att).json()["id"])
        r = http.post(f"{NOTES_API}/comment/feed", json=note_payload(no_emoji(text), ids))
        return str(_check(r).json()["id"])


def push(
    *,
    marker: Path,
    title: str,
    subtitle: str,
    pngs: dict[str, Path],
    body: Callable[[dict[str, dict]], dict],
    label: str,
    cover: Callable[[], Path | None] | None = None,
) -> str:
    """Create or update one Substack draft. `marker` remembers the draft id; never publishes.
    `cover` makes the cover image; it is called only when the draft has no cover yet, so a
    cover set by hand in Substack is kept."""
    pub = os.getenv("SUBSTACK_PUBLICATION_URL", "").rstrip("/")
    sid, connect = os.getenv("SUBSTACK_SID"), os.getenv("SUBSTACK_CONNECT_SID")
    if not (pub and sid):
        return "skipped: SUBSTACK_PUBLICATION_URL / SUBSTACK_SID not set"
    api = f"{pub}/api/v1"
    cookies = {"substack.sid": sid} | (
        {"connect.sid": connect} if connect else {}
    )  # connect.sid is optional
    with httpx.Client(cookies=cookies, timeout=60) as http:
        draft_id = json.loads(marker.read_text())["draft_id"] if marker.exists() else None
        draft: dict = {}
        if draft_id:
            r = http.get(f"{api}/drafts/{draft_id}")
            if r.status_code == 404:
                draft_id = None  # deleted in Substack: make a fresh one
            elif (draft := _check(r).json()).get("is_published"):
                return f"skipped: {label} is already published on Substack (draft {draft_id})"

        uploaded = {name: _upload(http, api, png) for name, png in pngs.items() if png.exists()}

        fields = {
            "draft_title": no_emoji(title).strip(),
            "draft_subtitle": no_emoji(subtitle).strip(),
            # emoji only ever sit inside JSON strings, so dropping them from the text keeps it valid JSON
            "draft_body": no_emoji(json.dumps(body(uploaded), ensure_ascii=False)),
        }
        if cover and not draft.get("cover_image") and (png := cover()):
            fields["cover_image"] = _upload(http, api, png)["url"]
        if draft_id:
            _check(http.put(f"{api}/drafts/{draft_id}", json=fields))
            return f"updated draft {draft_id} for {label} ({len(uploaded)} images)"

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
    return (
        f"created draft {draft_id} for {label} ({len(uploaded)} images): "
        f"{pub}/publish/post/{draft_id}"
    )


def publish(marker: Path, *, section_id: int | None = None, send: bool = False) -> str:
    """Publish the draft `marker` names (made by push()), optionally into a section; returns the
    post's URL and saves it in the marker. `send` also emails it to subscribers. Already published:
    returns the saved URL, so a rerun never posts twice."""
    rec = json.loads(marker.read_text())
    if rec.get("url"):
        return rec["url"]
    pub = os.environ["SUBSTACK_PUBLICATION_URL"].rstrip("/")
    api, draft = f"{pub}/api/v1", rec["draft_id"]
    with httpx.Client(cookies={"substack.sid": os.environ["SUBSTACK_SID"]}, timeout=60) as http:
        if section_id:
            fields = {"draft_section_id": section_id, "section_chosen": True}
            _check(http.put(f"{api}/drafts/{draft}", json=fields))
        _check(http.get(f"{api}/drafts/{draft}/prepublish"))
        body = {"send": send, "share_automatically": False}
        post = _check(http.post(f"{api}/drafts/{draft}/publish", json=body)).json()
    url = f"{pub}/p/{post['slug']}"
    atomic_write_text(marker, json.dumps(rec | {"url": url}))
    return url


def set_cover(marker: Path, png: Path) -> str:
    """Replace the cover of the unpublished draft `marker` names (cover.py's redo command)."""
    if not marker.exists():
        return f"skipped: no draft yet ({marker.name}); the next draft push adds the cover"
    pub = os.environ["SUBSTACK_PUBLICATION_URL"].rstrip("/")
    api, draft = f"{pub}/api/v1", json.loads(marker.read_text())["draft_id"]
    with httpx.Client(cookies={"substack.sid": os.environ["SUBSTACK_SID"]}, timeout=60) as http:
        if _check(http.get(f"{api}/drafts/{draft}")).json().get("is_published"):
            return (
                f"skipped: already published; upload {png} as the cover in Substack's post settings"
            )
        _check(
            http.put(f"{api}/drafts/{draft}", json={"cover_image": _upload(http, api, png)["url"]})
        )
    return f"cover set on draft {draft}: {pub}/publish/post/{draft}"


def push_draft(day: str) -> str:
    cfg = get_settings()
    updates = cfg.root / cfg.update_agent.updates_dir
    path = updates / f"{day}.json"
    if not path.exists():
        return f"skipped: no Morning Note for {day}"
    record = json.loads(path.read_text())
    if record.get("version") != 2:
        return f"skipped: {day} is not a v2 Morning Note"
    charts = updates / "charts" / day
    return push(
        marker=updates / "substack" / f"{day}.json",
        title=record["note"]["headline"],
        subtitle=_subtitle(day),
        pngs={ex["file"]: charts / ex["file"] for ex in record.get("exhibits", [])},
        body=lambda up: build_doc(record, up),
        label=day,
        cover=lambda: cover.for_note(day),
    )


if __name__ == "__main__":
    day = sys.argv[1] if len(sys.argv) > 1 else date.today().isoformat()
    try:
        print("substack:", push_draft(day))
    except (CookieExpiredError, httpx.HTTPError) as e:
        print("substack: FAILED:", e, file=sys.stderr)
        sys.exit(1)
