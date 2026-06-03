#!/usr/bin/env python3
# AUTO-GENERATED FROM .claude/ - DO NOT EDIT DIRECTLY
"""Classify interactive Claude Code Native Workflow JSONL evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from lib.io_utils import write_json


DISABLED_MESSAGE = "Workflow exists but is not enabled in this context."


def parse_args() -> argparse.Namespace:
    """Parse the evidence file and expected workflow name."""

    parser = argparse.ArgumentParser(description="Classify Native Workflow capability from Claude Code JSONL evidence")
    parser.add_argument("--jsonl", required=True, help="Claude Code session JSONL path")
    parser.add_argument("--workflow", required=True, help="Expected workflow name")
    parser.add_argument("--out", default="", help="Optional JSON report output")
    parser.add_argument("--json", action="store_true", help="Print JSON")
    return parser.parse_args()


def classify_evidence(path: Path, workflow: str) -> dict[str, Any]:
    """Return a stable capability classification without executing Claude Code."""

    resolved = path.resolve()
    lines = resolved.read_text(encoding="utf-8").splitlines()
    evidence = {
        "workflow_listed": False,
        "workflow_invoked": False,
        "async_launched": False,
        "completed_pass": False,
        "environment_disabled": False,
    }
    matching_lines: dict[str, list[int]] = {key: [] for key in evidence}
    for line_number, line in enumerate(lines, start=1):
        normalized_line = line.replace('\\"', '"')
        if workflow in line and "skill_listing" in line:
            evidence["workflow_listed"] = True
            matching_lines["workflow_listed"].append(line_number)
        if workflow in line and "Workflow" in line and "scriptPath" in line:
            evidence["workflow_invoked"] = True
            matching_lines["workflow_invoked"].append(line_number)
        if "async_launched" in line:
            evidence["async_launched"] = True
            matching_lines["async_launched"].append(line_number)
        if workflow in normalized_line and '"status":"PASS"' in normalized_line.replace(" ", ""):
            evidence["completed_pass"] = True
            matching_lines["completed_pass"].append(line_number)
        if DISABLED_MESSAGE in line:
            evidence["environment_disabled"] = True
            matching_lines["environment_disabled"].append(line_number)

    if evidence["environment_disabled"]:
        status = "UNAVAILABLE"
        reason = "workflow-tool-disabled-in-context"
        return_code = 2
    elif evidence["workflow_listed"] and evidence["workflow_invoked"] and evidence["async_launched"]:
        status = "PASS"
        reason = "interactive-native-workflow-enabled"
        return_code = 0
    else:
        status = "INCONCLUSIVE"
        reason = "insufficient-interactive-evidence"
        return_code = 1
    return {
        "schema_version": 1,
        "schema_name": "native-workflow-capability-probe",
        "status": status,
        "reason": reason,
        "return_code": return_code,
        "jsonl": str(resolved),
        "workflow": workflow,
        "evidence": evidence,
        "matching_lines": matching_lines,
    }


def main() -> int:
    """Classify one JSONL file and emit a structured result."""

    args = parse_args()
    try:
        payload = classify_evidence(Path(args.jsonl), args.workflow)
    except Exception as exc:
        payload = {
            "schema_version": 1,
            "schema_name": "native-workflow-capability-probe",
            "status": "INCONCLUSIVE",
            "reason": "evidence-read-failed",
            "return_code": 1,
            "jsonl": str(Path(args.jsonl).resolve()),
            "workflow": args.workflow,
            "error": str(exc),
        }
    if args.out.strip():
        write_json(Path(args.out).resolve(), payload)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"{payload['status']}: {payload['reason']}")
    return int(payload["return_code"])


if __name__ == "__main__":
    raise SystemExit(main())
