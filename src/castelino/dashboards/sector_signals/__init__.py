"""Sector Signal Significance dashboard: is today's technical signal on a sector worth a look, or noise?

signals.py turns each sector ETF's prices into event dates (RSI extremes, crosses, breakouts...);
stats.py runs an event study per sector x signal x horizon against a time-shift null, corrects for
multiple testing and splits by regime; run.py pulls prices from yfinance and writes the dashboard file.
"""
