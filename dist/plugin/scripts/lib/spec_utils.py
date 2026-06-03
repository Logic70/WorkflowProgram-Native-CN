# AUTO-GENERATED FROM .claude/ - DO NOT EDIT DIRECTLY
from __future__ import annotations

import fnmatch
import re
from typing import Any, Dict, Iterable, List, Optional


DEFAULT_STAGE_SLOT_ORDER = ["S1", "S2", "S3", "S4", "S5", "S6"]
_STAGE_SLOT_RE = re.compile(r"^S[1-6]$")


def path_matches_any(path: str, patterns: Iterable[str]) -> bool:
    """Return whether a relative path matches any declared glob pattern."""

    return any(fnmatch.fnmatch(path, pattern) for pattern in patterns)


def require_stage_slot(stage: Dict[str, Any]) -> str:
    """Read an explicit stage_slot from a stage definition."""

    stage_slot = str(stage.get("stage_slot", "")).strip()
    if stage_slot:
        if not _STAGE_SLOT_RE.fullmatch(stage_slot):
            raise RuntimeError(f"invalid stage_slot '{stage_slot}' for stage '{stage.get('id', '')}'")
        return stage_slot
    stage_id = str(stage.get("id", "")).strip()
    if _STAGE_SLOT_RE.fullmatch(stage_id):
        return stage_id
    raise RuntimeError(f"stage '{stage_id or '<unknown>'}' is missing explicit stage_slot")


def stage_slot_object_map(stages: Iterable[Dict[str, Any]], *, strict: bool = False) -> Dict[str, Dict[str, Any]]:
    """Map S1..S6 slots to stage definitions."""

    mapping: Dict[str, Dict[str, Any]] = {}
    for stage in stages:
        if not isinstance(stage, dict):
            continue
        if strict:
            stage_slot = require_stage_slot(stage)
        else:
            stage_slot = str(stage.get("stage_slot", "")).strip()
            if not stage_slot:
                continue
        if stage_slot not in mapping:
            mapping[stage_slot] = stage
    return mapping


def stage_slot_id_map(stages: Iterable[Dict[str, Any]], *, strict: bool = False) -> Dict[str, str]:
    """Map S1..S6 slots to stage ids."""

    mapping: Dict[str, str] = {}
    for stage_slot, stage in stage_slot_object_map(stages, strict=strict).items():
        stage_id = str(stage.get("id", "")).strip()
        if stage_id:
            mapping[stage_slot] = stage_id
    return mapping


def resolve_required_stage_slots(
    spec: Dict[str, Any],
    intent: str,
    default_slots: Optional[List[str]] = None,
) -> List[str]:
    """Resolve required stage slots for an intent flow."""

    fallback = list(default_slots or DEFAULT_STAGE_SLOT_ORDER)
    intent_flows = spec.get("intent_flows", {})
    if isinstance(intent_flows, dict):
        flow = intent_flows.get(intent, {})
        if isinstance(flow, dict):
            required = flow.get("required_stage_slots", [])
            if isinstance(required, list):
                values = [str(item).strip() for item in required if str(item).strip()]
                if values:
                    return values
    return fallback
