"""Quarterly fundamentals from SEC XBRL company facts. Code only: no model touches these numbers.

Cash flow statements in a 10-Q are year to date, so a quarter is a 6- or 9-month value minus the one
before it, and the fourth quarter is the annual value minus nine months. Every quarter is named by the
calendar quarter holding its midpoint (Oracle's Jun–Aug is Q3, Nvidia's late-Apr–late-Jul is Q2).
Money is in $bn."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

TAGS: dict[str, list[str]] = {  # tried in order; an earlier tag wins any period it covers
    "capex": [
        "PaymentsToAcquirePropertyPlantAndEquipment",
        "PaymentsToAcquireProductiveAssets",
        "PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities",
    ],
    "revenue": ["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues", "Revenue"],
    "ocf": ["NetCashProvidedByUsedInOperatingActivities", "CashFlowsFromUsedInOperatingActivities"],
    "debt_issued": [
        "ProceedsFromIssuanceOfLongTermDebt",
        "ProceedsFromIssuanceOfSeniorLongTermDebt",
        "ProceedsFromIssuanceOfDebt",
    ],
    "debt_repaid": ["RepaymentsOfLongTermDebt", "RepaymentsOfDebt"],
    "convert_issued": ["ProceedsFromConvertibleDebt", "ProceedsFromIssuanceOfConvertibleDebt"],
    "shares_issued": ["ProceedsFromIssuanceOfCommonStock"],
    "buybacks": ["PaymentsForRepurchaseOfCommonStock"],
    "interest_paid": ["InterestPaidNet", "InterestPaid"],
    # most hyperscalers report interest paid only yearly; the rate falls back to quarterly expense
    "interest_expense": ["InterestExpense", "InterestExpenseDebt", "InterestExpenseNonoperating"],
    # instants (balance sheet)
    "cash": ["CashAndCashEquivalentsAtCarryingValue", "CashAndCashEquivalents"],
    # Oracle tags its debt as notes payable (quarterly only in its own tags, so it has year-end
    # balances). Never DebtInstrumentCarryingAmount: that's one bond issue, not the total.
    "debt": ["LongTermDebt", "LongTermNotesPayable", "LongTermDebtNoncurrent"],
    # interest expense includes interest on finance leases, so leases join the rate's denominator
    "leases": ["FinanceLeaseLiability"],
    "rpo": ["RevenueRemainingPerformanceObligation"],
}
INSTANTS = ("cash", "debt", "leases", "rpo")
TAXONOMIES = ("us-gaap", "ifrs-full")
MIX_KEYS = ("own_cash", "debt", "convertible", "shares", "cash_on_hand")


def _d(s: str) -> date:
    return date.fromisoformat(s)


def _rows(facts: dict, concept: str) -> list[dict]:
    """USD facts for a concept: per tag the latest-filed value of each period, tags merged in order."""
    merged: dict[tuple, dict] = {}
    for tag in TAGS[concept]:
        per_tag: dict[tuple, dict] = {}
        for tax in TAXONOMIES:
            node = facts.get("facts", {}).get(tax, {}).get(tag, {})
            for r in node.get("units", {}).get("USD", []):
                k = (r.get("start"), r["end"])
                if k not in per_tag or r.get("filed", "") > per_tag[k].get("filed", ""):
                    per_tag[k] = r
        for k, r in per_tag.items():
            merged.setdefault(k, r)
    return list(merged.values())


def label(start: date, end: date) -> str:
    mid = start + (end - start) / 2
    return f"{mid.year}Q{(mid.month - 1) // 3 + 1}"


def _is_quarter(start: date, end: date) -> bool:
    return 80 <= (end - start).days + 1 <= 100


def quarterly(facts: dict, concept: str) -> dict[str, tuple[float, str]]:
    """Calendar-quarter label ("2026Q2") -> (value in $bn, period end), oldest first."""
    rows = [r for r in _rows(facts, concept) if r.get("start")]
    direct: dict[str, tuple[float, str]] = {}
    derived: dict[str, tuple[float, str]] = {}
    groups: dict[str, list[dict]] = {}
    for r in rows:
        s, e = _d(r["start"]), _d(r["end"])
        if _is_quarter(s, e):
            direct[label(s, e)] = (r["val"] / 1e9, r["end"])
        groups.setdefault(r["start"], []).append(r)
    for group in groups.values():  # year to date: each value minus the one before it
        group.sort(key=lambda r: r["end"])
        for prev, r in zip(group, group[1:], strict=False):
            s, e = _d(prev["end"]) + timedelta(days=1), _d(r["end"])
            if _is_quarter(s, e):
                derived[label(s, e)] = ((r["val"] - prev["val"]) / 1e9, r["end"])
    out = {**derived, **direct}  # a reported 3-month value beats a derived one
    return dict(sorted(out.items()))


def instant(facts: dict, concept: str) -> dict[str, float]:
    """Period end -> balance in $bn, oldest first."""
    rows = [r for r in _rows(facts, concept) if not r.get("start")]
    return dict(sorted((r["end"], r["val"] / 1e9) for r in rows))


def _at(balances: dict[str, float], day: date, tolerance: int = 10) -> float | None:
    """The balance reported nearest `day`, within `tolerance` days."""
    near = [(abs((_d(k) - day).days), v) for k, v in balances.items()]
    near = [x for x in near if x[0] <= tolerance]
    return min(near)[1] if near else None


def _largest_remainder(parts: dict[str, float]) -> dict[str, int] | None:
    total = sum(parts.values())
    if total <= 0:
        return None
    raw = {k: v / total * 100 for k, v in parts.items()}
    out = {k: int(v) for k, v in raw.items()}
    for k in sorted(raw, key=lambda k: raw[k] - out[k], reverse=True)[: 100 - sum(out.values())]:
        out[k] += 1
    return out


@dataclass
class Fundamentals:
    quarters: list[dict] = field(default_factory=list)
    ttm: dict = field(default_factory=dict)
    mix: dict[str, int] | None = None
    cents_per_dollar: int | None = None
    cents_year_ago: int | None = None
    ocf_share: int | None = None  # TTM capex as a % of TTM operating cash; None when that cash <= 0
    avg_rate: float | None = None
    yoy_pct: int | None = None
    rpo: float | None = None
    as_of: str | None = None


def _r(v: float | None, n: int = 2) -> float | None:
    return None if v is None else round(v, n)


def fundamentals(facts: dict) -> Fundamentals:
    cap = quarterly(facts, "capex")
    if not cap:
        return Fundamentals()
    q = {c: quarterly(facts, c) for c in TAGS if c not in INSTANTS + ("capex",)}
    labels = list(cap)[-10:]
    last4 = labels[-4:]
    quarters = [
        {
            "q": lab,
            "end": cap[lab][1],
            "capex": _r(cap[lab][0]),
            "revenue": _r(q["revenue"].get(lab, (None,))[0]),
            "ocf": _r(q["ocf"].get(lab, (None,))[0]),
        }
        for lab in labels
    ]

    def total(series: dict, required: bool) -> float | None:
        vals = [series.get(lab, (None,))[0] for lab in last4]
        if None in vals:
            return None if required else sum(v or 0 for v in vals)
        return sum(vals)

    end = _d(cap[labels[-1]][1])
    start = _d(cap[last4[0]][1]) - timedelta(days=91)  # the balance date before the window
    cash = instant(facts, "cash")
    c0, c1 = _at(cash, start), _at(cash, end)
    ttm = {
        "capex": total(cap, True),
        "ocf": total(q["ocf"], True),
        "revenue": total(q["revenue"], True),
        "debt_net": total(q["debt_issued"], False) - total(q["debt_repaid"], False),
        "convert_net": total(q["convert_issued"], False),
        "equity_net": total(q["shares_issued"], False) - total(q["buybacks"], False),
        "cash_drawdown": (c0 - c1) if c0 is not None and c1 is not None else 0.0,
        "interest_paid": total(q["interest_paid"], True)
        if total(q["interest_paid"], True) is not None
        else total(q["interest_expense"], True),
    }
    parts = {
        "own_cash": ttm["ocf"] or 0.0,
        "debt": ttm["debt_net"],
        "convertible": ttm["convert_net"],
        "shares": ttm["equity_net"],
        "cash_on_hand": ttm["cash_drawdown"],
    }
    mix = _largest_remainder({k: max(0.0, v) for k, v in parts.items()})

    def cents(lab: str | None) -> int | None:
        c, rv = cap.get(lab, (None,))[0], q["revenue"].get(lab, (None,))[0]
        return round(c / rv * 100) if c is not None and rv else None

    year_ago = labels[-5] if len(labels) >= 5 else None
    debt, leases = instant(facts, "debt"), instant(facts, "leases")
    ends = [start] + [_d(cap[lab][1]) for lab in last4]
    debts = [v + (_at(leases, d) or 0.0) for d in ends if (v := _at(debt, d)) is not None]
    rate = None
    if ttm["interest_paid"] is not None and debts and sum(debts) > 0:
        rate = round(ttm["interest_paid"] / (sum(debts) / len(debts)) * 100, 1)
    rpo = instant(facts, "rpo")
    return Fundamentals(
        quarters=quarters,
        ttm={k: _r(v) for k, v in ttm.items()},
        mix=mix,
        cents_per_dollar=cents(labels[-1]),
        cents_year_ago=cents(year_ago),
        ocf_share=round(ttm["capex"] / ttm["ocf"] * 100)
        if ttm["capex"] is not None and ttm["ocf"] and ttm["ocf"] > 0
        else None,
        avg_rate=rate,
        yoy_pct=round((cap[labels[-1]][0] / cap[year_ago][0] - 1) * 100)
        if year_ago and cap[year_ago][0]
        else None,
        rpo=_r(list(rpo.values())[-1], 1) if rpo else None,
        as_of=cap[labels[-1]][1],
    )
