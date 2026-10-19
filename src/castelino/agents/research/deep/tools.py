"""The research agents' tools: the Weekly / Trade Lab ToolBox (FRED, Yahoo, BLS, Polymarket, cited web search
with parallel prefetch, the board, the cost meter) framed for any topic, plus `x_search` over X's recent
search. Every result becomes a Fact in code, so an agent can only cite what a tool returned."""

from __future__ import annotations

import threading
from datetime import UTC, datetime, timedelta

from castelino.agents.trade.tools import TradeToolBox
from castelino.agents.update.facts import numbers_in
from castelino.agents.update.models import Fact
from castelino.agents.weekly.tools import SPECS, ToolError, _obj
from castelino.ai_sentiment import xapi

SEARCH_SYSTEM = (
    "You are a research assistant. Report only what reputable sources published. "
    "Quote figures exactly. One bullet per fact, each ending with its citation."
)
DATA_TOOLS = ["web_search", "fred_series", "yahoo_prices", "bls_series", "polymarket_odds"]
_START = {"type": "string", "description": "Window start, YYYY-MM-DD"}
SPECS_R: dict[str, dict] = {
    **SPECS,
    "fred_series": {
        "description": "A FRED series (e.g. UNRATE, CPIAUCSL, OPHNFB, PAYEMS) from start to today: "
        "level, change, high and low.",
        "parameters": _obj({"series_id": {"type": "string"}, "start": _START}),
    },
    "yahoo_prices": {
        "description": "Daily closes for a Yahoo Finance ticker (e.g. NVDA, MSFT, ^GSPC, XLK) from "
        "start to today.",
        "parameters": _obj({"ticker": {"type": "string"}, "start": _START}),
    },
    "web_search": {
        "description": "A cited web search on any question. Each cited line becomes a fact you can "
        "cite.",
        "parameters": _obj({"query": {"type": "string"}}),
    },
    "x_search": {
        "description": "Posts on X from the last 7 days only, for an X search query (e.g. 'enterprise "
        "AI adoption' or 'from:satyanadella AI'). Each post becomes a fact attributed to its author: "
        "cite it only as what that person said.",
        "parameters": _obj({"query": {"type": "string"}}),
    },
    "post_to_board": {
        "description": "Share something other researchers could use, with the ids of YOUR facts "
        "behind it.",
        "parameters": SPECS["post_to_board"]["parameters"],
    },
    "read_board": {
        "description": "Read what other researchers posted; their facts become citable by you.",
        "parameters": _obj({}),
    },
}


def allowed_tools() -> list[str]:
    """x_search only when X_BEARER_TOKEN is set."""
    return DATA_TOOLS + (["x_search"] if xapi.has_key() else [])


def is_x(f: Fact) -> bool:
    return f.source_url.startswith("https://x.com/")


def handle(f: Fact) -> str:
    return f.source_url.split("/")[3]


class XBudget:
    """X posts left for one report, shared by its agents (every post read counts against X's cap)."""

    def __init__(self, left: int):
        self.left = max(0, left)
        self._lock = threading.Lock()

    def spend(self, n: int) -> None:
        with self._lock:
            self.left = max(0, self.left - n)


class ResearchToolBox(TradeToolBox):
    search_system = SEARCH_SYSTEM
    search_frame = "Today is {end:%Y-%m-%d}. "

    def __init__(
        self, *args, x_budget: XBudget | None = None, x_get=None, x_per_call: int = 10, **kw
    ):
        super().__init__(*args, **kw)
        self.x_budget, self._x_get, self.x_per_call = x_budget, x_get, x_per_call
        self.x_posts = 0

    def specs(self) -> list[dict]:
        names = [*self.allowed, "post_to_board", "read_board"]
        return [{"type": "function", "name": n, "strict": True, **SPECS_R[n]} for n in names]

    def _ids(self, n: int) -> list[str]:
        # after compaction only cited facts remain: count on from the highest own id, never len(facts)
        k = len(self.prefix)
        own = [
            int(f.id[k:]) for f in self.facts if f.id.startswith(self.prefix) and f.id[k:].isdigit()
        ]
        top = max(own, default=0)
        return [f"{self.prefix}{top + i + 1}" for i in range(n)]

    def _x_search(self, query: str) -> list[Fact]:
        left = self.x_budget.left if self.x_budget else 0
        if left <= 0:
            raise ToolError("X budget for this report is used up")
        now = datetime.now(UTC)
        fmt = "%Y-%m-%dT%H:%M:%SZ"
        start = (now - timedelta(days=7) + timedelta(minutes=5)).strftime(fmt)  # inside X's reach
        end = (now - timedelta(seconds=30)).strftime(fmt)  # X's rule
        n = min(self.x_per_call, left)
        get = self._x_get or xapi._get
        posts = xapi.search(f"{query} -is:retweet", start, end, get=get, cap=n, max_results=n)[:n]
        self.x_budget.spend(len(posts))
        self.x_posts += len(posts)
        if not posts:
            raise ToolError("no posts on X in the last 7 days for that query")
        return [
            Fact(
                id=i,
                text=f"@{p['author']}: {p['text']}",
                numbers=numbers_in(p["text"]),
                provenance="reported",
                source_title=f"@{p['author']} on X",
                source_url=p["url"],
            )
            for i, p in zip(self._ids(len(posts)), posts, strict=True)
        ]
