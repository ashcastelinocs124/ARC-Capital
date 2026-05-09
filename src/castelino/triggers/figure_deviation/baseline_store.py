"""Per-(figure × lexicon) baseline persistence.

Wave 3 Task 3.2 — adds the canonical disk store for the generic
`FigureBaseline` type. Lives separately from `data/personas/` (which holds
audio-source rich `SpeakerPersona` files) so that non-audio sources (X API,
Sonar tweets) have a place to write their lighter baselines without colliding.

The store enforces the lexicon-version invariant on every load: if the
stored baseline was built against lexicon version N but the current lexicon
YAML is at version M with M != N, `load()` raises `LexiconVersionMismatch`
rather than silently producing wrong z-scores. The user is directed to run
`castelino figure-refresh --figure <id> --lexicon <name>` to rebuild.

Path layout: `<base_dir>/<figure_id>/<lexicon_name>.json`. Parallel to the
persona layout introduced in Task 2.3 but in a different base directory.
"""
from __future__ import annotations

import json
from pathlib import Path

import yaml

from castelino.triggers.figure_deviation.models import FigureBaseline


class LexiconVersionMismatch(RuntimeError):
    """Raised when a stored baseline's lexicon_version disagrees with the
    current lexicon YAML's version. Carrying corrupt baselines silently
    would invalidate every z-score downstream, so this is fail-fast.
    """


class BaselineStore:
    """Disk-backed persistence for `FigureBaseline` objects.

    The default location is `data/figure_baselines/`. `lexicon_dir` is used
    to validate the lexicon_version field on load — passing both lets a
    single store drive every figure × lexicon combination.
    """

    def __init__(
        self,
        *,
        base_dir: Path | None = None,
        lexicon_dir: Path | None = None,
    ) -> None:
        self._base_dir = base_dir or Path("data/figure_baselines")
        self._lexicon_dir = lexicon_dir or Path("data/lexicons")

    # ───────────────── path resolution ─────────────────

    def baseline_path(self, *, figure_id: str, lexicon_name: str) -> Path:
        return self._base_dir / figure_id / f"{lexicon_name}.json"

    def _lexicon_path(self, lexicon_name: str) -> Path:
        return self._lexicon_dir / f"{lexicon_name}.yaml"

    # ───────────────── write ───────────────────────────

    def save(self, baseline: FigureBaseline) -> Path:
        """Persist a baseline. Creates the figure's directory if missing."""
        path = self.baseline_path(
            figure_id=baseline.figure_id,
            lexicon_name=baseline.lexicon_name,
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(baseline.model_dump_json(indent=2))
        return path

    # ───────────────── read with version check ─────────

    def _current_lexicon_version(self, lexicon_name: str) -> int:
        """Read the `version` field from the lexicon YAML.

        Versions in YAML may be int or str ("v1", "v3"). We coerce to int
        if possible (stripping a leading 'v'); otherwise compare as strings.
        """
        path = self._lexicon_path(lexicon_name)
        if not path.exists():
            raise FileNotFoundError(
                f"Lexicon YAML missing: {path}. Cannot validate baseline "
                f"version for {lexicon_name!r}.",
            )
        raw = yaml.safe_load(path.read_text())
        version = raw.get("version")
        if isinstance(version, str) and version.startswith("v"):
            try:
                return int(version[1:])
            except ValueError:
                pass
        if isinstance(version, str):
            try:
                return int(version)
            except ValueError as e:
                raise ValueError(
                    f"Lexicon {lexicon_name!r} has unparseable version: "
                    f"{version!r}",
                ) from e
        return int(version)

    def load(self, *, figure_id: str, lexicon_name: str) -> FigureBaseline:
        """Read a baseline and validate its lexicon_version.

        Raises:
            FileNotFoundError: baseline JSON missing, OR lexicon YAML missing
                (cannot validate without it).
            LexiconVersionMismatch: stored baseline's version differs from
                current lexicon YAML's version. The exception message tells
                the operator which CLI command to run to refresh.
        """
        path = self.baseline_path(
            figure_id=figure_id, lexicon_name=lexicon_name,
        )
        if not path.exists():
            raise FileNotFoundError(
                f"No baseline for {figure_id} × {lexicon_name} at {path}. "
                f"Run `castelino figure-refresh --figure {figure_id} "
                f"--lexicon {lexicon_name}` to build it.",
            )
        baseline = FigureBaseline.model_validate_json(path.read_text())
        current_version = self._current_lexicon_version(lexicon_name)
        if baseline.lexicon_version != current_version:
            raise LexiconVersionMismatch(
                f"Baseline {figure_id} × {lexicon_name} was built against "
                f"lexicon version {baseline.lexicon_version} but the current "
                f"lexicon is version {current_version}. Z-scores would be "
                f"incoherent. Run `castelino figure-refresh --figure "
                f"{figure_id} --lexicon {lexicon_name}` to rebuild against "
                f"the current lexicon.",
            )
        return baseline
