from __future__ import annotations

import re

from castelino.agents.update.models import DailyUpdate, MarketSnapshot

# ponytail: only figures carrying a unit are checked; plain counts like "day 10" or years pass
# unchecked. The guard verifies a figure exists in the snapshot, not which series it belongs to.
_UNIT = r"(%|percent|per cent|percentage points?|pp|basis points?|bps|bp)"
_FIG = re.compile(r"(?<![\w.])([-+]?)(\d+(?:\.\d+)?)\s*" + _UNIT + r"(?![a-z])", re.I)


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


def _supported(
    value: float, decimals: int, signed: bool, nums: set[float], probs: set[float]
) -> bool:
    tol = 0.5 * 10**-decimals + 1e-9  # half a unit of the displayed precision
    cands = list(nums) + [p * 100 for p in probs]  # probabilities may be shown as percents
    if signed:
        return any(abs(n - value) <= tol for n in cands)
    return any(abs(abs(n) - abs(value)) <= tol for n in cands)


def _texts(u: DailyUpdate) -> list[str]:
    out = [u.headline, u.economy, u.asset_classes, u.predictions_changed]
    out += [t.text for t in u.themes_touched] + [t.text for t in u.new_themes]
    out += [r.text for r in u.sector_reads]
    return out


def find_unsupported(update: DailyUpdate, snapshot: MarketSnapshot) -> list[str]:
    dump = snapshot.model_dump()
    probs: set[float] = set()
    _numbers(dump.pop("prediction"), probs)
    nums: set[float] = set()
    _numbers(dump, nums)
    nums |= probs
    bad: set[str] = set()
    for text in _texts(update):
        for m in _FIG.finditer(text):
            sign, digits = m.group(1), m.group(2)
            decimals = len(digits.split(".")[1]) if "." in digits else 0
            value = float(sign + digits)
            if not _supported(value, decimals, bool(sign), nums, probs):
                bad.add(m.group(0).strip())
    return sorted(bad)
