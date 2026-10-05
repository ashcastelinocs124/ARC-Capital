"""Deterministic quote guard: an adoption claim counts only if its quote is in the source text."""

from __future__ import annotations

import re

from castelino.adoption.models import Claim

_QUOTES = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"'})


def _norm(s: str) -> str:
    s = re.sub(r"\s+", " ", s.translate(_QUOTES))
    s = re.sub(
        r" ([.,;:!?)\]])", r"\1", s
    )  # html.parser puts a space at tag boundaries ("learning .")
    return s.strip().casefold()


def keep_verified(claims: list[Claim], text: str) -> tuple[list[Claim], list[Claim]]:
    """Split claims into (kept, dropped). Dropped: quote absent from text, depth not in 1..3, or duplicate quote."""
    hay = _norm(text)
    kept: list[Claim] = []
    dropped: list[Claim] = []
    seen: set[str] = set()
    for c in claims:
        q = _norm(c.quote)
        if not q or c.depth not in (1, 2, 3) or q not in hay or q in seen:
            dropped.append(c)
            continue
        seen.add(q)
        kept.append(c)
    return kept, dropped
