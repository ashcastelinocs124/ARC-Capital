"""Recipe Writer: layer 3 of the Hire pillar (registered in agents.yaml as recipe_writer).

For a company whose careers site has no known data address, GPT-6 Astra explores the site once
through a headless browser and proposes a Recipe (sources/recipes.py) saying where the job
titles live. Astra never fetches or counts titles itself: test_recipe and submit_recipe run our
fixed replay code, and a recipe is saved only if that replay returns titles from an allowed host.
Every refresh then replays the saved recipe with no model (layers 1 and 2).
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

from pydantic import ValidationError

from castelino.adoption.sources import recipes
from castelino.adoption.sources.recipes import Recipe
from castelino.config import get_settings

log = logging.getLogger(__name__)

# GPT-6 Astra API price per 1M tokens: input, cached input, output (developers.openai.com, 2026-10-05).
USD_PER_M = (10.0, 1.0, 50.0)
# Hiring platforms a recipe may point at besides the company's own domain.
ATS_HOSTS = (
    "myworkdayjobs.com",
    "greenhouse.io",
    "lever.co",
    "icims.com",
    "oraclecloud.com",
    "ultipro.com",
    "successfactors.com",
    "successfactors.eu",
    "eightfold.ai",
    "phenompeople.com",
    "ashbyhq.com",
    "smartrecruiters.com",
    "jobvite.com",
    "taleo.net",
    "avature.net",
    "workable.com",
    "paylocity.com",
    "dayforcehcm.com",
    "adp.com",
)

SYSTEM = """You find where a company's open job titles come from on its careers website, so that
plain code can read them later without you. You have a headless browser through tools.

Work like this:
1. open_page the careers start URL. Look at `json_requests`: careers sites usually load their
   job list from a JSON address. Prefer that (a kind="json" recipe): it is faster and sturdier.
2. If no JSON address carries the jobs, use page elements (a kind="dom" recipe): a CSS selector
   matching each job title (check it with sample_selector) and, if there are several pages, a
   selector for the next-page control.
3. Write the recipe. To page through results, put {page} or {offset} in the url or POST body
   (this works for dom recipes too, and is sturdier than a next-page button). Then call
   test_recipe. It runs the recipe with our own code and returns how many titles it got and a
   sample. Fix and retest until the sample is real job titles and the count matches the total
   number of open jobs the site shows (e.g. "1,234 results").
4. Call submit_recipe with the passing recipe and that site total as expected_total. That ends
   the task. Our code rejects a recipe that returns under 90% of expected_total (capped at 2,000).

We want EVERY open job worldwide: no location, team, category or keyword filters in the recipe.

Rules: only read pages. Never log in, create accounts, submit forms or apply for jobs. Do not try
to get around bot protection; if the site blocks the browser, say so and stop. The recipe must
point at the company's own site or its hiring platform. Never invent titles or counts: the only
numbers that matter come from test_recipe."""

_RECIPE_SCHEMA = Recipe.model_json_schema()
TOOLS = [
    {
        "type": "function",
        "name": "open_page",
        "description": "Load a page headless. Returns final URL, title, visible text (truncated), "
        "job-related links, and the JSON requests the page made (url, method, preview).",
        "parameters": {
            "type": "object",
            "properties": {"url": {"type": "string"}},
            "required": ["url"],
        },
    },
    {
        "type": "function",
        "name": "sample_selector",
        "description": "Load a page and return up to 15 texts matching a CSS selector, plus the match count.",
        "parameters": {
            "type": "object",
            "properties": {"url": {"type": "string"}, "css": {"type": "string"}},
            "required": ["url", "css"],
        },
    },
    {
        "type": "function",
        "name": "test_recipe",
        "description": "Run a recipe with our replay code. Returns count and 10 sample titles, or the error.",
        "parameters": {
            "type": "object",
            "properties": {"recipe": _RECIPE_SCHEMA},
            "required": ["recipe"],
        },
    },
    {
        "type": "function",
        "name": "submit_recipe",
        "description": "Submit the final recipe. Accepted only if our replay returns titles from an "
        "allowed host and at least 90% of expected_total (capped at 2,000).",
        "parameters": {
            "type": "object",
            "properties": {
                "recipe": _RECIPE_SCHEMA,
                "expected_total": {
                    "type": "integer",
                    "description": "Total open jobs the site itself displays, unfiltered",
                },
            },
            "required": ["recipe", "expected_total"],
        },
    },
]


def _site(host: str) -> str:
    """Naive registrable domain: careers.lilly.com -> lilly.com (fine for US issuers' domains)."""
    parts = host.lower().split(".")
    return ".".join(parts[-2:])


@dataclass
class RecipeResult:
    ticker: str
    recipe: Recipe | None = None
    count: int = 0
    sample: list[str] = field(default_factory=list)
    cost_usd: float = 0.0
    steps: int = 0
    note: str = ""


class Browser:
    """One headless Chromium for a company's whole session; read-only page loads."""

    def __init__(self):
        from playwright.sync_api import sync_playwright  # optional 'browser' extra

        self._pw = sync_playwright().start()
        self.pw_browser = self._pw.chromium.launch(headless=True)  # also used by dom replay
        self._ctx = self.pw_browser.new_context(accept_downloads=False)

    def close(self) -> None:
        self.pw_browser.close()
        self._pw.stop()

    def _load(self, url: str):
        if urlparse(url).scheme not in ("http", "https"):
            raise ValueError("only http(s) URLs")
        page = self._ctx.new_page()
        seen: list[dict] = []

        def on_response(resp):
            if "json" in (resp.headers.get("content-type") or "") and len(seen) < 25:
                try:
                    preview = resp.text()[:300]
                except Exception:  # noqa: BLE001 - body not available (redirect, stream)
                    preview = ""
                seen.append({"url": resp.url, "method": resp.request.method, "preview": preview})

        page.on("response", on_response)
        page.goto(url, wait_until="networkidle", timeout=30_000)
        return page, seen

    def open_page(self, url: str) -> dict:
        page, seen = self._load(url)
        try:
            links = page.eval_on_selector_all(
                "a[href]", "els => els.map(e => [e.innerText.trim(), e.href])"
            )
            jobby = [
                {"text": t[:80], "href": h}
                for t, h in links
                if re.search(r"job|career|search|opening|position|role", t + h, re.I)
            ][:30]
            return {
                "final_url": page.url,
                "title": page.title(),
                "text": page.inner_text("body")[:6000],
                "links": jobby,
                "json_requests": seen,
            }
        finally:
            page.close()

    def sample_selector(self, url: str, css: str) -> dict:
        page, _ = self._load(url)
        try:
            loc = page.locator(css)
            return {"count": loc.count(), "texts": [t.strip() for t in loc.all_inner_texts()[:15]]}
        finally:
            page.close()


class RecipeWriter:
    """Bounded GPT-6 Astra tool loop: explore, test, submit. Saves nothing itself."""

    def __init__(self, client=None, browser_factory=Browser):
        cfg = get_settings()
        self._cfg = cfg.adoption
        if client is None:
            from openai import OpenAI

            client = OpenAI(api_key=cfg.openai_api_key, timeout=cfg.openai.request_timeout_s)
        self._client = client
        self._browser_factory = browser_factory

    @staticmethod
    def _cost(usage) -> float:
        cached = getattr(getattr(usage, "input_tokens_details", None), "cached_tokens", 0) or 0
        fresh = usage.input_tokens - cached
        return (
            fresh * USD_PER_M[0] + cached * USD_PER_M[1] + usage.output_tokens * USD_PER_M[2]
        ) / 1e6

    def _check(
        self, raw: dict, allowed: set[str], browser=None
    ) -> tuple[Recipe | None, list[str], str]:
        """Our code, not the model: validate, check the host, replay. -> (recipe, titles, error)."""
        try:
            r = Recipe.model_validate(raw)
        except ValidationError as e:
            return None, [], f"invalid recipe: {e.errors()[:3]}"
        host = (
            urlparse(r.url.replace("{page}", "1").replace("{offset}", "0")).hostname or ""
        ).lower()
        if _site(host) not in allowed and not any(host.endswith(a) for a in ATS_HOSTS):
            return None, [], f"host {host} is not the company's site or a known hiring platform"
        try:
            titles = recipes.replay(r, browser=browser)
        except Exception as e:  # noqa: BLE001 - report any replay failure back to the model
            return r, [], f"replay failed: {type(e).__name__}: {str(e)[:300]}"
        return r, titles, "" if titles else "replay returned no titles"

    def _create(self, **kw):
        import time

        from castelino import benchmark

        started = time.monotonic()
        resp = self._client.responses.create(
            model=self._cfg.recipe_model, instructions=SYSTEM, tools=TOOLS, **kw
        )
        benchmark.record_call(
            "recipe_writer",
            self._cfg.recipe_model,
            {"system": SYSTEM, **kw},
            benchmark.response_output(resp),
            started=started,
            tokens=benchmark.usage_of(resp),
        )
        return resp

    def run(self, ticker: str, name: str, start_url: str) -> RecipeResult:
        res = RecipeResult(ticker)
        allowed = {_site(urlparse(start_url).hostname or "")}
        browser = self._browser_factory()
        try:
            try:  # the careers page may redirect to another domain the company owns
                allowed.add(
                    _site(urlparse(browser.open_page(start_url)["final_url"]).hostname or "")
                )
            except Exception as e:  # noqa: BLE001
                log.info("start page probe failed for %s: %s", ticker, e)
            user = f"Company: {name} (ticker {ticker}). Careers start URL: {start_url}"
            resp = self._create(input=user)
            while True:
                res.steps += 1
                res.cost_usd += self._cost(resp.usage)
                calls = [o for o in resp.output if getattr(o, "type", "") == "function_call"]
                if not calls:
                    res.note = (resp.output_text or "stopped without submitting").strip()[:500]
                    return res
                outputs = []
                for c in calls:
                    out, done = self._tool(
                        c.name, json.loads(c.arguments or "{}"), browser, allowed, res
                    )
                    outputs.append(
                        {
                            "type": "function_call_output",
                            "call_id": c.call_id,
                            "output": json.dumps(out)[:12000],
                        }
                    )
                    if done:
                        return res
                if res.steps >= self._cfg.recipe_max_steps:
                    res.note = f"step cap ({self._cfg.recipe_max_steps}) reached"
                    return res
                if res.cost_usd >= self._cfg.recipe_max_usd:
                    res.note = f"spend cap (${self._cfg.recipe_max_usd:.2f}) reached"
                    return res
                resp = self._create(previous_response_id=resp.id, input=outputs)
        finally:
            browser.close()

    def _tool(
        self, name: str, args: dict, browser, allowed: set[str], res: RecipeResult
    ) -> tuple[dict, bool]:
        """Run one tool call -> (result for the model, whether the task is finished)."""
        try:
            if name == "open_page":
                return browser.open_page(args["url"]), False
            if name == "sample_selector":
                return browser.sample_selector(args["url"], args["css"]), False
            if name in ("test_recipe", "submit_recipe"):
                r, titles, err = self._check(
                    args.get("recipe") or {}, allowed, getattr(browser, "pw_browser", None)
                )
                if err:
                    return {"accepted": False, "error": err}, False
                if name == "test_recipe":
                    return {"count": len(titles), "sample": titles[:10]}, False
                want = min(int(args.get("expected_total") or 0), recipes.MAX_POSTINGS)
                if len(titles) < 0.9 * want:
                    return {
                        "accepted": False,
                        "error": f"replay got {len(titles)} titles but the site shows {want}+; "
                        "paging is probably not working",
                    }, False
                res.recipe, res.count, res.sample = r, len(titles), titles[:10]
                return {"accepted": True, "count": len(titles)}, True
        except Exception as e:  # noqa: BLE001 - tool errors go back to the model, never crash the loop
            return {"error": f"{type(e).__name__}: {str(e)[:300]}"}, False
        return {"error": f"unknown tool {name}"}, False


def save(res: RecipeResult, recipes_dir: Path) -> Path:
    recipes_dir.mkdir(parents=True, exist_ok=True)
    path = recipes_dir / f"{res.ticker}.json"
    path.write_text(res.recipe.model_dump_json(indent=2, exclude_none=True))
    return path
