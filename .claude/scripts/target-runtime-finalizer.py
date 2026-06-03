#!/usr/bin/env python3
"""Finalize and atomically publish a generated target workflow run."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

from lib.io_utils import write_json
from lib.yaml_utils import load_yaml_mapping


MANUAL_EXECUTOR_PROVIDERS = {"current_agent", "manual"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Finalize generated target workflow runtime outputs")
    parser.add_argument("--spec", required=True, help="Path to target workflow-spec.yaml")
    parser.add_argument("--run-root", required=True, help="Current run root")
    parser.add_argument("--target-root", required=True, help="Target workflow root")
    parser.add_argument("--state", required=True, help="Path to target-state.json")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def safe_rel(path_text: str) -> str:
    cleaned = path_text.strip().replace("\\", "/")
    while cleaned.startswith("./"):
        cleaned = cleaned[2:]
    if not cleaned or cleaned.startswith("/") or ".." in cleaned.split("/"):
        raise ValueError(f"unsafe relative path: {path_text}")
    return cleaned


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(str(path))
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON root must be object: {path}")
    return payload


def dot_get(payload: Dict[str, Any], field: str) -> Any:
    value: Any = payload
    for part in field.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    return value


def publish_policy(spec: Dict[str, Any]) -> Dict[str, Any]:
    policy = spec.get("target_publish_policy", {})
    return policy if isinstance(policy, dict) else {}


def policy_enabled(policy: Dict[str, Any]) -> bool:
    return bool(policy.get("enabled", False))


def mark_state_failed(state_path: Path, reason: str, *, failure_kind: str = "implementation") -> None:
    try:
        state = load_json(state_path)
    except Exception:
        state = {
            "schema_version": 1,
            "schema_name": "target-workflow-runtime-state",
            "run_id": state_path.parent.name,
        }
    state["status"] = "FAIL"
    state["failure_kind"] = failure_kind
    state["failure_reason"] = reason
    state["finalizer_status"] = "FAIL"
    state["updated_at"] = utc_now()
    write_json(state_path, state)


def mark_state_published(state_path: Path, manifest_path: str, publish_seal: Dict[str, Any]) -> None:
    state = load_json(state_path)
    state["status"] = "PASS"
    state["failure_kind"] = "none"
    state["failure_reason"] = ""
    state["finalizer_status"] = "PASS"
    state["published"] = True
    state["publish_manifest"] = manifest_path
    state["publish_seal"] = publish_seal
    state["finalized_at"] = utc_now()
    state["updated_at"] = utc_now()
    write_json(state_path, state)


def verify_run_artifacts(run_root: Path, state: Dict[str, Any], policy: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], List[str]]:
    errors: List[str] = []
    required = policy.get("required_run_artifacts", [])
    if not isinstance(required, list) or not required:
        required = ["target-state.json", "node-results.json", "artifact-provenance.json"]
    for raw_path in required:
        rel = safe_rel(str(raw_path))
        if not (run_root / rel).exists():
            errors.append(f"missing required run artifact: {rel}")

    state_status = str(state.get("status", "")).strip()
    provider = str(state.get("executor_provider", state.get("provider", ""))).strip()
    manual_evidence_mode = provider in MANUAL_EXECUTOR_PROVIDERS and state_status == "BLOCKED"
    if state_status != "PASS" and not manual_evidence_mode:
        errors.append(f"target-state status must be PASS before publish, got {state.get('status')}")
    if str(state.get("failure_kind", "")).strip() != "none":
        errors.append(f"target-state failure_kind must be none before publish, got {state.get('failure_kind')}")

    node_payload = load_json(run_root / str(state.get("node_results_path", "node-results.json")))
    nodes = node_payload.get("nodes", [])
    if not isinstance(nodes, list) or not nodes:
        errors.append("node-results.json.nodes must be a non-empty list")
    else:
        failed = [str(item.get("node_id", "")) for item in nodes if isinstance(item, dict) and str(item.get("status", "")).strip() != "PASS"]
        if failed:
            errors.append(f"node-results contains failed nodes: {failed}")

    provenance_payload = load_json(run_root / str(state.get("artifact_provenance_path", "artifact-provenance.json")))
    artifacts = provenance_payload.get("artifacts", [])
    if not isinstance(artifacts, list):
        errors.append("artifact-provenance.json.artifacts must be a list")
        artifacts = []
    for idx, raw_artifact in enumerate(artifacts):
        if not isinstance(raw_artifact, dict):
            errors.append(f"artifact-provenance artifacts[{idx}] must be object")
            continue
        rel = safe_rel(str(raw_artifact.get("path", "")))
        source = run_root / rel
        if not source.exists():
            errors.append(f"artifact source missing: {rel}")
            continue
        expected_digest = str(raw_artifact.get("sha256", "")).strip()
        if source.is_file() and expected_digest and sha256_file(source) != expected_digest:
            errors.append(f"artifact digest mismatch: {rel}")
    if manual_evidence_mode:
        errors.extend(verify_manual_executor_evidence(run_root, nodes, artifacts, provider))
    return [item for item in artifacts if isinstance(item, dict)], errors


def verify_manual_executor_evidence(
    run_root: Path,
    nodes: List[Any],
    artifacts: List[Any],
    provider: str,
) -> List[str]:
    errors: List[str] = []
    artifact_paths = {str(item.get("path", "")).strip() for item in artifacts if isinstance(item, dict)}
    for idx, raw_node in enumerate(nodes):
        if not isinstance(raw_node, dict):
            continue
        node_id = str(raw_node.get("node_id", "")).strip()
        evidence_rel = str(raw_node.get("executor_evidence_path", "")).strip()
        if not evidence_rel:
            errors.append(f"manual executor node missing executor_evidence_path: {node_id or idx}")
            continue
        evidence = load_json(run_root / safe_rel(evidence_rel))
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
            continue
        for output in outputs:
            path = safe_rel(str(output.get("path", "") if isinstance(output, dict) else output))
            if path not in artifact_paths:
                errors.append(f"executor evidence output lacks provenance: {path}")
    return errors


def collect_required_report_seals(run_root: Path, policy: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], List[str]]:
    errors: List[str] = []
    seals: List[Dict[str, Any]] = []
    reports = policy.get("required_reports", [])
    if reports is None:
        reports = []
    if not isinstance(reports, list):
        return seals, ["target_publish_policy.required_reports must be a list"]
    for idx, raw_report in enumerate(reports):
        if not isinstance(raw_report, dict):
            errors.append(f"target_publish_policy.required_reports[{idx}] must be object")
            continue
        rel = safe_rel(str(raw_report.get("path", "")))
        field = str(raw_report.get("status_field", "")).strip()
        pass_values = [str(item).strip() for item in raw_report.get("pass_values", [])] if isinstance(raw_report.get("pass_values", []), list) else []
        if not field or not pass_values:
            errors.append(f"target_publish_policy.required_reports[{idx}] requires status_field and pass_values")
            continue
        report_path = run_root / rel
        payload = load_json(report_path)
        observed = dot_get(payload, field)
        seals.append(
            {
                "path": rel,
                "status_field": field,
                "observed": observed,
                "sha256": sha256_file(report_path) if report_path.is_file() else "",
            }
        )
        if str(observed).strip() not in pass_values:
            errors.append(f"required report {rel} field {field} must be one of {pass_values}, got {observed}")
    return seals, errors


def verify_required_reports(run_root: Path, policy: Dict[str, Any]) -> List[str]:
    _seals, errors = collect_required_report_seals(run_root, policy)
    return errors


def planned_publish_files(run_root: Path, policy: Dict[str, Any], artifacts: List[Dict[str, Any]]) -> Tuple[List[Tuple[Path, str]], List[str]]:
    errors: List[str] = []
    publish_root = safe_rel(str(policy.get("publish_root", "")))
    explicit = policy.get("publish_artifacts", [])
    planned: List[Tuple[Path, str]] = []
    if isinstance(explicit, list) and explicit:
        for idx, raw_item in enumerate(explicit):
            if not isinstance(raw_item, dict):
                errors.append(f"target_publish_policy.publish_artifacts[{idx}] must be object")
                continue
            source_rel = safe_rel(str(raw_item.get("from", "")))
            dest_rel = safe_rel(str(raw_item.get("to", source_rel)))
            if not dest_rel.startswith(publish_root + "/") and dest_rel != publish_root:
                dest_rel = f"{publish_root}/{dest_rel}"
            planned.append((run_root / source_rel, dest_rel))
    else:
        prefix = publish_root + "/"
        for artifact in artifacts:
            rel = safe_rel(str(artifact.get("path", "")))
            if rel == publish_root or rel.startswith(prefix):
                planned.append((run_root / rel, rel))
    if not planned:
        errors.append("no current-run artifacts are eligible for publish")
    for source, dest_rel in planned:
        if not source.exists():
            errors.append(f"publish source missing: {source}")
        if not dest_rel.startswith(publish_root + "/") and dest_rel != publish_root:
            errors.append(f"publish destination must stay under publish_root: {dest_rel}")
    return planned, errors


def copy_planned_files(planned: List[Tuple[Path, str]], stage_root: Path, publish_root: str) -> List[Dict[str, Any]]:
    published: List[Dict[str, Any]] = []
    prefix = publish_root + "/"
    for source, dest_rel in planned:
        relative_to_publish = dest_rel[len(prefix):] if dest_rel.startswith(prefix) else Path(dest_rel).name
        destination = stage_root / relative_to_publish
        if source.is_dir():
            shutil.copytree(source, destination, dirs_exist_ok=True)
            published.append({"path": dest_rel, "kind": "dir"})
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        published.append({"path": dest_rel, "kind": "file", "sha256": sha256_file(destination)})
    return published


def atomic_replace_dir(stage_root: Path, final_root: Path, run_id: str) -> None:
    final_root.parent.mkdir(parents=True, exist_ok=True)
    backup_root = final_root.parent / f".{final_root.name}.previous-{run_id}"
    if backup_root.exists():
        shutil.rmtree(backup_root)
    if final_root.exists():
        os.replace(final_root, backup_root)
    os.replace(stage_root, final_root)
    if backup_root.exists():
        shutil.rmtree(backup_root)


def finalize_run(spec_path: Path, run_root: Path, target_root: Path, state_path: Path) -> Dict[str, Any]:
    spec = load_yaml_mapping(spec_path)
    policy = publish_policy(spec)
    summary_path = run_root / "outputs" / "stages" / "target-finalizer-summary.json"
    if not policy_enabled(policy):
        payload = {
            "schema_version": 1,
            "status": "PASS",
            "skipped": True,
            "reason": "target_publish_policy disabled",
            "run_root": str(run_root),
            "target_root": str(target_root),
        }
        write_json(summary_path, payload)
        return payload

    publish_root = safe_rel(str(policy.get("publish_root", "")))
    manifest_path = safe_rel(str(policy.get("manifest_path", "")))
    latest_marker = safe_rel(str(policy.get("latest_marker", "")))
    run_id = run_root.name
    errors: List[str] = []
    state = load_json(state_path)
    artifacts, artifact_errors = verify_run_artifacts(run_root, state, policy)
    errors.extend(artifact_errors)
    required_report_seals, required_report_errors = collect_required_report_seals(run_root, policy)
    errors.extend(required_report_errors)
    planned, plan_errors = planned_publish_files(run_root, policy, artifacts)
    errors.extend(plan_errors)
    if errors:
        reason = "; ".join(errors)
        mark_state_failed(state_path, f"target finalizer failed: {reason}")
        payload = {
            "schema_version": 1,
            "status": "FAIL",
            "failure_kind": "implementation",
            "errors": errors,
            "run_root": str(run_root),
            "target_root": str(target_root),
            "publish_root": publish_root,
        }
        write_json(summary_path, payload)
        return payload

    final_root = target_root / publish_root
    stage_root = final_root.parent / f".{final_root.name}.tmp-{run_id}"
    if stage_root.exists():
        shutil.rmtree(stage_root)
    stage_root.mkdir(parents=True, exist_ok=True)
    published = copy_planned_files(planned, stage_root, publish_root)
    node_results_path = run_root / str(state.get("node_results_path", "node-results.json"))
    provenance_path = run_root / str(state.get("artifact_provenance_path", "artifact-provenance.json"))
    publish_seal = {
        "producer": "target-runtime-finalizer.py",
        "source_state_status": str(state.get("status", "")),
        "state_sha256": sha256_file(state_path),
        "node_results_sha256": sha256_file(node_results_path),
        "artifact_provenance_sha256": sha256_file(provenance_path),
        "required_reports": required_report_seals,
    }
    manifest_rel = manifest_path[len(publish_root) + 1:] if manifest_path.startswith(publish_root + "/") else Path(manifest_path).name
    latest_rel = latest_marker[len(publish_root) + 1:] if latest_marker.startswith(publish_root + "/") else Path(latest_marker).name
    manifest_payload = {
        "schema_version": 1,
        "producer": "target-runtime-finalizer.py",
        "finalizer_status": "PASS",
        "status": "COMPLETE",
        "verdict": "PASS",
        "run_id": run_id,
        "run_root": str(run_root),
        "target_root": str(target_root),
        "published_at": utc_now(),
        "workflow_name": str(spec.get("meta", {}).get("name", "")) if isinstance(spec.get("meta", {}), dict) else "",
        "workflow_version": str(spec.get("meta", {}).get("version", "")) if isinstance(spec.get("meta", {}), dict) else "",
        "artifact_count": len(published),
        "artifacts": published,
        **publish_seal,
    }
    write_json(stage_root / manifest_rel, manifest_payload)
    marker_payload = {
        "schema_version": 1,
        "status": "COMPLETE",
        "run_id": run_id,
        "run_root": str(run_root),
        "manifest": manifest_path,
        "published_at": manifest_payload["published_at"],
    }
    write_json(stage_root / latest_rel, marker_payload)
    atomic_replace_dir(stage_root, final_root, run_id)
    mark_state_published(state_path, manifest_path, publish_seal)
    payload = {
        "schema_version": 1,
        "status": "PASS",
        "run_root": str(run_root),
        "target_root": str(target_root),
        "publish_root": publish_root,
        "manifest_path": manifest_path,
        "latest_marker": latest_marker,
        "artifact_count": len(published),
        "published": published,
    }
    write_json(summary_path, payload)
    return payload


def main() -> int:
    args = parse_args()
    spec_path = Path(args.spec).resolve()
    run_root = Path(args.run_root).resolve()
    target_root = Path(args.target_root).resolve()
    state_path = Path(args.state).resolve()
    try:
        payload = finalize_run(spec_path, run_root, target_root, state_path)
    except Exception as exc:
        mark_state_failed(state_path, f"target finalizer failed: {exc}")
        payload = {
            "schema_version": 1,
            "status": "FAIL",
            "failure_kind": "implementation",
            "error": str(exc),
            "run_root": str(run_root),
            "target_root": str(target_root),
        }
        write_json(run_root / "outputs" / "stages" / "target-finalizer-summary.json", payload)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"[{payload['status']}] target finalizer run_root={run_root}")
    return 0 if payload.get("status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
