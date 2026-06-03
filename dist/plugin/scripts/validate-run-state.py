#!/usr/bin/env python3
# AUTO-GENERATED FROM .claude/ - DO NOT EDIT DIRECTLY
"""
按 LowLevel 的状态与产物契约校验 RUN_ROOT/state.json。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

from lib.diagnostics import DiagnosticCollector


VALID_INTENT = {"develop", "audit", "iterate", "validate"}
VALID_APPROVAL_STATUS = {"pending", "approved", "rejected", "auto-approved"}
VALID_STAGE_STATUS = {"running", "blocked", "failed", "done"}
VALID_VERDICT = {"PASS", "WARN", "FAIL", "ENVIRONMENT-SKIP"}
VALID_FAILURE_KIND = {"none", "design", "implementation", "environment", "conflict"}

VALID_ROOT = {"PLUGIN_ROOT", "TARGET_ROOT", "RUN_ROOT", "TEMP_ROOT"}
VALID_PRODUCER = {"S0", "S1", "S2", "S3", "S4", "S5", "S6"}
VALID_FORMAT = {"md", "yaml", "json", "jsonl", "txt", "dir"}
VALID_LIFECYCLE = {"ephemeral", "evidence", "deliverable", "cache"}
VALID_STATUS = {"planned", "generated", "validated", "applied", "conflict", "archived"}
VALID_KIND = {
    "spec",
    "view",
    "agent",
    "skill",
    "command",
    "rule",
    "settings",
    "report",
    "test_scenario",
    "transcript",
    "event_log",
    "state_snapshot",
    "requirement_index",
    "question_backlog",
    "requirement_logic_map",
    "context_findings",
    "design_source",
    "node_design",
    "implementation_plan",
    "acceptance_tests",
    "traceability_matrix",
    "design_review_packet",
    "design_review_issue",
    "design_review_closure",
    "design_review_gate",
    "change_context",
    "existing_workflow_readback",
    "change_policy",
    "impact_analysis",
    "change_policy_validation",
    "change_traceability",
    "candidate_asset",
    "managed_manifest",
    "managed_plan",
    "managed_result",
    "managed_rollback",
    "managed_recovery",
    "build_manifest",
    "host_capability_report",
    "host_bootstrap_plan",
    "host_bootstrap_apply",
    "host_bootstrap_execution",
    "host_bootstrap_manifest",
    "host_capability_candidates",
    "host_bootstrap_instructions",
    "team_plan",
    "team_result",
    "team_join",
}


def parse_args() -> argparse.Namespace:
    """解析待校验的 RUN_ROOT 状态快照路径。"""
    parser = argparse.ArgumentParser(description="Validate RUN_ROOT state.json")
    parser.add_argument("--state", required=True, help="Path to state.json")
    parser.add_argument("--json", action="store_true", help="Print JSON result")
    return parser.parse_args()


def validate_enum(value: Any, valid_set: set[str], field: str, errors: List[str]) -> None:
    """当枚举字段超出允许值时追加一条 schema 错误。"""
    text = str(value)
    if text not in valid_set:
        errors.append(f"{field} must be one of {sorted(valid_set)}, got: {text}")


def validate_values(values: Dict[str, Any], errors: List[str]) -> None:
    """校验 state.json 顶层 `values` 对象。"""
    required = [
        "request_id",
        "intent",
        "target_root",
        "plugin_root",
        "run_root",
        "approval_status",
        "stage_status",
        "validation_verdict",
        "failure_kind",
        "next_action",
    ]
    for field in required:
        if field not in values:
            errors.append(f"values.{field} is required")

    if "intent" in values:
        validate_enum(values["intent"], VALID_INTENT, "values.intent", errors)
    if "approval_status" in values:
        validate_enum(values["approval_status"], VALID_APPROVAL_STATUS, "values.approval_status", errors)
    if "stage_status" in values:
        validate_enum(values["stage_status"], VALID_STAGE_STATUS, "values.stage_status", errors)
    if "validation_verdict" in values:
        validate_enum(values["validation_verdict"], VALID_VERDICT, "values.validation_verdict", errors)
    if "failure_kind" in values:
        validate_enum(values["failure_kind"], VALID_FAILURE_KIND, "values.failure_kind", errors)


def validate_artifact(index: int, artifact: Dict[str, Any], errors: List[str]) -> None:
    """按低层状态契约校验单个 artifact 条目。"""
    prefix = f"artifacts[{index}]"
    required = [
        "id",
        "kind",
        "root",
        "path",
        "producer",
        "format",
        "lifecycle",
        "status",
        "managed",
    ]
    for field in required:
        if field not in artifact:
            errors.append(f"{prefix}.{field} is required")

    if "kind" in artifact:
        validate_enum(artifact["kind"], VALID_KIND, f"{prefix}.kind", errors)
    if "root" in artifact:
        validate_enum(artifact["root"], VALID_ROOT, f"{prefix}.root", errors)
    if "producer" in artifact:
        validate_enum(artifact["producer"], VALID_PRODUCER, f"{prefix}.producer", errors)
    if "format" in artifact:
        validate_enum(artifact["format"], VALID_FORMAT, f"{prefix}.format", errors)
    if "lifecycle" in artifact:
        validate_enum(artifact["lifecycle"], VALID_LIFECYCLE, f"{prefix}.lifecycle", errors)
    if "status" in artifact:
        validate_enum(artifact["status"], VALID_STATUS, f"{prefix}.status", errors)

    path_value = str(artifact.get("path", ""))
    if path_value.startswith("/"):
        errors.append(f"{prefix}.path must be relative, got absolute path: {path_value}")

    managed_value = artifact.get("managed")
    if not isinstance(managed_value, bool):
        errors.append(f"{prefix}.managed must be boolean")
    # managed artifact 表示这类文件允许在 managed apply 契约下回写到 TARGET_ROOT。
    if managed_value and str(artifact.get("root")) != "TARGET_ROOT":
        errors.append(f"{prefix}.managed=true only allowed when root=TARGET_ROOT")


def main() -> int:
    """加载 state.json，执行校验，并输出文本或 JSON 诊断结果。"""
    args = parse_args()
    state_path = Path(args.state).resolve()
    if not state_path.exists():
        diagnostics = DiagnosticCollector()
        diagnostics.error(f"state file not found: {state_path}")
        if args.json:
            print(json.dumps(diagnostics.payload(state=str(state_path)), ensure_ascii=False, indent=2))
        else:
            print(f"Error: state file not found: {state_path}", file=sys.stderr)
        return 1

    try:
        payload = json.loads(state_path.read_text(encoding="utf-8"))
    except Exception as exc:
        diagnostics = DiagnosticCollector()
        diagnostics.error(f"cannot parse JSON: {exc}")
        if args.json:
            print(json.dumps(diagnostics.payload(state=str(state_path)), ensure_ascii=False, indent=2))
        else:
            print(f"Error: cannot parse JSON: {exc}", file=sys.stderr)
        return 1

    diagnostics = DiagnosticCollector()
    errors = diagnostics.errors
    if payload.get("schema_version") != 1:
        errors.append("schema_version must be 1")
    if not str(payload.get("schema_name", "")).strip():
        errors.append("schema_name is required")
    values = payload.get("values")
    artifacts = payload.get("artifacts")
    if not isinstance(values, dict):
        errors.append("values must be an object")
        values = {}
    if not isinstance(artifacts, list):
        errors.append("artifacts must be a list")
        artifacts = []

    validate_values(values, errors)

    seen_ids = set()
    for idx, item in enumerate(artifacts):
        if not isinstance(item, dict):
            errors.append(f"artifacts[{idx}] must be an object")
            continue
        validate_artifact(idx, item, errors)
        aid = str(item.get("id", ""))
        if aid:
            # artifact id 会被后续报告和工具链当作稳定引用，因此这里必须拒绝重复值。
            if aid in seen_ids:
                errors.append(f"Duplicate artifact id: {aid}")
            seen_ids.add(aid)

    result = diagnostics.payload(state=str(state_path))
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"[{result['status']}] state={state_path}")
        for item in errors:
            print(f"[ERROR] {item}")
        for item in result["warnings"]:
            print(f"[WARN] {item}")
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
