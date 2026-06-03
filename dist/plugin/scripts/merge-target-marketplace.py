#!/usr/bin/env python3
# AUTO-GENERATED FROM .claude/ - DO NOT EDIT DIRECTLY
"""Plan a safe merge of a target workflow plugin into an existing marketplace checkout."""

from __future__ import annotations

import argparse
import copy
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Tuple

from lib.io_utils import iso_now, write_json


PUBLISH_DIR = "outputs/stages/publish"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Plan existing marketplace merge for a target workflow plugin")
    parser.add_argument("--package-root", required=True)
    parser.add_argument("--run-root", required=True)
    parser.add_argument("--repo-path", required=True)
    parser.add_argument("--plugin-id", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--marketplace-name", default="")
    parser.add_argument("--update-existing-entry", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def load_json(path: Path) -> Tuple[Dict[str, Any], str]:
    if not path.exists():
        return {}, "missing"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {}, f"invalid: {exc}"
    if not isinstance(payload, dict):
        return {}, "invalid: root is not a JSON object"
    return payload, ""


def semver(value: str) -> Tuple[int, int, int] | None:
    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", value.strip())
    if not match:
        return None
    return tuple(int(item) for item in match.groups())


def source_matches(entry: Dict[str, Any], expected: str) -> bool:
    source = entry.get("source")
    return isinstance(source, str) and source == expected


def marketplace_entry(plugin_json: Dict[str, Any], plugin_id: str, plugin_path: str, version: str) -> Dict[str, Any]:
    description = str(plugin_json.get("description", "WorkflowProgram generated Claude Code workflow plugin")).strip()
    homepage = str(plugin_json.get("homepage", "")).strip()
    repository = str(plugin_json.get("repository", "")).strip()
    payload: Dict[str, Any] = {
        "name": plugin_id,
        "source": plugin_path,
        "description": description,
        "version": version,
        "license": str(plugin_json.get("license", "MIT")).strip() or "MIT",
        "keywords": list(plugin_json.get("keywords", ["workflow", "claude-code", "workflowprogram"])),
        "category": "workflow",
        "tags": ["workflow", "claude-code"],
        "strict": False,
    }
    if homepage:
        payload["homepage"] = homepage
    if repository:
        payload["repository"] = repository
    return payload


def emit_report(
    *,
    run_root: Path,
    repo_path: Path,
    manifest_path: Path,
    marketplace_name: str,
    plugin_id: str,
    expected_source: str,
    status: str,
    action: str,
    block_reason: str = "",
    errors: List[str] | None = None,
    warnings: List[str] | None = None,
    current_entry: Dict[str, Any] | None = None,
    preview: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    errors = errors or []
    warnings = warnings or []
    resolution = {
        "schema_version": 1,
        "generated_at": iso_now(),
        "repo_path": str(repo_path),
        "manifest_path": str(manifest_path),
        "marketplace_name": marketplace_name or None,
        "plugin_id": plugin_id,
        "expected_source": expected_source,
        "existing_entry": current_entry,
    }
    write_json(run_root / PUBLISH_DIR / "marketplace-resolution.json", resolution)
    plan = {
        "schema_version": 1,
        "generated_at": iso_now(),
        "status": status,
        "action": action,
        "block_reason": block_reason or None,
        "errors": errors,
        "warnings": warnings,
        "repo_path": str(repo_path),
        "manifest_path": str(manifest_path),
        "marketplace_name": marketplace_name or None,
        "plugin_id": plugin_id,
        "expected_source": expected_source,
    }
    write_json(run_root / PUBLISH_DIR / "marketplace-merge-plan.json", plan)
    write_json(
        run_root / PUBLISH_DIR / "marketplace-manifest-preview.json",
        {
            "schema_version": 1,
            "generated_at": iso_now(),
            "status": status,
            "marketplace_json": preview,
        },
    )
    report = {
        "schema_version": 1,
        "generated_at": iso_now(),
        "status": status,
        "errors": errors,
        "warnings": warnings,
        "checks": [
            {"name": "existing_marketplace_manifest_ready", "status": "PASS" if not errors else "FAIL", "detail": str(manifest_path)},
            {"name": "marketplace_merge_action", "status": status, "detail": action},
        ],
    }
    write_json(run_root / PUBLISH_DIR / "marketplace-validation-report.json", report)
    return {**plan, "marketplace_json": preview}


def plan_merge(
    *,
    package_root: Path,
    run_root: Path,
    repo_path: Path,
    plugin_id: str,
    version: str,
    marketplace_name: str,
    update_existing_entry: bool,
) -> Dict[str, Any]:
    manifest_path = repo_path / ".claude-plugin" / "marketplace.json"
    expected_source = f"./plugins/{plugin_id}"
    manifest, manifest_error = load_json(manifest_path)
    plugin_json, plugin_error = load_json(package_root / ".claude-plugin" / "plugin.json")

    if manifest_error == "missing":
        return emit_report(
            run_root=run_root,
            repo_path=repo_path,
            manifest_path=manifest_path,
            marketplace_name="",
            plugin_id=plugin_id,
            expected_source=expected_source,
            status="BLOCKED",
            action="blocked",
            block_reason="existing_marketplace_manifest_missing",
            errors=[f"existing marketplace manifest not found: {manifest_path}"],
        )
    if manifest_error:
        return emit_report(
            run_root=run_root,
            repo_path=repo_path,
            manifest_path=manifest_path,
            marketplace_name="",
            plugin_id=plugin_id,
            expected_source=expected_source,
            status="BLOCKED",
            action="blocked",
            block_reason="existing_marketplace_manifest_invalid",
            errors=[manifest_error],
        )
    if plugin_error:
        return emit_report(
            run_root=run_root,
            repo_path=repo_path,
            manifest_path=manifest_path,
            marketplace_name=str(manifest.get("name", "")).strip(),
            plugin_id=plugin_id,
            expected_source=expected_source,
            status="FAIL",
            action="blocked",
            block_reason="package_plugin_manifest_invalid",
            errors=[plugin_error],
        )

    resolved_name = str(manifest.get("name", "")).strip()
    if not resolved_name:
        return emit_report(
            run_root=run_root,
            repo_path=repo_path,
            manifest_path=manifest_path,
            marketplace_name="",
            plugin_id=plugin_id,
            expected_source=expected_source,
            status="BLOCKED",
            action="blocked",
            block_reason="existing_marketplace_manifest_invalid",
            errors=["existing marketplace name is missing"],
        )
    if marketplace_name.strip() and marketplace_name.strip() != resolved_name:
        return emit_report(
            run_root=run_root,
            repo_path=repo_path,
            manifest_path=manifest_path,
            marketplace_name=resolved_name,
            plugin_id=plugin_id,
            expected_source=expected_source,
            status="BLOCKED",
            action="blocked",
            block_reason="marketplace_name_mismatch",
            errors=[f"provided marketplace name '{marketplace_name}' does not match '{resolved_name}'"],
        )

    plugins = manifest.get("plugins")
    if not isinstance(plugins, list):
        return emit_report(
            run_root=run_root,
            repo_path=repo_path,
            manifest_path=manifest_path,
            marketplace_name=resolved_name,
            plugin_id=plugin_id,
            expected_source=expected_source,
            status="BLOCKED",
            action="blocked",
            block_reason="existing_marketplace_manifest_invalid",
            errors=["existing marketplace plugins must be a list"],
        )

    matching = [entry for entry in plugins if isinstance(entry, dict) and str(entry.get("name", "")).strip() == plugin_id]
    if len(matching) > 1:
        return emit_report(
            run_root=run_root,
            repo_path=repo_path,
            manifest_path=manifest_path,
            marketplace_name=resolved_name,
            plugin_id=plugin_id,
            expected_source=expected_source,
            status="BLOCKED",
            action="blocked",
            block_reason="marketplace_plugin_exists",
            errors=[f"multiple marketplace entries already exist for {plugin_id}"],
        )

    preview = copy.deepcopy(manifest)
    preview_plugins = preview.setdefault("plugins", [])
    new_entry = marketplace_entry(plugin_json, plugin_id, expected_source, version)
    if not matching:
        preview_plugins.append(new_entry)
        return emit_report(
            run_root=run_root,
            repo_path=repo_path,
            manifest_path=manifest_path,
            marketplace_name=resolved_name,
            plugin_id=plugin_id,
            expected_source=expected_source,
            status="PASS",
            action="append",
            preview=preview,
        )

    current = matching[0]
    if not update_existing_entry:
        return emit_report(
            run_root=run_root,
            repo_path=repo_path,
            manifest_path=manifest_path,
            marketplace_name=resolved_name,
            plugin_id=plugin_id,
            expected_source=expected_source,
            status="BLOCKED",
            action="blocked",
            block_reason="marketplace_plugin_exists",
            errors=[f"plugin {plugin_id} already exists; pass --update-existing-entry to update it"],
            current_entry=current,
        )
    if not source_matches(current, expected_source):
        return emit_report(
            run_root=run_root,
            repo_path=repo_path,
            manifest_path=manifest_path,
            marketplace_name=resolved_name,
            plugin_id=plugin_id,
            expected_source=expected_source,
            status="BLOCKED",
            action="blocked",
            block_reason="marketplace_source_mismatch",
            errors=[f"existing source for {plugin_id} is not {expected_source}"],
            current_entry=current,
        )
    old_version = str(current.get("version", "")).strip()
    current_version = semver(old_version)
    next_version = semver(version)
    if current_version is None or next_version is None or next_version <= current_version:
        return emit_report(
            run_root=run_root,
            repo_path=repo_path,
            manifest_path=manifest_path,
            marketplace_name=resolved_name,
            plugin_id=plugin_id,
            expected_source=expected_source,
            status="BLOCKED",
            action="blocked",
            block_reason="marketplace_version_not_bumped",
            errors=[f"new version {version} must be greater than existing version {old_version or '<missing>'}"],
            current_entry=current,
        )

    for index, entry in enumerate(preview_plugins):
        if isinstance(entry, dict) and str(entry.get("name", "")).strip() == plugin_id:
            preview_plugins[index] = new_entry
            break
    return emit_report(
        run_root=run_root,
        repo_path=repo_path,
        manifest_path=manifest_path,
        marketplace_name=resolved_name,
        plugin_id=plugin_id,
        expected_source=expected_source,
        status="PASS",
        action="update",
        current_entry=current,
        preview=preview,
    )


def main() -> int:
    args = parse_args()
    payload = plan_merge(
        package_root=Path(args.package_root).resolve(),
        run_root=Path(args.run_root).resolve(),
        repo_path=Path(args.repo_path).resolve(),
        plugin_id=args.plugin_id.strip(),
        version=args.version.strip(),
        marketplace_name=args.marketplace_name.strip(),
        update_existing_entry=args.update_existing_entry,
    )
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"[{payload['status']}] action={payload.get('action')}")
    return 0 if payload["status"] == "PASS" else (2 if payload["status"] == "BLOCKED" else 1)


if __name__ == "__main__":
    raise SystemExit(main())
