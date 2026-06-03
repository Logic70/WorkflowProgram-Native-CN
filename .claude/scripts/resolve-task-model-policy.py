#!/usr/bin/env python3
"""Resolve logical task-type to model-alias mappings for Native Workflow JS agent calls.

Reads an optional task-model-policy.json, verifies each declared alias, and writes
a deterministic resolution to RUN_ROOT/outputs/stages/task-model-resolution.json
(or --out path). Unknown or unavailable aliases are converted to "inherit" with
auditable fallback evidence.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from lib.io_utils import utc_now, write_json
from lib.reporting import with_report_fields

DEFAULT_MAPPING: Dict[str, str] = {
    "clarification": "deepseek-v4-flash[1M]",
    "repository-exploration": "deepseek-v4-flash[1M]",
    "generation": "deepseek-v4-flash[1M]",
    "static-review": "deepseek-v4-flash[1M]",
    "architecture": "deepseek-v4-pro[1M]",
    "complex-generation": "deepseek-v4-pro[1M]",
    "risk-review": "deepseek-v4-pro[1M]",
    "publish-verification": "deepseek-v4-pro[1M]",
}

DEFAULT_TASK_TYPES = list(DEFAULT_MAPPING.keys())


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Resolve task-type -> model-alias mappings for Native Workflow JS."
    )
    parser.add_argument("--run-root", default="", help="Run root directory for resolution output")
    parser.add_argument("--out", default="", help="Explicit output path (overrides run-root default)")
    parser.add_argument(
        "--task-type", action="append", default=[], dest="task_types",
        help="Task type to resolve (repeatable). If omitted, resolve all standard types.",
    )
    parser.add_argument(
        "--available-model", action="append", default=[], dest="available_models",
        help="Available model alias (repeatable). CLI takes precedence over AVAILABLE_MODELS env.",
    )
    parser.add_argument("--policy", default="", help="Optional path to task-model-policy.json")
    parser.add_argument("--json", action="store_true", help="Print resolution JSON to stdout")
    return parser.parse_args()


def load_policy_with_source(
    policy_path: Optional[str],
) -> Tuple[Dict[str, Any], str, Optional[str]]:
    """Load an optional task-model-policy.json.

    Returns (policy_dict, source_string, fallback_reason_or_None).
    fallback_reason is POLICY_FILE_UNAVAILABLE or POLICY_FILE_INVALID when the
    file path was explicitly provided but could not be loaded as valid JSON dict.
    """
    if not policy_path:
        return {}, "built-in-default", None
    path = Path(policy_path)
    if not path.is_file():
        return {}, "built-in-default", "POLICY_FILE_UNAVAILABLE"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}, "built-in-default", "POLICY_FILE_INVALID"
    if not isinstance(payload, dict):
        return {}, "built-in-default", "POLICY_FILE_INVALID"
    return payload, "policy-file", None


def resolve_task_models(
    policy: Dict[str, Any],
    available_aliases: Optional[List[str]] = None,
    task_types: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Resolve task-type -> model-alias mapping from policy or built-in default.

    Returns (taskModels: dict, fallbacks: list, policySource: str).
    """
    policy_task_types: Dict[str, str] = {}
    policy_source = "built-in-default"

    if isinstance(policy.get("taskTypes"), dict):
        declared = policy["taskTypes"]
        if isinstance(declared, dict):
            policy_task_types = {str(k): str(v) for k, v in declared.items() if isinstance(k, str) and isinstance(v, str)}
            policy_source = "policy-file"

    # Determine which task types to resolve
    if task_types is not None and len(task_types) > 0:
        # Use only the requested task types in CLI first-seen order
        # Deduplicate while preserving order
        seen = set()
        ordered_task_types = []
        for tt in task_types:
            if tt not in seen:
                seen.add(tt)
                ordered_task_types.append(tt)
        task_type_list = ordered_task_types
    else:
        task_type_list = list(DEFAULT_TASK_TYPES)

    resolved: Dict[str, str] = {}
    fallbacks: List[Dict[str, str]] = []
    available = set(available_aliases) if available_aliases else None

    for task_type in task_type_list:
        # Determine alias: policy overrides default, unknown task types fall back immediately
        if task_type in DEFAULT_MAPPING:
            default_alias = DEFAULT_MAPPING[task_type]
            alias = policy_task_types.get(task_type, default_alias)
        elif task_type in policy_task_types:
            alias = policy_task_types[task_type]
        else:
            # Task type not in default mapping and not in policy
            resolved[task_type] = "inherit"
            fallbacks.append({
                "taskType": task_type,
                "requestedModel": None,
                "effectiveModel": "inherit",
                "reason": "TASK_TYPE_UNMAPPED",
            })
            continue

        effective = alias

        if alias == "inherit":
            effective = "inherit"
        elif available is not None and alias not in available:
            # Explicit available-model list exists and alias is not in it
            effective = "inherit"
            fallbacks.append({
                "taskType": task_type,
                "requestedModel": alias,
                "effectiveModel": "inherit",
                "reason": "MODEL_ALIAS_UNAVAILABLE",
            })
        # Do NOT reject custom aliases just because they are not in DEFAULT_MAPPING.values()
        # Only reject when an explicit available-model list exists and does not contain the alias.

        resolved[task_type] = effective

    return {
        "taskModels": resolved,
        "fallbacks": fallbacks,
        "policySource": policy_source,
    }


def build_resolution(
    run_root: Optional[Path],
    policy_path: Optional[str],
    available_aliases: Optional[List[str]] = None,
    task_types: Optional[List[str]] = None,
    out_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Build the full task-model-resolution.json payload."""
    policy, source, policy_fallback_reason = load_policy_with_source(policy_path)
    resolution = resolve_task_models(policy, available_aliases, task_types)

    # If policy had a loading fallback, record it as a fallback entry
    if policy_fallback_reason:
        resolution["fallbacks"].append({
            "taskType": None,
            "requestedModel": None,
            "effectiveModel": "inherit",
            "reason": policy_fallback_reason,
        })
        resolution["policySource"] = "built-in-default"

    status = "PASS" if len(resolution["fallbacks"]) == 0 else "PASS_WITH_FALLBACKS"

    effective_policy_source: str = resolution["policySource"]
    if effective_policy_source == "policy-file":
        effective_policy_source = policy_path or "policy-file"

    payload: Dict[str, Any] = {
        "schemaVersion": 1,
        "status": status,
        "policySource": effective_policy_source,
        "taskModels": resolution["taskModels"],
        "fallbacks": resolution["fallbacks"],
        "generatedAt": utc_now(),
    }

    # Record which resolution path was taken
    resolution_order: List[str] = []
    if policy_path:
        resolution_order.append("cli-policy-path")
    if available_aliases:
        resolution_order.append("explicit-availability")
    resolution_order.append("built-in-default")
    payload["resolutionOrder"] = resolution_order

    return with_report_fields(payload, schema_name="task-model-resolution", failure_kind="none" if status == "PASS" else "model_policy_fallback")


def resolve_output_path(run_root: Optional[Path], out_arg: str) -> Path:
    """Determine the output path for the resolution JSON.

    If --out is provided, use that exact path.
    Otherwise, derive from run_root as RUN_ROOT/outputs/stages/task-model-resolution.json.
    """
    if out_arg:
        return Path(out_arg).resolve()
    if run_root:
        return run_root / "outputs" / "stages" / "task-model-resolution.json"
    raise ValueError("At least one of --run-root or --out is required.")


def main() -> int:
    args = parse_args()

    # Resolve run-root and out - at least one is required
    run_root: Optional[Path] = None
    if args.run_root.strip():
        run_root = Path(args.run_root.strip()).resolve()
    try:
        output_path = resolve_output_path(run_root, args.out.strip())
    except ValueError as exc:
        payload = with_report_fields(
            {
                "schemaVersion": 1,
                "status": "FAIL",
                "policySource": "built-in-default",
                "taskModels": {},
                "fallbacks": [{"reason": "OUTPUT_PATH_REQUIRED", "message": str(exc)}],
                "generatedAt": utc_now(),
            },
            schema_name="task-model-resolution",
            error_code="OUTPUT_PATH_REQUIRED",
            failure_kind="input",
        )
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 2

    policy_path = args.policy.strip() if args.policy.strip() else None

    # Resolve available models: CLI --available-model takes precedence over env var
    available_aliases: Optional[List[str]] = None
    if args.available_models:
        available_aliases = [a.strip() for a in args.available_models if a.strip()]
    else:
        available_env = os.environ.get("AVAILABLE_MODELS", "").strip()
        available_aliases = [a.strip() for a in available_env.split(",") if a.strip()] if available_env else None

    # Resolve task types
    task_types: Optional[List[str]] = None
    if args.task_types:
        task_types = [t.strip() for t in args.task_types if t.strip()]

    try:
        payload = build_resolution(run_root, policy_path, available_aliases, task_types)
    except Exception as exc:
        payload = {
            "schemaVersion": 1,
            "status": "FAIL",
            "policySource": policy_path or "built-in-default",
            "taskModels": {},
            "fallbacks": [{"reason": f"Resolver error: {exc}"}],
            "generatedAt": utc_now(),
        }

    # Write resolution to file
    output_path.parent.mkdir(parents=True, exist_ok=True)
    write_json(output_path, payload)

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))

    return 0 if payload["status"] in ("PASS", "PASS_WITH_FALLBACKS") else 1


if __name__ == "__main__":
    raise SystemExit(main())
