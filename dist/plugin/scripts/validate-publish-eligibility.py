#!/usr/bin/env python3
# AUTO-GENERATED FROM .claude/ - DO NOT EDIT DIRECTLY
"""Validate whether a target workflow is eligible for marketplace publishing."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List

from lib.io_utils import iso_now, write_json
from lib.target_claude_guard import guard_required_by_spec, guard_validation_errors, target_claude_guard_config
from lib.target_design_refs import PERSISTENT_DEFAULTS, resolve_target_design_refs
from lib.yaml_utils import try_load_yaml_mapping


PUBLISH_DIR = "outputs/stages/publish"
REQUIRED_TARGET_FILES = [
    ".workflowprogram/design/workflow-spec.yaml",
    ".workflowprogram/design/workflow-maintenance.md",
    ".workflowprogram/runtime/runtime-manifest.json",
    ".workflowprogram/managed-files.json",
]
LEGACY_TARGET_FILE_ALIASES = {
    ".workflowprogram/design/workflow-maintenance.md": [".workflowprogram/design/workflow-lowlevel.md"],
}
REQUIRED_DEVELOP_EVIDENCE = [
    "state.json",
    "events.jsonl",
    "outputs/managed-change-result.json",
    "outputs/stages/design-review/closure.json",
    "outputs/stages/s5-validation-summary.json",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate target workflow publish eligibility")
    parser.add_argument("--target-root", required=True, help="Target workflow root")
    parser.add_argument("--run-root", required=True, help="Current publish RUN_ROOT")
    parser.add_argument("--develop-run-root", default="", help="Optional completed develop RUN_ROOT")
    parser.add_argument("--allow-warn", action="store_true", help="Allow latest S5 WARN with explicit acceptance")
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


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def relative(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


def latest_develop_run(target_root: Path, current_run_root: Path) -> Path | None:
    runs_root = target_root / ".workflowprogram" / "runs"
    if not runs_root.exists():
        return None
    candidates: List[Path] = []
    for candidate in runs_root.iterdir():
        if not candidate.is_dir():
            continue
        if candidate.resolve() == current_run_root.resolve():
            continue
        summary = candidate / "outputs" / "stages" / "s5-validation-summary.json"
        route = candidate / "outputs" / "stages" / "s0-route.json"
        route_payload = load_json(route)
        if summary.exists() and str(route_payload.get("intent", "develop")).strip() == "develop":
            candidates.append(candidate)
    if not candidates:
        return None
    return sorted(candidates, key=lambda item: (item.stat().st_mtime, item.name), reverse=True)[0]


def manifest_entry_paths(manifest: Dict[str, Any]) -> List[str]:
    entries = manifest.get("entries", [])
    if not isinstance(entries, list):
        return []
    paths: List[str] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        rel_path = str(entry.get("relative_path", "")).strip()
        if rel_path:
            paths.append(rel_path)
    return paths


def managed_conflicts(managed_result: Dict[str, Any]) -> List[Dict[str, Any]]:
    conflicts = managed_result.get("conflicts", [])
    return [item for item in conflicts if isinstance(item, dict)] if isinstance(conflicts, list) else []


def validate_eligibility(
    *,
    target_root: Path,
    run_root: Path,
    develop_run_root: Path | None,
    allow_warn: bool,
) -> Dict[str, Any]:
    errors: List[str] = []
    warnings: List[str] = []
    checks: List[Dict[str, Any]] = []

    def check(name: str, passed: bool, detail: str, *, severity: str = "error") -> None:
        checks.append({"name": name, "status": "PASS" if passed else "FAIL", "detail": detail, "severity": severity})
        if not passed:
            if severity == "warning":
                warnings.append(detail)
            else:
                errors.append(detail)

    if not target_root.exists():
        check("target_root_exists", False, f"target root not found: {target_root}")
    else:
        check("target_root_exists", True, f"target root exists: {target_root}")

    observed_files: List[Dict[str, str]] = []
    for rel_path in REQUIRED_TARGET_FILES:
        candidate_paths = [rel_path, *LEGACY_TARGET_FILE_ALIASES.get(rel_path, [])]
        existing_rel_path = next((candidate for candidate in candidate_paths if (target_root / candidate).exists()), "")
        exists = bool(existing_rel_path)
        detail = (
            f"{existing_rel_path} exists"
            if existing_rel_path
            else f"{rel_path} is missing; accepted legacy aliases={LEGACY_TARGET_FILE_ALIASES.get(rel_path, []) or ['<none>']}"
        )
        check(f"required_target_file:{rel_path}", exists, detail)
        if existing_rel_path:
            path = target_root / existing_rel_path
            if path.is_file():
                observed_files.append({"path": existing_rel_path, "canonical_path": rel_path, "sha256": sha256_file(path)})

    target_spec = try_load_yaml_mapping(target_root / ".workflowprogram" / "design" / "workflow-spec.yaml")
    if target_spec and guard_required_by_spec(target_spec):
        guard_config = target_claude_guard_config(target_spec)
        guard_rel = str(guard_config.get("file", "CLAUDE.md")).strip() or "CLAUDE.md"
        guard_path = target_root / guard_rel
        check("target_claude_guard_file_present", guard_path.exists(), f"{guard_rel} {'exists' if guard_path.exists() else 'is missing'}")
        if guard_path.exists() and guard_path.is_file():
            guard_errors = guard_validation_errors(guard_path.read_text(encoding="utf-8"), target_spec)
            check(
                "target_claude_guard_valid",
                not guard_errors,
                "target CLAUDE guard valid" if not guard_errors else "; ".join(guard_errors),
            )
    target_design_refs = resolve_target_design_refs(target_spec)
    target_design_governed = target_design_refs.canonical or bool(target_design_refs.persistent_refs)
    if target_design_governed:
        for key in ("design_overview", "design_detail", "acceptance_tests", "traceability_matrix"):
            rel_path = target_design_refs.persistent_refs.get(key, PERSISTENT_DEFAULTS[key])
            path = target_root / rel_path
            check(
                f"persistent_target_design_source:{key}",
                path.exists() and path.is_file(),
                f"{rel_path} {'exists' if path.exists() else 'is missing'}",
            )

    selected_develop_run = develop_run_root or latest_develop_run(target_root, run_root)
    if selected_develop_run is None:
        check("develop_run_selected", False, "no completed develop RUN_ROOT with S5 evidence was found")
    else:
        check("develop_run_selected", selected_develop_run.exists(), f"develop RUN_ROOT selected: {selected_develop_run}")

    develop_evidence: Dict[str, str] = {}
    s5_summary: Dict[str, Any] = {}
    managed_result: Dict[str, Any] = {}
    if selected_develop_run and selected_develop_run.exists():
        for rel_path in REQUIRED_DEVELOP_EVIDENCE:
            path = selected_develop_run / rel_path
            exists = path.exists()
            check(f"develop_evidence:{rel_path}", exists, f"{rel_path} {'exists' if exists else 'is missing'}")
            if exists and path.is_file():
                develop_evidence[rel_path] = sha256_file(path)
        s5_summary = load_json(selected_develop_run / "outputs" / "stages" / "s5-validation-summary.json")
        verdict = str(s5_summary.get("verdict", "")).strip()
        s5_ok = verdict == "PASS" or (allow_warn and verdict == "WARN")
        check("s5_verdict_publishable", s5_ok, f"latest develop S5 verdict={verdict or '<missing>'}")
        if verdict == "WARN" and allow_warn:
            warnings.append("publishing with S5 WARN was explicitly allowed")
        managed_result = load_json(selected_develop_run / "outputs" / "managed-change-result.json")
        conflicts = managed_conflicts(managed_result)
        check("managed_result_has_no_conflicts", not conflicts, f"managed conflicts={len(conflicts)}")

    manifest = load_json(target_root / ".workflowprogram" / "managed-files.json")
    managed_paths = manifest_entry_paths(manifest)
    check("managed_manifest_has_entries", bool(managed_paths), f"managed manifest entries={len(managed_paths)}")
    missing_managed = [path for path in managed_paths if not (target_root / path).exists()]
    check("managed_manifest_paths_exist", not missing_managed, f"missing managed paths={missing_managed or ['<none>']}")

    host_report = {}
    if selected_develop_run:
        host_report = load_json(selected_develop_run / "outputs" / "stages" / "host-capability-report.json")
    capabilities = host_report.get("capabilities", []) if isinstance(host_report.get("capabilities", []), list) else []
    missing_required = [
        str(item.get("id", "<unknown>"))
        for item in capabilities
        if isinstance(item, dict) and bool(item.get("required", False)) and str(item.get("status", "")).strip() != "ready"
    ]
    check("required_host_capabilities_ready", not missing_required, f"missing required host capabilities={missing_required or ['<none>']}")

    eligible = not errors
    payload = {
        "schema_version": 1,
        "generated_at": iso_now(),
        "eligible": eligible,
        "status": "PASS" if eligible else "FAIL",
        "errors": errors,
        "warnings": warnings,
        "target_root": str(target_root),
        "run_root": str(run_root),
        "develop_run_root": str(selected_develop_run) if selected_develop_run else None,
        "allow_warn": allow_warn,
        "checks": checks,
        "observed_target_files": observed_files,
        "develop_evidence": develop_evidence,
        "s5_verdict": s5_summary.get("verdict"),
        "managed_manifest_paths": managed_paths,
    }
    write_json(run_root / PUBLISH_DIR / "publish-eligibility.json", payload)
    return payload


def main() -> int:
    args = parse_args()
    target_root = Path(args.target_root).resolve()
    run_root = Path(args.run_root).resolve()
    develop_run_root = Path(args.develop_run_root).resolve() if args.develop_run_root.strip() else None
    payload = validate_eligibility(
        target_root=target_root,
        run_root=run_root,
        develop_run_root=develop_run_root,
        allow_warn=args.allow_warn,
    )
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"[{payload['status']}] publish eligibility for {target_root}")
        for item in payload["errors"]:
            print(f"- ERROR: {item}")
        for item in payload["warnings"]:
            print(f"- WARN: {item}")
    return 0 if payload["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
