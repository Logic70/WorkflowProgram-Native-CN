# AUTO-GENERATED FROM .claude/ - DO NOT EDIT DIRECTLY
"""Utilities for WorkflowProgram-managed target project CLAUDE.md guard blocks."""

from __future__ import annotations

import hashlib
import re
from typing import Any, Dict, List, Tuple


DEFAULT_BLOCK_ID = "workflowprogram-runtime-guard"
DEFAULT_FILE = "CLAUDE.md"
DEFAULT_RUNTIME_ENTRY = ".workflowprogram/runtime/workflow-entry.py"
DEFAULT_ALLOWED_ACTIONS = ["run", "status", "resume", "diagnose"]
DEFAULT_FORBIDDEN_OPERATIONS = [
    "handwrite_final_report",
    "write_final_manifest",
    "write_latest_marker",
    "copy_run_outputs_to_final",
    "continue_after_runtime_fail",
]
VALID_REQUIRED_FOR = {"managed_runtime", "target_publish_policy"}
VALID_MERGE_VALUES = {
    "if_missing_file": {"create"},
    "if_existing_no_block": {"append_after_title", "append_to_end"},
    "if_existing_block": {"replace_managed_block"},
    "if_broken_block": {"conflict"},
}
VALID_BLOCKED_BEHAVIOR = {"current_node_evidence_only"}
VALID_FAILED_BEHAVIOR = {"diagnose_only"}


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def workflow_id_from_spec(spec: Dict[str, Any]) -> str:
    meta = spec.get("meta", {})
    if isinstance(meta, dict):
        value = str(meta.get("name", "")).strip()
        if value:
            return value
    return "target-workflow"


def guard_required_by_spec(spec: Dict[str, Any]) -> bool:
    runtime_policy = spec.get("target_runtime_policy", {})
    publish_policy = spec.get("target_publish_policy", {})
    managed_runtime = isinstance(runtime_policy, dict) and str(runtime_policy.get("mode", "")).strip() == "managed_runtime"
    publish_enabled = isinstance(publish_policy, dict) and publish_policy.get("enabled") is True
    return managed_runtime or publish_enabled


def default_guard_config(spec: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "enabled": guard_required_by_spec(spec),
        "file": DEFAULT_FILE,
        "mode": "managed_block",
        "block_id": DEFAULT_BLOCK_ID,
        "required_for": ["managed_runtime", "target_publish_policy"],
        "merge_policy": {
            "if_missing_file": "create",
            "if_existing_no_block": "append_after_title",
            "if_existing_block": "replace_managed_block",
            "if_broken_block": "conflict",
        },
        "content": {
            "runtime_entry": DEFAULT_RUNTIME_ENTRY,
            "allowed_actions": list(DEFAULT_ALLOWED_ACTIONS),
            "blocked_behavior": "current_node_evidence_only",
            "failed_behavior": "diagnose_only",
            "trusted_publisher": "target-runtime-finalizer.py",
            "forbidden_operations": list(DEFAULT_FORBIDDEN_OPERATIONS),
        },
    }


def target_claude_guard_config(spec: Dict[str, Any]) -> Dict[str, Any]:
    config = default_guard_config(spec)
    raw = spec.get("target_claude_guard")
    if not isinstance(raw, dict):
        return config

    for key in ("enabled", "file", "mode", "block_id", "required_for"):
        if key in raw:
            config[key] = raw[key]
    if isinstance(raw.get("merge_policy"), dict):
        merged = dict(config["merge_policy"])
        merged.update(raw["merge_policy"])
        config["merge_policy"] = merged
    if isinstance(raw.get("content"), dict):
        merged_content = dict(config["content"])
        merged_content.update(raw["content"])
        config["content"] = merged_content
    return config


def begin_marker(block_id: str) -> str:
    return f"<!-- BEGIN WORKFLOWPROGRAM RUNTIME GUARD: {block_id} -->"


def end_marker(block_id: str) -> str:
    return f"<!-- END WORKFLOWPROGRAM RUNTIME GUARD: {block_id} -->"


def render_guard_block(spec: Dict[str, Any], config: Dict[str, Any] | None = None) -> str:
    guard = config or target_claude_guard_config(spec)
    content = guard.get("content", {}) if isinstance(guard.get("content"), dict) else {}
    block_id = str(guard.get("block_id", DEFAULT_BLOCK_ID)).strip() or DEFAULT_BLOCK_ID
    runtime_entry = str(content.get("runtime_entry", DEFAULT_RUNTIME_ENTRY)).strip() or DEFAULT_RUNTIME_ENTRY
    trusted_publisher = str(content.get("trusted_publisher", "target-runtime-finalizer.py")).strip() or "target-runtime-finalizer.py"
    workflow_id = workflow_id_from_spec(spec)

    return "\n".join(
        [
            begin_marker(block_id),
            "## WorkflowProgram Runtime Guard",
            "",
            f"This project contains the WorkflowProgram-managed workflow `{workflow_id}`.",
            "",
            "Runtime is the only workflow orchestrator.",
            f"Use `{runtime_entry}` for workflow actions.",
            "",
            "Allowed actions:",
            "- `run`: start or continue a controlled runtime run.",
            "- `status`: inspect the current runtime state.",
            "- `resume`: ask runtime to validate submitted executor evidence and advance.",
            "- `diagnose`: explain a blocked or failed runtime state without publishing.",
            "",
            "If runtime state is `NEEDS_EVIDENCE` or `BLOCKED`, complete only the current node task and write executor evidence under the current run root.",
            "",
            "If runtime state is `FAILED`, stop workflow execution and run diagnose only.",
            "",
            "Do not manually write final reports, final manifests, latest markers, or final output directories.",
            "Do not copy run-scoped outputs into final outputs.",
            f"`{trusted_publisher}` is the only trusted publisher.",
            "",
            "Files written outside this runtime/finalizer path are not trusted workflow results.",
            end_marker(block_id),
            "",
        ]
    )


def marker_counts(text: str, block_id: str) -> Tuple[int, int]:
    return text.count(begin_marker(block_id)), text.count(end_marker(block_id))


def append_after_title(text: str, block: str) -> str:
    if not text.strip():
        return block
    lines = text.splitlines(keepends=True)
    insert_at = 0
    if lines and re.match(r"^\s*#\s+", lines[0]):
        insert_at = 1
        if len(lines) > 1 and not lines[1].strip():
            insert_at = 2
    if insert_at == 0:
        separator = "" if text.endswith("\n") else "\n"
        return f"{text}{separator}\n{block}"
    prefix = "".join(lines[:insert_at])
    suffix = "".join(lines[insert_at:])
    separator = "" if prefix.endswith("\n\n") else "\n"
    return f"{prefix}{separator}{block}\n{suffix}"


def apply_guard_block(existing_text: str, block: str, config: Dict[str, Any]) -> Tuple[str, str, str]:
    """Return status, action, and resulting text or conflict detail."""

    block_id = str(config.get("block_id", DEFAULT_BLOCK_ID)).strip() or DEFAULT_BLOCK_ID
    begin = begin_marker(block_id)
    end = end_marker(block_id)
    begin_count, end_count = marker_counts(existing_text, block_id)
    merge_policy = config.get("merge_policy", {}) if isinstance(config.get("merge_policy"), dict) else {}

    if not existing_text.strip():
        if merge_policy.get("if_missing_file", "create") != "create":
            return "CONFLICT", "conflict", "target CLAUDE.md is missing and merge policy does not allow create"
        return "PASS", "create", block

    if begin_count == 0 and end_count == 0:
        mode = str(merge_policy.get("if_existing_no_block", "append_after_title")).strip()
        if mode == "append_after_title":
            return "PASS", "append", append_after_title(existing_text, block)
        if mode == "append_to_end":
            separator = "" if existing_text.endswith("\n") else "\n"
            return "PASS", "append", f"{existing_text}{separator}\n{block}"
        return "CONFLICT", "conflict", f"unsupported no-block merge policy: {mode}"

    if begin_count != 1 or end_count != 1:
        return "CONFLICT", "conflict", "target CLAUDE.md contains duplicate or incomplete WorkflowProgram guard markers"

    start = existing_text.find(begin)
    end_start = existing_text.find(end)
    if start < 0 or end_start < 0 or end_start < start:
        return "CONFLICT", "conflict", "target CLAUDE.md WorkflowProgram guard markers are out of order"
    if str(merge_policy.get("if_existing_block", "replace_managed_block")).strip() != "replace_managed_block":
        return "CONFLICT", "conflict", "target CLAUDE.md already has a guard block and merge policy does not allow replacement"

    end_pos = end_start + len(end)
    if end_pos < len(existing_text) and existing_text[end_pos : end_pos + 1] == "\n":
        end_pos += 1
    new_text = existing_text[:start] + block + existing_text[end_pos:]
    return "PASS", "replace", new_text


def guard_validation_errors(text: str, spec: Dict[str, Any]) -> List[str]:
    config = target_claude_guard_config(spec)
    if config.get("enabled") is False:
        return []

    block_id = str(config.get("block_id", DEFAULT_BLOCK_ID)).strip() or DEFAULT_BLOCK_ID
    begin = begin_marker(block_id)
    end = end_marker(block_id)
    begin_count, end_count = marker_counts(text, block_id)
    errors: List[str] = []
    if begin_count != 1 or end_count != 1:
        errors.append(f"CLAUDE.md must contain exactly one WorkflowProgram runtime guard block for block_id={block_id}")
        return errors
    start = text.find(begin)
    finish = text.find(end)
    if finish < start:
        errors.append("CLAUDE.md WorkflowProgram runtime guard block markers are out of order")
        return errors
    block = text[start : finish + len(end)]
    required_markers = [
        "WorkflowProgram Runtime Guard",
        DEFAULT_RUNTIME_ENTRY,
        "`run`",
        "`status`",
        "`resume`",
        "`diagnose`",
        "`NEEDS_EVIDENCE`",
        "`BLOCKED`",
        "`FAILED`",
        "executor evidence",
        "final reports",
        "final manifests",
        "latest markers",
        "run-scoped outputs",
        "target-runtime-finalizer.py",
        "not trusted workflow results",
    ]
    for marker in required_markers:
        if marker not in block:
            errors.append(f"CLAUDE.md WorkflowProgram runtime guard block is missing marker: {marker}")
    if "physically prevent" in block.lower() or "cannot write files" in block.lower():
        errors.append("CLAUDE.md guard must not claim OS-level write prevention")
    return errors
