#!/usr/bin/env python3
# AUTO-GENERATED FROM .claude/ - DO NOT EDIT DIRECTLY
"""Validate final published state for a generated target workflow run."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List

from lib.yaml_utils import load_yaml_mapping


FINALIZER_PRODUCER = "target-runtime-finalizer.py"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate target final publish state")
    parser.add_argument("--spec", required=True, help="Path to target workflow-spec.yaml")
    parser.add_argument("--target-root", required=True, help="Target workflow root")
    parser.add_argument("--run-root", default="", help="Expected run root; defaults from manifest.run_root")
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


def load_json(path: Path, errors: List[str], label: str) -> Dict[str, Any]:
    if not path.exists():
        errors.append(f"{label} missing: {path}")
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        errors.append(f"{label} is not valid JSON: {exc}")
        return {}
    if not isinstance(payload, dict):
        errors.append(f"{label} JSON root must be object: {path}")
        return {}
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


def compare_resolved(path_a: Path, path_b: Path) -> bool:
    try:
        return path_a.resolve() == path_b.resolve()
    except Exception:
        return str(path_a) == str(path_b)


def validate_required_reports(run_root: Path, policy: Dict[str, Any], errors: List[str]) -> None:
    reports = policy.get("required_reports", [])
    if not isinstance(reports, list):
        errors.append("target_publish_policy.required_reports must be a list")
        return
    for idx, raw_report in enumerate(reports):
        if not isinstance(raw_report, dict):
            errors.append(f"target_publish_policy.required_reports[{idx}] must be object")
            continue
        try:
            rel = safe_rel(str(raw_report.get("path", "")))
        except ValueError as exc:
            errors.append(str(exc))
            continue
        field = str(raw_report.get("status_field", "")).strip()
        pass_values = [str(item).strip() for item in raw_report.get("pass_values", [])] if isinstance(raw_report.get("pass_values", []), list) else []
        if not field or not pass_values:
            errors.append(f"target_publish_policy.required_reports[{idx}] requires status_field and pass_values")
            continue
        payload = load_json(run_root / rel, errors, f"required report {rel}")
        if not payload:
            continue
        observed = dot_get(payload, field)
        if str(observed).strip() not in pass_values:
            errors.append(f"required report {rel} field {field} must be one of {pass_values}, got {observed}")


def validate_manifest_artifacts(target_root: Path, manifest: Dict[str, Any], publish_root: str, errors: List[str]) -> None:
    artifacts = manifest.get("artifacts", [])
    if not isinstance(artifacts, list) or not artifacts:
        errors.append("manifest.artifacts must be a non-empty list")
        return
    prefix = publish_root.rstrip("/") + "/"
    for idx, raw_artifact in enumerate(artifacts):
        if not isinstance(raw_artifact, dict):
            errors.append(f"manifest.artifacts[{idx}] must be object")
            continue
        try:
            rel = safe_rel(str(raw_artifact.get("path", "")))
        except ValueError as exc:
            errors.append(str(exc))
            continue
        if rel != publish_root and not rel.startswith(prefix):
            errors.append(f"manifest artifact must stay under publish_root: {rel}")
            continue
        path = target_root / rel
        if not path.exists():
            errors.append(f"published artifact missing: {rel}")
            continue
        expected_digest = str(raw_artifact.get("sha256", "")).strip()
        if path.is_file() and expected_digest and sha256_file(path) != expected_digest:
            errors.append(f"published artifact digest mismatch: {rel}")


def validate_run_evidence(run_root: Path, manifest: Dict[str, Any], policy: Dict[str, Any], errors: List[str]) -> None:
    state = load_json(run_root / "target-state.json", errors, "target-state.json")
    node_payload = load_json(run_root / "node-results.json", errors, "node-results.json")
    provenance_payload = load_json(run_root / "artifact-provenance.json", errors, "artifact-provenance.json")
    if state:
        if str(state.get("run_id", "")).strip() != str(manifest.get("run_id", "")).strip():
            errors.append("target-state run_id does not match manifest.run_id")
        if str(state.get("status", "")).strip() != "PASS":
            errors.append(f"target-state status must be PASS for published output, got {state.get('status')}")
        if str(state.get("finalizer_status", "")).strip() != "PASS":
            errors.append(f"target-state finalizer_status must be PASS, got {state.get('finalizer_status')}")
        if state.get("published") is not True:
            errors.append("target-state published must be true")
        expected_manifest = safe_rel(str(policy.get("manifest_path", "")))
        if str(state.get("publish_manifest", "")).strip().replace("\\", "/") != expected_manifest:
            errors.append("target-state publish_manifest does not match target_publish_policy.manifest_path")
    nodes = node_payload.get("nodes", []) if node_payload else []
    if not isinstance(nodes, list) or not nodes:
        errors.append("node-results.json.nodes must be a non-empty list")
    else:
        failed = [str(item.get("node_id", "")) for item in nodes if isinstance(item, dict) and str(item.get("status", "")).strip() != "PASS"]
        if failed:
            errors.append(f"node-results contains failed nodes: {failed}")
    artifacts = provenance_payload.get("artifacts", []) if provenance_payload else []
    if not isinstance(artifacts, list) or not artifacts:
        errors.append("artifact-provenance.json.artifacts must be a non-empty list")
    validate_required_reports(run_root, policy, errors)


def validate_publish_state(spec_path: Path, target_root: Path, expected_run_root: Path | None) -> Dict[str, Any]:
    errors: List[str] = []
    warnings: List[str] = []
    spec = load_yaml_mapping(spec_path)
    policy = publish_policy(spec)
    if policy.get("enabled") is not True:
        return {
            "schema_version": 1,
            "status": "PASS",
            "skipped": True,
            "reason": "target_publish_policy disabled",
            "errors": errors,
            "warnings": warnings,
            "target_root": str(target_root),
            "spec": str(spec_path),
        }

    try:
        publish_root = safe_rel(str(policy.get("publish_root", "")))
        manifest_rel = safe_rel(str(policy.get("manifest_path", "")))
        latest_rel = safe_rel(str(policy.get("latest_marker", "")))
    except ValueError as exc:
        errors.append(str(exc))
        publish_root = ""
        manifest_rel = ""
        latest_rel = ""

    manifest = load_json(target_root / manifest_rel, errors, "publish manifest") if manifest_rel else {}
    latest = load_json(target_root / latest_rel, errors, "latest marker") if latest_rel else {}
    run_root = expected_run_root
    if manifest:
        if str(manifest.get("producer", "")).strip() != FINALIZER_PRODUCER:
            errors.append("publish manifest producer must be target-runtime-finalizer.py")
        if str(manifest.get("finalizer_status", "")).strip() != "PASS":
            errors.append(f"publish manifest finalizer_status must be PASS, got {manifest.get('finalizer_status')}")
        if str(manifest.get("status", "")).strip() != "COMPLETE":
            errors.append(f"publish manifest status must be COMPLETE, got {manifest.get('status')}")
        if str(manifest.get("verdict", "")).strip() != "PASS":
            errors.append(f"publish manifest verdict must be PASS, got {manifest.get('verdict')}")
        if not str(manifest.get("run_id", "")).strip():
            errors.append("publish manifest run_id is required")
        manifest_run_root_text = str(manifest.get("run_root", "")).strip()
        if not manifest_run_root_text:
            errors.append("publish manifest run_root is required")
        else:
            manifest_run_root = Path(manifest_run_root_text)
            if run_root is not None and not compare_resolved(run_root, manifest_run_root):
                errors.append("publish manifest run_root does not match expected --run-root")
            run_root = run_root or manifest_run_root
        if publish_root:
            validate_manifest_artifacts(target_root, manifest, publish_root, errors)
    if latest and manifest:
        if str(latest.get("run_id", "")).strip() != str(manifest.get("run_id", "")).strip():
            errors.append("latest marker run_id does not match publish manifest")
        if str(latest.get("manifest", "")).strip().replace("\\", "/") != manifest_rel:
            errors.append("latest marker manifest does not match target_publish_policy.manifest_path")
        if str(latest.get("status", "")).strip() != "COMPLETE":
            errors.append(f"latest marker status must be COMPLETE, got {latest.get('status')}")
    if run_root is None:
        errors.append("run root is required to validate target publish state")
    else:
        validate_run_evidence(run_root, manifest, policy, errors)

    return {
        "schema_version": 1,
        "status": "PASS" if not errors else "FAIL",
        "errors": errors,
        "warnings": warnings,
        "target_root": str(target_root),
        "spec": str(spec_path),
        "run_root": str(run_root) if run_root is not None else "",
        "manifest": manifest_rel,
        "latest_marker": latest_rel,
    }


def main() -> int:
    args = parse_args()
    spec_path = Path(args.spec).resolve()
    target_root = Path(args.target_root).resolve()
    expected_run_root = Path(args.run_root).resolve() if args.run_root else None
    try:
        payload = validate_publish_state(spec_path, target_root, expected_run_root)
    except Exception as exc:
        payload = {
            "schema_version": 1,
            "status": "FAIL",
            "errors": [str(exc)],
            "warnings": [],
            "target_root": str(target_root),
            "spec": str(spec_path),
            "run_root": str(expected_run_root) if expected_run_root is not None else "",
        }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"[{payload['status']}] target publish state target_root={target_root}")
        for error in payload["errors"]:
            print(f"- ERROR: {error}")
        for warning in payload["warnings"]:
            print(f"- WARN: {warning}")
    return 0 if payload.get("status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
