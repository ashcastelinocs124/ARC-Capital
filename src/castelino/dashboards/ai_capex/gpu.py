"""GPU rental prices from Silicon Data's public index page, read once a day (the user's call, made
knowing its terms forbid storing the content without written consent; the API is paid and internal
use only). The page shows today's price and the change on a week, with no history, so the history is
ARC's own readings, one row per GPU per day."""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

from castelino.week_ahead import spend

URL = "https://www.silicondata.com/products/silicon-index"
GPUS = [
    "H100",
    "H200",
    "B200",
    "B300",
    "A100",
    "MI300X",
]  # the base index, not the -hyperscaler rows
# the page's text nodes and its up/down arrow images, in page order
_TOKENS = re.compile(r"hub-arrow-(up|down)\.svg|>([^<>]+)<")
_NAME = re.compile(r"(" + "|".join(GPUS) + r")(\([A-Z0-9]+\))?")


def parse(html: str) -> list[dict]:
    """Each GPU's first card: the name, then its $ price, then its arrow and its % change."""
    found: dict[str, dict] = {}
    cur: dict | None = None
    for arrow, text in _TOKENS.findall(html):
        t = text.strip()
        if arrow:
            if cur and cur.get("price") is not None:
                cur["down"] = arrow == "down"
        elif m := _NAME.fullmatch(t):
            cur = None if m.group(1) in found else {"gpu": m.group(1), "price": None}
        elif cur and cur["price"] is None and re.fullmatch(r"\$\d+(\.\d+)?", t):
            cur["price"] = float(t[1:])
        elif cur and cur["price"] is not None and re.fullmatch(r"\d+(\.\d+)?%", t):
            pct = float(t[:-1])
            found[cur["gpu"]] = {
                "gpu": cur["gpu"],
                "price": cur["price"],
                "change_7d_pct": -pct if cur.get("down") else pct,
            }
            cur = None
    if len(found) < 4:
        raise ValueError(f"silicon data: {len(found)} GPUs parsed; the page may have changed")
    return [found[g] for g in GPUS if g in found]


def record(rows: list[dict], day: str, path: Path) -> list[dict]:
    """Append the day's readings, replacing that day's earlier ones, and return the whole history."""
    hist = [json.loads(x) for x in path.read_text().splitlines()] if path.exists() else []
    hist = [h for h in hist if h["date"] != day]
    hist += [{"date": day, "gpu": r["gpu"], "price": r["price"]} for r in rows]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(h) + "\n" for h in hist))
    return hist


def lane(path: Path, get_text=spend.get_text, today: date | None = None) -> dict:
    day = (today or date.today()).isoformat()
    rows = parse(get_text(URL))
    return {
        "as_of": day,
        "rows": rows,
        "history": record(rows, day, path),
        "source": {"title": "Silicon Data index", "url": URL},
    }
