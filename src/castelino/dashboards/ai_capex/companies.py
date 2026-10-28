"""The companies on the dashboard, in page order."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class Co:
    ticker: str
    name: str
    kind: Literal["hyperscaler", "neocloud"]
    xbrl: bool = True  # False: files no quarterly XBRL (Nebius: 20-F + 6-K releases only)


COMPANIES = [
    Co("MSFT", "Microsoft", "hyperscaler"),
    Co("GOOGL", "Alphabet", "hyperscaler"),
    Co("AMZN", "Amazon", "hyperscaler"),
    Co("META", "Meta", "hyperscaler"),
    Co("ORCL", "Oracle", "hyperscaler"),
    Co("CRWV", "CoreWeave", "neocloud"),
    Co("NBIS", "Nebius", "neocloud", xbrl=False),
    Co("IREN", "IREN", "neocloud"),
]
DASHBOARD_TICKERS = {c.ticker for c in COMPANIES}
PRIVATE = ["Lambda", "Crusoe"]  # private neoclouds: power online vs contracted, cited search only
