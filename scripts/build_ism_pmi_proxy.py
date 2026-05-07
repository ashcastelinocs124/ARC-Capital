#!/usr/bin/env python3
"""Rebuild `data/ism_manufacturing_pmi.csv` as an INDPRO-based proxy for ISM PMI.

FRED removed the official ISM Manufacturing (`NAPM`) series in 2024. Until you
paste licensed ISM headline values into that CSV, this script approximates a
50± diffusion-scale series from **industrial production** MoM % changes so the
growth nowcaster can train end-to-end.

Run from repo root:
  PYTHONPATH=src .venv/bin/python scripts/build_ism_pmi_proxy.py
"""

from __future__ import annotations

from castelino.config import ROOT
from castelino.forecast.regime import _fetch_fred_series, _to_month_end


def main() -> None:
    indpro = _to_month_end(_fetch_fred_series("INDPRO"))
    chg = indpro.pct_change()
    proxy = 50.0 + 100.0 * chg
    proxy = proxy.clip(38.0, 72.0).dropna()

    out = ROOT / "data" / "ism_manufacturing_pmi.csv"
    lines = [
        "# ISM Manufacturing PMI target series for the growth nowcaster.",
        "# ---------------------------------------------------------------------------",
        "# OFFICIAL DATA: Replace `value` below with the published ISM Manufacturing",
        "# composite index when your data license permits.",
        "#",
        "# PROXY (default): Built from FRED INDPRO month-over-month % change mapped to",
        "# a diffusion-like scale — useful because FRED discontinued NAPM in June 2024.",
        "# Regenerate: PYTHONPATH=src python scripts/build_ism_pmi_proxy.py",
        "# ---------------------------------------------------------------------------",
        "date,value",
    ]
    for ts, v in proxy.items():
        lines.append(f"{ts.strftime('%Y-%m-%d')},{v:.4f}")

    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {out} ({len(proxy)} rows)")


if __name__ == "__main__":
    main()
