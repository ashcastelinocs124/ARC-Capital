"""After `vercel build`: write the copy of the built page that carries a dashboard's own link-preview tags
(the static site otherwise serves one index.html, so every shared link showed the generic ARC card).

frontend/vercel.json rewrites /dashboards/ai-capex to that copy, so a copy must always exist: when the
tags can't be written, the plain page is copied instead and only the card is lost.

Usage: python scripts/og_pages.py <built static dir>   (run from frontend/, after `vercel build`)
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path


def main(static_dir: Path) -> None:
    out = static_dir / "dashboards" / "ai-capex.html"
    try:
        from castelino.dashboards.ai_capex import card

        snapshot = (
            static_dir / "api" / "dashboards" / "ai-capex.json"
        )  # the build carries the snapshot
        print(f"og: {card.write_og(static_dir, snapshot) or 'no AI Demand & Capex snapshot'}")
    except Exception as e:  # noqa: BLE001 - never leave the rewrite pointing at nothing
        print(f"og: failed ({e})")
    if not out.exists():
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(static_dir / "index.html", out)
        print("og: copied the plain page (generic card)")


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".vercel/output/static"))
