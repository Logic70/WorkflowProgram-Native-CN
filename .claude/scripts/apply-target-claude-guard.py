#!/usr/bin/env python3
"""Apply a WorkflowProgram runtime guard block to TARGET_ROOT/CLAUDE.md."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict

from lib.io_utils import iso_now, write_json
from lib.target_claude_guard import (
    apply_guard_block,
    guard_required_by_spec,
    guard_validation_errors,
    render_guard_block,
    sha256_text,
    target_claude_guard_config,
)
from lib.yaml_utils import load_yaml_mapping


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Apply target project CLAUDE.md runtime guard block")
    parser.add_argument("--spec", required=True, help="Path to workflow-spec.yaml")
    parser.add_argument("--target-root", required=True, help="Target project root")
    parser.add_argument("--run-root", required=True, help="RUN_ROOT path")
    parser.add_argument("--json", action="store_true", help="Print JSON payload")
    return parser.parse_args()


def apply_guard(*, spec_path: Path, target_root: Path, run_root: Path) -> Dict[str, Any]:
    spec = load_yaml_mapping(spec_path)
    config = target_claude_guard_config(spec)
    stages_root = run_root / "outputs" / "stages"
    rendered_path = stages_root / "target-claude-guard.md"
    report_path = stages_root / "target-claude-guard-apply.json"

    if config.get("enabled") is False and not guard_required_by_spec(spec):
        payload = {
            "schema_version": 1,
            "generated_at": iso_now(),
            "status": "SKIPPED",
            "action": "skip",
            "reason": "target_claude_guard.enabled=false and guard is not required by target runtime policy",
            "target_root": str(target_root),
            "spec": str(spec_path),
        }
        write_json(report_path, payload)
        return payload

    block = render_guard_block(spec, config)
    rendered_path.parent.mkdir(parents=True, exist_ok=True)
    rendered_path.write_text(block, encoding="utf-8", newline="\n")

    file_rel = str(config.get("file", "CLAUDE.md")).strip() or "CLAUDE.md"
    guard_path = target_root / file_rel
    existing_text = guard_path.read_text(encoding="utf-8") if guard_path.exists() else ""
    before_hash = sha256_text(existing_text) if guard_path.exists() else None
    status, action, result = apply_guard_block(existing_text, block, config)

    if status != "PASS":
        payload = {
            "schema_version": 1,
            "generated_at": iso_now(),
            "status": "CONFLICT",
            "action": action,
            "reason": result,
            "target_root": str(target_root),
            "target_file": str(guard_path),
            "rendered_guard": str(rendered_path),
            "before_sha256": before_hash,
            "block_sha256": sha256_text(block),
            "remediation": "Fix or remove the broken WorkflowProgram runtime guard markers in CLAUDE.md, then rerun develop.",
        }
        write_json(report_path, payload)
        return payload

    validation_errors = guard_validation_errors(result, spec)
    if validation_errors:
        payload = {
            "schema_version": 1,
            "generated_at": iso_now(),
            "status": "FAIL",
            "action": action,
            "errors": validation_errors,
            "target_root": str(target_root),
            "target_file": str(guard_path),
            "rendered_guard": str(rendered_path),
            "before_sha256": before_hash,
            "block_sha256": sha256_text(block),
        }
        write_json(report_path, payload)
        return payload

    guard_path.parent.mkdir(parents=True, exist_ok=True)
    guard_path.write_text(result, encoding="utf-8", newline="\n")
    after_hash = sha256_text(result)
    manifest_path = target_root / ".workflowprogram" / "claude-guard-manifest.json"
    manifest = {
        "manifest_version": 1,
        "file": file_rel,
        "block_id": str(config.get("block_id", "workflowprogram-runtime-guard")).strip(),
        "workflow_id": str(spec.get("meta", {}).get("name", "target-workflow")) if isinstance(spec.get("meta"), dict) else "target-workflow",
        "last_applied_block_sha256": sha256_text(block),
        "file_sha256_after": after_hash,
        "updated_at": iso_now(),
    }
    write_json(manifest_path, manifest)
    payload = {
        "schema_version": 1,
        "generated_at": iso_now(),
        "status": "PASS",
        "action": action,
        "target_root": str(target_root),
        "target_file": str(guard_path),
        "rendered_guard": str(rendered_path),
        "manifest_path": str(manifest_path),
        "before_sha256": before_hash,
        "after_sha256": after_hash,
        "block_sha256": sha256_text(block),
    }
    write_json(report_path, payload)
    return payload


def main() -> int:
    args = parse_args()
    payload = apply_guard(
        spec_path=Path(args.spec).resolve(),
        target_root=Path(args.target_root).resolve(),
        run_root=Path(args.run_root).resolve(),
    )
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"[{payload['status']}] target CLAUDE guard action={payload.get('action')}")
    if payload["status"] == "CONFLICT":
        return 2
    return 0 if payload["status"] in {"PASS", "SKIPPED"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
