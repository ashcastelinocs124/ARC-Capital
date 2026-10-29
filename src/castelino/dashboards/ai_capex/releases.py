"""Figures only an earnings release prints: cloud growth, headline backlog, a neocloud's power, and all of
Nebius's quarter (it files no quarterly XBRL). The Release Reader copies each wanted figure with the
sentence it came from; code keeps it only if that sentence is in the release and prints the number.
Each release is read once: the result is cached by accession."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from castelino.adoption.sources.edgar import Release
from castelino.agents.base import StructuredAgent
from castelino.agents.update.facts import numbers_in
from castelino.config import get_settings
from castelino.dashboards.ai_capex.companies import COMPANIES

READ = """You read a company's quarterly earnings release, as filed with the SEC, and copy the figures
you are asked for, for the quarter just reported. For each figure the release prints: its name exactly
as asked, its value exactly as printed (a number in brackets is negative), its unit, and the sentence or
table row it came from, copied word for word. A growth rate is in percent. Leave out any figure the
release doesn't print; never work one out. period: the quarter as the release names it."""

WANTED: dict[str, list[str]] = {
    "MSFT": [
        "Azure and other cloud services revenue growth %",
        "commercial remaining performance obligation",
    ],
    "GOOGL": ["Google Cloud revenue", "Google Cloud revenue growth %"],
    "AMZN": ["AWS segment net sales", "AWS net sales growth %"],
    "ORCL": ["cloud infrastructure revenue growth %", "remaining performance obligations"],
    "CRWV": ["revenue backlog", "active power", "contracted power"],
    "NBIS": [  # its whole quarter: Nebius files no quarterly XBRL
        "revenue",
        "capital expenditures",
        "net cash from operating activities",
        "proceeds from borrowings",
        "repayments of borrowings",
        "proceeds from convertible notes",
        "proceeds from issuance of shares",
        "cash and cash equivalents",
        "contracted power",
        "active power",
    ],
    "IREN": ["contracted AI cloud revenue", "secured power", "operating AI cloud capacity"],
    "NVDA": ["Data Center revenue", "Data Center revenue growth %"],
}
NAMES = {c.ticker: c.name for c in COMPANIES} | {"NVDA": "Nvidia"}


class Kpi(BaseModel):  # LLM output (closed schema: no defaults)
    name: str
    value: float
    unit: Literal["billions", "millions", "percent", "megawatts", "gigawatts"]
    quote: str


class KpiTable(BaseModel):  # LLM output (closed schema: no defaults)
    period: str
    kpis: list[Kpi]


class KpiReader(StructuredAgent[KpiTable]):
    name = "capex_release_reader"
    output_schema = KpiTable
    tier = "fast"
    max_output_tokens = 8000  # the default 2048 can all go on reasoning, leaving no answer

    def __init__(self) -> None:
        self.model = get_settings().ai_capex.reader_model

    def system_prompt(self) -> str:
        return READ

    def user_prompt(self, *, company: str, wanted: list[str], text: str) -> str:
        asks = "\n".join(f"- {w}" for w in wanted)
        return (
            f"Company: {company}\n\nFigures wanted:\n{asks}\n\nEarnings release:\n{text[:80_000]}"
        )


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower()


def checked_kpis(table: KpiTable, text: str) -> KpiTable:
    """Only figures whose sentence is in the release and prints the value."""
    hay = _norm(text)
    keep = [
        k
        for k in table.kpis
        if _norm(k.quote) in hay
        and round(abs(k.value), 6) in {round(abs(n), 6) for n in numbers_in(k.quote)}
    ]
    return table.model_copy(update={"kpis": keep})


def read_release(ticker: str, release: Release, client, cache_dir: Path, reader=KpiReader) -> dict:
    """The checked figures of one release, read once and cached by accession."""
    path = cache_dir / "releases" / f"{ticker}-{release.accession}.json"
    if path.exists():
        return json.loads(path.read_text())
    text = client.release_text(release)
    table = checked_kpis(
        reader()(company=NAMES.get(ticker, ticker), wanted=WANTED[ticker], text=text), text
    )
    out = {
        "accession": release.accession,
        "filed": release.filed,
        "url": release.url,
        "period": table.period,
        "kpis": {k.name: {"value": k.value, "unit": k.unit, "quote": k.quote} for k in table.kpis},
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=1))
    return out
