"""Run the Recipe Writer (GPT-6 Astra, layer 3) for companies with custom careers sites.

Usage: uv run --extra browser python scripts/write_recipes.py TICKER=START_URL [...] [--budget 10]
Each accepted recipe is saved to data/adoption/recipes/<TICKER>.json. Check its sample titles
against the live careers page, then add `TICKER,recipe,TICKER` to data/adoption/job_boards.csv.
Stops starting new companies once the total spend reaches --budget (default $10).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yfinance as yf

from castelino.adoption.recipe_agent import RecipeWriter, save

RECIPES = Path(__file__).resolve().parent.parent / "data" / "adoption" / "recipes"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("targets", nargs="+", help="TICKER=START_URL")
    ap.add_argument("--budget", type=float, default=10.0)
    a = ap.parse_args()
    writer, spent, ok = RecipeWriter(), 0.0, 0
    for target in a.targets:
        ticker, _, url = target.partition("=")
        if spent >= a.budget:
            print(f"{ticker}: skipped, budget ${a.budget:.2f} used up")
            continue
        name = yf.Ticker(ticker).info.get("longName") or ticker
        res = writer.run(ticker, name, url)
        spent += res.cost_usd
        head = f"{ticker}: ${res.cost_usd:.2f}, {res.steps} steps"
        if res.recipe is None:
            print(f"{head} — no recipe. {res.note}")
            continue
        ok += 1
        print(f"{head} — {res.recipe.kind} recipe, {res.count} titles → {save(res, RECIPES)}")
        print("  sample: " + " | ".join(res.sample))
        print(f"  add after checking: {ticker},recipe,{ticker}")
    print(f"\n{ok}/{len(a.targets)} recipes, total ${spent:.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
