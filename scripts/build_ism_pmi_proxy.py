#!/usr/bin/env python3
"""Rebuild `data/ism_manufacturing_pmi.csv` as a regional-Fed (Empire + Philly) ISM proxy.

FRED removed the official ISM series (`NAPM`) in 2024; the mean of the two regional
Fed diffusion indices (0 = neutral) is a real, current stand-in.

Run from repo root:
  PYTHONPATH=src .venv/bin/python scripts/build_ism_pmi_proxy.py
"""

from __future__ import annotations

import pandas as pd

from castelino.config import ROOT
from castelino.forecast.regime import _fetch_fred_series, _to_month_end


def main() -> None:
    ny = _to_month_end(_fetch_fred_series("GACDISA066MSFRBNY"))
    ph = _to_month_end(_fetch_fred_series("GACDFSA066MSFRBPHI"))
    proxy = pd.concat([ny, ph], axis=1).mean(axis=1).dropna()

    out = ROOT / "data" / "ism_manufacturing_pmi.csv"
    lines = [
        "# ISM Manufacturing PMI target series for the growth nowcaster.",
        "# ---------------------------------------------------------------------------",
        "# Mean of FRED GACDISA066MSFRBNY (Empire State) + GACDFSA066MSFRBPHI (Philly Fed)",
        "# general business conditions; 0 = neutral. ISM proxy; swap in licensed ISM if available.",
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
