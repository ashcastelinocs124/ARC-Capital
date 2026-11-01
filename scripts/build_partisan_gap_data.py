"""Bundle the Partisan Policy Gap study's outputs into one JSON for /dashboards/partisan-gap.

The study lives in github.com/ashcastelinocs124/spx-drawdown-risk-model (partisan-policy-gap/outputs).
It is a fixed 1921-2024 study, so the page ships this file instead of a Refresh job.

Usage: python3 -I scripts/build_partisan_gap_data.py <path to partisan-policy-gap/outputs>
"""

import csv
import json
import statistics
import sys
from pathlib import Path

OUT = (
    Path(__file__).resolve().parent.parent
    / "frontend/src/components/dashboards/partisanGap/data.json"
)
MIN_YEARS = 8  # a party mix needs this many years to rank as "best"


def num(v):
    if v == "":
        return None
    try:
        f = float(v)
    except ValueError:
        return v
    return int(f) if f.is_integer() and "." not in v else round(f, 5)


def read(src, name, keep=None):
    with open(src / name, newline="") as f:
        rows = [{k: num(v) for k, v in r.items()} for r in csv.DictReader(f)]
    return [{k: r[k] for k in keep} for r in rows] if keep else rows


def mean(xs):
    xs = [x for x in xs if x is not None]
    return round(statistics.fmean(xs), 5) if xs else None


def thirds(rows, key, out):
    """Average of `out` in the lower, middle and upper third of `key` (as d3.quantile, i.e. R-7)."""
    rows = [r for r in rows if r[key] is not None]
    q1, q2 = statistics.quantiles([r[key] for r in rows], n=3, method="inclusive")
    tests = [
        ("Narrow", lambda x: x <= q1),
        ("Middle", lambda x: q1 < x <= q2),
        ("Wide", lambda x: x > q2),
    ]
    res = []
    for bucket, t in tests:
        v = [r[out] for r in rows if t(r[key]) and r[out] is not None]
        res.append({"bucket": bucket, "mean": mean(v), "n": len(v)})
    return res


def main(src):
    src = Path(src)
    annual = read(
        src,
        "gap_annual.csv",
        [
            "year",
            "gap_index",
            "gap_change",
            "vote_gap_z",
            "econ_gap_z",
            "business_gap_z",
            "immig_gap_z",
            "foreign_gap_z",
            "sp_tr",
            "bond_tr",
            "rvol",
            "vix_avg",
        ],
    )
    legislative = read(
        src,
        "legislative_by_congress.csv",
        [
            "congress",
            "year",
            "platform_z",
            "vote_gap_z",
            "unity",
            "bipartisan",
            "consensus",
            "public_laws",
            "law_pages",
            "divided",
        ],
    )
    vix = [
        {"m": r["month"], "vix": r["vix"], "gap": r["gap_index"]}
        for r in read(src, "vix_monthly_slim.csv")
    ]
    combos = read(src, "combo_returns.csv")
    recent = read(src, "recent_windows.csv")
    post_tests = read(src, "post_election_tests.csv")

    outcomes = ["sp_tr", "bond_tr", "rvol", "vix_avg"]
    terciles = {
        o: thirds(
            [r for r in annual if o != "vix_avg" or 1990 <= r["year"] <= 2024], "gap_index", o
        )
        for o in outcomes
    }
    direction = {
        o: [
            {
                "bucket": b,
                "mean": mean(
                    [r[o] for r in annual if r["gap_change"] is not None and t(r["gap_change"])]
                ),
                "n": sum(
                    1
                    for r in annual
                    if r["gap_change"] is not None and t(r["gap_change"]) and r[o] is not None
                ),
            }
            for b, t in [("Narrowing", lambda x: x < 0), ("Widening", lambda x: x > 0)]
        ]
        for o in outcomes
    }
    measures = [
        ("public_laws", "Public laws enacted"),
        ("law_pages", "Pages of law enacted"),
        ("unity", "Party-unity vote share"),
        ("bipartisan", "Bipartisan vote share"),
        ("consensus", "Near-unanimous vote share"),
    ]
    leg_div = [
        {
            "measure": k,
            "label": lab,
            "unified": mean([r[k] for r in legislative if r["divided"] == 0]),
            "divided": mean([r[k] for r in legislative if r["divided"] == 1]),
        }
        for k, lab in measures
    ]
    late = [r for r in recent if r["start"] >= 1980]
    ps = [
        r[k]
        for r in post_tests
        for k in ("far_p", "gap_p", "gap_trend_p", "chg_p")
        if r[k] is not None
    ]
    avg = next(r for r in combos if r["government"] == "All")
    ranked = [r for r in combos if r["government"] != "All" and r["n"] >= MIN_YEARS]
    best = {k: max(ranked, key=lambda r: r[k]) for k in ("sp_tr", "bond_tr")}

    data = {
        "annual": annual,
        "regressions": read(src, "gap_regressions.csv"),
        "components": read(src, "gap_components.csv"),
        "value": read(src, "gap_value.csv"),
        "recent": recent,
        "vix": vix,
        "vix_tests": read(src, "vix_tests.csv"),
        "control_cells": read(
            src, "gap_control_cells.csv", ["outcome", "government", "beliefs", "mean", "n"]
        ),
        "control_tests": read(src, "gap_control_tests.csv"),
        "combos": combos,
        "control_detail": read(src, "control_detail.csv"),
        "post_cells": read(src, "post_election_cells.csv"),
        "post_tests": post_tests,
        "legislative": legislative,
        "leg_tests": read(src, "legislative_tests.csv"),
        "leg_topics": read(src, "legislative_topics.csv"),
        "correlations": read(src, "correlations.csv"),
        "derived": {
            "terciles": terciles,
            "direction": direction,
            "vix_terciles": thirds([{"g": r["gap"], "v": r["vix"]} for r in vix], "g", "v"),
            "leg_div": leg_div,
            "recent_sig": {
                "total": len(late),
                "simple": sum(r["p"] < 0.05 for r in late),
                "trend": sum(r["p_trend"] < 0.05 for r in late),
            },
            "post_sig": {"total": len(ps), "sig": sum(p < 0.05 for p in ps)},
            "best": {
                k: {"combo": r["combo"], "value": r[k], "n": r["n"], "avg": avg[k]}
                for k, r in best.items()
            },
            "min_years": MIN_YEARS,
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, separators=(",", ":"), ensure_ascii=False) + "\n")
    print(f"wrote {OUT} ({OUT.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main(sys.argv[1])
