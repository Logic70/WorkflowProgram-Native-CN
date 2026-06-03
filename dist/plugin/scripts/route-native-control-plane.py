#!/usr/bin/env python3
# AUTO-GENERATED FROM .claude/ - DO NOT EDIT DIRECTLY
"""Select Native Workflow JS control plane authoring."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from lib.io_utils import write_json


RETIRED_RUNTIME_MARKERS = [
    ".workflowprogram/design/workflow-spec.yaml",
    ".workflowprogram/runtime",
]
NATIVE_WORKFLOW_ROOT = ".claude/workflows"
VALID_MODES = {"auto", "native"}


def parse_args() -> argparse.Namespace:
    """Parse deterministic control-plane routing arguments."""

    parser = argparse.ArgumentParser(description="Route WorkflowProgram develop authoring to Native Workflow JS")
    parser.add_argument("--target-root", default="", help="Target project root")
    parser.add_argument("--mode", choices=sorted(VALID_MODES), default="auto", help="Explicit override or automatic routing")
    parser.add_argument("--out", default="", help="Optional JSON evidence output")
    parser.add_argument("--json", action="store_true", help="Print JSON")
    return parser.parse_args()


def existing_native_workflows(target_root: Path) -> list[str]:
    """List target-local Native Workflow JS files."""

    workflow_root = target_root / NATIVE_WORKFLOW_ROOT
    if not workflow_root.exists():
        return []
    return sorted(path.relative_to(target_root).as_posix() for path in workflow_root.glob("*.js") if path.is_file())


def existing_retired_runtime_markers(target_root: Path) -> list[str]:
    """List retired runtime markers that require manual migration attention."""

    return [marker for marker in RETIRED_RUNTIME_MARKERS if (target_root / marker).exists()]


def route_control_plane(target_root: Path, requested_mode: str) -> dict[str, Any]:
    """Return one auditable native-or-legacy authoring decision."""

    native_workflows = existing_native_workflows(target_root)
    retired_runtime_markers = existing_retired_runtime_markers(target_root)
    if requested_mode == "native":
        mode = "native"
        reason = "explicit-native"
    elif retired_runtime_markers:
        mode = "native"
        reason = "existing-retired-runtime-native-default"
    else:
        mode = "native"
        reason = "default-native"

    return {
        "schema_version": 1,
        "schema_name": "workflowprogram-control-plane-route",
        "status": "PASS",
        "target_root": str(target_root.resolve()),
        "requested_mode": requested_mode,
        "control_plane_mode": mode,
        "entry_skill": "workflowprogram-native-develop",
        "reason": reason,
        "retired_runtime_markers": retired_runtime_markers,
        "manual_migration_required": bool(retired_runtime_markers),
        "native_workflows": native_workflows,
        "automatic_rewrite": False,
    }


def main() -> int:
    """Resolve and optionally persist the control-plane route."""

    args = parse_args()
    target_root = Path(args.target_root).resolve() if args.target_root.strip() else Path.cwd().resolve()
    payload = route_control_plane(target_root, args.mode)
    if args.out.strip():
        write_json(Path(args.out).resolve(), payload)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"mode={payload['control_plane_mode']} entry_skill={payload['entry_skill']} reason={payload['reason']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
