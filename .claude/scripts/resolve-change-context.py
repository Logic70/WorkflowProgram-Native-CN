#!/usr/bin/env python3
"""Resolve whether a target workflow change requires controlled evolution evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, Optional

from lib.io_utils import utc_now, write_json
from lib.reporting import with_report_fields


POLICY_REQUIRED_KINDS = {"modify_existing", "redesign_existing", "ambiguous_existing_create"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Resolve WorkflowProgram change context for a target root")
    parser.add_argument("--request", default="", help="Original user request")
    parser.add_argument("--target-root", required=True, help="Target project root")
    parser.add_argument("--route", default="", help="Path to route-intent.json")
    parser.add_argument("--out", default="", help="Optional path to write change-context JSON")
    parser.add_argument("--json", action="store_true", help="Print JSON")
    return parser.parse_args()


def load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def sha256_file(path: Path) -> Optional[str]:
    if not path.exists() or not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def has_relevant_claude_assets(target_root: Path) -> bool:
    claude_root = target_root / ".claude"
    if not claude_root.exists():
        return False
    for relative in ("skills", "agents", "commands", "rules", "settings.json"):
        path = claude_root / relative
        if path.is_file():
            return True
        if path.is_dir() and any(item.is_file() for item in path.rglob("*")):
            return True
    return False


def managed_manifest_valid(path: Path) -> bool:
    payload = load_json(path)
    if not payload:
        return False
    return isinstance(payload.get("entries"), list)


def infer_target_state(flags: Dict[str, Any]) -> str:
    if flags["has_managed_manifest"] and not flags["managed_manifest_valid"]:
        return "partial_workflow"
    if flags["has_design_spec"] or flags["managed_manifest_valid"]:
        return "existing_managed_workflow"
    if flags["has_maintenance"]:
        return "partial_workflow"
    if flags["has_claude_assets"]:
        return "existing_unmanaged_workflow"
    return "empty_target"


def fallback_request_kind(request: str) -> str:
    text = request.lower()
    if any(token in text for token in ("redesign", "重新设计", "重做", "重构", "推倒重来")):
        return "redesign_existing"
    if any(token in text for token in ("修改", "更新", "调整", "扩展", "拆分", "删除", "增加", "补充", "应用", "落地")):
        return "modify_existing"
    if any(token in text for token in ("创建", "新建", "设计一个", "生成", "搭建", "create", "build")):
        return "create_new"
    return "unknown"


def build_context(target_root: Path, request: str, route_payload: Dict[str, Any]) -> Dict[str, Any]:
    design_spec = target_root / ".workflowprogram" / "design" / "workflow-spec.yaml"
    maintenance = target_root / ".workflowprogram" / "design" / "workflow-maintenance.md"
    managed_manifest = target_root / ".workflowprogram" / "managed-files.json"
    maintenance_sha256 = sha256_file(maintenance)
    flags: Dict[str, Any] = {
        "has_design_spec": design_spec.exists(),
        "has_maintenance": maintenance.exists(),
        "has_lowlevel": maintenance.exists(),  # Deprecated compatibility alias.
        "has_managed_manifest": managed_manifest.exists(),
        "managed_manifest_valid": managed_manifest_valid(managed_manifest),
        "has_claude_assets": has_relevant_claude_assets(target_root),
        "design_spec_sha256": sha256_file(design_spec),
        "maintenance_sha256": maintenance_sha256,
        "lowlevel_sha256": maintenance_sha256,  # Deprecated compatibility alias.
        "managed_manifest_sha256": sha256_file(managed_manifest),
    }
    target_state = infer_target_state(flags)
    route_kind = str(route_payload.get("request_kind", "")).strip() or fallback_request_kind(request)
    request_kind = route_kind
    if target_state != "empty_target" and route_kind == "create_new":
        request_kind = "ambiguous_existing_create"
    change_policy_required = target_state != "empty_target" and request_kind in POLICY_REQUIRED_KINDS
    payload = {
        "generated_at": utc_now(),
        "target_root": str(target_root),
        "target_state": target_state,
        "request_kind": request_kind,
        "route_request_kind": route_kind,
        "change_policy_required": change_policy_required,
        "requires_clarification": request_kind == "ambiguous_existing_create" or target_state == "partial_workflow",
        "flags": flags,
        "fingerprints": {
            "design_spec_sha256": flags["design_spec_sha256"],
            "maintenance_sha256": flags["maintenance_sha256"],
            "lowlevel_sha256": flags["lowlevel_sha256"],
            "managed_manifest_sha256": flags["managed_manifest_sha256"],
        },
        "observed_at": utc_now(),
        "route_intent": route_payload.get("intent"),
        "route_entry_skill": route_payload.get("entry_skill"),
        "request": request,
    }
    return with_report_fields(payload, schema_name="change-context", failure_kind="none")


def main() -> int:
    args = parse_args()
    target_root = Path(args.target_root).resolve()
    route_payload = load_json(Path(args.route).resolve()) if args.route.strip() else {}
    payload = build_context(target_root, args.request, route_payload)
    if args.out.strip():
        write_json(Path(args.out).resolve(), payload)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(
            f"target_state={payload['target_state']} request_kind={payload['request_kind']} "
            f"change_policy_required={payload['change_policy_required']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
