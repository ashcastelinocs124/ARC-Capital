"""Shared types for the AI Adoption Index (research metric; not part of the trading pipeline)."""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel

BUCKETS = ("large", "small")
PILLARS = ("talk", "hire", "spend")
GICS_SECTORS = (
    "Information Technology",
    "Communication Services",
    "Consumer Discretionary",
    "Financials",
    "Health Care",
    "Industrials",
    "Consumer Staples",
    "Energy",
    "Utilities",
    "Materials",
    "Real Estate",
)


class Claim(BaseModel):
    """One adoption claim: a verbatim filing quote and its depth (1 pilot, 2 deployed, 3 revenue-linked)."""

    quote: str
    depth: int


class ExtractedClaims(BaseModel):
    claims: list[Claim]


@dataclass(frozen=True)
class Company:
    ticker: str
    bucket: str
    sector: str
    market_cap: float
    name: str = ""  # company name for display, e.g. "Apple Inc."


@dataclass
class CompanyScore:
    company: Company
    raw: dict[str, float | None]
    s: dict[str, float | None]
    score: float | None
    pillars_used: int
    hire_snapshot: float | None = None
    accession: str | None = None
