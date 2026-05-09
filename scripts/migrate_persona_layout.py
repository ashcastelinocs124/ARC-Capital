"""Wave 2 Task 2.3 — migrate persona JSON files to the nested layout.

Old:  data/personas/<id>.json                         (one file per speaker)
New:  data/personas/<id>/<lexicon_name>.json          (per-figure directory)

The lexicon_name is read from the `lexicon_version` field inside each persona
JSON, so the migration is information-preserving — no manual mapping needed.

Idempotent: running twice on the same directory produces the same result and
reports zero additional moves on the second run. The `--reverse` flag flips
the layout back for safe rollback if the migration introduces unexpected
behaviour downstream.

Usage:
    python scripts/migrate_persona_layout.py
    python scripts/migrate_persona_layout.py --reverse
    python scripts/migrate_persona_layout.py --personas-dir data/personas
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def migrate(*, personas_dir: Path, reverse: bool = False) -> int:
    """Move all legacy `<id>.json` files into nested `<id>/<lexicon>.json`.

    With `reverse=True`, undo: collapse `<id>/<lexicon>.json` back to
    `<id>.json` (used for rollback if the migration introduces drift).

    Returns the number of files moved on this invocation. Idempotent.
    """
    if not personas_dir.exists():
        return 0

    if reverse:
        return _reverse_migrate(personas_dir)

    moved = 0
    for entry in sorted(personas_dir.iterdir()):
        # Only flat files at the top level of personas/ are legacy targets.
        if not entry.is_file() or entry.suffix != ".json":
            continue
        speaker_id = entry.stem
        try:
            data = json.loads(entry.read_text())
        except json.JSONDecodeError:
            print(f"  skip {entry}: not valid JSON", file=sys.stderr)
            continue
        lexicon_name = data.get("lexicon_version")
        if not lexicon_name:
            print(
                f"  skip {entry}: no lexicon_version field — cannot infer "
                f"target file name",
                file=sys.stderr,
            )
            continue
        target_dir = personas_dir / speaker_id
        target_dir.mkdir(exist_ok=True)
        target = target_dir / f"{lexicon_name}.json"
        if target.exists():
            print(f"  skip {speaker_id}: target {target} already exists",
                  file=sys.stderr)
            continue
        entry.rename(target)
        print(f"  migrated: {entry.name} -> {speaker_id}/{lexicon_name}.json")
        moved += 1
    return moved


def _reverse_migrate(personas_dir: Path) -> int:
    """Flatten `<id>/<lexicon>.json` back to `<id>.json`.

    Only operates on directories containing exactly one JSON file (since the
    flat layout has no way to represent a figure with multiple lexicons; if
    there are multiple, --reverse cannot be applied without data loss).
    """
    moved = 0
    for entry in sorted(personas_dir.iterdir()):
        if not entry.is_dir():
            continue
        json_files = sorted(entry.glob("*.json"))
        if len(json_files) != 1:
            if json_files:
                print(
                    f"  skip {entry.name}: has {len(json_files)} lexicons — "
                    f"reverse to flat layout would lose data",
                    file=sys.stderr,
                )
            continue
        speaker_id = entry.name
        target = personas_dir / f"{speaker_id}.json"
        if target.exists():
            print(f"  skip {speaker_id}: target {target} already exists",
                  file=sys.stderr)
            continue
        json_files[0].rename(target)
        # Clean up the now-empty directory
        try:
            entry.rmdir()
        except OSError:
            pass  # not empty (some other artefact present); leave it
        print(f"  reversed: {speaker_id}/{json_files[0].name} -> {speaker_id}.json")
        moved += 1
    return moved


def _main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--personas-dir",
        type=Path,
        default=Path("data/personas"),
        help="Path to the personas directory (default: data/personas).",
    )
    parser.add_argument(
        "--reverse",
        action="store_true",
        help="Flatten nested layout back to legacy flat layout (rollback).",
    )
    args = parser.parse_args()
    moved = migrate(personas_dir=args.personas_dir, reverse=args.reverse)
    direction = "reversed" if args.reverse else "migrated"
    print(f"\n{direction}: {moved} file(s)")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
