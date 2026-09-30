"""Agent catalog: agents.yaml descriptions + live prompt/tier/schema read from code."""

from __future__ import annotations

import importlib
import os
import re
from pathlib import Path

import yaml
from fastapi import APIRouter

from castelino.config import ROOT

router = APIRouter()

REGISTRY = Path(ROOT) / "agents.yaml"
_SRC = Path(ROOT) / "src"
_AGENT_CLASS = re.compile(r"^class (\w+)\(StructuredAgent\[", re.M)
# journal plumbing every pipeline schema carries; not what the agent "says"
_PLUMBING = {"kind", "entry_id", "timestamp"}


def _import(path: str):
    """'pkg.mod.Name' or 'pkg.mod:NAME' -> object."""
    mod, _, name = path.replace(":", ".").rpartition(".")
    return getattr(importlib.import_module(mod), name)


def _type_name(t) -> str:
    s = t.__name__ if isinstance(t, type) else repr(t)
    return re.sub(r"\b(?:[a-z_]+\.)+", "", s.replace("typing.", ""))  # drop module prefixes


def _fields(schema) -> list[dict]:
    out = []
    for name, f in schema.model_fields.items():
        if name in _PLUMBING or name.startswith("parent_"):
            continue
        out.append(
            {"name": name, "type": _type_name(f.annotation), "description": f.description or ""}
        )
    return out


def _model_for(tier: str | None) -> str | None:
    if not tier:
        return None
    try:
        from castelino.agents.base import _resolve_model_id
        from castelino.config import get_settings

        return _resolve_model_id(get_settings(), tier)
    except Exception:  # noqa: BLE001 — unknown tier just shows without a model id
        return None


def _entry(raw: dict) -> dict:
    e = {
        "id": raw["id"],
        "name": raw["name"],
        "group": raw.get("group", "Other"),
        "summary": raw.get("summary", ""),
        "tools": raw.get("tools") or [],
        "memory": raw.get("memory") or {"reads": [], "writes": [], "persists": ""},
        "class_path": raw.get("class"),
        "tier": raw.get("tier"),
        "model": None,
        "prompt": None,
        "prompt_source": None,
        "output": None,
        "error": None,
        # presence only — a key's value never leaves the server
        "dependencies": [
            {
                "key": d["key"],
                "required": bool(d.get("required", True)),
                "why": d.get("why", ""),
                "set": bool(os.environ.get(d["key"], "").strip()),
            }
            for d in raw.get("dependencies") or []
        ],
        "raw_keys": sorted(raw),
    }
    try:
        if raw.get("class"):
            cls = _import(raw["class"])
            try:
                agent = cls()
            except TypeError:  # constructor needs runtime args; prompt/tier are usually static
                agent = cls.__new__(cls)
            tier = getattr(agent, "tier", None)
            e["tier"] = tier if isinstance(tier, str) else e["tier"]
            e["prompt"] = agent.system_prompt()
            e["prompt_source"] = f"{raw['class']}.system_prompt()"
            e["output"] = {"name": cls.output_schema.__name__, "fields": _fields(cls.output_schema)}
        if raw.get("prompt"):
            e["prompt"] = _import(raw["prompt"])
            e["prompt_source"] = raw["prompt"]
        if raw.get("schema"):
            schema = _import(raw["schema"])
            e["output"] = {"name": schema.__name__, "fields": _fields(schema)}
    except Exception as exc:  # noqa: BLE001 — one bad entry must not break the catalog
        e["error"] = f"{type(exc).__name__}: {exc}"
    e["model"] = _model_for(e["tier"])
    return e


def _agent_classes() -> list[dict]:
    """Every StructuredAgent subclass in src/, found by source scan (no imports)."""
    found = []
    for f in sorted(_SRC.rglob("*.py")):
        for m in _AGENT_CLASS.finditer(f.read_text()):
            module = ".".join(f.relative_to(_SRC).with_suffix("").parts)
            found.append(
                {
                    "class_name": m.group(1),
                    "class_path": f"{module}.{m.group(1)}",
                    "file": str(f.relative_to(ROOT)),
                }
            )
    return found


def build_catalog(registry: Path | None = None) -> dict:
    raw = yaml.safe_load(Path(registry or REGISTRY).read_text()) or {}
    entries = [_entry(r) for r in raw.get("agents", [])]
    registered = {e["class_path"] for e in entries if e["class_path"]}
    groups = list(dict.fromkeys(e["group"] for e in entries))
    return {
        "agents": entries,
        "groups": groups,
        "unregistered": [c for c in _agent_classes() if c["class_path"] not in registered],
    }


@router.get("/agents/catalog")
def agent_catalog():
    return build_catalog()
