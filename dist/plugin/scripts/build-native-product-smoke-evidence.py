#!/usr/bin/env python3
# AUTO-GENERATED FROM .claude/ - DO NOT EDIT DIRECTLY
"""Aggregate evaluated Native Workflow product smoke evidence.

This script does not inspect raw Claude Code JSONL and does not execute
Claude Code. It only consumes JSON reports produced by
build-native-interactive-smoke.py evaluate, then writes the coarse
native-product-interactive-smoke.json file used by the retirement assessor.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_NAME = "native-product-interactive-smoke-evidence"
REQUIRED_WORKFLOWS = ["develop", "validate", "audit", "iterate", "publish"]
WORKFLOW_ALIASES = {
    "workflowprogram-develop": "develop",
    "workflowprogram-validate": "validate",
    "workflowprogram-audit": "audit",
    "workflowprogram-iterate": "iterate",
    "workflowprogram-publish": "publish",
}
REQUIRED_FLAGS = [
    *REQUIRED_WORKFLOWS,
    "discovery",
    "scriptPath",
    "agent",
    "schema",
    "pass",
    "blocked_path",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Aggregate Native product smoke evaluator reports")
    parser.add_argument(
        "--evaluation",
        action="append",
        default=[],
        help="Path to a JSON report from build-native-interactive-smoke.py evaluate; repeatable",
    )
    parser.add_argument("--out", default="", help="Write aggregate evidence JSON to this path")
    parser.add_argument("--json", action="store_true", help="Print aggregate evidence JSON")
    return parser.parse_args()


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path}: invalid JSON: {exc}") from exc
    except OSError as exc:
        raise ValueError(f"{path}: failed to read file: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected a JSON object")
    return data


def workflow_key(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    if value in WORKFLOW_ALIASES:
        return WORKFLOW_ALIASES[value]
    for prefix, key in WORKFLOW_ALIASES.items():
        if value.endswith(prefix):
            return key
    return None


def aggregate(evaluation_paths: list[Path]) -> dict[str, Any]:
    flags = {key: False for key in REQUIRED_FLAGS}
    source_evaluations: list[dict[str, Any]] = []
    rejected: list[dict[str, str]] = []

    for path in evaluation_paths:
        try:
            report = load_json(path)
        except ValueError as exc:
            rejected.append({"path": str(path), "reason": str(exc)})
            continue

        if report.get("schema_name") != "native-workflow-interactive-smoke":
            rejected.append({"path": str(path), "reason": "schema_name is not native-workflow-interactive-smoke"})
            continue
        if report.get("status") != "PASS":
            rejected.append({"path": str(path), "reason": f"status is {report.get('status')!r}, expected 'PASS'"})
            continue

        wf_key = workflow_key(report.get("workflow"))
        if wf_key is None:
            rejected.append({"path": str(path), "reason": f"unknown workflow {report.get('workflow')!r}"})
            continue

        evidence = report.get("evidence")
        if not isinstance(evidence, dict):
            rejected.append({"path": str(path), "reason": "missing evidence object"})
            continue

        flags[wf_key] = True
        if evidence.get("skill_listing") is True:
            flags["discovery"] = True
        if evidence.get("workflow_invoked") is True:
            flags["scriptPath"] = True
        if evidence.get("agent_started") is True:
            flags["agent"] = True
        if evidence.get("schema_result") is True:
            flags["schema"] = True
        if evidence.get("completed_pass") is True:
            flags["pass"] = True
        if evidence.get("completed_blocked") is True:
            flags["blocked_path"] = True

        source_evaluations.append(
            {
                "path": str(path),
                "workflow": report.get("workflow"),
                "scenario": report.get("scenario"),
                "evidenceProfile": report.get("evidenceProfile"),
                "runIds": report.get("runIds", []),
                "jsonl": report.get("jsonl"),
                "journalJsonl": report.get("journalJsonl"),
            }
        )

    missing = [key for key in REQUIRED_FLAGS if flags.get(key) is not True]
    declared_complete = not missing
    payload: dict[str, Any] = {
        "schemaVersion": 1,
        "schemaName": SCHEMA_NAME,
        "status": "PASS" if declared_complete else "FAIL",
        "generatedAt": utc_now(),
        "declaredComplete": declared_complete,
        **flags,
        "missingCoverage": missing,
        "sourceEvaluations": source_evaluations,
        "rejectedEvaluations": rejected,
        "notes": [
            "Generated only from build-native-interactive-smoke.py evaluate reports.",
            "Do not edit flags manually; rerun this aggregator after collecting real interactive JSONL evidence.",
        ],
    }
    return payload


def main() -> int:
    args = parse_args()
    paths = [Path(item).resolve() for item in args.evaluation]
    payload = aggregate(paths)

    if args.out.strip():
        out = Path(args.out).resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.json or not args.out.strip():
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["declaredComplete"] is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
