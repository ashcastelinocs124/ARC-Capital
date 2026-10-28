"""Figures only the news and earnings calls carry: capex guidance, new bonds and loans and their rates,
funding off the balance sheet, supply delays, a private neocloud's power. One cited web search per
topic; only lines with a citation are kept (`facts_from_search`), the Cited Reader picks the figures
from them, and code keeps a figure only if its own line prints it. Results are cached by key (the
newest filing's accession, or the ISO week), so no answer is paid for twice."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from castelino.agents.base import StructuredAgent
from castelino.agents.update.facts import facts_from_search
from castelino.config import get_settings

SYSTEM = """You search the web for one company's figures and answer in short lines, one fact per line,
each starting with its date (month and year) and carrying a citation. Use the latest reports first:
the company's own releases, filings and earnings calls, then major news outlets. Copy figures exactly
as the source prints them. Leave out anything you can't cite."""

TOPICS: dict[str, str] = {
    "guidance": (
        "{company} ({ticker}): its latest full-year capital expenditure guidance as it states it "
        "(the year it covers, and whether it includes finance leases), and its reported capex for the "
        "last completed full year on the same definition."
    ),
    "borrowing": (
        "{company} ({ticker}): bonds, notes, convertible notes and term loans issued in {year}: "
        "amount, interest rate or coupon or SOFR margin, maturity, date."
    ),
    "off_balance": (
        "{company} ({ticker}): leases signed but not yet commenced, and data center joint ventures or "
        "off-balance-sheet financing, with amounts and dates."
    ),
    "delays": (
        "{company} ({ticker}): data center, power or capacity delays and guidance cuts caused by them, "
        "with dates, in the last 12 months."
    ),
    "power": (
        "{company}: data center power online and power contracted, in MW or GW, as of its latest report."
    ),
    "backlog": (
        "{company} ({ticker}): remaining performance obligations or cloud backlog for the latest "
        "quarter and a year earlier."
    ),
}

READ = """You read cited lines about one company and pull out the figures for one topic. Each line has an
id in brackets. For each figure: a short label (e.g. "guidance", "actual", "10-yr bond", "leases not yet
commenced", "power online", "power contracted", "backlog", "backlog a year ago", or a few words naming a
delay), its value exactly as the line prints it (value_high for the top of a range), its unit, the
period or year it covers, its date (YYYY-MM or YYYY-MM-DD), and the id of the one line it came from.
A dated event with no figure (a delay) has value null and unit "none". A guidance with no full-year
dollar figure is a "guidance" item with value null. Never compute or combine figures; use only what one
line prints. Return nothing for a line that isn't about the topic."""


class Item(BaseModel):  # LLM output (closed schema: no defaults)
    label: str
    value: float | None
    value_high: float | None
    unit: Literal["billions", "millions", "percent", "megawatts", "gigawatts", "none"]
    period: str
    date: str
    fact_id: str


class Items(BaseModel):  # LLM output (closed schema: no defaults)
    items: list[Item]


class CitedReader(StructuredAgent[Items]):
    name = "capex_cited_reader"
    output_schema = Items
    tier = "fast"

    def __init__(self) -> None:
        self.model = get_settings().ai_capex.reader_model

    def system_prompt(self) -> str:
        return READ

    def user_prompt(self, *, company: str, topic: str, lines: str) -> str:
        return f"Company: {company}\nTopic: {topic}\n\nCited lines:\n{lines}"


def _search(system: str, user: str):
    from castelino.data.web_search import search_cited

    return search_cited(system, user)


def cited_items(
    company: str,
    ticker: str,
    topic: str,
    key: str,
    cache_dir: Path,
    *,
    search=None,
    reader=CitedReader,
    year: int | None = None,
) -> list[dict]:
    """The checked figures for one company and topic, each with its source line; cached by key."""
    path = cache_dir / "cited" / f"{ticker}-{topic}-{key}.json"
    if path.exists():
        return json.loads(path.read_text())
    from datetime import date

    ask = TOPICS[topic].format(company=company, ticker=ticker, year=year or date.today().year)
    text, cites = (search or _search)(SYSTEM, ask)
    facts = {f.id: f for f in facts_from_search("W", text, cites)}
    out: list[dict] = []
    if facts:
        lines = "\n".join(f"[{f.id}] {f.text}" for f in facts.values())
        for it in reader()(company=company, topic=topic, lines=lines).items:
            fact = facts.get(it.fact_id)
            if fact is None:
                continue
            nums = {round(abs(n), 6) for n in fact.numbers}
            if any(
                v is not None and round(abs(v), 6) not in nums for v in (it.value, it.value_high)
            ):
                continue  # a figure its own line doesn't print
            out.append(
                it.model_dump()
                | {
                    "source": {
                        "title": fact.source_title,
                        "url": fact.source_url,
                        "line": fact.text,
                    }
                }
            )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=1))
    return out
