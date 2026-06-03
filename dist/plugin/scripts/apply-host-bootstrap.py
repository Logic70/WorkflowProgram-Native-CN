#!/usr/bin/env python3
# AUTO-GENERATED FROM .claude/ - DO NOT EDIT DIRECTLY
"""
执行可自动化的 host bootstrap，并把结果写入 RUN_ROOT 证据。

- 只自动应用 `project_local + approval_required=false`
- `host_global` 与 `manual_only` 永不自动执行，只记录 skipped 和 plan 证据
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List

from lib.host_probe_utils import detect_ready_status
from lib.host_team_utils import bootstrap_assets, host_capabilities_from_spec, host_global_adapter, project_local_outputs
from lib.io_utils import iso_now, write_json
from lib.yaml_utils import load_yaml_mapping


ADAPTER_TIMEOUT_SECONDS = 120


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Apply approved host bootstrap actions")
    parser.add_argument("--spec", required=True, help="Path to workflow-spec.yaml")
    parser.add_argument("--target-root", required=True, help="TARGET_ROOT path")
    parser.add_argument("--run-root", required=True, help="RUN_ROOT path")
    parser.add_argument("--allow-host-global", action="store_true", help="Deprecated no-op; host-global bootstrap is plan-only")
    parser.add_argument("--json", action="store_true", help="Print JSON payload")
    return parser.parse_args()


def write_bootstrap_output(path: Path, capability_id: str, summary: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix == ".json":
        write_json(
            path,
            {
                "capability_id": capability_id,
                "summary": summary,
                "applied_at": iso_now(),
            },
        )
        return
    if path.suffix:
        path.write_text(
            "\n".join(
                [
                    f"capability_id: {capability_id}",
                    f"summary: {summary}",
                    f"applied_at: {iso_now()}",
                    "",
                ]
            ),
            encoding="utf-8",
            newline="\n",
        )
        return
    path.mkdir(parents=True, exist_ok=True)


def sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def write_bootstrap_asset(path: Path, asset: Dict[str, Any]) -> Dict[str, Any]:
    asset_format = str(asset.get("format", "")).strip()
    executable = bool(asset.get("executable", False))
    path.parent.mkdir(parents=True, exist_ok=True)
    if asset_format == "json":
        write_json(path, asset.get("content"))
    else:
        content = str(asset.get("content", ""))
        path.write_text(content.rstrip("\n") + "\n", encoding="utf-8", newline="\n")
        if executable:
            path.chmod(path.stat().st_mode | 0o755)
    return {
        "path": str(path),
        "format": asset_format,
        "executable": executable,
        "sha256": sha256_file(path),
        "size_bytes": path.stat().st_size if path.exists() and path.is_file() else 0,
    }


def truncate_text(text: str, *, limit: int = 2000) -> str:
    normalized = text.strip()
    return normalized[:limit]


def execute_host_global_adapter(capability: Dict[str, Any]) -> Dict[str, Any]:
    capability_id = str(capability.get("id", "")).strip()
    adapter = host_global_adapter(capability)
    adapter_type = str(adapter.get("type", "")).strip()
    result: Dict[str, Any] = {
        "capability_id": capability_id,
        "attempted_at": iso_now(),
        "adapter_type": adapter_type or None,
        "status": "skipped",
        "command": None,
        "changed_paths": [],
        "stdout": "",
        "stderr": "",
        "reason": "",
    }
    if not adapter_type:
        result["reason"] = "no host-global adapter declared"
        return result

    if adapter_type == "symlink_binary":
        source_binary = str(adapter.get("source_binary", "")).strip()
        target_path = Path(str(adapter.get("target_path", "")).strip()).expanduser()
        resolved_source = shutil.which(source_binary) if source_binary else None
        if not resolved_source:
            result["status"] = "failed"
            result["reason"] = f"source binary not found: {source_binary or '<missing>'}"
            return result
        if not str(target_path).startswith("/"):
            result["status"] = "failed"
            result["reason"] = "adapter.target_path must be absolute"
            return result
        target_path.parent.mkdir(parents=True, exist_ok=True)
        if target_path.exists() or target_path.is_symlink():
            target_path.unlink()
        target_path.symlink_to(Path(resolved_source))
        result["status"] = "succeeded"
        result["reason"] = "created symlink adapter"
        result["changed_paths"] = [str(target_path)]
        result["command"] = [f"symlink {resolved_source} -> {target_path}"]
        return result

    package_name = str(adapter.get("package", "")).strip()
    extra_args = [str(item) for item in adapter.get("extra_args", [])] if isinstance(adapter.get("extra_args"), list) else []
    if not package_name:
        result["status"] = "failed"
        result["reason"] = f"adapter.package is required for {adapter_type}"
        return result
    if adapter_type == "uv_tool":
        cmd = ["uv", "tool", "install", package_name, *extra_args]
    elif adapter_type == "pipx_install":
        cmd = ["pipx", "install", package_name, *extra_args]
    elif adapter_type == "npm_global":
        cmd = ["npm", "install", "-g", package_name, *extra_args]
    else:
        result["status"] = "failed"
        result["reason"] = f"unsupported adapter type: {adapter_type}"
        return result
    result["command"] = cmd
    try:
        completed = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
            timeout=ADAPTER_TIMEOUT_SECONDS,
        )
    except Exception as exc:
        result["status"] = "failed"
        result["reason"] = f"adapter execution failed: {exc}"
        return result
    result["stdout"] = truncate_text(completed.stdout)
    result["stderr"] = truncate_text(completed.stderr)
    if completed.returncode == 0:
        result["status"] = "succeeded"
        result["reason"] = "adapter command exited successfully"
    else:
        result["status"] = "failed"
        result["reason"] = f"adapter command exited with code {completed.returncode}"
    return result


def apply_host_bootstrap(spec_path: Path, target_root: Path, run_root: Path, *, allow_host_global: bool) -> Dict[str, Any]:
    spec = load_yaml_mapping(spec_path)
    applied: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []
    host_global_attempts: List[Dict[str, Any]] = []
    manifest_entries: List[Dict[str, Any]] = []
    bootstrap_root = (target_root / ".workflowprogram" / "bootstrap").resolve()
    manifest_path = bootstrap_root / "bootstrap-assets-manifest.json"

    for capability in host_capabilities_from_spec(spec):
        bootstrap = capability.get("bootstrap", {})
        if not isinstance(bootstrap, dict):
            skipped.append({"capability_id": capability.get("id"), "reason": "missing bootstrap definition"})
            continue
        scope = str(bootstrap.get("scope", "")).strip()
        if scope != "project_local":
            if scope == "host_global":
                skipped.append({"capability_id": capability.get("id"), "reason": "host_global bootstrap is plan-only and must be completed outside WorkflowProgram"})
            else:
                skipped.append({"capability_id": capability.get("id"), "reason": f"bootstrap.scope={scope or 'manual_only'} is not auto-applied"})
            continue
        if bool(capability.get("approval_required", False)):
            skipped.append({"capability_id": capability.get("id"), "reason": "approval_required=true"})
            continue
        outputs = project_local_outputs(capability)
        assets = bootstrap_assets(capability)
        if not outputs:
            skipped.append({"capability_id": capability.get("id"), "reason": "no project_local_outputs declared"})
            continue

        summary = str(bootstrap.get("summary", "")).strip() or f"Applied project-local bootstrap for {capability.get('id')}"
        written: List[str] = []
        materialized_assets: List[Dict[str, Any]] = []
        asset_by_path = {str(item.get("path", "")).strip(): item for item in assets if str(item.get("path", "")).strip()}
        capability_id = str(capability.get("id", "")).strip()
        for rel_path in outputs:
            path = (target_root / rel_path).resolve()
            if not str(path).startswith(str(bootstrap_root)):
                skipped.append({"capability_id": capability.get("id"), "reason": f"unsafe bootstrap output path: {rel_path}"})
                continue
            asset = asset_by_path.get(rel_path)
            if asset is not None:
                materialized = write_bootstrap_asset(path, asset)
                materialized["relative_path"] = rel_path
                materialized_assets.append(materialized)
            else:
                write_bootstrap_output(path, capability_id, summary)
            written.append(rel_path)
        if written:
            ready_after_apply, recheck_status, recheck_message = detect_ready_status(target_root, capability)
            applied.append(
                {
                    "capability_id": capability_id,
                    "written_outputs": written,
                    "materialized_assets": materialized_assets,
                    "summary": summary,
                    "safety_boundary": ".workflowprogram/bootstrap/**",
                    "ready_after_apply": ready_after_apply,
                    "recheck_status": recheck_status,
                    "recheck_message": recheck_message,
                }
            )
            manifest_entries.append(
                {
                    "capability_id": capability_id,
                    "summary": summary,
                    "written_outputs": written,
                    "materialized_assets": materialized_assets,
                    "recheck_status": recheck_status,
                    "recheck_message": recheck_message,
                }
            )

    manifest_written = False
    if manifest_entries:
        manifest_payload = {
            "generated_at": iso_now(),
            "spec": str(spec_path),
            "target_root": str(target_root),
            "bootstrap_root": str(bootstrap_root),
            "entries": manifest_entries,
        }
        write_json(manifest_path, manifest_payload)
        manifest_written = True

    payload = {
        "generated_at": iso_now(),
        "spec": str(spec_path),
        "target_root": str(target_root),
        "run_root": str(run_root),
        "applied": applied,
        "skipped": skipped,
        "host_global_attempts": host_global_attempts,
        "manifest_path": str(manifest_path) if manifest_written else None,
    }
    write_json(run_root / "outputs" / "stages" / "host-bootstrap-apply.json", payload)
    if host_global_attempts:
        write_json(
            run_root / "outputs" / "stages" / "host-bootstrap-execution.json",
            {
                "generated_at": iso_now(),
                "spec": str(spec_path),
                "target_root": str(target_root),
                "run_root": str(run_root),
                "attempts": host_global_attempts,
            },
        )
    return payload


def main() -> int:
    args = parse_args()
    payload = apply_host_bootstrap(
        Path(args.spec).resolve(),
        Path(args.target_root).resolve(),
        Path(args.run_root).resolve(),
        allow_host_global=bool(args.allow_host_global),
    )
    if args.json:
        print(json.dumps({"status": "PASS", **payload}, ensure_ascii=False, indent=2))
    else:
        print(f"[PASS] applied={len(payload['applied'])} skipped={len(payload['skipped'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
