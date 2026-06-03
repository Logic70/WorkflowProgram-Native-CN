#!/usr/bin/env python3
"""Validate per-run change-policy evidence before managed target writes."""

from __future__ import annotations

import argparse
import fnmatch
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List

from lib.diagnostics import DiagnosticCollector
from lib.io_utils import utc_now, write_json
from lib.reporting import with_report_fields


VALID_MODES = {"incremental", "replace_managed", "redesign_from_existing"}
VALID_SCOPES = {"parameter", "node", "graph", "contract", "runtime", "docs", "multi"}
REQUIRED_POLICY_FIELDS = {
    "schema_version",
    "mode",
    "scope",
    "target_state",
    "affected_artifacts",
    "preserve_user_edits",
    "requires_approval",
    "reason",
}
REQUIRED_IMPACT_FIELDS = {
    "old_design_sources_read",
    "readback_evidence_path",
    "existing_managed_manifest_status",
    "affected_spec_sections",
    "affected_design_source_sections",
    "affected_test_contract_categories",
    "affected_target_assets",
    "risks",
    "verification_plan",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate WorkflowProgram change policy evidence")
    parser.add_argument("--policy", required=True, help="Path to change-policy.json")
    parser.add_argument("--impact", required=True, help="Path to impact-analysis.json")
    parser.add_argument("--change-context", required=True, help="Path to original change-context.json")
    parser.add_argument("--current-context", default="", help="Optional freshly resolved change-context.json")
    parser.add_argument("--readback", default="", help="Path to existing-workflow-readback.json")
    parser.add_argument("--target-root", default="", help="Target root used for path validation")
    parser.add_argument("--run-root", default="", help="Run root used for default output")
    parser.add_argument("--out", default="", help="Optional validation report path")
    parser.add_argument("--auto-approve", action="store_true", help="Treat approval as auto-approved")
    parser.add_argument("--approval-status", default="", choices=["", "approved"], help="Manual approval status")
    parser.add_argument("--json", action="store_true", help="Print JSON")
    return parser.parse_args()


def load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def is_relative_safe(path: str) -> bool:
    value = path.strip().replace("\\", "/")
    return bool(value) and not value.startswith("/") and ".." not in Path(value).parts


def validate_path_list(name: str, value: Any, diagnostics: DiagnosticCollector, *, allow_glob: bool = False) -> List[str]:
    if not isinstance(value, list) or not value:
        diagnostics.error(f"{name} must be a non-empty list")
        return []
    normalized: List[str] = []
    for item in value:
        text = str(item).strip().replace("\\", "/")
        if not text:
            diagnostics.error(f"{name} contains an empty path")
            continue
        if not is_relative_safe(text):
            diagnostics.error(f"{name} contains unsafe path: {text}")
            continue
        if not allow_glob and any(ch in text for ch in "*?[]"):
            diagnostics.error(f"{name} does not allow glob pattern: {text}")
            continue
        normalized.append(text)
    return normalized


def fingerprints_changed(original: Dict[str, Any], current: Dict[str, Any]) -> List[str]:
    if not original or not current:
        return []
    original_fps = original.get("fingerprints", {}) if isinstance(original.get("fingerprints"), dict) else {}
    current_fps = current.get("fingerprints", {}) if isinstance(current.get("fingerprints"), dict) else {}
    changed: List[str] = []
    fingerprint_keys = ("design_spec_sha256", "maintenance_sha256", "managed_manifest_sha256")
    legacy_aliases = {"maintenance_sha256": "lowlevel_sha256"}
    for key in fingerprint_keys:
        legacy_key = legacy_aliases.get(key)
        original_value = original_fps.get(key, original_fps.get(legacy_key)) if legacy_key else original_fps.get(key)
        current_value = current_fps.get(key, current_fps.get(legacy_key)) if legacy_key else current_fps.get(key)
        if original_value != current_value:
            changed.append(key)
    return changed


def determine_approval_mode(auto_approve: bool, approval_status: str, requires_approval: bool) -> str:
    if not requires_approval:
        return "not-required"
    if auto_approve:
        return "auto-approved"
    if approval_status == "approved":
        return "approved"
    return "pending"


def matches_any(path: str, patterns: Iterable[str]) -> bool:
    return any(fnmatch.fnmatch(path, pattern) for pattern in patterns)


def main() -> int:
    args = parse_args()
    policy_path = Path(args.policy).resolve()
    impact_path = Path(args.impact).resolve()
    context_path = Path(args.change_context).resolve()
    current_context_path = Path(args.current_context).resolve() if args.current_context.strip() else None
    readback_path = Path(args.readback).resolve() if args.readback.strip() else None

    policy = load_json(policy_path)
    impact = load_json(impact_path)
    context = load_json(context_path)
    current_context = load_json(current_context_path) if current_context_path else {}
    diagnostics = DiagnosticCollector()
    block_reason = ""

    if not policy:
        diagnostics.error(f"change-policy.json is missing or invalid: {policy_path}")
        block_reason = "change_policy_required"
    if not impact:
        diagnostics.error(f"impact-analysis.json is missing or invalid: {impact_path}")
        block_reason = block_reason or "impact_analysis_missing"
    if not context:
        diagnostics.error(f"change-context.json is missing or invalid: {context_path}")
        block_reason = block_reason or "change_context_missing"

    if policy:
        missing = sorted(REQUIRED_POLICY_FIELDS - set(policy))
        for field in missing:
            diagnostics.error(f"change-policy.json missing required field: {field}")
        if policy.get("schema_version") != 1:
            diagnostics.error("change-policy.json schema_version must be 1")
        mode = str(policy.get("mode", "")).strip()
        scope = str(policy.get("scope", "")).strip()
        if mode not in VALID_MODES:
            diagnostics.error(f"change-policy.json mode must be one of {sorted(VALID_MODES)}")
        if scope not in VALID_SCOPES:
            diagnostics.error(f"change-policy.json scope must be one of {sorted(VALID_SCOPES)}")
        target_state = str(policy.get("target_state", "")).strip()
        context_state = str(context.get("target_state", "")).strip()
        if context_state and target_state != context_state:
            diagnostics.error(f"change-policy.json target_state '{target_state}' does not match change-context '{context_state}'")
        affected_artifacts = validate_path_list("change-policy.json affected_artifacts", policy.get("affected_artifacts"), diagnostics)
        allowed_derived = validate_path_list(
            "change-policy.json allowed_derived_artifacts",
            policy.get("allowed_derived_artifacts", []),
            diagnostics,
            allow_glob=True,
        ) if policy.get("allowed_derived_artifacts") else []
        if not isinstance(policy.get("preserve_user_edits"), bool):
            diagnostics.error("change-policy.json preserve_user_edits must be boolean")
        if not isinstance(policy.get("requires_approval"), bool):
            diagnostics.error("change-policy.json requires_approval must be boolean")
        if not str(policy.get("reason", "")).strip():
            diagnostics.error("change-policy.json reason must be non-empty")
        if policy.get("requires_approval") and not str(policy.get("approval_reason", "")).strip():
            diagnostics.error("change-policy.json approval_reason is required when requires_approval=true")
        if target_state in {"existing_unmanaged_workflow", "partial_workflow"} and policy.get("requires_approval") is not True:
            diagnostics.error(f"{target_state} changes require requires_approval=true")
        if mode == "redesign_from_existing" and policy.get("requires_approval") is not True:
            diagnostics.error("redesign_from_existing requires approval")
        if readback_path and mode == "redesign_from_existing" and not readback_path.exists():
            diagnostics.error(f"redesign_from_existing requires readback evidence: {readback_path}")
        approval_mode = determine_approval_mode(bool(args.auto_approve), args.approval_status, bool(policy.get("requires_approval", False)))
        if policy.get("requires_approval") is True and approval_mode == "pending":
            diagnostics.error("approval is required but no trusted approval was provided")
            block_reason = block_reason or "change_approval_missing"
    else:
        affected_artifacts = []
        allowed_derived = []
        approval_mode = "pending"

    if impact:
        missing_impact = sorted(REQUIRED_IMPACT_FIELDS - set(impact))
        for field in missing_impact:
            diagnostics.error(f"impact-analysis.json missing required field: {field}")
        if "spec_change_required" in impact and impact.get("spec_change_required") is False and not str(impact.get("spec_change_reason", "")).strip():
            diagnostics.error("impact-analysis.json spec_change_reason is required when spec_change_required=false")
        if (
            "test_contract_change_required" in impact
            and impact.get("test_contract_change_required") is False
            and not str(impact.get("test_contract_change_reason", "")).strip()
        ):
            diagnostics.error("impact-analysis.json test_contract_change_reason is required when test_contract_change_required=false")

    stale_fingerprints = fingerprints_changed(context, current_context)
    if stale_fingerprints:
        diagnostics.error(f"change context is stale: {stale_fingerprints}")
        block_reason = block_reason or "change_context_stale"

    if diagnostics.errors and not block_reason:
        block_reason = "change_policy_invalid"

    expanded_allowed = sorted({*affected_artifacts, *allowed_derived})
    payload = {
        "generated_at": utc_now(),
        "policy_path": str(policy_path),
        "impact_path": str(impact_path),
        "change_context_path": str(context_path),
        "current_context_path": str(current_context_path) if current_context_path else None,
        "readback_path": str(readback_path) if readback_path else None,
        "approval_mode": approval_mode,
        "block_reason": block_reason or None,
        "affected_artifacts": affected_artifacts,
        "allowed_derived_artifacts": allowed_derived,
        "expanded_allowed_artifacts": expanded_allowed,
        "stale_fingerprints": stale_fingerprints,
        "errors": diagnostics.errors,
        "warnings": diagnostics.warnings,
        "status": diagnostics.status,
        "sample_match_check": {
            "enabled": bool(expanded_allowed),
            "all_affected_allowed": all(matches_any(path, expanded_allowed) for path in affected_artifacts) if expanded_allowed else True,
        },
    }
    payload = with_report_fields(
        payload,
        schema_name="change-policy-validation",
        error_code=None if diagnostics.status == "PASS" else "CHANGE_POLICY_FAILURE",
        failure_kind="none" if diagnostics.status == "PASS" else "design",
        remediation=[
            {
                "code": "FIX_CHANGE_POLICY_EVIDENCE",
                "summary": "Regenerate route/context/readback/change-policy/impact evidence before managed apply.",
            }
        ]
        if diagnostics.status != "PASS"
        else [],
    )

    out_path: Path | None = None
    if args.out.strip():
        out_path = Path(args.out).resolve()
    elif args.run_root.strip():
        out_path = Path(args.run_root).resolve() / "outputs" / "stages" / "validate-change-policy.json"
    if out_path:
        write_json(out_path, payload)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"{payload['status']} change-policy validation")
    return 0 if payload["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
