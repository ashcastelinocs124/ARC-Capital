"""Backfill from cached news + calendar over the last N days.

Each significant historical event fires a real pipeline pass. Useful for
seeding short-term memory with realistic content before showing the system.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from castelino.triggers.runner import replay_historical


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=30, help="History window in days.")
    args = parser.parse_args()
    replay_historical(days=args.days)


if __name__ == "__main__":
    main()
