from __future__ import annotations

import re

from castelino.agents.update.models import DailyUpdate, MarketSnapshot

# ponytail: only figures carrying a unit (%, bp, pp) are checked; plain counts like
# "day 10" or years pass unchecked. Extend the pattern if the model starts inventing bare numbers.
_FIG = re.compile(r"(?<![\w.])([-+]?\d+(?:\.\d+)?)\s*(%|bp|pp)")


def _numbers(obj, out: set[float]) -> None:
    if isinstance(obj, bool):
        return
    if isinstance(obj, (int, float)):
        out.add(float(obj))
    elif isinstance(obj, dict):
        for v in obj.values():
            _numbers(v, out)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            _numbers(v, out)


def _supported(x: float, nums: set[float]) -> bool:
    # direct match (rounding slack) or a probability shown as a percent (0.71 -> 71%)
    return any(abs(abs(n) - x) <= 0.051 or abs(abs(n) * 100 - x) <= 0.51 for n in nums)


def _texts(u: DailyUpdate) -> list[str]:
    out = [u.headline, u.economy, u.asset_classes, u.predictions_changed]
    out += [t.text for t in u.themes_touched] + [t.text for t in u.new_themes]
    out += [r.text for r in u.sector_reads]
    return out


def find_unsupported(update: DailyUpdate, snapshot: MarketSnapshot) -> list[str]:
    nums: set[float] = set()
    _numbers(snapshot.model_dump(), nums)
    bad: set[str] = set()
    for text in _texts(update):
        for m in _FIG.finditer(text):
            if not _supported(abs(float(m.group(1))), nums):
                bad.add(m.group(0).strip())
    return sorted(bad)
