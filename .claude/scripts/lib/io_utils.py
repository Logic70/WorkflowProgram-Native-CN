from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict


def utc_now() -> str:
    """Return a stable UTC timestamp formatted for evidence files."""

    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def iso_now() -> str:
    """Alias used by scripts that prefer iso_now naming."""

    return utc_now()


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    """Write normalized UTF-8 JSON after creating parent directories."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
