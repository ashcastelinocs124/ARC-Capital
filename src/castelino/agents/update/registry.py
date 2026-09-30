from __future__ import annotations

import json
from pathlib import Path

from castelino.agents.update.fsio import atomic_write_text
from castelino.forecast.regime import RegimeForecast

MODELS = ("growth", "inflation")


class ModelRegistry:
    """Versioned refit results plus a per-model pointer to the version being served.

    A version file holds a full RegimeForecast bundle (both models). The refit is
    deterministic (fixed seed/hyperparameters), so a version stores forecast,
    metrics and config, not a pickled model. Rollback moves a pointer.
    """

    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _version_path(self, version: str) -> Path:
        return self.root / f"{version}.json"

    def _next_version(self) -> str:
        nums = [int(p.stem[1:]) for p in self.root.glob("v[0-9]*.json")]
        return f"v{(max(nums) if nums else 0) + 1:04d}"

    def save_version(self, bundle: RegimeForecast) -> str:
        version = self._next_version()
        atomic_write_text(self._version_path(version), bundle.to_json())
        return version

    def pointers(self) -> dict[str, str]:
        p = self.root / "current.json"
        if not p.is_file():
            return {}
        try:
            return json.loads(p.read_text())
        except (json.JSONDecodeError, OSError):
            return {}

    def set_pointer(self, model: str, version: str) -> None:
        if model not in MODELS:
            raise KeyError(f"unknown model {model!r}")
        if not self._version_path(version).is_file():
            raise KeyError(f"unknown version {version!r}")
        ptrs = self.pointers()
        ptrs[model] = version
        atomic_write_text(self.root / "current.json", json.dumps(ptrs, indent=2))

    def rollback(self, model: str, version: str) -> None:
        self.set_pointer(model, version)

    def _load(self, version: str) -> RegimeForecast:
        return RegimeForecast.model_validate_json(self._version_path(version).read_text())

    def current(self) -> RegimeForecast | None:
        ptrs = self.pointers()
        if not all(ptrs.get(m) for m in MODELS):
            return None
        growth = self._load(ptrs["growth"]).growth
        inflation = self._load(ptrs["inflation"]).inflation
        return RegimeForecast(asof=max(growth.asof, inflation.asof),
                              growth=growth, inflation=inflation)
