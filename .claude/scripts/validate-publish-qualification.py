#!/usr/bin/env python3
"""Validate Native Workflow publish qualification.

Reads a native-workflow-manifest, independently recomputes candidateHash
and asset checksums, checks all six gates PASS, and verifies target managed
assets are not in drift or unmanaged conflict.

Exit codes:
  0 - PASS (ready to publish)
  1 - BLOCKED_PUBLISH (manifest, gate, or checksum issue)
  2 - BLOCKED_CONFLICT (target drift or unmanaged conflict)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List


EXCLUDE_PREFIXES = (".workflowprogram/runs/", ".git/")

ALLOWED_MANAGED_PREFIXES = (".claude/", ".workflowprogram/design/", ".workflowprogram/runtime/")

SCHEMA_VERSION = 1
SCHEMA_NAME = "native-publish-qualification"

REQUIRED_GATES = [
    "designReview",
    "staticValidation",
    "interactiveSmoke",
    "assetScope",
    "driftCheck",
    "manifest",
]


def candidate_tree_hash(root: Path) -> str:
    """Stable hash of every file under root (relative path + bytes)."""
    if not root.is_dir():
        raise FileNotFoundError(f"Candidate root not found: {root}")
    files = sorted(path for path in root.rglob("*") if path.is_file())
    if not files:
        raise ValueError(f"Candidate root is empty after exclusion: {root}")
    digest = hashlib.sha256()
    for path in files:
        relative = path.relative_to(root).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return f"sha256:{digest.hexdigest()}"


def target_tree_hash(root: Path) -> str:
    """Hash relative paths and bytes of every file under root, excluding mutable runtime material."""
    if not root.is_dir():
        raise FileNotFoundError(f"Target root not found: {root}")
    files = sorted(
        path for path in root.rglob("*")
        if path.is_file()
        and not path.relative_to(root).as_posix().startswith(EXCLUDE_PREFIXES)
    )
    if not files:
        return f"sha256:{hashlib.sha256(b'').hexdigest()}"
    digest = hashlib.sha256()
    for path in files:
        relative = path.relative_to(root).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return f"sha256:{digest.hexdigest()}"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_managed_manifest(target_root: Path) -> Dict[str, Any]:
    path = target_root / ".workflowprogram" / "managed-files.json"
    if not path.exists():
        return {"manifest_version": 1, "entries": []}
    return json.loads(path.read_text(encoding="utf-8"))


def validate_manifest_schema(manifest: Dict[str, Any]) -> List[str]:
    issues: List[str] = []
    if manifest.get("schemaName") != "native-workflow-manifest":
        issues.append("Manifest schemaName is not native-workflow-manifest")
    if manifest.get("schemaVersion") != 1:
        issues.append("Manifest schemaVersion is not 1")
    if manifest.get("status") != "PASS":
        issues.append(f"Manifest status is {manifest.get('status')}, expected PASS")
    if not manifest.get("runId"):
        issues.append("Manifest is missing runId")
    if not manifest.get("workflowName"):
        issues.append("Manifest is missing workflowName")

    # blockingIssues must be present and strictly empty
    if "blockingIssues" not in manifest:
        issues.append("Manifest is missing blockingIssues")
    else:
        bissues = manifest["blockingIssues"]
        if not isinstance(bissues, list):
            issues.append(f"Manifest blockingIssues is not a list: {type(bissues).__name__}")
        elif bissues:
            issues.append(f"Manifest blockingIssues is not empty: {bissues}")

    # evidence must be non-empty list
    evidence = manifest.get("evidence")
    if not isinstance(evidence, list) or len(evidence) == 0:
        issues.append("Manifest evidence is missing or empty")

    # assets must be non-empty list
    assets = manifest.get("assets")
    if not isinstance(assets, list) or len(assets) == 0:
        issues.append("Manifest assets is missing or empty")

    return issues


def validate_asset_safety(manifest: Dict[str, Any]) -> List[str]:
    """Validate that every declared asset has a safe, canonical relative path
    and that there are no duplicates."""
    issues: List[str] = []
    assets = manifest.get("assets", [])
    seen: set[str] = set()

    for i, asset in enumerate(assets):
        if not isinstance(asset, dict):
            issues.append(f"Asset[{i}] is not an object: {type(asset).__name__}")
            continue
        rel = asset.get("relativePath", "")
        if not rel or not isinstance(rel, str):
            issues.append(f"Asset[{i}] has empty or non-string relativePath")
            continue
        # Must not be absolute
        if rel.startswith("/") or rel.startswith("\\"):
            issues.append(f"Asset[{i}] relativePath is absolute: {rel}")
        # Must not contain ..
        if ".." in rel.split("/"):
            issues.append(f"Asset[{i}] relativePath contains path traversal: {rel}")
        # Must start with an allowed prefix
        if not rel.startswith(ALLOWED_MANAGED_PREFIXES):
            issues.append(f"Asset[{i}] relativePath not under allowed managed prefix: {rel}")

        # No duplicates
        if rel in seen:
            issues.append(f"Asset[{i}] duplicate relativePath: {rel}")
        seen.add(rel)

    return issues


def validate_asset_coverage(manifest: Dict[str, Any], candidate_root: Path) -> List[str]:
    """Declared assets must exactly match the set of files under allowed
    prefixes within the candidate root (no missing, no extra)."""
    issues: List[str] = []
    declared_assets = manifest.get("assets", [])
    declared_paths: set[str] = set()
    for asset in declared_assets:
        if isinstance(asset, dict) and isinstance(asset.get("relativePath"), str):
            declared_paths.add(asset["relativePath"])

    actual_paths: set[str] = set()
    for path in sorted(candidate_root.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(candidate_root).as_posix()
        if not relative.startswith(ALLOWED_MANAGED_PREFIXES):
            continue
        actual_paths.add(relative)

    missing = actual_paths - declared_paths
    extra = declared_paths - actual_paths

    for p in sorted(missing):
        issues.append(f"Asset {p} exists in candidate root but is not declared in manifest")
    for p in sorted(extra):
        issues.append(f"Asset {p} is declared in manifest but does not exist in candidate root")

    return issues


def validate_gates(manifest: Dict[str, Any]) -> List[str]:
    issues: List[str] = []
    gates = manifest.get("gates")
    if not isinstance(gates, list) or not gates:
        issues.append("Manifest gates are missing or empty")
        return issues

    # Check for duplicate gate names
    seen_names: set[str] = set()
    for g in gates:
        if isinstance(g, dict) and "name" in g:
            name = g["name"]
            if name in seen_names:
                issues.append(f"Duplicate gate name: {name}")
            seen_names.add(name)

    gate_map = {g["name"]: g for g in gates if isinstance(g, dict) and "name" in g}
    for required in REQUIRED_GATES:
        if required not in gate_map:
            issues.append(f"Missing required gate: {required}")
            continue
        gate = gate_map[required]
        if gate.get("status") != "PASS":
            issues.append(f"Gate {required} status is {gate.get('status')}")
    return issues


def validate_candidate_integrity(manifest: Dict[str, Any], candidate_root: Path) -> List[str]:
    issues: List[str] = []
    declared_hash = manifest.get("candidateHash", "")
    if not declared_hash:
        issues.append("Manifest is missing candidateHash")
        return issues

    try:
        actual_hash = candidate_tree_hash(candidate_root)
    except (FileNotFoundError, ValueError) as exc:
        issues.append(f"Cannot compute candidate hash: {exc}")
        return issues

    if actual_hash != declared_hash:
        issues.append(f"candidateHash mismatch: manifest={declared_hash} actual={actual_hash}")

    # Validate asset checksums
    declared_assets = manifest.get("assets", [])
    if not isinstance(declared_assets, list):
        issues.append("Manifest assets is not a list")
        return issues

    for asset in declared_assets:
        if not isinstance(asset, dict):
            continue
        rel = asset.get("relativePath", "")
        declared_sha = asset.get("sha256", "")
        asset_path = candidate_root / rel
        if not asset_path.exists():
            issues.append(f"Declared asset {rel} does not exist in candidate root")
            continue
        actual_sha = sha256_file(asset_path)
        if actual_sha != declared_sha:
            issues.append(f"Asset checksum drift: {rel} manifest={declared_sha} actual={actual_sha}")

    return issues


def validate_target_assets(manifest: Dict[str, Any], target_root: Path) -> List[str]:
    """Check target managed assets for drift or unmanaged conflicts."""
    issues: List[str] = []
    managed_manifest = load_managed_manifest(target_root)
    entries = {e["relative_path"]: e for e in managed_manifest.get("entries", [])}

    declared_assets = manifest.get("assets", [])
    if not isinstance(declared_assets, list):
        return issues

    for asset in declared_assets:
        if not isinstance(asset, dict):
            continue
        rel = asset.get("relativePath", "")
        target_path = target_root / rel

        if not target_path.exists():
            # Target does not exist ─ allowed
            continue

        target_sha = sha256_file(target_path)
        managed_entry = entries.get(rel)

        if managed_entry is None:
            # Target exists but is not managed ─ BLOCKED_CONFLICT
            issues.append(
                f"Target asset {rel} exists but is not managed by WorkflowProgram "
                f"(unmanaged conflict)"
            )
            continue

        # Managed entry exists ─ target hash must equal last_applied_hash
        last_applied = managed_entry.get("last_applied_hash", "")
        if target_sha != last_applied:
            issues.append(
                f"Target managed asset {rel} is in drift: "
                f"current={target_sha} last_applied={last_applied}"
            )

    return issues


def build_qualification(args: argparse.Namespace) -> Dict[str, Any]:
    manifest_path = Path(args.manifest)
    if not manifest_path.exists():
        raise FileNotFoundError(f"Manifest not found: {manifest_path}")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    candidate_root = Path(args.candidate_root).resolve()
    target_root = Path(args.target_root).resolve()

    # Target root must exist and be a directory
    if not target_root.exists():
        raise FileNotFoundError(f"Target root not found: {target_root}")
    if not target_root.is_dir():
        raise NotADirectoryError(f"Target root must be a directory: {target_root}")

    blocking_issues: List[str] = []

    schema_issues = validate_manifest_schema(manifest)
    blocking_issues.extend(schema_issues)

    gate_issues = validate_gates(manifest)
    blocking_issues.extend(gate_issues)

    # Asset safety and coverage (runs before target drift check so that
    # target drift only consumes already-validated safe paths)
    safety_issues = validate_asset_safety(manifest)
    blocking_issues.extend(safety_issues)
    coverage_issues = validate_asset_coverage(manifest, candidate_root)
    blocking_issues.extend(coverage_issues)

    # Candidate integrity only proceeds if assets pass basic safety
    if not safety_issues:
        integrity_issues = validate_candidate_integrity(manifest, candidate_root)
        blocking_issues.extend(integrity_issues)

    # Target drift check only after asset safety is confirmed
    if not safety_issues:
        target_issues = validate_target_assets(manifest, target_root)
    else:
        target_issues = []
    blocking_issues.extend(target_issues)

    has_target_conflict = any("unmanaged conflict" in i or "is in drift" in i for i in target_issues)

    try:
        target_hash = target_tree_hash(target_root)
    except Exception:
        target_hash = ""

    if blocking_issues:
        status = "BLOCKED_CONFLICT" if has_target_conflict else "BLOCKED_PUBLISH"
    else:
        status = "PASS"

    return {
        "schemaVersion": SCHEMA_VERSION,
        "schemaName": SCHEMA_NAME,
        "status": status,
        "candidateHash": manifest.get("candidateHash", ""),
        "targetHash": target_hash,
        "manifest": {
            "candidateHash": manifest.get("candidateHash", ""),
            "workflowName": manifest.get("workflowName", ""),
            "manifestPath": str(manifest_path.resolve()),
        },
        "gates": manifest.get("gates", []),
        "evidence": manifest.get("evidence", []),
        "blockingIssues": blocking_issues,
    }


def exit_code_for_status(status: str) -> int:
    if status == "PASS":
        return 0
    if status == "BLOCKED_CONFLICT":
        return 2
    return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate Native Workflow publish qualification")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--candidate-root", required=True)
    parser.add_argument("--target-root", required=True)
    parser.add_argument("--json", action="store_true")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        payload = build_qualification(args)
    except Exception as exc:
        payload = {
            "schemaVersion": SCHEMA_VERSION,
            "schemaName": SCHEMA_NAME,
            "status": "BLOCKED_PUBLISH",
            "candidateHash": "",
            "targetHash": "",
            "manifest": {},
            "gates": [],
            "evidence": [],
            "blockingIssues": [str(exc)],
        }
    if getattr(args, "json", False):
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(payload["status"])
    return exit_code_for_status(payload["status"])


if __name__ == "__main__":
    sys.exit(main())
