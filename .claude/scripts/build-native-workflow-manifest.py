#!/usr/bin/env python3
"""Build a deterministic Native Workflow manifest.

Computes a stable candidate tree hash, validates four evidence reports,
and emits a native-workflow-manifest with six gates:
  designReview, staticValidation, interactiveSmoke, assetScope, driftCheck, manifest.

All six gates must PASS before the manifest is valid for publish qualification.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List


ALLOWED_MANAGED_PREFIXES = (".claude/", ".workflowprogram/design/", ".workflowprogram/runtime/")

SCHEMA_VERSION = 1
SCHEMA_NAME = "native-workflow-manifest"


def candidate_tree_hash(root: Path) -> str:
    """Stable hash of every file under root (relative path + bytes)."""
    if not root.is_dir():
        raise FileNotFoundError(f"Candidate root not found: {root}")
    files = sorted(path for path in root.rglob("*") if path.is_file())
    if not files:
        raise ValueError(f"Candidate root is empty: {root}")
    digest = hashlib.sha256()
    for path in files:
        relative = path.relative_to(root).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return f"sha256:{digest.hexdigest()}"


def load_report(path: Path) -> Dict[str, Any]:
    """Load and validate a JSON object report."""
    if not path.exists():
        raise FileNotFoundError(f"Report not found: {path}")
    raw = path.read_text(encoding="utf-8")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Malformed JSON in report {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"Report must be a JSON object, got {type(payload).__name__}: {path}")
    return payload


def _validate_blocking_issues(report: Dict[str, Any], label: str) -> List[str]:
    """Validate that blockingIssues is present, is a list, and is strictly empty."""
    issues: List[str] = []
    if "blockingIssues" not in report:
        issues.append(f"{label} is missing blockingIssues field")
        return issues
    bissues = report["blockingIssues"]
    if not isinstance(bissues, list):
        issues.append(f"{label} blockingIssues is not a list: {type(bissues).__name__}")
        return issues
    if bissues:
        issues.append(f"{label} has blocking issues: {bissues}")
    return issues


def validate_design_review(report: Dict[str, Any], candidate_hash: str) -> List[str]:
    issues: List[str] = []
    if report.get("status") != "PASS":
        issues.append("Design review status is not PASS")
    if report.get("candidateHash") != candidate_hash:
        issues.append("Design review candidateHash does not match current candidate")
    issues.extend(_validate_blocking_issues(report, "Design review"))
    return issues


def validate_static_validation(report: Dict[str, Any], candidate_hash: str) -> List[str]:
    issues: List[str] = []
    if report.get("status") != "PASS":
        issues.append("Static validation status is not PASS")
    if report.get("candidateHash") != candidate_hash:
        issues.append("Static validation candidateHash does not match current candidate")
    issues.extend(_validate_blocking_issues(report, "Static validation"))
    return issues


def validate_interactive_smoke(report: Dict[str, Any], candidate_hash: str) -> List[str]:
    issues: List[str] = []
    if report.get("status") != "PASS":
        issues.append("Interactive smoke status is not PASS")
    if report.get("candidateHash") != candidate_hash:
        issues.append("Interactive smoke candidateHash does not match current candidate")
    issues.extend(_validate_blocking_issues(report, "Interactive smoke"))
    evidence = report.get("interactiveEvidence") or report.get("evidence")
    if not isinstance(evidence, list) or len(evidence) == 0:
        issues.append("Interactive smoke must have non-empty evidence array")
    return issues


def validate_drift(report: Dict[str, Any], candidate_hash: str) -> List[str]:
    issues: List[str] = []
    if report.get("status") != "PASS":
        issues.append("Drift report status is not PASS")
    if report.get("candidateHash") != candidate_hash:
        issues.append("Drift report candidateHash does not match current candidate")
    issues.extend(_validate_blocking_issues(report, "Drift report"))
    if report.get("driftCheck") != "PASS":
        issues.append("Drift report driftCheck is not PASS")
    return issues


def validate_asset_scope(candidate_root: Path, workflow_script: Path) -> List[str]:
    issues: List[str] = []
    # Workflow script must reside inside candidate_root
    try:
        workflow_script.resolve().relative_to(candidate_root.resolve())
    except ValueError:
        issues.append(f"Workflow script {workflow_script} is not inside candidate root {candidate_root}")

    # No files outside managed prefixes
    for path in candidate_root.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(candidate_root).as_posix()
        if not relative.startswith(ALLOWED_MANAGED_PREFIXES):
            issues.append(f"Asset {relative} is outside managed prefixes {ALLOWED_MANAGED_PREFIXES}")

    # Must have at least one asset
    assets = sorted(
        p for p in candidate_root.rglob("*")
        if p.is_file() and p.relative_to(candidate_root).as_posix().startswith(ALLOWED_MANAGED_PREFIXES)
    )
    if not assets:
        issues.append("Candidate tree contains no managed assets")

    return issues


def build_gates(
    candidate_hash: str,
    design_issues: List[str],
    static_issues: List[str],
    smoke_issues: List[str],
    asset_issues: List[str],
    drift_issues: List[str],
) -> List[Dict[str, Any]]:
    """Build the five substantive gates. Manifest gate is added separately."""
    gates: List[Dict[str, Any]] = [
        {
            "name": "designReview",
            "status": "PASS" if not design_issues else "FAIL",
            "blockingIssues": design_issues,
        },
        {
            "name": "staticValidation",
            "status": "PASS" if not static_issues else "FAIL",
            "blockingIssues": static_issues,
        },
        {
            "name": "interactiveSmoke",
            "status": "PASS" if not smoke_issues else "FAIL",
            "blockingIssues": smoke_issues,
        },
        {
            "name": "assetScope",
            "status": "PASS" if not asset_issues else "FAIL",
            "blockingIssues": asset_issues,
        },
        {
            "name": "driftCheck",
            "status": "PASS" if not drift_issues else "FAIL",
            "blockingIssues": drift_issues,
        },
    ]
    return gates


def list_assets(candidate_root: Path) -> List[Dict[str, str]]:
    assets: List[Dict[str, str]] = []
    for path in sorted(candidate_root.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(candidate_root).as_posix()
        if not relative.startswith(ALLOWED_MANAGED_PREFIXES):
            continue
        sha = hashlib.sha256(path.read_bytes()).hexdigest()
        assets.append({
            "relativePath": relative,
            "sha256": sha,
        })
    return assets


def build_manifest(args: argparse.Namespace) -> Dict[str, Any]:
    # Validate required inputs are non-empty
    run_id = str(args.run_id).strip()
    if not run_id:
        raise ValueError("run-id must not be empty")
    workflow_name = str(args.workflow_name).strip()
    if not workflow_name:
        raise ValueError("workflow-name must not be empty")

    candidate_root = Path(args.candidate_root).resolve()
    if not candidate_root.is_dir():
        raise FileNotFoundError(f"Candidate root not found: {candidate_root}")
    files = sorted(p for p in candidate_root.rglob("*") if p.is_file())
    if not files:
        raise ValueError(f"Candidate root is empty: {candidate_root}")

    workflow_script = Path(args.workflow_script).resolve()
    if not workflow_script.is_file():
        raise FileNotFoundError(f"Workflow script not found: {workflow_script}")
    candidate_hash = candidate_tree_hash(candidate_root)

    # Validate reports
    blocking_issues: List[str] = []

    # Load reports (failures become gate issues)
    design_issues: List[str] = []
    static_issues: List[str] = []
    smoke_issues: List[str] = []
    drift_issues: List[str] = []

    try:
        design_report = load_report(Path(args.design_review_report))
        design_issues = validate_design_review(design_report, candidate_hash)
    except (FileNotFoundError, ValueError) as exc:
        design_issues.append(str(exc))

    try:
        static_report = load_report(Path(args.static_validation_report))
        static_issues = validate_static_validation(static_report, candidate_hash)
    except (FileNotFoundError, ValueError) as exc:
        static_issues.append(str(exc))

    try:
        smoke_report = load_report(Path(args.interactive_smoke_report))
        smoke_issues = validate_interactive_smoke(smoke_report, candidate_hash)
    except (FileNotFoundError, ValueError) as exc:
        smoke_issues.append(str(exc))

    try:
        drift_report = load_report(Path(args.drift_report))
        drift_issues = validate_drift(drift_report, candidate_hash)
    except (FileNotFoundError, ValueError) as exc:
        drift_issues.append(str(exc))

    asset_issues = validate_asset_scope(candidate_root, workflow_script)
    assets = list_assets(candidate_root)

    # The workflow script must be one of the managed assets, not merely a file
    # somewhere under candidate_root.
    try:
        wf_relative = workflow_script.relative_to(candidate_root).as_posix()
    except ValueError:
        wf_relative = None
    asset_paths = {asset["relativePath"] for asset in assets}
    if wf_relative and wf_relative not in asset_paths:
        asset_issues.append(f"Workflow script {wf_relative} is not in managed assets list")

    # Build five substantive gates first
    gates = build_gates(candidate_hash, design_issues, static_issues, smoke_issues, asset_issues, drift_issues)

    # Manifest gate: only PASS when manifest is structurally complete
    other_gate_names = {g["name"] for g in gates}
    required_other = {"designReview", "staticValidation", "interactiveSmoke", "assetScope", "driftCheck"}
    manifest_complete = required_other.issubset(other_gate_names)
    gates.append({
        "name": "manifest",
        "status": "PASS" if manifest_complete else "FAIL",
        "blockingIssues": [] if manifest_complete else ["Manifest is structurally incomplete: missing required gates"],
    })

    all_pass = all(g["status"] == "PASS" for g in gates)
    if not all_pass:
        for g in gates:
            if g["status"] != "PASS":
                blocking_issues.extend(g.get("blockingIssues", []))

    evidence_refs = [
        str(Path(args.design_review_report).resolve()),
        str(Path(args.static_validation_report).resolve()),
        str(Path(args.interactive_smoke_report).resolve()),
        str(Path(args.drift_report).resolve()),
    ]

    payload = {
        "schemaVersion": SCHEMA_VERSION,
        "schemaName": SCHEMA_NAME,
        "status": "PASS" if all_pass else "BLOCKED_PUBLISH",
        "runId": args.run_id,
        "workflowName": args.workflow_name,
        "workflowScript": str(workflow_script),
        "candidateRoot": str(candidate_root),
        "candidateHash": candidate_hash,
        "assets": assets,
        "gates": gates,
        "evidence": evidence_refs,
        "blockingIssues": blocking_issues,
    }

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build a Native Workflow manifest with six gates")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--candidate-root", required=True)
    parser.add_argument("--workflow-name", required=True)
    parser.add_argument("--workflow-script", required=True)
    parser.add_argument("--design-review-report", required=True)
    parser.add_argument("--static-validation-report", required=True)
    parser.add_argument("--interactive-smoke-report", required=True)
    parser.add_argument("--drift-report", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--json", action="store_true")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        payload = build_manifest(args)
    except Exception as exc:
        payload = {
            "schemaVersion": SCHEMA_VERSION,
            "schemaName": SCHEMA_NAME,
            "status": "BLOCKED_PUBLISH",
            "runId": args.run_id if hasattr(args, "run_id") else "",
            "workflowName": args.workflow_name if hasattr(args, "workflow_name") else "",
            "candidateHash": "",
            "assets": [],
            "gates": [],
            "evidence": [],
            "blockingIssues": [str(exc)],
        }
    if getattr(args, "json", False):
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(payload["status"])
    return 0 if payload["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
