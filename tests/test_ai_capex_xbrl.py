from castelino.dashboards.ai_capex import xbrl

FY = "2025-07-01"  # a July fiscal year, like Microsoft's


def fact(end, val_bn, start=None, filed="2026-08-01"):
    f = {"end": end, "val": val_bn * 1e9, "filed": filed, "form": "10-Q"}
    if start:
        f["start"] = start
    return f


def facts(gaap=None, ifrs=None):
    wrap = lambda d: {t: {"units": {"USD": rows}} for t, rows in (d or {}).items()}  # noqa: E731
    return {"facts": {"us-gaap": wrap(gaap), "ifrs-full": wrap(ifrs)}}


YTD_CAPEX = [  # cash flow statements are year to date: 3, 6, 9 and 12 months
    fact("2025-09-30", 10, FY),
    fact("2025-12-31", 25, FY),
    fact("2026-03-31", 45, FY),
    fact("2026-06-30", 70, FY),
]


def test_ytd_becomes_quarters():
    q = xbrl.quarterly(facts({"PaymentsToAcquirePropertyPlantAndEquipment": YTD_CAPEX}), "capex")
    assert {k: round(v[0], 6) for k, v in q.items()} == {
        "2025Q3": 10, "2025Q4": 15, "2026Q1": 20, "2026Q2": 25,
    }  # fmt: skip
    assert q["2026Q2"][1] == "2026-06-30"


def test_restated_duplicate_keeps_latest_filed():
    rows = [
        fact("2025-09-30", 10, FY, filed="2025-10-29"),
        fact("2025-09-30", 11, FY, filed="2026-10-28"),  # restated in a later filing
    ]
    q = xbrl.quarterly(facts({"PaymentsToAcquirePropertyPlantAndEquipment": rows}), "capex")
    assert round(q["2025Q3"][0], 6) == 11


def test_direct_quarter_wins_and_tags_merge_in_order():
    rows = [fact("2026-03-31", 30, "2026-01-01")]  # a 3-month fact, as income statements report
    older = [fact("2025-12-31", 28, "2025-10-01")]  # an older tag carries an earlier quarter
    q = xbrl.quarterly(
        facts({"RevenueFromContractWithCustomerExcludingAssessedTax": rows, "Revenues": older}),
        "revenue",
    )
    assert {k: round(v[0], 6) for k, v in q.items()} == {"2026Q1": 30, "2025Q4": 28}


def test_midpoint_label():
    oracle = [fact("2026-08-31", 5, "2026-06-01")]  # Jun–Aug: mostly July and August
    nvidia = [fact("2026-07-27", 7, "2026-04-28")]  # Apr 28–Jul 27: mostly May and June
    tag = "PaymentsToAcquirePropertyPlantAndEquipment"
    assert list(xbrl.quarterly(facts({tag: oracle}), "capex")) == ["2026Q3"]
    assert list(xbrl.quarterly(facts({tag: nvidia}), "capex")) == ["2026Q2"]


def test_ifrs_revenue_found():
    q = xbrl.quarterly(facts(ifrs={"Revenue": [fact("2026-06-30", 2, "2026-04-01")]}), "revenue")
    assert round(q["2026Q2"][0], 6) == 2


def _company(ocf=100.0, debt_issued=30.0, debt_repaid=0.0, shares=0.0, buybacks=20.0):
    """Four quarters ending 2026Q2, with TTM totals split evenly across them."""
    ends = [("2025-07-01", "2025-09-30"), ("2025-10-01", "2025-12-31"),
            ("2026-01-01", "2026-03-31"), ("2026-04-01", "2026-06-30")]  # fmt: skip
    q = lambda total: [fact(e, total / 4, s) for s, e in ends]  # noqa: E731
    return facts(
        {
            "PaymentsToAcquirePropertyPlantAndEquipment": q(80),
            "RevenueFromContractWithCustomerExcludingAssessedTax": q(400),
            "NetCashProvidedByUsedInOperatingActivities": q(ocf),
            "ProceedsFromIssuanceOfLongTermDebt": q(debt_issued),
            "RepaymentsOfLongTermDebt": q(debt_repaid),
            "ProceedsFromIssuanceOfCommonStock": q(shares),
            "PaymentsForRepurchaseOfCommonStock": q(buybacks),
            "InterestPaidNet": q(4),
            "CashAndCashEquivalentsAtCarryingValue": [fact("2025-06-30", 50), fact("2026-06-30", 50)],
            "LongTermDebt": [fact(e, 100) for e in ("2025-06-30", "2025-09-30", "2025-12-31", "2026-03-31", "2026-06-30")],
            "RevenueRemainingPerformanceObligation": [fact("2026-06-30", 682)],
        }
    )  # fmt: skip


def test_mix_sums_to_100_and_negatives_are_zero():
    f = xbrl.fundamentals(_company())  # ocf 100, debt_net +30, equity_net −20, no cash drawn
    assert f.mix == {"own_cash": 77, "debt": 23, "convertible": 0, "shares": 0, "cash_on_hand": 0}
    assert sum(f.mix.values()) == 100
    assert f.cents_per_dollar == 20  # 20 of capex on 100 of revenue
    assert f.ocf_share == 80  # 80 of capex on 100 of operating cash (last 4 quarters)
    assert f.rpo == 682
    assert f.as_of == "2026-06-30"


def test_negative_ocf():
    f = xbrl.fundamentals(_company(ocf=-5.0))
    assert f.ocf_share is None
    assert f.mix["own_cash"] == 0
    assert f.mix["debt"] == 100


def test_avg_rate():
    # 4 of interest a year on 100 of debt at each of the last 5 quarter ends
    assert xbrl.fundamentals(_company()).avg_rate == 4.0


def test_avg_rate_falls_back_to_interest_expense():
    # most hyperscalers report interest paid only once a year; interest expense is quarterly
    f = _company()
    gaap = f["facts"]["us-gaap"]
    gaap["InterestExpense"] = gaap.pop("InterestPaidNet")
    gaap["InterestExpense"]["units"]["USD"] = [
        dict(r, val=r["val"] * 2) for r in gaap["InterestExpense"]["units"]["USD"]
    ]
    assert xbrl.fundamentals(f).avg_rate == 8.0


def test_avg_rate_counts_finance_leases_and_notes_payable():
    # interest expense includes lease interest (Microsoft: $71bn of finance leases), so leases join
    # the denominator; Oracle tags its debt as notes payable, not LongTermDebt
    f = _company()
    gaap = f["facts"]["us-gaap"]
    gaap["LongTermNotesPayable"] = gaap.pop("LongTermDebt")
    gaap["FinanceLeaseLiability"] = {
        "units": {"USD": [dict(r) for r in gaap["LongTermNotesPayable"]["units"]["USD"]]}
    }
    assert xbrl.fundamentals(f).avg_rate == 2.0  # 4 a year on 100 of notes + 100 of leases


def test_avg_rate_from_one_balance_and_never_per_instrument():
    # Oracle's 10-Qs tag total debt only in its own tags: one year-end balance is all there is.
    # DebtInstrumentCarryingAmount is one bond issue, never the total, so it's not read.
    f = _company()
    gaap = f["facts"]["us-gaap"]
    gaap["LongTermDebt"]["units"]["USD"] = [fact("2026-06-30", 100)]
    assert xbrl.fundamentals(f).avg_rate == 4.0
    gaap["DebtInstrumentCarryingAmount"] = gaap.pop("LongTermDebt")
    assert xbrl.fundamentals(f).avg_rate is None
