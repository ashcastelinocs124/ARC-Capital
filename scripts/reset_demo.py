"""Wipe everything (journals, portfolio, exposure, system_state, reports) for demo runs."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from castelino.config import get_settings
from castelino.memory import io as memio


def main() -> None:
    cfg = get_settings()
    paths = cfg.resolved_paths

    for f in (
        paths.data / "portfolio.json",
        paths.data / "exposure_snapshot.json",
        paths.data / "system_state.json",
        paths.data / "news_cache.json",
        paths.data / "calendar_cache.json",
    ):
        if f.exists():
            f.unlink()
            print(f"  removed {f}")
    if paths.reports.exists():
        shutil.rmtree(paths.reports)
        print(f"  removed {paths.reports}")
    memio.reset_journals(confirm_token="I_KNOW_WHAT_I_AM_DOING")
    print("  journals reset")
    print("done.")


if __name__ == "__main__":
    main()
