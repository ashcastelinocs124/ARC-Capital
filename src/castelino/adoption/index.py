"""Aggregate company scores into sector x size-bucket index cells. Pure functions, no I/O."""

from __future__ import annotations

from dataclasses import dataclass

from castelino.adoption.models import CompanyScore


@dataclass(frozen=True)
class Cell:
    sector: str | None  # None = the whole size bucket
    bucket: str
    n: int
    ew: float | None
    cw: float | None
    thin: bool


def aggregate(scores: list[CompanyScore], thin_below: int = 5) -> list[Cell]:
    """Equal-weighted and market-cap-weighted mean score per (sector, bucket) and per bucket."""
    groups: dict[tuple[str | None, str], list[CompanyScore]] = {}
    for cs in scores:
        if cs.score is None:
            continue
        c = cs.company
        groups.setdefault((c.sector, c.bucket), []).append(cs)
        groups.setdefault((None, c.bucket), []).append(cs)
    cells = []
    for (sector, bucket), rows in sorted(groups.items(), key=lambda kv: (kv[0][1], kv[0][0] or "")):
        n = len(rows)
        ew = sum(r.score for r in rows) / n
        capped = [(r.company.market_cap, r.score) for r in rows if r.company.market_cap > 0]
        cw = sum(m * s for m, s in capped) / sum(m for m, _ in capped) if capped else None
        cells.append(Cell(sector, bucket, n, ew, cw, n < thin_below))
    return cells


def _concentration(cell: Cell | None) -> float | None:
    if cell is None or cell.cw is None or cell.ew is None:
        return None
    return cell.cw - cell.ew


def headline(cells: list[Cell]) -> dict[str, float | None]:
    by = {c.bucket: c for c in cells if c.sector is None}
    large, mid, small = by.get("large"), by.get("mid"), by.get("small")
    large_ew = large.ew if large else None
    small_ew = small.ew if small else None
    return {
        "large_ew": large_ew,
        "mid_ew": mid.ew if mid else None,
        "small_ew": small_ew,
        "spread": (small_ew - large_ew) if large_ew is not None and small_ew is not None else None,
        "large_concentration": _concentration(large),
        "mid_concentration": _concentration(mid),
        "small_concentration": _concentration(small),
    }
