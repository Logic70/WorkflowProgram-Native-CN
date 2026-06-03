#!/usr/bin/env python3
# AUTO-GENERATED FROM .claude/ - DO NOT EDIT DIRECTLY
"""Validate generated target workflow managed-runtime state and evidence."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List


REQUIRED_EVENTS = {"TargetRuntimeStarted", "TargetRuntimeCompleted"}
VALID_STATUS = {"PASS", "WARN", "FAIL", "BLOCKED", "ENVIRONMENT-SKIP"}
VALID_FAILURE_KIND = {"none", "design", "implementation", "environment", "conflict"}
MANUAL_EXECUTOR_PROVIDERS = {"current_agent", "manual"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate target managed runtime state")
    parser.add_argument("--state", required=True, help="Path to target-state.json")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def load_json(path: Path, errors: List[str]) -> Dict[str, Any]:
    if not path.exists():
        errors.append(f"missing file: {path}")
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        errors.append(f"cannot parse JSON {path}: {exc}")
        return {}
    if not isinstance(payload, dict):
        errors.append(f"JSON root must be object: {path}")
        return {}
    return payload


def load_events(path: Path, errors: List[str]) -> List[Dict[str, Any]]:
    if not path.exists():
        errors.append(f"missing file: {path}")
        return []
    events: List[Dict[str, Any]] = []
    for idx, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            errors.append(f"invalid JSONL event at line {idx}: {exc}")
            continue
        if not isinstance(payload, dict):
            errors.append(f"event line {idx} must be object")
            continue
        events.append(payload)
    return events


def safe_rel(path_text: str) -> str:
    cleaned = path_text.strip().replace("\\", "/")
    while cleaned.startswith("./"):
        cleaned = cleaned[2:]
    if not cleaned or cleaned.startswith("/") or ".." in cleaned.split("/"):
        raise ValueError(f"unsafe relative path: {path_text}")
    return cleaned


def validate_executor_evidence(
    run_root: Path,
    node: Dict[str, Any],
    provider: str,
    provenance_paths: set[str],
    errors: List[str],
) -> None:
    node_id = str(node.get("node_id", "")).strip()
    evidence_rel = str(node.get("executor_evidence_path", "")).strip()
    if not evidence_rel:
        errors.append(f"manual/current-agent node missing executor_evidence_path: {node_id}")
        return
    try:
        evidence_path = run_root / safe_rel(evidence_rel)
    except ValueError as exc:
        errors.append(str(exc))
        return
    evidence = load_json(evidence_path, errors)
    if not evidence:
        return
    if int(evidence.get("schema_version", 0) or 0) != 1:
        errors.append(f"executor evidence schema_version must be 1: {evidence_rel}")
    if str(evidence.get("node_id", "")).strip() != node_id:
        errors.append(f"executor evidence node_id mismatch: {evidence_rel}")
    if str(evidence.get("provider", "")).strip() != provider:
        errors.append(f"executor evidence provider mismatch: {evidence_rel}")
    if str(evidence.get("status", "")).strip() != "PASS":
        errors.append(f"executor evidence status must be PASS: {evidence_rel}")
    for field in ("operator", "started_at", "completed_at"):
        if not str(evidence.get(field, "")).strip():
            errors.append(f"executor evidence {field} is required: {evidence_rel}")
    if not isinstance(evidence.get("input_refs", []), list):
        errors.append(f"executor evidence input_refs must be a list: {evidence_rel}")
    if not isinstance(evidence.get("output_refs", []), list):
        errors.append(f"executor evidence output_refs must be a list: {evidence_rel}")
    outputs = evidence.get("outputs", [])
    if not isinstance(outputs, list) or not outputs:
        errors.append(f"executor evidence outputs must be a non-empty list: {evidence_rel}")
        return
    for output in outputs:
        output_rel = str(output.get("path", "") if isinstance(output, dict) else output).strip()
        try:
            rel = safe_rel(output_rel)
        except ValueError as exc:
            errors.append(str(exc))
            continue
        if rel not in provenance_paths:
            errors.append(f"executor evidence output lacks artifact provenance: {rel}")


def validate_state(state_path: Path) -> Dict[str, Any]:
    errors: List[str] = []
    warnings: List[str] = []
    state = load_json(state_path, errors)
    run_root = state_path.parent
    status = str(state.get("status", "")).strip()
    failure_kind = str(state.get("failure_kind", "")).strip()
    if state.get("schema_version") != 1:
        errors.append("schema_version must be 1")
    if state.get("schema_name") != "target-workflow-runtime-state":
        errors.append("schema_name must be target-workflow-runtime-state")
    if status not in VALID_STATUS:
        errors.append(f"status must be one of {sorted(VALID_STATUS)}")
    if failure_kind not in VALID_FAILURE_KIND:
        errors.append(f"failure_kind must be one of {sorted(VALID_FAILURE_KIND)}")

    node_payload = load_json(run_root / str(state.get("node_results_path", "node-results.json")), errors)
    provenance_payload = load_json(run_root / str(state.get("artifact_provenance_path", "artifact-provenance.json")), errors)
    events = load_events(run_root / str(state.get("events_path", "target-events.jsonl")), errors)
    event_types = {str(item.get("event", "")).strip() for item in events}
    missing_events = sorted(REQUIRED_EVENTS - event_types)
    for event in missing_events:
        errors.append(f"missing lifecycle event: {event}")

    nodes = node_payload.get("nodes", [])
    if not isinstance(nodes, list) or not nodes:
        errors.append("node-results.json.nodes must be a non-empty list")
        nodes = []
    artifacts = provenance_payload.get("artifacts", [])
    if not isinstance(artifacts, list):
        errors.append("artifact-provenance.json.artifacts must be a list")
        artifacts = []
    provenance_paths = {str(item.get("path", "")).strip() for item in artifacts if isinstance(item, dict)}
    provider = str(state.get("executor_provider", state.get("provider", ""))).strip()
    manual_provider = provider in MANUAL_EXECUTOR_PROVIDERS
    if status == "BLOCKED":
        if not manual_provider:
            errors.append("BLOCKED target state is only allowed for current_agent/manual executor providers")
        if state.get("manual_finalizer_required") is not True:
            errors.append("BLOCKED current-agent/manual state requires manual_finalizer_required=true")
    if status == "PASS" and manual_provider and str(state.get("finalizer_status", "")).strip() != "PASS":
        errors.append("manual/current-agent target-state PASS requires finalizer_status=PASS")
    for idx, raw_node in enumerate(nodes):
        if not isinstance(raw_node, dict):
            errors.append(f"nodes[{idx}] must be object")
            continue
        node_id = str(raw_node.get("node_id", "")).strip()
        node_status = str(raw_node.get("status", "")).strip()
        if not node_id:
            errors.append(f"nodes[{idx}].node_id is required")
        if node_status not in {"PASS", "FAIL", "BLOCKED"}:
            errors.append(f"nodes[{idx}].status must be PASS, FAIL, or BLOCKED")
        if node_status == "BLOCKED" and not (status == "BLOCKED" and manual_provider):
            errors.append(f"BLOCKED node is only allowed for BLOCKED current_agent/manual target state: {node_id}")
        if status == "PASS" and node_status != "PASS":
            errors.append(f"PASS target state cannot contain failed node: {node_id}")
        outputs = raw_node.get("outputs", [])
        if not isinstance(outputs, list):
            errors.append(f"nodes[{idx}].outputs must be a list")
            outputs = []
        if status in {"PASS", "BLOCKED"} and node_status == "PASS":
            for output in outputs:
                rel = str(output).strip()
                if rel and not rel.startswith("$") and "/" in rel and rel not in provenance_paths:
                    errors.append(f"missing artifact provenance for output: {rel}")
        if manual_provider and status in {"PASS", "BLOCKED"} and node_status == "PASS":
            validate_executor_evidence(run_root, raw_node, provider, provenance_paths, errors)

    if status == "PASS" and failure_kind != "none":
        errors.append("PASS target state must use failure_kind=none")
    if status not in {"PASS", "BLOCKED"} and failure_kind == "none":
        warnings.append("non-PASS target state should usually provide a non-none failure_kind")

    return {
        "status": "PASS" if not errors else "FAIL",
        "errors": errors,
        "warnings": warnings,
        "state": str(state_path),
    }


def main() -> int:
    args = parse_args()
    payload = validate_state(Path(args.state).resolve())
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"[{payload['status']}] {payload['state']}")
        for error in payload["errors"]:
            print(f"[ERROR] {error}")
        for warning in payload["warnings"]:
            print(f"[WARN] {warning}")
    return 0 if payload["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
