"""Forecast layer — deterministic ML nowcasters whose outputs feed agents.

Currently exposes:
- `regime`: month-ahead direction nowcasters for ISM Manufacturing PMI and
  headline CPI (MoM, level changes), used to label a 4-quadrant regime.
"""
