"""The Census Bureau's Business Trends and Outlook Survey: the share of US firms that used AI in the last
two weeks, overall and by number of employees. Published as .xlsx every two weeks. The question now
reads "Super Intelligence or SI (formerly ... AI)", so rows are matched by question id, not text."""

from __future__ import annotations

import io

import httpx
import openpyxl

URL_SIZE = "https://www.census.gov/hfp/btos/downloads/Employment%20Size%20Class.xlsx"
URL_NATIONAL = "https://www.census.gov/hfp/btos/downloads/National.xlsx"
QUESTION, YES = 7, 1  # "In the last two weeks, did this business use ... AI ...?" -> Yes
CLASSES = {  # employment size class -> (label, the dashboard's bucket)
    "A": ("1–4", "small"),
    "B": ("5–9", "small"),
    "C": ("10–19", "small"),
    "D": ("20–49", "small"),
    "E": ("50–99", "mid"),
    "F": ("100–249", "mid"),
    "G": ("250+", "large"),
}


def _sheet(xlsx: bytes, name: str) -> list[tuple]:
    wb = openpyxl.load_workbook(io.BytesIO(xlsx), read_only=True, data_only=True)
    return list(wb[name].iter_rows(values_only=True))


def _yes(xlsx: bytes) -> tuple[str, dict[str | None, float]]:
    """(newest sample date, {size class or None: % yes}) from the Response Estimates sheet."""
    rows = _sheet(xlsx, "Response Estimates")
    head = list(rows[0])
    col = head.index("Answer") + 1  # sample dates follow, newest first
    q, a = head.index("Question ID"), head.index("Answer ID")
    size = head.index("Empsize") if "Empsize" in head else None
    out: dict[str | None, float] = {}
    for r in rows[1:]:
        if r[q] == QUESTION and r[a] == YES and r[col] not in (None, "."):
            out[r[size] if size is not None else None] = float(str(r[col]).rstrip("%"))
    return str(head[col]), out


def parse(size_xlsx: bytes, national_xlsx: bytes) -> dict:
    smpdt, by = _yes(size_xlsx)
    _, nat = _yes(national_xlsx)
    ref_end = None
    for r in _sheet(size_xlsx, "Collection and Reference Dates")[1:]:
        if r and str(r[3]) == smpdt and r[7] is not None:
            ref_end = f"{r[7]:%Y-%m-%d}"
    return {
        "smpdt": smpdt,
        "ref_end": ref_end,
        "overall_pct": nat.get(None),
        "by_class": [
            {"code": c, "label": label, "pct": by[c], "bucket": bucket}
            for c, (label, bucket) in CLASSES.items()
            if c in by
        ],
        "source": {
            "title": "Census Bureau, Business Trends and Outlook Survey",
            "url": "https://www.census.gov/hfp/btos/",
        },
    }


def fetch(get=httpx.get) -> dict:
    files = [
        get(u, timeout=60, follow_redirects=True, headers={"User-Agent": "Mozilla/5.0"})
        for u in (URL_SIZE, URL_NATIONAL)
    ]
    for f in files:
        f.raise_for_status()
    return parse(files[0].content, files[1].content)
