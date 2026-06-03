#!/usr/bin/env python3
"""Validate S3 design-review closure before S4 target writes."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List

from lib.diagnostics import DiagnosticCollector
from lib.io_utils import utc_now, write_json
from lib.reporting import with_report_fields


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate WorkflowProgram design-review gate")
    parser.add_argument("--run-root", required=True, help="RUN_ROOT for this develop run")
    parser.add_argument("--packet", default="", help="design-review-packet.json path")
    parser.add_argument("--issues", default="", help="issues.json path")
    parser.add_argument("--closure", default="", help="closure.json path")
    parser.add_argument("--out", default="", help="gate-validation.json output path")
    parser.add_argument("--json", action="store_true", help="Print JSON result")
    return parser.parse_args()


def load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def sha256_file(path: Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def packet_sha256(packet_path: Path) -> str | None:
    return sha256_file(packet_path)


def issue_list(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    raw = payload.get("issues", [])
    if not isinstance(raw, list):
        return []
    return [item for item in raw if isinstance(item, dict)]


def validate_issue_schema(issue: Dict[str, Any], diagnostics: DiagnosticCollector) -> None:
    required = [
        "id",
        "round_found",
        "status",
        "severity",
        "blocking",
        "lens",
        "affected_requirements",
        "affected_artifacts",
        "problem",
        "why_it_matters",
        "required_fix",
        "resolved_by",
        "resolution_evidence",
        "residual_risk",
    ]
    issue_id = str(issue.get("id", "<missing>"))
    for field in required:
        if field not in issue:
            diagnostics.error(f"issue {issue_id} missing required field: {field}")
    if str(issue.get("status", "")) not in {"open", "resolved", "accepted_risk", "superseded"}:
        diagnostics.error(f"issue {issue_id} has invalid status: {issue.get('status')}")
    if str(issue.get("severity", "")) not in {"blocker", "major", "minor", "info"}:
        diagnostics.error(f"issue {issue_id} has invalid severity: {issue.get('severity')}")
    if not isinstance(issue.get("blocking"), bool):
        diagnostics.error(f"issue {issue_id}.blocking must be boolean")
    if issue.get("status") == "resolved":
        if not str(issue.get("resolved_by", "")).strip():
            diagnostics.error(f"resolved issue {issue_id} missing resolved_by")
        evidence = issue.get("resolution_evidence", [])
        if not isinstance(evidence, list) or not evidence:
            diagnostics.error(f"resolved issue {issue_id} missing resolution_evidence")
    if issue.get("status") == "accepted_risk" and not str(issue.get("residual_risk", "")).strip():
        diagnostics.error(f"accepted risk issue {issue_id} missing residual_risk")


def current_fingerprints(run_root: Path, expected: Dict[str, Any]) -> Dict[str, str | None]:
    current: Dict[str, str | None] = {}
    for rel_path in expected:
        current[rel_path] = sha256_file(run_root / rel_path)
    return current


def validate_gate(run_root: Path, packet_path: Path, issues_path: Path, closure_path: Path) -> Dict[str, Any]:
    diagnostics = DiagnosticCollector()
    packet = load_json(packet_path)
    issues_payload = load_json(issues_path)
    closure = load_json(closure_path)

    if not packet:
        diagnostics.error(f"design-review packet missing or invalid: {packet_path}")
    elif packet.get("status") != "PASS":
        diagnostics.error(f"design-review packet status must be PASS, got: {packet.get('status')}")

    issues = issue_list(issues_payload)
    if not issues_payload:
        diagnostics.error(f"design-review issues missing or invalid: {issues_path}")
    elif "issues" not in issues_payload or not isinstance(issues_payload.get("issues"), list):
        diagnostics.error("design-review issues.json must contain an issues list")
    for issue in issues:
        validate_issue_schema(issue, diagnostics)

    open_blockers = [
        issue
        for issue in issues
        if bool(issue.get("blocking", False)) and str(issue.get("status", "")) == "open"
    ]
    if open_blockers:
        diagnostics.error(f"open blocking design-review issues remain: {[issue.get('id') for issue in open_blockers]}")

    accepted_risks = [issue for issue in issues if str(issue.get("status", "")) == "accepted_risk"]
    if not closure:
        diagnostics.error(f"design-review closure missing or invalid: {closure_path}")
    else:
        if closure.get("status") != "PASS":
            diagnostics.error(f"design-review closure status must be PASS, got: {closure.get('status')}")
        try:
            open_blocking_count = int(closure.get("open_blocking_count", -1))
        except Exception:
            open_blocking_count = -1
        if open_blocking_count != 0:
            diagnostics.error("design-review closure open_blocking_count must be 0")
        expected_packet_sha = packet_sha256(packet_path)
        if expected_packet_sha and closure.get("packet_sha256") != expected_packet_sha:
            diagnostics.error("design-review closure packet_sha256 is stale")

    expected_fps = packet.get("artifact_fingerprints", {}) if isinstance(packet.get("artifact_fingerprints"), dict) else {}
    current_fps = current_fingerprints(run_root, expected_fps)
    stale_artifacts = [
        rel_path
        for rel_path, expected_sha in expected_fps.items()
        if expected_sha != current_fps.get(rel_path)
    ]
    if stale_artifacts:
        diagnostics.error(f"design-review packet artifact fingerprints are stale: {stale_artifacts}")
    closure_fps = closure.get("artifact_fingerprints", {}) if isinstance(closure.get("artifact_fingerprints"), dict) else {}
    stale_closure_artifacts = [
        rel_path
        for rel_path, expected_sha in closure_fps.items()
        if expected_sha != current_fps.get(rel_path)
    ]
    if closure and stale_closure_artifacts:
        diagnostics.error(f"design-review closure artifact fingerprints are stale: {stale_closure_artifacts}")

    status = diagnostics.status
    block_reason = None if status == "PASS" else "design_review_unresolved"
    payload = {
        "generated_at": utc_now(),
        "run_root": str(run_root),
        "packet_path": str(packet_path),
        "issues_path": str(issues_path),
        "closure_path": str(closure_path),
        "issue_count": len(issues),
        "open_blocking_count": len(open_blockers),
        "accepted_risk_count": len(accepted_risks),
        "stale_artifacts": stale_artifacts,
        "stale_closure_artifacts": stale_closure_artifacts,
        "block_reason": block_reason,
        "errors": diagnostics.errors,
        "warnings": diagnostics.warnings,
        "status": status,
    }
    return with_report_fields(
        payload,
        schema_name="design-review-gate-validation",
        error_code=None if status == "PASS" else "DESIGN_REVIEW_GATE_FAILURE",
        failure_kind="none" if status == "PASS" else "design",
        remediation=[
            {
                "code": "CLOSE_DESIGN_REVIEW",
                "summary": "Resolve blocking design-review issues and regenerate closure before S4 writes.",
            }
        ]
        if status != "PASS"
        else [],
    )


def main() -> int:
    args = parse_args()
    run_root = Path(args.run_root).resolve()
    review_root = run_root / "outputs" / "stages" / "design-review"
    packet_path = Path(args.packet).resolve() if args.packet.strip() else review_root / "design-review-packet.json"
    issues_path = Path(args.issues).resolve() if args.issues.strip() else review_root / "issues.json"
    closure_path = Path(args.closure).resolve() if args.closure.strip() else review_root / "closure.json"
    out_path = Path(args.out).resolve() if args.out.strip() else review_root / "gate-validation.json"
    payload = validate_gate(run_root, packet_path, issues_path, closure_path)
    write_json(out_path, payload)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"{payload['status']} design-review gate")
    return 0 if payload["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
