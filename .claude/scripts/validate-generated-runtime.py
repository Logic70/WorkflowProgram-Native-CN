#!/usr/bin/env python3
"""
校验目标工作流持久化的 deterministic runtime 资产是否与 workflow-spec.yaml 一致。
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List

from lib.host_team_utils import (
    agent_team_contract_from_spec,
    agent_team_enabled,
    capability_discovery_from_spec,
    host_global_adapter,
    host_capabilities_from_spec,
    node_loop_enabled,
    runtime_capabilities_from_contract,
)
from lib.target_claude_guard import guard_required_by_spec, guard_validation_errors, target_claude_guard_config
from lib.yaml_utils import load_yaml_mapping


REQUIRED_GENERATED_RUNTIME_KEYS = {
    "runtime_root",
    "design_spec_path",
    "entry_script",
    "runner_script",
    "state_validator_script",
    "runtime_manifest",
    "run_root_dir",
    "mode",
    "runtime_capabilities",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate target-side generated runtime assets")
    parser.add_argument("--spec", required=True, help="Path to persistent workflow-spec.yaml")
    parser.add_argument("--target-root", required=True, help="Target workflow root")
    parser.add_argument("--json", action="store_true", help="Print JSON payload")
    return parser.parse_args()


def normalize_rel_path(value: str) -> str:
    normalized = str(value).strip().replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized


def registry_file_map(spec: Dict[str, Any]) -> Dict[str, str]:
    registry = spec.get("registry", {}) if isinstance(spec.get("registry", {}), dict) else {}
    result: Dict[str, str] = {}
    for bucket in ("agents", "skills"):
        entries = registry.get(bucket, [])
        if not isinstance(entries, list):
            continue
        for raw_entry in entries:
            if not isinstance(raw_entry, dict):
                continue
            name = str(raw_entry.get("name", "")).strip()
            file_name = str(raw_entry.get("file", "")).strip()
            if name and file_name:
                result[name] = file_name
    return result


def node_prompt_boundary_errors(spec: Dict[str, Any], target_root: Path, target_publish_policy: Dict[str, Any]) -> List[str]:
    """Validate prompt assets that are used as managed-runtime node owners."""

    graph = spec.get("workflow_graph", {}) if isinstance(spec.get("workflow_graph", {}), dict) else {}
    nodes = graph.get("nodes", []) if isinstance(graph.get("nodes", []), list) else []
    registry = registry_file_map(spec)
    manifest_path = normalize_rel_path(str(target_publish_policy.get("manifest_path", "")))
    latest_marker = normalize_rel_path(str(target_publish_policy.get("latest_marker", "")))
    finalizer_owned = {item for item in (manifest_path, latest_marker) if item}
    finalizer_owned_names = {Path(item).name for item in finalizer_owned if Path(item).name}
    run_root_markers = (
        "WORKFLOWPROGRAM_OUTPUT_ROOT",
        "active run root",
        "current run root",
        "RUN_ROOT",
        "run-scoped",
    )
    errors: List[str] = []
    checked: set[str] = set()

    for raw_node in nodes:
        if not isinstance(raw_node, dict):
            continue
        owner = str(raw_node.get("owner", "")).strip()
        if not owner or owner.startswith("script:"):
            continue
        file_name = registry.get(owner, "")
        if not file_name:
            continue
        normalized_file = normalize_rel_path(file_name)
        prompt_path = target_root / normalized_file
        if normalized_file in checked:
            continue
        checked.add(normalized_file)
        if not prompt_path.exists() or not prompt_path.is_file():
            continue
        try:
            prompt_text = prompt_path.read_text(encoding="utf-8")
        except Exception:
            continue
        for marker in sorted(finalizer_owned | finalizer_owned_names):
            if marker and marker in prompt_text:
                errors.append(
                    f"managed-runtime node owner prompt must not reference finalizer-owned publish artifact "
                    f"{marker}: {normalized_file}"
                )
        node_output_refs = [
            normalize_rel_path(str(item))
            for item in raw_node.get("output_refs", [])
            if str(item).strip()
        ] if isinstance(raw_node.get("output_refs", []), list) else []
        mentions_node_output = any(ref and ref in prompt_text for ref in node_output_refs)
        if mentions_node_output and not any(marker in prompt_text for marker in run_root_markers):
            errors.append(
                "managed-runtime node owner prompt mentions workflow output refs but is missing "
                f"active-run-root/WORKFLOWPROGRAM_OUTPUT_ROOT guidance: {normalized_file}"
            )
    return errors


def validate_generated_runtime(spec_path: Path, target_root: Path) -> Dict[str, Any]:
    errors: List[str] = []
    warnings: List[str] = []

    if not spec_path.exists():
        return {
            "status": "FAIL",
            "errors": [f"workflow spec not found: {spec_path}"],
            "warnings": warnings,
            "spec": str(spec_path),
            "target_root": str(target_root),
        }
    if not target_root.exists():
        return {
            "status": "FAIL",
            "errors": [f"target root not found: {target_root}"],
            "warnings": warnings,
            "spec": str(spec_path),
            "target_root": str(target_root),
        }

    try:
        spec = load_yaml_mapping(spec_path)
        contract = spec.get("generated_runtime_contract")
        if not isinstance(contract, dict):
            errors.append("generated_runtime_contract must be a mapping/object")
            contract = {}

        missing_keys = sorted(REQUIRED_GENERATED_RUNTIME_KEYS - set(contract.keys()))
        if missing_keys:
            errors.append(f"generated_runtime_contract missing required keys: {', '.join(missing_keys)}")

        normalized = {key: str(contract.get(key, "")).strip() for key in REQUIRED_GENERATED_RUNTIME_KEYS if key != "runtime_capabilities"}
        expected_runtime_capabilities = runtime_capabilities_from_contract(contract)
        capability_discovery = capability_discovery_from_spec(spec)
        declared_host_capabilities = host_capabilities_from_spec(spec)
        host_global_adapter_declared = any(
            str(item.get("bootstrap", {}).get("scope", "")).strip() == "host_global" and bool(host_global_adapter(item))
            for item in declared_host_capabilities
            if isinstance(item, dict) and isinstance(item.get("bootstrap"), dict)
        )
        declared_agent_team = agent_team_contract_from_spec(spec)
        declared_node_loop_enabled = node_loop_enabled(spec)
        target_runtime_policy = spec.get("target_runtime_policy", {})
        if not isinstance(target_runtime_policy, dict):
            target_runtime_policy = {}
        target_executor_policy = spec.get("target_executor_policy", {})
        if not isinstance(target_executor_policy, dict):
            target_executor_policy = {}
        managed_runtime = str(target_runtime_policy.get("mode", "")).strip() == "managed_runtime"
        target_publish_policy = spec.get("target_publish_policy", {})
        if not isinstance(target_publish_policy, dict):
            target_publish_policy = {}
        target_publish_enabled = target_publish_policy.get("enabled") is True
        target_claude_guard = target_claude_guard_config(spec)
        main_entry = (
            str(spec.get("test_contract", {}).get("entry", {}).get("main_entry", "")).strip()
            if isinstance(spec.get("test_contract", {}), dict)
            else ""
        )

        entry_path = target_root / normalized.get("entry_script", "")
        runner_path = target_root / normalized.get("runner_script", "")
        validator_path = target_root / normalized.get("state_validator_script", "")
        manifest_path = target_root / normalized.get("runtime_manifest", "")
        design_spec_target = target_root / normalized.get("design_spec_path", "")

        for label, path in (
            ("entry_script", entry_path),
            ("runner_script", runner_path),
            ("state_validator_script", validator_path),
            ("runtime_manifest", manifest_path),
        ):
            if not str(path):
                continue
            if not path.exists():
                errors.append(f"{label} is missing: {path}")

        if design_spec_target and design_spec_target != spec_path:
            errors.append(
                "generated_runtime_contract.design_spec_path does not point back to the validated persistent workflow-spec.yaml"
            )

        manifest_payload: Dict[str, Any] = {}
        if manifest_path.exists():
            try:
                manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                errors.append(f"runtime manifest is not valid JSON: {exc}")

        if manifest_payload:
            expected_pairs = {
                "runtime_root": normalized.get("runtime_root", ""),
                "design_spec_path": normalized.get("design_spec_path", ""),
                "entry_script": normalized.get("entry_script", ""),
                "runner_script": normalized.get("runner_script", ""),
                "state_validator_script": normalized.get("state_validator_script", ""),
                "runtime_manifest": normalized.get("runtime_manifest", ""),
                "run_root_dir": normalized.get("run_root_dir", ""),
                "runtime_mode": normalized.get("mode", ""),
                "runtime_capabilities": expected_runtime_capabilities,
                "managed_runtime": managed_runtime,
                "target_runtime_policy_mode": str(target_runtime_policy.get("mode", "")).strip(),
                "target_executor_policy": target_executor_policy,
                "target_publish_policy_enabled": target_publish_enabled,
                "default_entry_skill": main_entry,
                "capability_discovery_enabled": bool(capability_discovery.get("enabled", False)),
                "capability_discovery_domains": capability_discovery.get("domains", []) if isinstance(capability_discovery.get("domains", []), list) else [],
                "host_capabilities_declared": bool(declared_host_capabilities),
                "host_global_adapter_declared": host_global_adapter_declared,
                "agent_team_enabled": agent_team_enabled(declared_agent_team),
                "node_loop_enabled": declared_node_loop_enabled,
            }
            for key, expected in expected_pairs.items():
                observed_value = manifest_payload.get(key)
                if isinstance(expected, list):
                    observed = [str(item).strip() for item in observed_value] if isinstance(observed_value, list) else []
                    if observed != expected:
                        errors.append(f"runtime manifest field '{key}' mismatch: expected '{expected}', got '{observed}'")
                    continue
                if isinstance(expected, bool):
                    observed = observed_value if isinstance(observed_value, bool) else None
                    if observed is not expected:
                        errors.append(f"runtime manifest field '{key}' mismatch: expected '{expected}', got '{observed}'")
                    continue
                if isinstance(expected, dict):
                    observed = observed_value if isinstance(observed_value, dict) else None
                    if observed != expected:
                        errors.append(f"runtime manifest field '{key}' mismatch: expected '{expected}', got '{observed}'")
                    continue
                observed = str(observed_value).strip() if observed_value is not None else ""
                if observed != str(expected).strip():
                    errors.append(f"runtime manifest field '{key}' mismatch: expected '{expected}', got '{observed}'")

        if entry_path.exists():
            entry_text = entry_path.read_text(encoding="utf-8")
            for needle in (
                f"DEFAULT_ENTRY_SKILL = {main_entry!r}",
                f"DESIGN_SPEC_REL = {normalized.get('design_spec_path', '')!r}",
                f"RUNNER_SCRIPT_REL = {normalized.get('runner_script', '')!r}",
                f"STATE_VALIDATOR_SCRIPT_REL = {normalized.get('state_validator_script', '')!r}",
                "workflowprogram-python",
            ):
                if needle not in entry_text:
                    errors.append(f"entry wrapper is missing expected marker: {needle}")
            if capability_discovery.get("enabled") is True and "DISCOVER_HOST_SCRIPT = \"discover-host-capabilities.py\"" not in entry_text:
                errors.append("entry wrapper is missing discover-host-capabilities.py integration marker")
            if declared_host_capabilities and "PROBE_HOST_SCRIPT = \"probe-host-capabilities.py\"" not in entry_text:
                errors.append("entry wrapper is missing probe-host-capabilities.py integration marker")
            if declared_host_capabilities and "ENVIRONMENT_REMEDIATION_SCRIPT = \"generate-environment-remediation.py\"" not in entry_text:
                errors.append("entry wrapper is missing generate-environment-remediation.py integration marker")
            if agent_team_enabled(declared_agent_team) and "TEAM_ORCHESTRATION_ENABLED = True" not in entry_text:
                errors.append("entry wrapper is missing TEAM_ORCHESTRATION_ENABLED marker")
            if declared_node_loop_enabled and "NODE_LOOP_EXECUTION_ENABLED = True" not in entry_text:
                errors.append("entry wrapper is missing NODE_LOOP_EXECUTION_ENABLED marker")
            if managed_runtime and "TARGET_MANAGED_RUNTIME_ENABLED = True" not in entry_text:
                errors.append("entry wrapper is missing TARGET_MANAGED_RUNTIME_ENABLED marker")
            if target_publish_enabled:
                if "TARGET_PUBLISH_FINALIZER_ENABLED = True" not in entry_text:
                    errors.append("entry wrapper is missing TARGET_PUBLISH_FINALIZER_ENABLED marker")
                if "target-runtime-finalizer.py" not in entry_text:
                    errors.append("entry wrapper is missing target-runtime-finalizer.py integration marker")
                if "validate_target_publish_state(" not in entry_text:
                    errors.append("entry wrapper is missing validate-target-publish-state.py execution marker")
                if "runner_blocked_phase" not in entry_text or 'runner_blocked_phase == "executor_evidence"' not in entry_text:
                    errors.append("entry wrapper is missing executor-evidence BLOCKED finalizer skip marker")
                if "target_atomic_publish" not in expected_runtime_capabilities:
                    errors.append(
                        "generated_runtime_contract.runtime_capabilities must include target_atomic_publish when target_publish_policy.enabled=true"
                    )
            forbidden_executor_markers = ["claude_cli", "[args.claude_bin, \"-p\"", "Claude binary for claude_cli"]
            matched_forbidden = [marker for marker in forbidden_executor_markers if marker in entry_text]
            if matched_forbidden:
                errors.append(f"entry wrapper must not hard-code Claude CLI executor markers: {matched_forbidden}")

        if runner_path.exists():
            runner_text = runner_path.read_text(encoding="utf-8")
            expected_runner_marker = "target-workflow-runner.py" if managed_runtime else "workflow-runner.py"
            for needle in (expected_runner_marker, "--entry-skill", "--intent", "workflowprogram-python"):
                if needle not in runner_text:
                    errors.append(f"runner wrapper is missing expected marker: {needle}")
            if managed_runtime and 'scripts" / "workflow-runner.py"' in runner_text:
                errors.append("managed-runtime runner wrapper must not delegate to product workflow-runner.py")
            forbidden_executor_markers = ["claude_cli", "[args.claude_bin, \"-p\"", "Claude binary for claude_cli"]
            matched_forbidden = [marker for marker in forbidden_executor_markers if marker in runner_text]
            if matched_forbidden:
                errors.append(f"runner wrapper must not hard-code Claude CLI executor markers: {matched_forbidden}")

        if validator_path.exists():
            validator_text = validator_path.read_text(encoding="utf-8")
            expected_validator_marker = "validate-target-runtime-state.py" if managed_runtime else "validate-run-state.py"
            for needle in (expected_validator_marker, "workflowprogram-python"):
                if needle not in validator_text:
                    errors.append(f"state validator wrapper is missing expected marker: {needle}")
            if managed_runtime and "validate-run-state.py" in validator_text:
                errors.append("managed-runtime state validator wrapper must not delegate to product validate-run-state.py")

        if manifest_payload and target_publish_enabled:
            shared_scripts = manifest_payload.get("shared_scripts", [])
            shared_script_values = [str(item).strip() for item in shared_scripts] if isinstance(shared_scripts, list) else []
            if "target-runtime-finalizer.py" not in shared_script_values:
                errors.append("runtime manifest shared_scripts must include target-runtime-finalizer.py when target_publish_policy.enabled=true")
            if "validate-target-publish-state.py" not in shared_script_values:
                errors.append("runtime manifest shared_scripts must include validate-target-publish-state.py when target_publish_policy.enabled=true")

        if managed_runtime:
            runtime_root = target_root / normalized.get("runtime_root", "")
            forbidden_local_shared_patterns = (
                "target-workflow-runner.py*",
                "target-runtime-finalizer.py*",
                "validate-target-runtime-state.py*",
                "validate-target-publish-state.py*",
            )
            if runtime_root.exists():
                for pattern in forbidden_local_shared_patterns:
                    for path in sorted(runtime_root.glob(pattern)):
                        errors.append(
                            "managed-runtime shared control-plane script must not be vendored under generated runtime root: "
                            f"{path.relative_to(target_root).as_posix()}"
                        )

        if managed_runtime and main_entry:
            registry = spec.get("registry", {}) if isinstance(spec.get("registry", {}), dict) else {}
            command_file = ""
            commands = registry.get("commands", []) if isinstance(registry.get("commands", []), list) else []
            for raw_command in commands:
                if not isinstance(raw_command, dict):
                    continue
                if str(raw_command.get("name", "")).strip() == main_entry:
                    command_file = str(raw_command.get("file", "")).strip()
                    break
            if not command_file:
                errors.append("managed-runtime workflow main_entry must resolve to registry.commands")
            else:
                command_path = target_root / command_file
                if not command_path.exists():
                    errors.append(f"managed-runtime command wrapper is missing: {command_path}")
                else:
                    command_text = command_path.read_text(encoding="utf-8")
                    if ".workflowprogram/runtime/workflow-entry.py" not in command_text:
                        errors.append("managed-runtime command must invoke .workflowprogram/runtime/workflow-entry.py")
                    prompt_heavy_markers = ["### Stage", "按顺序调用每个阶段", "不要跳过", "主控模型不得手写"]
                    prompt_heavy_markers.extend(["outputs/stride-audit", "手写报告", "逐节点手写", "直接生成报告"])
                    prompt_heavy_markers.extend(
                        [
                            "Step 1",
                            "Step 2",
                            "run_manifest.json",
                            "run-manifest.json",
                            ".report-latest",
                            ".workflowprogram-latest.json",
                            "copying reports",
                            "copy outputs",
                            "manual execute",
                            "manually execute",
                            "status `COMPLETE`",
                            "status COMPLETE",
                            "doctor",
                            "contract",
                        ]
                    )
                    matched = [marker for marker in prompt_heavy_markers if marker in command_text]
                    if matched:
                        errors.append(f"managed-runtime command must be wrapper-only; prompt-heavy markers found: {matched}")
        if managed_runtime or guard_required_by_spec(spec):
            guard_file = str(target_claude_guard.get("file", "CLAUDE.md")).strip() or "CLAUDE.md"
            guard_path = target_root / guard_file
            if not guard_path.exists():
                errors.append(f"managed-runtime target CLAUDE guard is missing: {guard_file}")
            else:
                guard_errors = guard_validation_errors(guard_path.read_text(encoding="utf-8"), spec)
                errors.extend(f"managed-runtime target CLAUDE guard invalid: {item}" for item in guard_errors)
        if managed_runtime and target_publish_enabled:
            errors.extend(node_prompt_boundary_errors(spec, target_root, target_publish_policy))
    except Exception as exc:
        errors.append(str(exc))

    return {
        "status": "PASS" if not errors else "FAIL",
        "errors": errors,
        "warnings": warnings,
        "spec": str(spec_path),
        "target_root": str(target_root),
    }


def main() -> int:
    args = parse_args()
    payload = validate_generated_runtime(Path(args.spec).resolve(), Path(args.target_root).resolve())
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"[{payload['status']}] {payload['target_root']}")
        for item in payload["errors"]:
            print(f"- ERROR: {item}")
        for item in payload["warnings"]:
            print(f"- WARN: {item}")
    return 0 if payload["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
