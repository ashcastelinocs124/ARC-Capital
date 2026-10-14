#!/usr/bin/env python3
"""Rebuild `data/ism_manufacturing_pmi.csv` by hand. Every Model refit already does this.

Run from repo root:
  PYTHONPATH=src .venv/bin/python scripts/build_ism_pmi_proxy.py
"""

from castelino.forecast.regime import ISM_PROXY_CSV, rebuild_ism_proxy

if __name__ == "__main__":
    print(f"Wrote {ISM_PROXY_CSV} through {rebuild_ism_proxy()}")
