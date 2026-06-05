#!/usr/bin/env python3
# AUTO-GENERATED FROM .claude/ - DO NOT EDIT DIRECTLY
"""Normalize host-side Native develop reports into re-entrant Workflow JS evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any


def load_json(path: Path) -> dict[str, Any]:
    """Load one report object."""

    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Report must be a JSON object: {path}")
    return payload


def candidate_files(root: Path) -> list[Path]:
    """Return candidate files in stable relative-path order."""

    if not root.is_dir():
        raise FileNotFoundError(f"Candidate root not found: {root}")
    files = sorted(path for path in root.rglob("*") if path.is_file())
    if not files:
        raise ValueError(f"Candidate root is empty: {root}")
    return files


def candidate_hash(root: Path, files: list[Path]) -> str:
    """Hash relative paths and bytes so supporting-asset changes invalidate evidence."""

    digest = hashlib.sha256()
    for path in files:
        relative = path.relative_to(root).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return f"sha256:{digest.hexdigest()}"


def sha256_file(path: Path) -> str:
    """Return one file hash using the managed-assets hash format."""

    return hashlib.sha256(path.read_bytes()).hexdigest()


def is_absolute_path_ref(value: Any) -> bool:
    """Return true for non-empty POSIX, Windows drive, or UNC path strings."""

    if not isinstance(value, str) or not value.strip():
        return False
    text = value.strip()
    return text.startswith("/") or text.startswith("\\\\") or (len(text) >= 3 and text[0].isalpha() and text[1] == ":")


def path_identity(value: str) -> str:
    """Normalize Windows and WSL references to the same comparison identity."""

    text = value.strip().replace("\\", "/").rstrip("/")
    wsl_match = re.match(r"^/mnt/([A-Za-z])/(.*)$", text)
    if wsl_match:
        return f"{wsl_match.group(1).lower()}:/{wsl_match.group(2)}"
    if re.match(r"^[A-Za-z]:/", text):
        return text[0].lower() + text[1:]
    return text


def report_issues(payload: dict[str, Any], fallback: str) -> list[str]:
    """Extract readable blocking issues from known report shapes."""

    issues: list[str] = []
    for key in ("blockingIssues", "errors", "conflicts"):
        value = payload.get(key)
        if not isinstance(value, list):
            continue
        for item in value:
            if isinstance(item, dict):
                issues.append(str(item.get("message") or item.get("reason") or item))
            else:
                issues.append(str(item))
    return issues or [fallback]


def path_is_within(path: Path, root: Path) -> bool:
    """Return true when path resolves inside root."""

    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def validate_stage_report(stage: str, payload: dict[str, Any], candidate_root: Path) -> Path:
    """Require real generation/validation report schemas bound to the candidate tree."""

    schema_by_stage = {
        "generation": "native-workflow-js-generation",
        "validation": "native-workflow-js-validation",
    }
    expected_schema = schema_by_stage[stage]
    if payload.get("schema_name") != expected_schema:
        raise ValueError(f"{stage} report must use schema `{expected_schema}`.")
    if payload.get("schema_version") != 1:
        raise ValueError(f"{stage} report must use schema_version `1`.")
    if str(payload.get("status", "")).upper() != "PASS":
        raise ValueError(f"{stage} report did not pass: " + "; ".join(report_issues(payload, "status is not PASS")))
    if payload.get("errors") != []:
        raise ValueError(f"{stage} report contains errors: " + "; ".join(report_issues(payload, "errors must be empty")))

    script_key = "candidate_script" if stage == "generation" else "script"
    raw_script = payload.get(script_key)
    if not is_absolute_path_ref(raw_script):
        raise ValueError(f"{stage} report must contain an absolute `{script_key}`.")
    script_path = Path(str(raw_script)).resolve()
    if not script_path.is_file() or not path_is_within(script_path, candidate_root):
        raise ValueError(f"{stage} report `{script_key}` must identify a file in the current candidate tree.")
    relative_script = script_path.relative_to(candidate_root.resolve()).as_posix()
    if not re.fullmatch(r"\.claude/workflows/[^/]+\.js", relative_script):
        raise ValueError(f"{stage} report `{script_key}` must identify a `.claude/workflows/*.js` candidate.")
    return script_path


def build_report_evidence(stage: str, candidate_root: Path, report_path: Path) -> dict[str, Any]:
    """Normalize generation or validation reports."""

    files = candidate_files(candidate_root)
    digest = candidate_hash(candidate_root, files)
    payload = load_json(report_path)
    script_path = validate_stage_report(stage, payload, candidate_root)
    status = str(payload.get("status", "")).upper()
    evidence: dict[str, Any] = {
        "status": "PASS" if status == "PASS" else status or "FAIL",
        "candidateHash": digest,
        "workflowScriptPath": str(script_path),
        "evidence": [str(report_path.resolve())],
        "blockingIssues": [] if status == "PASS" else report_issues(payload, f"{stage} report did not pass."),
    }
    if stage == "generation":
        evidence["candidateRefs"] = [str(path.resolve()) for path in files]
    return evidence


def managed_result_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Return the managed-change-result from a direct or nested apply report."""

    if payload.get("schema_name") == "managed-change-result":
        return payload
    nested = payload.get("managed_result")
    if isinstance(nested, dict) and nested.get("schema_name") == "managed-change-result":
        return nested
    raise ValueError("Apply report must be a `managed-change-result` report or contain one in `managed_result`.")


def indexed_entries(items: Any, label: str) -> dict[str, dict[str, Any]]:
    """Index report entries by relative path and reject malformed duplicates."""

    if not isinstance(items, list):
        raise ValueError(f"{label} must be an array.")
    indexed: dict[str, dict[str, Any]] = {}
    for item in items:
        if not isinstance(item, dict) or not isinstance(item.get("relative_path"), str) or not item["relative_path"].strip():
            raise ValueError(f"{label} entries must contain a non-empty `relative_path`.")
        relative_path = item["relative_path"]
        if relative_path in indexed:
            raise ValueError(f"{label} contains duplicate relative_path: {relative_path}")
        indexed[relative_path] = item
    return indexed


def absolute_report_path(payload: dict[str, Any], key: str, label: str) -> Path:
    """Read one required absolute path from a report."""

    raw_value = payload.get(key)
    if not is_absolute_path_ref(raw_value):
        raise ValueError(f"{label} must contain an absolute non-empty `{key}`.")
    return Path(str(raw_value)).resolve()


def build_apply_evidence(candidate_root: Path, target_root: Path, report_path: Path) -> dict[str, Any]:
    """Verify managed apply coverage and return a structured apply manifest."""

    files = candidate_files(candidate_root)
    digest = candidate_hash(candidate_root, files)
    managed = managed_result_payload(load_json(report_path))
    if managed.get("schema_version") != 1:
        raise ValueError("Managed apply report must use schema_version `1`.")
    conflicts = managed.get("conflicts")
    if not isinstance(conflicts, list):
        raise ValueError("Managed apply report `conflicts` must be an array.")
    if conflicts:
        return {
            "status": "CONFLICT",
            "candidateHash": digest,
            "evidence": [str(report_path.resolve())],
            "blockingIssues": report_issues(managed, "Managed apply reported conflicts."),
            "applyManifest": None,
        }
    status = str(managed.get("status", "")).upper()
    if status and status != "PASS":
        raise ValueError("Managed apply report did not pass: " + "; ".join(report_issues(managed, f"status is {status}")))
    if managed.get("error_code") not in (None, ""):
        raise ValueError("Managed apply report contains an error code: " + str(managed.get("error_code")))

    managed_target_root = absolute_report_path(managed, "target_root", "Managed apply report")
    managed_source_root = absolute_report_path(managed, "source_root", "Managed apply report")
    managed_run_root = absolute_report_path(managed, "run_root", "Managed apply report")
    if path_identity(str(managed_target_root)) != path_identity(str(target_root.resolve())):
        raise ValueError("Managed apply report `target_root` does not match the requested target root.")
    if path_identity(str(managed_source_root)) != path_identity(str(candidate_root.resolve())):
        raise ValueError("Managed apply report `source_root` does not match the current candidate root.")

    manifest_path = absolute_report_path(managed, "manifest_path", "Managed apply report")
    expected_manifest_path = (target_root / ".workflowprogram" / "managed-files.json").resolve()
    if path_identity(str(manifest_path)) != path_identity(str(expected_manifest_path)):
        raise ValueError("Managed apply report `manifest_path` must identify TARGET_ROOT/.workflowprogram/managed-files.json.")
    if not manifest_path.exists():
        raise FileNotFoundError(f"Managed apply manifest not found: {manifest_path}")

    actual_report_path = (managed_run_root / "outputs" / "managed-change-result.json").resolve()
    if not actual_report_path.is_file():
        raise FileNotFoundError(f"Managed apply result not found at RUN_ROOT/outputs/managed-change-result.json: {actual_report_path}")
    actual_managed = load_json(actual_report_path)
    if actual_managed.get("schema_name") != "managed-change-result" or actual_managed != managed:
        raise ValueError("Apply evidence does not match the persisted managed-change-result report.")

    manifest = load_json(manifest_path)
    manifest_by_path = indexed_entries(manifest.get("entries"), "Managed apply manifest `entries`")

    applied = managed.get("applied")
    skipped = managed.get("skipped")
    if not isinstance(applied, list) or not isinstance(skipped, list):
        raise ValueError("Managed apply report must contain `applied` and `skipped` arrays.")
    report_by_path = indexed_entries([*applied, *skipped], "Managed apply report entries")

    normalized_entries: list[dict[str, str]] = []
    for path in files:
        relative_path = path.relative_to(candidate_root).as_posix()
        expected_hash = sha256_file(path)
        report_entry = report_by_path.get(relative_path)
        if report_entry is None:
            raise ValueError(f"Managed apply report does not cover candidate file: {relative_path}")
        action = str(report_entry.get("action", "")).strip()
        reported_hash = str(report_entry.get("applied_sha256", "")).strip()
        if action not in {"create", "update", "noop"}:
            raise ValueError(f"Managed apply report has invalid action for {relative_path}: {action or '<empty>'}")
        if reported_hash != expected_hash:
            raise ValueError(f"Managed apply report hash does not match candidate file: {relative_path}")
        manifest_entry = manifest_by_path.get(relative_path)
        if not isinstance(manifest_entry, dict) or str(manifest_entry.get("last_applied_hash", "")).strip() != expected_hash:
            raise ValueError(f"Managed apply manifest does not own the applied candidate hash: {relative_path}")
        target_path = target_root / relative_path
        if not target_path.is_file() or sha256_file(target_path) != expected_hash:
            raise ValueError(f"Managed target file does not match the applied candidate hash: {relative_path}")
        normalized_entries.append({"path": relative_path, "action": action, "sha256": expected_hash})

    evidence_paths = [report_path.resolve(), actual_report_path, manifest_path]
    return {
        "status": "PASS",
        "candidateHash": digest,
        "targetRoot": str(target_root.resolve()),
        "evidence": list(dict.fromkeys(str(path) for path in evidence_paths)),
        "blockingIssues": [],
        "applyManifest": {
            "manifestPath": str(manifest_path),
            "reportPath": str(actual_report_path),
            "entries": normalized_entries,
        },
    }


def validate_smoke_report(
    candidate_root: Path,
    candidate_digest: str,
    path: Path,
    expected_status: str,
) -> tuple[dict[str, Any] | None, list[str]]:
    """Validate one interactive-smoke evaluator report and normalize its proof."""

    try:
        payload = load_json(path)
    except Exception as exc:
        return None, [f"Smoke evidence is not valid JSON: {path} - {exc}"]

    issues: list[str] = []
    if payload.get("schema_name") != "native-workflow-interactive-smoke":
        issues.append(f"Smoke evidence is not a `native-workflow-interactive-smoke` evaluator report: {path}")
    if payload.get("schema_version") != 1:
        issues.append(f"Smoke evaluator report must use schema_version `1`: {path}")
    if str(payload.get("status", "")).upper() != "PASS" or payload.get("return_code") != 0:
        issues.append(f"Smoke evaluator report did not pass: {path}")
    if payload.get("blockingIssues") != []:
        issues.append(f"Smoke evaluator report contains blocking issues: {path}")

    workflow = payload.get("workflow")
    script_path = payload.get("scriptPath")
    script_hash = payload.get("scriptHash")
    report_candidate_hash = payload.get("candidateHash")
    report_expected_status = payload.get("expectedStatus")
    scenario = payload.get("scenario")
    evidence_profile = payload.get("evidenceProfile")
    run_ids = payload.get("runIds")
    evidence = payload.get("evidence")
    if not isinstance(workflow, str) or not workflow.strip():
        issues.append(f"Smoke evaluator report has no workflow name: {path}")
        candidate_script = None
    else:
        candidate_script = candidate_root / ".claude" / "workflows" / f"{workflow}.js"
        if not candidate_script.exists():
            issues.append(f"Smoke evaluator workflow is not present in the candidate tree: {workflow}")
    if not is_absolute_path_ref(script_path):
        issues.append(f"Smoke evaluator report has no absolute `scriptPath`: {path}")
    elif candidate_script is not None and path_identity(script_path) != path_identity(str(candidate_script.resolve())):
        issues.append(f"Smoke evaluator `scriptPath` does not identify the candidate workflow: {workflow}")
    if not isinstance(script_hash, str) or not script_hash.startswith("sha256:"):
        issues.append(f"Smoke evaluator report has no `scriptHash`: {path}")
    elif candidate_script is not None and candidate_script.exists() and script_hash != f"sha256:{sha256_file(candidate_script)}":
        issues.append(f"Smoke evaluator `scriptHash` does not match the candidate workflow: {workflow}")
    if report_candidate_hash != candidate_digest:
        issues.append(f"Smoke evaluator `candidateHash` does not match the current candidate tree: {path}")
    if report_expected_status != expected_status:
        issues.append(f"Smoke evaluator `expectedStatus` does not match requested status `{expected_status}`: {path}")
    if not isinstance(scenario, str) or not scenario.strip():
        issues.append(f"Smoke evaluator report has no non-empty scenario: {path}")
    if evidence_profile not in {"full", "early-blocker", "completion", "agent-schema"}:
        issues.append(f"Smoke evaluator report has invalid `evidenceProfile`: {path}")
    if evidence_profile == "early-blocker" and report_expected_status != "BLOCKED":
        issues.append(f"Smoke evaluator `early-blocker` profile is only valid with expectedStatus `BLOCKED`: {path}")
    if not isinstance(run_ids, list) or not run_ids or not all(isinstance(item, str) and item.strip() for item in run_ids):
        issues.append(f"Smoke evaluator report has no non-empty runIds: {path}")
    if not isinstance(evidence, dict):
        issues.append(f"Smoke evaluator report has no evidence object: {path}")
        evidence = {}

    for key in ("workflow_invoked", "async_launched", "agent_started", "schema_result"):
        if evidence.get(key) is not True:
            issues.append(f"Smoke evaluator report is missing evidence `{key}`: {path}")
    completion_key = "completed_pass" if expected_status == "PASS" else "completed_blocked"
    opposite_key = "completed_blocked" if expected_status == "PASS" else "completed_pass"
    if evidence.get(completion_key) is not True:
        issues.append(f"Smoke evaluator report is missing evidence `{completion_key}`: {path}")
    if evidence.get(opposite_key) is True:
        issues.append(f"Smoke evaluator report contains unexpected evidence `{opposite_key}`: {path}")
    if issues:
        return None, issues

    return {
        "reportPath": str(path.resolve()),
        "reportHash": f"sha256:{sha256_file(path)}",
        "workflow": workflow.strip(),
        "scriptPath": script_path.strip(),
        "scriptHash": script_hash,
        "candidateHash": report_candidate_hash,
        "scenarioId": scenario.strip(),
        "expectedStatus": expected_status,
        "runIds": run_ids,
        "evidenceProfile": evidence_profile,
        "evidence": {
            "workflow_invoked": True,
            "async_launched": True,
            "agent_started": True,
            "schema_result": True,
            completion_key: True,
        },
    }, []


def build_smoke_evidence(candidate_root: Path, status: str, evidence_paths: list[Path]) -> dict[str, Any]:
    """Normalize only evaluator-proven interactive smoke evidence."""

    files = candidate_files(candidate_root)
    digest = candidate_hash(candidate_root, files)
    expected_status = status.upper()
    blocking_issues: list[str] = []
    reports: list[dict[str, Any]] = []

    for path in evidence_paths:
        if not path.exists():
            blocking_issues.append(f"Smoke evidence path not found: {path}")
            continue
        if expected_status not in {"PASS", "BLOCKED"}:
            blocking_issues.append("Interactive smoke was explicitly marked as failed.")
            continue
        report, issues = validate_smoke_report(candidate_root, digest, path, expected_status)
        blocking_issues.extend(issues)
        if report is not None:
            reports.append(report)

    return {
        "status": "PASS" if not blocking_issues and reports else "FAIL",
        "candidateHash": digest,
        "evidence": [item["reportPath"] for item in reports],
        "smokeReports": reports,
        "blockingIssues": blocking_issues,
    }


def build_parser() -> argparse.ArgumentParser:
    """Build CLI parser."""

    parser = argparse.ArgumentParser(description="Build WorkflowProgram Native develop evidence")
    subparsers = parser.add_subparsers(dest="stage", required=True)
    for stage in ("generation", "validation", "apply"):
        sub = subparsers.add_parser(stage)
        sub.add_argument("--candidate-root", required=True)
        if stage == "apply":
            sub.add_argument("--target-root", required=True)
        sub.add_argument("--report", required=True)
        sub.add_argument("--json", action="store_true")
    smoke = subparsers.add_parser("smoke")
    smoke.add_argument("--candidate-root", required=True)
    smoke.add_argument("--status", required=True, choices=("PASS", "BLOCKED", "FAIL"))
    smoke.add_argument("--evidence", required=True, nargs="+")
    smoke.add_argument("--json", action="store_true")
    return parser


def main() -> int:
    """Normalize evidence and return a stable status code."""

    args = build_parser().parse_args()
    try:
        candidate_root = Path(args.candidate_root).resolve()
        if args.stage == "smoke":
            payload = build_smoke_evidence(candidate_root, args.status, [Path(item).resolve() for item in args.evidence])
        elif args.stage == "apply":
            payload = build_apply_evidence(candidate_root, Path(args.target_root).resolve(), Path(args.report).resolve())
        else:
            payload = build_report_evidence(args.stage, candidate_root, Path(args.report).resolve())
    except Exception as exc:
        payload = {
            "status": "FAIL",
            "candidateHash": "",
            "evidence": [],
            "blockingIssues": [str(exc)],
        }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"{payload['status']}: {payload.get('candidateHash', '')}")
    return 0 if payload["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
