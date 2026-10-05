"""Pure scoring math for the AI Adoption Index. No I/O."""

from __future__ import annotations

import statistics

from castelino.adoption.models import PILLARS

CLIP = 3.0


def talk_raw(depths: list[int], words: int) -> float | None:
    """Depth-weighted AI claims per 1,000 filing words. No text means missing, not zero."""
    if words <= 0:
        return None
    return sum(depths) / (words / 1000)


def hire_raw(ai: int, total: int) -> float | None:
    """Share of open postings that are AI/ML engineer roles."""
    if total <= 0:
        return None
    return ai / total


def spend_raw(capex: float | None, rnd: float | None, revenue: float | None) -> float | None:
    """(Capex + R&D) / revenue, trailing twelve months. Inputs are magnitudes."""
    if revenue is None or revenue <= 0:
        return None
    if capex is None and rnd is None:
        return None
    return ((capex or 0.0) + (rnd or 0.0)) / revenue


def pillar_scores(raw: dict[str, dict[str, float | None]]) -> dict[str, dict[str, float | None]]:
    """z-score each pillar across the whole universe, clip at +-3, map to 0-100 (average = 50)."""
    out: dict[str, dict[str, float | None]] = {t: {k: None for k in PILLARS} for t in raw}
    for k in PILLARS:
        vals = {t: r[k] for t, r in raw.items() if r.get(k) is not None}
        if not vals:
            continue
        # statistics is exact for identical values; a hand-rolled mean leaves sigma ~1e-17 for 0.1, 0.1, 0.1
        mu = statistics.fmean(vals.values())
        sigma = statistics.pstdev(vals.values())
        for t, v in vals.items():
            z = 0.0 if sigma == 0 else max(-CLIP, min(CLIP, (v - mu) / sigma))
            out[t][k] = 50 + (50 / CLIP) * z
    return out


def company_score(
    s: dict[str, float | None], weights: dict[str, float] | None = None
) -> tuple[float | None, int]:
    """Weighted mean over the pillars a company has; needs at least 2 of 3. Returns (score, pillars_used)."""
    w = weights or {k: 1 / len(PILLARS) for k in PILLARS}
    present = {k: v for k, v in s.items() if v is not None}
    if len(present) < 2:
        return None, len(present)
    return sum(w[k] * v for k, v in present.items()) / sum(w[k] for k in present), len(present)
