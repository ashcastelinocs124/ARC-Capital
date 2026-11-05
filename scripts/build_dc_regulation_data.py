"""Bundle the AI data center regulatory index study into JSON for /dashboards/data-centers.

The study lives in github.com/ashcastelinocs124/spx-drawdown-risk-model (ai-datacenter-regulatory-index).
It is a fixed Nov 4, 2026 snapshot, so the page ships these files instead of a Refresh job:
data.json (winners, investments, polls, index scores) and evidence.json (the 1,000 indicator rows,
loaded only by the state detail). Scores are recomputed from the evidence the way the study's
dashboard does, and must match its outputs/index_scores.csv.

Usage: python3 -I scripts/build_dc_regulation_data.py <path to ai-datacenter-regulatory-index>
"""

import csv
import json
import statistics
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "frontend/src/components/dashboards/dcRegulation"
COMPS = [("Power", 0.30), ("Permitting", 0.25), ("Tax", 0.15), ("Environment", 0.15),
         ("Operating rules", 0.10), ("Administration", 0.05)]  # fmt: skip
NAMES = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas", "CA": "California", "CO": "Colorado",
    "CT": "Connecticut", "DE": "Delaware", "FL": "Florida", "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho",
    "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas", "KY": "Kentucky", "LA": "Louisiana",
    "ME": "Maine", "MD": "Maryland", "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota",
    "MS": "Mississippi", "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada",
    "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York", "NC": "North Carolina",
    "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma", "OR": "Oregon", "PA": "Pennsylvania",
    "RI": "Rhode Island", "SC": "South Carolina", "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas",
    "UT": "Utah", "VT": "Vermont", "VA": "Virginia", "WA": "Washington", "WV": "West Virginia",
    "WI": "Wisconsin", "WY": "Wyoming",
}  # fmt: skip


def scores(evidence: list[dict]) -> list[dict]:
    """Component = mean of its scored indicators (0 when none are); composite = weighted sum."""
    out = []
    for st in NAMES:
        mine = [r for r in evidence if r["state"] == st]
        row = {"state": st, "name": NAMES[st], "n_pending": sum(bool(r["pending"]) for r in mine)}
        total = 0.0
        for comp, w in COMPS:
            v = [r["level"] for r in mine if r["component"] == comp and r["level"] is not None]
            s = sum(v) / len(v) if v else 0.0
            row[comp] = round(s, 1)
            total += s * w
        row["composite"] = round(total, 1)
        out.append(row)
    out.sort(key=lambda r: -r["composite"])
    for i, r in enumerate(out, 1):
        r["rank"] = i
    return out


def main(study: Path) -> None:
    ev_dir = study / "evidence"

    def load(name):
        return json.loads((ev_dir / name).read_text())

    evidence = load("index_evidence.json")
    sc = scores(evidence)
    with open(study / "outputs/index_scores.csv", newline="") as f:
        csv_scores = {r["state"]: float(r["composite"]) for r in csv.DictReader(f)}
    off = {
        r["state"]: (r["composite"], csv_scores.get(r["state"]))
        for r in sc
        if r["composite"] != csv_scores.get(r["state"])
    }
    assert not off, f"scores differ from the study's index_scores.csv: {off}"

    def level(ind, f):
        return sum(
            r["indicator"] == ind and r["level"] is not None and f(r["level"]) for r in evidence
        )

    summary = {
        "median": round(statistics.median(r["composite"] for r in sc), 2),
        "moratorium_now": level("pm_moratorium", lambda v: v == 100),
        "moratorium_pending": level("pm_moratorium", lambda v: v == 60),
        "tariff_approved": level("pw_tariff", lambda v: v >= 70),
        "cost_alloc": level("pw_cost_alloc", lambda v: v == 100),
        "confident_share": round(
            sum(r["confidence"] in ("high", "medium") for r in evidence) / len(evidence), 4
        ),
        "unscored": sum(r["level"] is None for r in evidence),
        "rows": len(evidence),
        "newest_source": max(str(r["source_date"])[:10] for r in evidence),
    }
    indicators = {r["indicator"]: [r["indicator_label"], r["component"]] for r in evidence}
    data = {
        "senate": load("senate_winners.json"),
        "governors": load("governors.json"),
        "investments": load("dc_investments.json"),
        "polls": load("polls.json"),
        "scores": sc,
        "summary": summary,
        "indicators": indicators,
        "names": NAMES,
    }
    keep = (
        "state",
        "indicator",
        "level",
        "evidence",
        "pending",
        "confidence",
        "source_date",
        "source_url",
    )
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "data.json").write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")))
    (OUT / "evidence.json").write_text(
        json.dumps(
            [{k: r[k] for k in keep} for r in evidence], ensure_ascii=False, separators=(",", ":")
        )
    )
    top, bottom = sc[0], sc[-1]
    print(
        f"{len(sc)} states, top {top['state']} {top['composite']}, bottom {bottom['state']} {bottom['composite']}"
    )
    print("summary:", summary)
    print(f"wrote {OUT / 'data.json'} and evidence.json")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
