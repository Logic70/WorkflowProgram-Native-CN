#!/usr/bin/env python3
# AUTO-GENERATED FROM .claude/ - DO NOT EDIT DIRECTLY
"""Validate the foreground clarification gate before Native Workflow authoring."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from lib.io_utils import write_json


REQUIRED_LENSES = [
    "purpose",
    "object_model",
    "process_model",
    "decision_model",
    "evidence_model",
    "acceptance_model",
    "boundary_model",
]


def error(rule: str, message: str) -> dict[str, str]:
    """Return one stable readiness error."""

    return {"rule": rule, "message": message}


def has_content(value: Any) -> bool:
    """Accept a non-empty string, list, or object as clarified lens content."""

    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, dict)):
        return bool(value)
    return False


def validate_readiness(path: Path, expected_target_root: Path | None = None) -> dict[str, Any]:
    """Validate one confirmed Native authoring requirement packet."""

    resolved = path.resolve()
    errors: list[dict[str, str]] = []
    if not resolved.exists():
        errors.append(error("READINESS_NOT_FOUND", f"Readiness packet not found: {resolved}"))
        payload: dict[str, Any] = {}
    else:
        try:
            payload = json.loads(resolved.read_text(encoding="utf-8"))
        except Exception as exc:
            payload = {}
            errors.append(error("READINESS_JSON_INVALID", str(exc)))

    if payload and not isinstance(payload, dict):
        errors.append(error("READINESS_OBJECT_REQUIRED", "Readiness packet must be a JSON object."))
        payload = {}

    request = payload.get("request")
    target_root = payload.get("target_root")
    lenses = payload.get("lenses")
    success_criteria = payload.get("success_criteria")
    open_questions = payload.get("open_questions")

    if not isinstance(request, str) or not request.strip():
        errors.append(error("REQUEST_REQUIRED", "`request` must preserve the confirmed user requirement."))
    if not isinstance(target_root, str) or not target_root.strip():
        errors.append(error("TARGET_ROOT_REQUIRED", "`target_root` must be a non-empty path string."))
    elif expected_target_root is not None and Path(target_root).resolve() != expected_target_root.resolve():
        errors.append(
            error(
                "TARGET_ROOT_MISMATCH",
                f"`target_root` must match the requested target root: {expected_target_root.resolve()}",
            )
        )
    if payload.get("confirmed_by_user") is not True:
        errors.append(error("USER_CONFIRMATION_REQUIRED", "`confirmed_by_user` must be true before generation."))
    if not isinstance(lenses, dict):
        errors.append(error("LENSES_REQUIRED", "`lenses` must be an object."))
        lenses = {}
    for lens in REQUIRED_LENSES:
        if not has_content(lenses.get(lens)):
            errors.append(error("LENS_REQUIRED", f"`lenses.{lens}` must be clarified before generation."))
    if not isinstance(success_criteria, list) or not success_criteria or not all(has_content(item) for item in success_criteria):
        errors.append(error("SUCCESS_CRITERIA_REQUIRED", "`success_criteria` must contain at least one non-empty item."))
    if not isinstance(open_questions, list):
        errors.append(error("OPEN_QUESTIONS_REQUIRED", "`open_questions` must be an array."))
    elif open_questions:
        errors.append(error("OPEN_QUESTIONS_BLOCK_GENERATION", "Resolve open questions before generation."))

    return {
        "schema_version": 1,
        "schema_name": "native-workflow-authoring-readiness",
        "status": "BLOCKED" if errors else "PASS",
        "packet": str(resolved),
        "target_root": target_root if isinstance(target_root, str) else None,
        "errors": errors,
    }


def build_parser() -> argparse.ArgumentParser:
    """Build the readiness validator CLI."""

    parser = argparse.ArgumentParser(description="Validate Native Workflow authoring readiness")
    parser.add_argument("--packet", required=True, help="Confirmed Native authoring requirement packet")
    parser.add_argument("--target-root", help="Optional target root that the packet must match")
    parser.add_argument("--out", help="Optional structured JSON output path")
    parser.add_argument("--json", action="store_true", help="Print structured JSON")
    return parser


def main() -> int:
    """Validate readiness and return a stable exit code."""

    args = build_parser().parse_args()
    payload = validate_readiness(Path(args.packet), Path(args.target_root) if args.target_root else None)
    if args.out:
        write_json(Path(args.out).resolve(), payload)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"{payload['status']}: {payload['packet']}")
        for item in payload["errors"]:
            print(f"  [{item['rule']}] {item['message']}")
    return 0 if payload["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
