"""Resolve live audio stream URLs for scheduled Fed events."""
from __future__ import annotations

import re

FOMC_MONETARY_POLICY_PAGE = "https://www.federalreserve.gov/monetarypolicy.htm"

_YT_RX = re.compile(r"https?://(?:www\.)?(?:youtube\.com/watch\?v=|youtu\.be/)[\w\-]+")


def parse_fomc_live_url(html: str) -> str | None:
    """Find the first YouTube live URL in the FOMC monetary-policy page HTML."""
    m = _YT_RX.search(html)
    return m.group(0) if m else None
