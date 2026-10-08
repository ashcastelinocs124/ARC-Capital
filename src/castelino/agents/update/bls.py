"""BLS public API v2: CPI components and wages the FRED headline series don't break out."""

from __future__ import annotations

import os

import pandas as pd
import requests

from castelino.agents.update.models import Fact, Point, SeriesRef

URL = "https://api.bls.gov/publicAPI/v2/timeseries/data/"
# Seasonally adjusted index levels; we report month-over-month % changes.
SERIES = {
    "CUSR0000SAH1": "CPI shelter m/m",
    "CUSR0000SA0E": "CPI energy m/m",
    "CUSR0000SAF1": "CPI food m/m",
    "CES0500000003": "Average hourly earnings m/m",
}


def fetch(ids: list[str], post=requests.post) -> dict[str, list[tuple[str, float]]]:
    """series id -> [("Aug 2026", value), ...] newest first. Keyless works (25 calls/day)."""
    payload: dict = {"seriesid": list(ids)}
    if key := os.environ.get("BLS_API_KEY", "").strip():
        payload["registrationkey"] = key
    r = post(URL, json=payload, timeout=30)
    r.raise_for_status()
    body = r.json()
    if body.get("status") != "REQUEST_SUCCEEDED":
        raise RuntimeError(f"BLS: {body.get('message') or body.get('status')}")
    out: dict[str, list[tuple[str, float]]] = {}
    for s in body["Results"]["series"]:
        rows = []
        for d in s.get("data", []):
            if not d["period"].startswith("M") or d["period"] == "M13":
                continue
            try:
                rows.append((f"{d['periodName'][:3]} {d['year']}", float(d["value"])))
            except ValueError:  # "-" = not published
                continue
        out[s["seriesID"]] = rows
    return out


def _month(label: str) -> str:  # "Aug 2026" -> "2026-08"
    return pd.Timestamp(f"1 {label}").strftime("%Y-%m")


def bls_facts(fetch_fn=fetch, upto=None) -> list[Fact]:
    """upto(series_id) -> "YYYY-MM": ignore later months (rebuilding a past day's note)."""
    data = fetch_fn(list(SERIES))
    facts: list[Fact] = []
    for sid, name in SERIES.items():
        rows = data.get(sid) or []
        if upto and (cut := upto(sid)):
            rows = [r for r in rows if _month(r[0]) <= cut]
        if len(rows) < 3:
            continue
        (p0, v0), (p1, v1), (_, v2) = rows[:3]
        latest, prior = round((v0 / v1 - 1) * 100, 2), round((v1 / v2 - 1) * 100, 2)
        change = round(latest - prior, 2)
        facts.append(
            Fact(
                id=f"B{len(facts) + 1}",
                text=f"{name}: {latest:.2f}% ({p0}), prior {prior:.2f}% ({p1}), "
                f"change {change:+.2f}pp",
                numbers=[latest, prior, change],
                provenance="data",
                series=SeriesRef(
                    kind="release",
                    provider="bls",
                    id=sid,
                    label=name,
                    points=[
                        Point(label=f"{p1} data", value=prior),
                        Point(label=f"{p0} data", value=latest),
                    ],
                ),
                source_title=f"BLS {sid}",
                source_url=f"https://data.bls.gov/timeseries/{sid}",
            )
        )
    return facts
