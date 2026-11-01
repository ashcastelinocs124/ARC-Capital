"""Bundle the Partisan Policy Gap study's outputs into one JSON for /dashboards/partisan-gap.

The study lives in github.com/ashcastelinocs124/spx-drawdown-risk-model (partisan-policy-gap/outputs).
It is a fixed 1921-2024 study, so the page ships this file instead of a Refresh job.

Usage: python3 -I scripts/build_partisan_gap_data.py <path to partisan-policy-gap/outputs>
"""

import csv
import json
import random
import statistics
import sys
from pathlib import Path

OUT = (
    Path(__file__).resolve().parent.parent
    / "frontend/src/components/dashboards/partisanGap/data.json"
)
MIN_YEARS = 8  # a party mix needs this many years to rank as "best"
ERA = 5  # years either side: a mix's years are measured against the 11 years around each one
SHUFFLES = 20_000


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


def excess(annual, k):
    """Each year's return minus the average of the 11 years around it (fewer at the ends), so a party
    mix is judged against its own era: 1930s years against the 1930s, 2010s years against the 2010s."""
    r = {a["year"]: a[k] for a in annual if a[k] is not None}
    return {
        y: v - statistics.fmean(r[t] for t in range(y - ERA, y + ERA + 1) if t in r)
        for y, v in r.items()
    }


def shuffle_p(ex, years, rng):
    """Share of random draws whose gap to the other years is at least as wide as these years' gap.
    Draws take whole Congresses (2-year blocks), since a mix's years come in runs."""
    ys = sorted(ex)
    blocks = [ys[i : i + 2] for i in range(0, len(ys), 2)]
    total, n_all, n = sum(ex.values()), len(ex), len(years)

    def gap(pick):
        s = sum(ex[y] for y in pick)
        return s / len(pick) - (total - s) / (n_all - len(pick))

    obs = abs(gap(years))
    hits = 0
    for _ in range(SHUFFLES):
        pick = [y for b in rng.sample(blocks, -(-n // 2)) for y in b][:n]
        hits += abs(gap(pick)) >= obs
    return round(hits / SHUFFLES, 4)


def era_rows(rows, name, ex, rng=None):
    """Era-adjusted average returns per party mix; with `rng`, a shuffle p-value against the rest."""
    out = []
    for r in rows:
        if r["government"] == "All":
            continue
        ys = [int(y) for y in str(r["years"]).split(", ")]
        e = {"name": r[name], "n": len(ys)}
        for k, xs in ex.items():
            e[k] = mean([xs[y] for y in ys])
            if rng:
                e[k + "_p"] = shuffle_p(xs, ys, rng)
        out.append(e)
    return sorted(out, key=lambda e: -e["sp_tr"])


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
    ex = {k: excess(annual, k) for k in ("sp_tr", "bond_tr")}
    era = era_rows(combos, "combo", ex, random.Random(1))
    ranked = [e for e in era if e["n"] >= MIN_YEARS]
    best = {k: max(ranked, key=lambda e: e[k]) for k in ex}
    control_detail = read(src, "control_detail.csv")

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
        "control_detail": control_detail,
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
            "era": {
                "window": 2 * ERA + 1,
                "combos": era,
                "detail": era_rows(control_detail, "setup", ex),
            },
            "best": {
                k: {"combo": e["name"], "value": e[k], "n": e["n"], "p": e[k + "_p"]}
                for k, e in best.items()
            },
            "min_years": MIN_YEARS,
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, separators=(",", ":"), ensure_ascii=False) + "\n")
    print(f"wrote {OUT} ({OUT.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main(sys.argv[1])
