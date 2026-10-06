"""Replay saved job-board recipes: layer 2 of the Hire pillar.

A recipe says WHERE a company's open job titles live on a custom careers site: either a JSON
address the page loads (kind="json"), or page elements plus a next-page button (kind="dom").
The Recipe Writer (adoption/recipe_agent.py, GPT-6 Astra) proposes recipes once; this fixed
code is the only thing that ever fetches titles from them, both when the writer tests a recipe
and on every refresh. No model runs here.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

import httpx
from pydantic import BaseModel, Field

MAX_POSTINGS = 2000  # same cap as the platform readers in jobs.py
MAX_PAGES = 100


class Recipe(BaseModel):
    """Where a careers site's job titles are. Put {page} or {offset} in url or body to page."""

    kind: Literal["json", "dom"]
    url: str = Field(description="Address to load; may contain {page} or {offset} (json and dom)")
    method: Literal["GET", "POST"] = "GET"
    body: dict[str, Any] | None = Field(
        None, description="JSON body for POST; may use {page}/{offset}"
    )
    items: str = Field("", description="json: dotted path to the list of jobs ('' = top level)")
    title: str = Field("title", description="json: dotted path to the title inside one job")
    page_start: int = Field(1, description="json: first {page} number")
    page_size: int = Field(20, description="json: jobs per page, the step for {offset}")
    title_selector: str | None = Field(None, description="dom: CSS selector of each job title")
    next_selector: str | None = Field(
        None, description="dom: CSS selector of the next-page control"
    )


def load(path: Path) -> Recipe:
    return Recipe.model_validate_json(path.read_text())


def _dig(obj: Any, path: str) -> Any:
    for key in filter(None, path.split(".")):
        obj = obj[int(key)] if isinstance(obj, list) else obj[key]
    return obj


def _fill(value: Any, page: int, offset: int) -> Any:
    """Substitute {page}/{offset} in strings, keeping a bare placeholder an int (APIs want 2, not "2")."""
    if isinstance(value, str):
        if value in ("{page}", "{offset}"):
            return page if value == "{page}" else offset
        return value.replace("{page}", str(page)).replace("{offset}", str(offset))
    if isinstance(value, dict):
        return {k: _fill(v, page, offset) for k, v in value.items()}
    if isinstance(value, list):
        return [_fill(v, page, offset) for v in value]
    return value


def _paged(r: Recipe) -> bool:
    text = r.url + json.dumps(r.body or {})
    return "{page}" in text or "{offset}" in text


def replay_json(r: Recipe, http: httpx.Client) -> list[str]:
    titles: list[str] = []
    seen_page: list[str] | None = None
    for i in range(MAX_PAGES if _paged(r) else 1):
        page, offset = r.page_start + i, i * r.page_size
        url, body = _fill(r.url, page, offset), _fill(r.body, page, offset)
        resp = http.request(r.method, url, json=body) if r.method == "POST" else http.get(url)
        resp.raise_for_status()
        got = [str(_dig(j, r.title)).strip() for j in _dig(resp.json(), r.items)]
        got = [t for t in got if t]
        # Stop on an empty page, or one identical to the last (a site that ignores the page param).
        if not got or got == seen_page:
            break
        titles += got
        seen_page = got
        if len(titles) >= MAX_POSTINGS:
            break
    return titles[:MAX_POSTINGS]


def replay_dom(r: Recipe, browser=None) -> list[str]:
    """Headless Chromium: collect title_selector texts, click next_selector until nothing new.

    `browser` reuses an open Playwright browser (the Recipe Writer's session): Playwright's sync
    API can't start a second instance in the same thread.
    """
    if not r.title_selector:
        raise ValueError("dom recipe needs title_selector")
    if browser is None:
        from playwright.sync_api import sync_playwright  # optional 'browser' extra

        with sync_playwright() as p:
            b = p.chromium.launch(headless=True)
            try:
                return replay_dom(r, b)
            finally:
                b.close()
    titles: list[str] = []
    last: list[str] | None = None
    by_url = _paged(r)  # {page}/{offset} in the url: load each page; else click next_selector
    page = browser.new_page()
    try:
        for i in range(MAX_PAGES):
            if by_url or i == 0:
                url = _fill(r.url, r.page_start + i, i * r.page_size)
                page.goto(url, wait_until="networkidle", timeout=30_000)
            got = [t.strip() for t in page.locator(r.title_selector).all_inner_texts() if t.strip()]
            if not got or got == last:  # empty, or the next page didn't change anything
                break
            titles += got
            last = got
            if by_url:
                if len(titles) >= MAX_POSTINGS:
                    break
                continue
            nxt = page.locator(r.next_selector) if r.next_selector else None
            if len(titles) >= MAX_POSTINGS or nxt is None or not nxt.count():
                break
            if not nxt.first.is_enabled():
                break
            nxt.first.click()
            page.wait_for_load_state("networkidle", timeout=30_000)
    finally:
        page.close()
    return titles[:MAX_POSTINGS]


def replay(r: Recipe, http: httpx.Client | None = None, browser=None) -> list[str]:
    if r.kind == "json":
        own = http is None
        http = http or httpx.Client(
            timeout=30, follow_redirects=True, headers={"Accept-Encoding": "gzip, deflate"}
        )
        try:
            return replay_json(r, http)
        finally:
            if own:
                http.close()
    return replay_dom(r, browser)
