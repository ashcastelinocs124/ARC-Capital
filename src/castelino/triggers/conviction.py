"""Directional Conviction Ledger — accumulates headline signals over time.

Every scored headline (materiality ≥ 0.3) gets appended with its growth and
inflation direction. Four decayed sums (growth_bullish, growth_bearish,
inflation_bullish, inflation_bearish) are computed on each tick using an
exponential half-life decay. The pipeline fires when any dimension sum or
dimension spread crosses the configured threshold.

All math is deterministic — no LLM calls.
"""

from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from castelino.config import get_settings
from castelino.triggers.significance import HeadlineScore

log = logging.getLogger(__name__)


@dataclass
class ConvictionSnapshot:
    growth_bullish: float
    growth_bearish: float
    inflation_bullish: float
    inflation_bearish: float

    @property
    def dominant_dimension(self) -> str:
        sums = {
            "growth_bullish": self.growth_bullish,
            "growth_bearish": self.growth_bearish,
            "inflation_bullish": self.inflation_bullish,
            "inflation_bearish": self.inflation_bearish,
        }
        return max(sums, key=sums.get)  # type: ignore[arg-type]

    @property
    def growth_spread(self) -> float:
        return abs(self.growth_bullish - self.growth_bearish)

    @property
    def inflation_spread(self) -> float:
        return abs(self.inflation_bullish - self.inflation_bearish)

    @property
    def max_single(self) -> float:
        return max(
            self.growth_bullish,
            self.growth_bearish,
            self.inflation_bullish,
            self.inflation_bearish,
        )

    @property
    def max_spread(self) -> float:
        return max(self.growth_spread, self.inflation_spread)


@dataclass
class ConvictionFireResult:
    should_fire: bool
    reason: str
    snapshot: ConvictionSnapshot
    contributing_headlines: list[str]


def _ledger_path() -> Path:
    return get_settings().resolved_paths.data / "conviction_ledger.json"


def _read_ledger() -> list[dict]:
    p = _ledger_path()
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text())
        return data.get("entries", [])
    except (json.JSONDecodeError, KeyError):
        log.warning("conviction ledger corrupt — resetting")
        return []


def _write_ledger(entries: list[dict]) -> None:
    p = _ledger_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "entries": entries,
        "last_computed": datetime.now(UTC).isoformat(),
    }
    p.write_text(json.dumps(data, indent=2))


def append(scores: list[HeadlineScore]) -> int:
    """Append scored headlines to the ledger. Returns count of entries added."""
    entries = _read_ledger()
    existing_ids = {e["headline_id"] for e in entries}
    now = datetime.now(UTC).isoformat()
    added = 0
    for s in scores:
        if s.materiality < 0.3:
            continue
        if s.headline_id in existing_ids:
            continue
        entries.append({
            "headline_id": s.headline_id,
            "title": s.title,
            "materiality": s.materiality,
            "growth_direction": s.growth_direction,
            "inflation_direction": s.inflation_direction,
            "timestamp": now,
        })
        added += 1
    if added:
        _write_ledger(entries)
        log.info("conviction ledger: +%d entries (total %d)", added, len(entries))
    return added


def prune() -> int:
    """Remove entries older than ledger_ttl_hours. Returns count removed."""
    cfg = get_settings().conviction
    entries = _read_ledger()
    cutoff = datetime.now(UTC) - timedelta(hours=cfg.ledger_ttl_hours)
    kept = [e for e in entries if datetime.fromisoformat(e["timestamp"]) >= cutoff]
    removed = len(entries) - len(kept)
    if removed:
        _write_ledger(kept)
        log.info("conviction ledger pruned: %d entries removed", removed)
    return removed


def _decay(materiality: float, age_hours: float, half_life: float) -> float:
    return materiality * math.pow(2, -age_hours / half_life)


def compute() -> ConvictionSnapshot:
    """Compute the four directional decayed sums from the current ledger."""
    cfg = get_settings().conviction
    entries = _read_ledger()
    now = datetime.now(UTC)

    sums = {
        "growth_bullish": 0.0,
        "growth_bearish": 0.0,
        "inflation_bullish": 0.0,
        "inflation_bearish": 0.0,
    }

    for e in entries:
        ts = datetime.fromisoformat(e["timestamp"])
        age_hours = (now - ts).total_seconds() / 3600
        decayed = _decay(e["materiality"], age_hours, cfg.half_life_hours)

        gd = e.get("growth_direction", "neutral")
        if gd == "up":
            sums["growth_bullish"] += decayed
        elif gd == "down":
            sums["growth_bearish"] += decayed

        inf = e.get("inflation_direction", "neutral")
        if inf == "up":
            sums["inflation_bullish"] += decayed
        elif inf == "down":
            sums["inflation_bearish"] += decayed

    return ConvictionSnapshot(**sums)


def contributing_headlines(dimension: str | None = None) -> list[str]:
    """Return headline titles that contribute to the dominant (or given) dimension."""
    entries = _read_ledger()
    if dimension is None:
        dimension = compute().dominant_dimension

    dim_map = {
        "growth_bullish": ("growth_direction", "up"),
        "growth_bearish": ("growth_direction", "down"),
        "inflation_bullish": ("inflation_direction", "up"),
        "inflation_bearish": ("inflation_direction", "down"),
    }
    if dimension not in dim_map:
        return []

    field, value = dim_map[dimension]
    cfg = get_settings().conviction
    now = datetime.now(UTC)

    scored: list[tuple[float, str]] = []
    for e in entries:
        if e.get(field) != value:
            continue
        age_hours = (now - datetime.fromisoformat(e["timestamp"])).total_seconds() / 3600
        decayed = _decay(e["materiality"], age_hours, cfg.half_life_hours)
        scored.append((decayed, e["title"]))

    scored.sort(reverse=True)
    return [title for _, title in scored]


def check_fire() -> ConvictionFireResult:
    """Check whether the conviction ledger warrants firing the pipeline."""
    cfg = get_settings().conviction
    prune()
    snap = compute()

    if snap.max_single >= cfg.fire_threshold:
        return ConvictionFireResult(
            should_fire=True,
            reason=f"{snap.dominant_dimension} = {snap.max_single:.2f} ≥ {cfg.fire_threshold}",
            snapshot=snap,
            contributing_headlines=contributing_headlines(snap.dominant_dimension),
        )

    if snap.max_spread >= cfg.spread_threshold:
        spread_dim = "growth" if snap.growth_spread >= snap.inflation_spread else "inflation"
        return ConvictionFireResult(
            should_fire=True,
            reason=f"{spread_dim} spread = {snap.max_spread:.2f} ≥ {cfg.spread_threshold}",
            snapshot=snap,
            contributing_headlines=contributing_headlines(snap.dominant_dimension),
        )

    return ConvictionFireResult(
        should_fire=False,
        reason=f"max_single={snap.max_single:.2f}, max_spread={snap.max_spread:.2f} — below thresholds",
        snapshot=snap,
        contributing_headlines=[],
    )
