#!/usr/bin/env python3
"""Classify interactive Claude Code Native Workflow JSONL evidence."""

from __future__ import annotations

import argparse
import html
import json
from pathlib import Path
from typing import Any
import re

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
        "sdk_cli_print_mode": False,
        "workflow_prompt_attempt": False,
    }
    matching_lines: dict[str, list[int]] = {key: [] for key in evidence}

    def _content_items(record: dict[str, Any]) -> list[dict[str, Any]]:
        """Return JSONL message content items that are objects."""

        message = record.get("message")
        if not isinstance(message, dict):
            return []
        content = message.get("content")
        if not isinstance(content, list):
            return []
        return [item for item in content if isinstance(item, dict)]

    def _has_workflow_tool_invocation(record: dict[str, Any]) -> bool:
        """Detect a real Workflow tool call, not prompt or assistant text."""

        if record.get("tool") == "Workflow" and isinstance(record.get("input"), dict):
            return bool(record["input"].get("scriptPath"))
        for item in _content_items(record):
            if item.get("type") == "tool_use" and item.get("name") == "Workflow":
                tool_input = item.get("input")
                if isinstance(tool_input, dict) and tool_input.get("scriptPath"):
                    return True
        return False

    def _has_async_launch(record: dict[str, Any]) -> bool:
        """Detect structural async launch evidence."""

        if record.get("status") == "async_launched":
            return True
        tool_result = record.get("toolUseResult")
        if isinstance(tool_result, dict) and tool_result.get("status") == "async_launched":
            return True
        return False

    def _has_completed_pass(record: dict[str, Any], normalized_line: str) -> bool:
        """Detect a completed PASS result from non-prompt evidence."""

        def _parse_result_content(content: str) -> dict[str, Any] | None:
            match = re.search(r"<result>(.*?)</result>", content, flags=re.DOTALL)
            if not match:
                return None
            result_text = match.group(1).strip()
            for candidate in (result_text, html.unescape(result_text)):
                try:
                    payload = json.loads(candidate)
                except json.JSONDecodeError:
                    continue
                if isinstance(payload, dict):
                    return payload
            return None

        content = ""
        if record.get("type") == "notification":
            message = record.get("message")
            if isinstance(message, dict):
                content = str(message.get("content") or "")
            if not content:
                content = str(record.get("content") or "")
        elif record.get("type") == "queue-operation":
            content = str(record.get("content") or "")
        elif record.get("origin", {}).get("kind") == "task-notification":
            message = record.get("message")
            if isinstance(message, dict):
                content = str(message.get("content") or "")
        if "<result>" not in content:
            return False
        payload = _parse_result_content(content)
        if not payload:
            return False
        return payload.get("workflow") == workflow and payload.get("status") == "PASS"

    for line_number, line in enumerate(lines, start=1):
        normalized_line = line.replace('\\"', '"')
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            record = {}
        event_type = record.get("type") if isinstance(record, dict) else None
        is_prompt_text = event_type in {"user", "queue-operation"}
        if (
            ('"entrypoint"' in normalized_line and '"sdk-cli"' in normalized_line)
            or ('"promptSource"' in normalized_line and '"sdk"' in normalized_line)
        ):
            evidence["sdk_cli_print_mode"] = True
            matching_lines["sdk_cli_print_mode"].append(line_number)
        if "ultrawork" in line or ("Workflow" in line and "scriptPath" in line):
            evidence["workflow_prompt_attempt"] = True
            matching_lines["workflow_prompt_attempt"].append(line_number)
        if workflow in line and "skill_listing" in line:
            evidence["workflow_listed"] = True
            matching_lines["workflow_listed"].append(line_number)
        if isinstance(record, dict) and _has_workflow_tool_invocation(record):
            evidence["workflow_invoked"] = True
            matching_lines["workflow_invoked"].append(line_number)
        if isinstance(record, dict) and _has_async_launch(record):
            evidence["async_launched"] = True
            matching_lines["async_launched"].append(line_number)
        if isinstance(record, dict) and _has_completed_pass(record, normalized_line):
            evidence["completed_pass"] = True
            matching_lines["completed_pass"].append(line_number)
        if DISABLED_MESSAGE in line:
            evidence["environment_disabled"] = True
            matching_lines["environment_disabled"].append(line_number)

    if evidence["environment_disabled"]:
        status = "UNAVAILABLE"
        reason = "workflow-tool-disabled-in-context"
        return_code = 2
    elif (
        evidence["sdk_cli_print_mode"]
        and evidence["workflow_prompt_attempt"]
        and not evidence["workflow_invoked"]
    ):
        status = "UNAVAILABLE"
        reason = "non-interactive-sdk-cli-did-not-expose-workflow-tool"
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
