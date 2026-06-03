#!/usr/bin/env python3
"""
探测 workflow-spec.yaml 中声明的宿主能力，并把结果写入 RUN_ROOT 证据。
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List

from lib.host_team_utils import host_capabilities_from_spec, host_global_adapter, project_local_outputs
from lib.host_probe_utils import detect_ready_status
from lib.io_utils import iso_now, write_json
from lib.reporting import with_report_fields
from lib.yaml_utils import load_yaml_mapping


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Probe host capabilities declared in workflow-spec.yaml")
    parser.add_argument("--spec", required=True, help="Path to workflow-spec.yaml")
    parser.add_argument("--target-root", required=True, help="TARGET_ROOT path")
    parser.add_argument("--run-root", required=True, help="RUN_ROOT path")
    parser.add_argument("--json", action="store_true", help="Print JSON payload")
    return parser.parse_args()


def build_report(spec_path: Path, target_root: Path, run_root: Path) -> Dict[str, Any]:
    spec = load_yaml_mapping(spec_path)
    capabilities = host_capabilities_from_spec(spec)
    checked_at = iso_now()
    report_capabilities: List[Dict[str, Any]] = []
    bootstrap_plan: List[Dict[str, Any]] = []

    for capability in capabilities:
        ready, status, message = detect_ready_status(target_root, capability)
        capability_id = str(capability.get("id", "")).strip()
        scope = str(capability.get("bootstrap", {}).get("scope", "")).strip() if isinstance(capability.get("bootstrap"), dict) else ""
        project_outputs = project_local_outputs(capability)
        report_capabilities.append(
            {
                "id": capability_id,
                "kind": str(capability.get("kind", "")).strip(),
                "name": str(capability.get("name", "")).strip(),
                "required": bool(capability.get("required", False)),
                "status": status,
                "message": message,
                "checked_at": checked_at,
                "approval_required": bool(capability.get("approval_required", False)),
                "bootstrap_scope": scope or "manual_only",
                "project_local_outputs": project_outputs,
            }
        )
        if not ready:
            bootstrap = capability.get("bootstrap", {}) if isinstance(capability.get("bootstrap"), dict) else {}
            bootstrap_plan.append(
                {
                    "capability_id": capability_id,
                    "kind": str(capability.get("kind", "")).strip(),
                    "required": bool(capability.get("required", False)),
                    "scope": scope or "manual_only",
                    "summary": str(bootstrap.get("summary", "")).strip() or f"Resolve missing capability: {capability_id}",
                    "approval_required": bool(capability.get("approval_required", False)),
                    "project_local_outputs": project_outputs,
                    "adapter": host_global_adapter(capability) if scope == "host_global" else {},
                }
            )

    required_missing = [
        item
        for item in report_capabilities
        if item.get("required") is True and str(item.get("status", "")).strip() != "ready"
    ]
    report = {
        "generated_at": checked_at,
        "spec": str(spec_path),
        "target_root": str(target_root),
        "run_root": str(run_root),
        "all_required_ready": not required_missing,
        "capabilities": report_capabilities,
        "bootstrap_plan": bootstrap_plan,
    }
    return with_report_fields(
        report,
        schema_name="host-capability-report",
        error_code="HOST_CAPABILITY_MISSING" if required_missing else None,
        failure_kind="environment" if required_missing else "none",
        remediation=[
            {
                "code": "APPLY_OR_COMPLETE_HOST_BOOTSTRAP",
                "summary": "Review host-bootstrap-plan.json and complete project-local, host-global, or manual bootstrap steps.",
            }
        ]
        if bootstrap_plan
        else [],
    )


def main() -> int:
    args = parse_args()
    spec_path = Path(args.spec).resolve()
    target_root = Path(args.target_root).resolve()
    run_root = Path(args.run_root).resolve()
    run_root.mkdir(parents=True, exist_ok=True)
    report = build_report(spec_path, target_root, run_root)
    report_path = run_root / "outputs" / "stages" / "host-capability-report.json"
    write_json(report_path, report)
    if report.get("bootstrap_plan"):
        write_json(
            run_root / "outputs" / "stages" / "host-bootstrap-plan.json",
            with_report_fields(
                {"generated_at": report.get("generated_at"), "plan": report["bootstrap_plan"]},
                schema_name="host-bootstrap-plan",
                error_code="HOST_CAPABILITY_MISSING",
                failure_kind="environment",
                remediation=report.get("remediation", []),
            ),
        )
    if args.json:
        payload = {"status": "PASS", "report": report, "report_path": str(report_path)}
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"[PASS] host capability report written to {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
