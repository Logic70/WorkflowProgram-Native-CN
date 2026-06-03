from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import yaml


def preprocess_yaml_text(text: str) -> str:
    """Strip BOM and leading HTML comments before YAML parsing."""

    cleaned = text.lstrip("\ufeff")
    while True:
        stripped = cleaned.lstrip()
        if not stripped.startswith("<!--"):
            return cleaned
        end = stripped.find("-->")
        if end < 0:
            return cleaned
        cleaned = stripped[end + 3 :].lstrip("\r\n")


def parse_yaml_mapping(text: str) -> Dict[str, Any]:
    """Parse YAML text and require the root node to be a mapping."""

    payload = yaml.safe_load(preprocess_yaml_text(text))
    if not isinstance(payload, dict):
        raise ValueError("YAML payload must parse to a mapping object")
    return payload


def load_yaml_mapping(path: Path) -> Dict[str, Any]:
    """Load a YAML mapping from disk."""

    return parse_yaml_mapping(path.read_text(encoding="utf-8"))


def try_load_yaml_mapping(path: Path) -> Dict[str, Any]:
    """Best-effort mapping loader for judge/smoke style consumers."""

    if not path.exists():
        return {}
    try:
        return load_yaml_mapping(path)
    except Exception:
        return {}
