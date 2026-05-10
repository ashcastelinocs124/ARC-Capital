"""Historical backtest harness — gpt-4o, Oct 2023 onwards.

This module is the *historical* backtest (full pipeline replay over a date
range). It is distinct from `castelino.backtest_regression` which is a
deterministic fixture-replay regression suite.

Design: docs/plans/2026-05-08-backtest-design.md
Plan:   docs/plans/2026-05-08-backtest-plan.md
"""

BACKTEST_AS_OF_ENV = "BACKTEST_AS_OF"
