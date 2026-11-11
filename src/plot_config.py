"""Safe, portable TonyPlotPy .set files (JSON, never executable code)."""
from __future__ import annotations

import json
import os
from pathlib import Path
from .version import APP_VERSION


def encode(value):
    if isinstance(value, dict):
        return {"mapping": [[encode(key), encode(item)] for key, item in value.items()]}
    if isinstance(value, tuple):
        return {"tuple": [encode(item) for item in value]}
    if isinstance(value, list):
        return [encode(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise ValueError("Unsupported configuration value")


def decode(value):
    if isinstance(value, list):
        return [decode(item) for item in value]
    if isinstance(value, dict):
        if set(value) == {"mapping"}:
            return {decode(key): decode(item) for key, item in value["mapping"]}
        if set(value) == {"tuple"}:
            return tuple(decode(item) for item in value["tuple"])
        raise ValueError("Invalid configuration encoding")
    return value


def remap_paths(value, mapping):
    if isinstance(value, str):
        return mapping.get(value, value)
    if isinstance(value, dict):
        return {remap_paths(key, mapping): remap_paths(item, mapping) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return type(value)(remap_paths(item, mapping) for item in value)
    return value


def save_config(path, state):
    path = Path(path)
    mapping = {}
    for kind in ("str", "log"):
        for filename in state["files"][kind]:
            try:
                mapping[filename] = os.path.relpath(filename, path.parent)
            except ValueError:
                mapping[filename] = filename
    portable = remap_paths(state, mapping)
    document = {"format": "TonyPlotPy", "schema_version": 2,
                "app_version": APP_VERSION, "state": encode(portable)}
    path.write_text(json.dumps(document, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def load_config(path):
    path = Path(path)
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict) or document.get("format") != "TonyPlotPy" or document.get("schema_version") not in (1, 2):
        raise ValueError("This is not a supported TonyPlotPy set file")
    state = decode(document["state"])
    if not isinstance(state, dict) or state.get("active") not in ("str", "log"):
        raise ValueError("Invalid plotting configuration")
    if document["schema_version"] == 1:
        doping = state.get("field_settings", {}).get("code:115", {})
        if doping.get("doping_mode", "absolute") == "absolute":
            state = remap_paths(state, {"code:115": "absolute_net_doping"})
            if "extra_fields" in state:
                state["extra_fields"] = ["absolute_net_doping" if code == 115 else code
                                         for code in state["extra_fields"]]
    mapping = {}
    for kind in ("str", "log"):
        for filename in state["files"][kind]:
            mapping[filename] = str((path.parent / filename).resolve())
    return remap_paths(state, mapping)
