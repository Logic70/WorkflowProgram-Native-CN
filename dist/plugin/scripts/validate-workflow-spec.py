#!/usr/bin/env python3
# AUTO-GENERATED FROM .claude/ - DO NOT EDIT DIRECTLY
"""
按 WorkflowProgram 的低层契约校验 workflow-spec.yaml。
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Set

from lib.capability_discovery import KNOWN_CAPABILITY_DISCOVERY_DOMAINS
from lib.diagnostics import DiagnosticCollector
from lib.host_team_utils import (
    VALID_BOOTSTRAP_ASSET_FORMATS,
    VALID_BOOTSTRAP_SCOPES,
    VALID_HOST_GLOBAL_ADAPTER_TYPES,
    VALID_HOST_CAPABILITY_KINDS,
    VALID_RUNTIME_CAPABILITIES,
    VALID_TEAM_JOIN_POLICIES,
    agent_team_enabled,
    ensure_relative_bootstrap_output,
    runtime_capabilities_from_contract,
    string_list,
)
from lib.spec_utils import stage_slot_id_map
from lib.target_claude_guard import (
    DEFAULT_ALLOWED_ACTIONS,
    DEFAULT_FORBIDDEN_OPERATIONS,
    DEFAULT_RUNTIME_ENTRY,
    VALID_BLOCKED_BEHAVIOR,
    VALID_FAILED_BEHAVIOR,
    VALID_MERGE_VALUES,
    VALID_REQUIRED_FOR,
    guard_required_by_spec,
)
from lib.target_design_refs import (
    ALLOWED_DESIGN_REF_FIELDS,
    CANONICAL_RUN_DEFAULTS,
    REQUIRED_RUN_REF_KEYS,
    resolve_target_design_refs,
)
from lib.yaml_utils import load_yaml_mapping


REQUIRED_TOP_KEYS = {
    "meta",
    "stages",
    "intent_flows",
    "agent_refs",
    "skills",
    "registry",
    "constraints",
    "resource_limits",
    "runtime_contract",
    "generated_runtime_contract",
    "test_contract",
}
OPTIONAL_TOP_KEYS = {
    "capability_discovery",
    "design_refs",
    "host_capabilities",
    "agent_team_contract",
    "workflow_graph",
    "target_runtime_policy",
    "target_executor_policy",
    "target_publish_policy",
    "target_claude_guard",
}

REQUIRED_META_KEYS = {
    "name",
    "version",
    "target_platform",
    "source_design",
    "complexity",
}

VALID_COMPLEXITY = {"S", "M", "L", "XL"}
VALID_INTENT = {"develop", "audit", "iterate", "validate"}
VALID_STAGE_SLOTS = {"S1", "S2", "S3", "S4", "S5", "S6"}
REQUIRED_STAGE_SLOT_ORDER = ["S1", "S2", "S3", "S4", "S5", "S6"]
VALID_PATTERNS = {
    "Sequential",
    "Fan-out/Fan-in",
    "Explore",
    "Event-Driven",
    "Test-Driven",
    "Specialized",
    "Specialized Agent",
}
VALID_TERMINALS = {"abort", "end", "done", "complete", "stop", "finish"}
VALID_VERDICT = {"PASS", "WARN", "FAIL", "ENVIRONMENT-SKIP"}
VALID_STAGE_STATUS = {"running", "blocked", "failed", "done"}
VALID_WORKFLOW_GRAPH_GATES = {
    "none",
    "user_approval",
    "auto_approval",
    "manual_review",
    "quality_gate",
    "test_gate",
    "done",
}
VALID_WORKFLOW_GRAPH_NODE_COMPLEXITY = {"simple", "moderate", "complex"}
VALID_WORKFLOW_GRAPH_DESIGN_INTENSITY = {"basic", "standard", "detailed"}
VALID_NODE_DESIGN_EXEMPTION_ACCEPTED_BY = {"user", "design_review"}
VALID_LOOP_MODES = {"ralph"}
VALID_LOOP_GOAL_SOURCES = {"user", "model_subgoal"}
VALID_LOOP_FEEDBACK_KINDS = {"validator", "verifier", "test"}
VALID_LOOP_FAILURE_EFFECTS = {"feedback", "gate", "hard_fail"}
VALID_LOOP_MAX_ITERATION_EFFECTS = {"fail", "warn"}
VALID_TARGET_RUNTIME_MODES = {"managed_runtime"}
VALID_TARGET_RUNTIME_ENTRY_MODES = {"wrapper_only"}
VALID_TARGET_RUNTIME_GRAPH_SOURCES = {"workflow_graph"}
VALID_TARGET_RUNTIME_OWNER_FAILURE = {"terminal"}
VALID_TARGET_RUNTIME_OUTPUT_FAILURE = {"retry_then_terminal", "terminal"}
VALID_TARGET_EXECUTOR_PROVIDERS = {"fixture_host", "command_adapter", "current_agent", "manual"}
VALID_TARGET_EXECUTOR_UNSUPPORTED_VERDICTS = {"FAIL"}
FORBIDDEN_TARGET_PUBLISH_PREFIXES = (".claude/", ".workflowprogram/", "config/scripts/")
VALID_TARGET_CLAUDE_GUARD_MODES = {"managed_block"}
REQUIRED_FAILURE_KINDS = {"none", "design", "implementation", "environment", "conflict"}
VALID_ENV_SKIP_CHECKS = {
    "runtime_host_available",
    "runtime_host_ready",
    "target_root_writable",
}
DEPRECATED_ENV_SKIP_CHECKS = {
    "claude_cli_available",
    "claude_cli_logged_in",
}
REQUIRED_RUNTIME_CONTRACT_KEYS = {"write_boundaries", "required_evidence", "failure_kinds", "environment_skip"}
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
VALID_ENTRY_TYPES = {"slash_command", "natural_language", "hybrid"}
RUNTIME_REF_PATTERN = re.compile(r"^runtime_contract\.([A-Za-z_][A-Za-z0-9_]*)$")
SAFE_RELATIVE_PATH_RE = re.compile(r"^(?!/)(?!.*(?:^|/)\.\.(?:/|$)).+$")
REGISTRY_FILE_PREFIXES = {
    "commands": ".claude/commands/",
    "skills": ".claude/skills/",
    "agents": ".claude/agents/",
    "hooks": ".claude/hooks/",
    # registry.runtime_assets declares target-side control-plane assets.
    "runtime_assets": ".workflowprogram/runtime/",
}


def parse_args() -> argparse.Namespace:
    """解析独立 spec 校验所需的命令行参数。"""

    parser = argparse.ArgumentParser(description="Validate workflow-spec.yaml")
    parser.add_argument("--spec", required=True, help="Path to workflow-spec.yaml")
    parser.add_argument("--json", action="store_true", help="Print structured report")
    return parser.parse_args()


def add_error(errors: List[str], msg: str) -> None:
    """追加一条 schema 错误信息。"""

    errors.append(msg)


def add_warn(warnings: List[str], msg: str) -> None:
    """追加一条不阻塞执行的 schema warning。"""

    warnings.append(msg)


def require_mapping(value: Any, field: str, errors: List[str]) -> Dict[str, Any]:
    """要求字段必须是 mapping/object，同时尽量保持校验器继续运行。"""

    if isinstance(value, dict):
        return value
    add_error(errors, f"{field} must be a mapping/object")
    return {}


def require_list(value: Any, field: str, errors: List[str]) -> List[Any]:
    """要求字段必须是列表，同时尽量保持校验器继续运行。"""

    if isinstance(value, list):
        return value
    add_error(errors, f"{field} must be a list")
    return []


def validate_top_level(spec: Dict[str, Any], errors: List[str], warnings: List[str]) -> None:
    """校验顶层控制面区段是否齐全。"""

    missing = sorted(REQUIRED_TOP_KEYS - set(spec.keys()))
    for key in missing:
        add_error(errors, f"Missing top-level key: {key}")
    extra = sorted(set(spec.keys()) - REQUIRED_TOP_KEYS - OPTIONAL_TOP_KEYS)
    if extra:
        add_warn(warnings, f"Extra top-level keys: {', '.join(extra)}")


def validate_meta(meta: Dict[str, Any], errors: List[str]) -> None:
    """校验用于标识 workflow spec 本身的元数据。"""

    missing = sorted(REQUIRED_META_KEYS - set(meta.keys()))
    for key in missing:
        add_error(errors, f"meta.{key} is required")

    complexity = str(meta.get("complexity", ""))
    if complexity and complexity not in VALID_COMPLEXITY:
        add_error(errors, f"meta.complexity must be one of {sorted(VALID_COMPLEXITY)}")


def validate_stages(
    stages: List[Any],
    agent_refs: Set[str],
    errors: List[str],
    warnings: List[str],
) -> Set[str]:
    """校验可执行阶段声明及其局部不变量。

    这里强制执行显式 `stage_slot` 模型，避免后续脚本再根据位置猜逻辑阶段。
    """

    stage_ids: Set[str] = set()
    transition_refs: List[str] = []
    observed_slots: List[str] = []
    seen_slots: Set[str] = set()

    if not stages:
        add_error(errors, "stages must not be empty")
        return stage_ids

    for idx, raw_stage in enumerate(stages):
        prefix = f"stages[{idx}]"
        stage = require_mapping(raw_stage, prefix, errors)
        stage_id = str(stage.get("id", "")).strip()
        stage_slot = str(stage.get("stage_slot", "")).strip()
        stage_name = str(stage.get("name", "")).strip()
        pattern = str(stage.get("pattern", "")).strip()

        if not stage_id:
            add_error(errors, f"{prefix}.id is required")
        elif not re.match(r"^[A-Za-z0-9_-]+$", stage_id):
            add_error(errors, f"{prefix}.id has invalid format: {stage_id}")
        elif stage_id in stage_ids:
            add_error(errors, f"Duplicate stage id: {stage_id}")
        else:
            stage_ids.add(stage_id)

        if not stage_name:
            add_error(errors, f"{prefix}.name is required")

        if not stage_slot:
            add_error(errors, f"{prefix}.stage_slot is required")
        elif stage_slot not in VALID_STAGE_SLOTS:
            add_error(errors, f"{prefix}.stage_slot must be one of {REQUIRED_STAGE_SLOT_ORDER}")
        elif stage_slot in seen_slots:
            add_error(errors, f"Duplicate stage_slot: {stage_slot}")
        else:
            seen_slots.add(stage_slot)
            observed_slots.append(stage_slot)

        if not pattern:
            add_error(errors, f"{prefix}.pattern is required")
        elif pattern not in VALID_PATTERNS:
            add_error(errors, f"{prefix}.pattern must be one of {sorted(VALID_PATTERNS)}")

        agent_ref = stage.get("agent_ref")
        if agent_ref is not None:
            agent_ref_str = str(agent_ref).strip()
            if agent_ref_str and agent_ref_str not in agent_refs:
                add_error(errors, f"{prefix}.agent_ref '{agent_ref_str}' not found in agent_refs")

        if "max_retries" in stage:
            value = stage["max_retries"]
            if not isinstance(value, int) or value < 0:
                add_error(errors, f"{prefix}.max_retries must be a non-negative integer")

        gate = stage.get("gate")
        if gate is not None and str(gate).strip() and str(gate) != "user_approval":
            add_warn(warnings, f"{prefix}.gate is uncommon: {gate}")

        for tkey in ("on_approve", "on_reject"):
            target = stage.get(tkey)
            if target is None:
                continue
            target_str = str(target).strip()
            if not target_str:
                continue
            transition_refs.append(target_str)

        steps = stage.get("steps")
        if steps is not None:
            if not isinstance(steps, list):
                add_error(errors, f"{prefix}.steps must be a list")
            elif not steps:
                add_warn(warnings, f"{prefix}.steps is empty")

        actions = stage.get("actions")
        if actions is not None:
            if not isinstance(actions, list):
                add_error(errors, f"{prefix}.actions must be a list")
            elif not actions:
                add_warn(warnings, f"{prefix}.actions is empty")

        output = stage.get("output")
        if output is None:
            add_warn(warnings, f"{prefix}.output is empty; recommend declaring explicit outputs")

    for ref in transition_refs:
        if ref not in stage_ids and ref not in VALID_TERMINALS:
            add_error(errors, f"Transition target '{ref}' is neither a stage id nor terminal {sorted(VALID_TERMINALS)}")

    missing_slots = [slot for slot in REQUIRED_STAGE_SLOT_ORDER if slot not in seen_slots]
    if missing_slots:
        add_error(errors, f"stages missing required stage_slot values: {', '.join(missing_slots)}")
    if observed_slots and observed_slots != REQUIRED_STAGE_SLOT_ORDER:
        add_error(errors, f"stages must appear in stage_slot order: {', '.join(REQUIRED_STAGE_SLOT_ORDER)}")

    return stage_ids


def validate_agent_refs(agent_refs: List[Any], errors: List[str]) -> Set[str]:
    """校验声明的可复用 agent 引用。"""

    names: Set[str] = set()
    if not agent_refs:
        add_error(errors, "agent_refs must not be empty")
        return names
    for idx, item in enumerate(agent_refs):
        text = str(item).strip()
        if not text:
            add_error(errors, f"agent_refs[{idx}] must not be empty")
            continue
        if text in names:
            add_error(errors, f"Duplicate agent ref: {text}")
            continue
        names.add(text)
    return names


def validate_skills(skills: List[Any], errors: List[str]) -> None:
    """校验 spec 中声明的逻辑 skill 列表。"""

    names: Set[str] = set()
    for idx, item in enumerate(skills):
        prefix = f"skills[{idx}]"
        if isinstance(item, dict):
            name = str(item.get("name", "")).strip()
        else:
            name = str(item).strip()
        if not name:
            add_error(errors, f"{prefix}.name is required")
            continue
        if name in names:
            add_error(errors, f"Duplicate skill name in spec: {name}")
            continue
        names.add(name)


def validate_registry(registry: Dict[str, Any], errors: List[str]) -> None:
    """校验 spec 中声明的目标 `.claude` registry 条目。"""

    for section, expected_prefix in REGISTRY_FILE_PREFIXES.items():
        entries = require_list(registry.get(section, []), f"registry.{section}", errors)
        seen_names: Set[str] = set()
        seen_files: Set[str] = set()
        for idx, item in enumerate(entries):
            prefix = f"registry.{section}[{idx}]"
            entry = require_mapping(item, prefix, errors)
            name = str(entry.get("name", "")).strip()
            file_path = str(entry.get("file", "")).strip()
            if not name:
                add_error(errors, f"{prefix}.name is required")
            elif name in seen_names:
                add_error(errors, f"Duplicate registry.{section} name: {name}")
            else:
                seen_names.add(name)
            if not file_path:
                add_error(errors, f"{prefix}.file is required")
            elif not file_path.startswith(expected_prefix):
                add_error(errors, f"{prefix}.file must start with {expected_prefix}")
            elif not SAFE_RELATIVE_PATH_RE.match(file_path):
                add_error(errors, f"{prefix}.file must be a safe relative path")
            elif file_path in seen_files:
                add_error(errors, f"Duplicate registry.{section} file: {file_path}")
            else:
                seen_files.add(file_path)


def collect_registry_names(registry: Dict[str, Any], sections: Set[str] | None = None) -> Set[str]:
    """收集 registry 中声明的 name。"""

    selected_sections = sections or set(REGISTRY_FILE_PREFIXES)
    names: Set[str] = set()
    for section in selected_sections:
        items = registry.get(section, []) if isinstance(registry, dict) else []
        if not isinstance(items, list):
            continue
        for item in items:
            if isinstance(item, dict):
                name = str(item.get("name", "")).strip()
            else:
                name = str(item).strip()
            if name:
                names.add(name)
    return names


def collect_registry_files(registry: Dict[str, Any]) -> Set[str]:
    """收集 registry 中声明的目标资产路径。"""

    files: Set[str] = set()
    for section in REGISTRY_FILE_PREFIXES:
        items = registry.get(section, []) if isinstance(registry, dict) else []
        if not isinstance(items, list):
            continue
        for item in items:
            if isinstance(item, dict):
                file_path = str(item.get("file", "")).strip()
                if file_path:
                    files.add(file_path)
    return files


def declared_deliverable_patterns(test_contract: Dict[str, Any]) -> Set[str]:
    """收集 test_contract.artifacts 中声明的交付物 pattern。"""

    artifacts = test_contract.get("artifacts", {}) if isinstance(test_contract, dict) else {}
    if not isinstance(artifacts, dict):
        return set()
    values: Set[str] = set()
    for key in ("deliverables", "optional_outputs"):
        raw_items = artifacts.get(key, [])
        if not isinstance(raw_items, list):
            continue
        values.update(str(item).strip() for item in raw_items if str(item).strip())
    return values


def is_declared_target_asset(path: str, registry_files: Set[str], deliverables: Set[str]) -> bool:
    """判断一个目标资产路径是否已由 registry 或 test_contract 声明。"""

    if path in registry_files or path in deliverables:
        return True
    return any(fnmatch.fnmatch(path, pattern) for pattern in deliverables)


def graph_target_output_refs(output_refs: List[str]) -> List[str]:
    """只提取会落到 TARGET_ROOT 的 graph output refs。"""

    return [
        ref
        for ref in output_refs
        if ref.startswith(".claude/")
        or ref.startswith(".workflowprogram/design/")
        or ref.startswith(".workflowprogram/runtime/")
    ]


def validate_workflow_graph(
    workflow_graph: Dict[str, Any],
    registry: Dict[str, Any],
    test_contract: Dict[str, Any],
    errors: List[str],
    warnings: List[str],
) -> None:
    """校验目标工作流自己的可变图契约。

    `stages` 与 `intent_flows` 描述 WorkflowProgram 自身 S0..S6 控制面；
    `workflow_graph` 描述生成后的目标工作流，允许使用请求特定节点，而不是强制套用 S1..S6。
    """

    if not workflow_graph:
        return

    for field in ("schema_version", "entrypoints", "nodes", "transitions", "templates_used"):
        if field not in workflow_graph:
            add_error(errors, f"workflow_graph.{field} is required when workflow_graph is declared")

    schema_version = workflow_graph.get("schema_version")
    if not isinstance(schema_version, int) or schema_version <= 0:
        add_error(errors, "workflow_graph.schema_version must be a positive integer")

    templates_used = workflow_graph.get("templates_used", [])
    if not isinstance(templates_used, list) or not templates_used:
        add_error(errors, "workflow_graph.templates_used must be a non-empty list")
        template_values: Set[str] = set()
    else:
        template_values = {str(item).strip() for item in templates_used if str(item).strip()}
        if len(template_values) != len([item for item in templates_used if str(item).strip()]):
            add_error(errors, "workflow_graph.templates_used contains duplicate or empty values")

    nodes = workflow_graph.get("nodes", [])
    if not isinstance(nodes, list) or not nodes:
        add_error(errors, "workflow_graph.nodes must be a non-empty list")
        nodes = []
    node_ids: Set[str] = set()
    adjacency: Dict[str, Set[str]] = {}
    registry_files = collect_registry_files(registry)
    deliverables = declared_deliverable_patterns(test_contract)

    for idx, raw_node in enumerate(nodes):
        prefix = f"workflow_graph.nodes[{idx}]"
        node = require_mapping(raw_node, prefix, errors)
        node_id = str(node.get("id", "")).strip()
        role = str(node.get("role", "")).strip()
        template = str(node.get("template", "")).strip()
        gate = str(node.get("gate", "")).strip()
        owner = str(node.get("owner", "")).strip()
        input_refs = node.get("input_refs")
        output_refs = node.get("output_refs")
        loop_policy = node.get("loop_policy")
        node_complexity = node.get("complexity")
        design_intensity = node.get("design_intensity")
        node_design_required = node.get("node_design_required")
        node_design_exemption = node.get("node_design_exemption")

        if not node_id:
            add_error(errors, f"{prefix}.id is required")
        elif not re.match(r"^[A-Za-z0-9_-]+$", node_id):
            add_error(errors, f"{prefix}.id has invalid format: {node_id}")
        elif node_id in node_ids:
            add_error(errors, f"Duplicate workflow_graph node id: {node_id}")
        else:
            node_ids.add(node_id)
            adjacency[node_id] = set()
        if not role:
            add_error(errors, f"{prefix}.role is required")
        if not template:
            add_error(errors, f"{prefix}.template is required")
        elif template_values and template not in template_values:
            add_error(errors, f"{prefix}.template must be listed in workflow_graph.templates_used")
        if gate and gate not in VALID_WORKFLOW_GRAPH_GATES:
            add_error(errors, f"{prefix}.gate must be one of {sorted(VALID_WORKFLOW_GRAPH_GATES)}")
        if not owner:
            add_error(errors, f"{prefix}.owner is required")
        if not isinstance(input_refs, list):
            add_error(errors, f"{prefix}.input_refs must be a list")
        if not isinstance(output_refs, list) or not output_refs:
            add_error(errors, f"{prefix}.output_refs must be a non-empty list")
            output_values: List[str] = []
        else:
            output_values = [str(item).strip() for item in output_refs if str(item).strip()]
            if len(output_values) != len(output_refs):
                add_error(errors, f"{prefix}.output_refs must not contain empty values")
        for output_idx, output_ref in enumerate(output_values):
            if output_ref.startswith("/") or not SAFE_RELATIVE_PATH_RE.match(output_ref):
                add_error(errors, f"{prefix}.output_refs[{output_idx}] must be a safe relative path or logical ref")
            if output_ref in graph_target_output_refs([output_ref]) and not is_declared_target_asset(output_ref, registry_files, deliverables):
                add_error(
                    errors,
                    f"{prefix}.output_refs[{output_idx}] target asset must be declared in registry or test_contract.artifacts: {output_ref}",
                )
        if node_complexity is not None and str(node_complexity).strip() not in VALID_WORKFLOW_GRAPH_NODE_COMPLEXITY:
            add_error(errors, f"{prefix}.complexity must be one of {sorted(VALID_WORKFLOW_GRAPH_NODE_COMPLEXITY)}")
        if design_intensity is not None and str(design_intensity).strip() not in VALID_WORKFLOW_GRAPH_DESIGN_INTENSITY:
            add_error(errors, f"{prefix}.design_intensity must be one of {sorted(VALID_WORKFLOW_GRAPH_DESIGN_INTENSITY)}")
        if node_design_required is not None and not isinstance(node_design_required, bool):
            add_error(errors, f"{prefix}.node_design_required must be boolean")
        if node_design_exemption is not None:
            if not isinstance(node_design_exemption, dict):
                add_error(errors, f"{prefix}.node_design_exemption must be a mapping/object")
            else:
                if not str(node_design_exemption.get("reason", "")).strip():
                    add_error(errors, f"{prefix}.node_design_exemption.reason is required")
                accepted_by = str(node_design_exemption.get("accepted_by", "")).strip()
                if accepted_by not in VALID_NODE_DESIGN_EXEMPTION_ACCEPTED_BY:
                    add_error(
                        errors,
                        f"{prefix}.node_design_exemption.accepted_by must be one of {sorted(VALID_NODE_DESIGN_EXEMPTION_ACCEPTED_BY)}",
                    )
        if loop_policy is not None:
            validate_node_loop_policy(node_id, loop_policy, prefix, errors, warnings)

    transitions = workflow_graph.get("transitions", [])
    if transitions is None:
        transitions = []
    if not isinstance(transitions, list):
        add_error(errors, "workflow_graph.transitions must be a list")
        transitions = []
    terminal_targets = set(VALID_TERMINALS) | {"success", "failure"}
    for idx, raw_transition in enumerate(transitions):
        prefix = f"workflow_graph.transitions[{idx}]"
        transition = require_mapping(raw_transition, prefix, errors)
        source = str(transition.get("from", "")).strip()
        target = str(transition.get("to", "")).strip()
        if not source:
            add_error(errors, f"{prefix}.from is required")
        elif source not in node_ids:
            add_error(errors, f"{prefix}.from references unknown node: {source}")
        if not target:
            add_error(errors, f"{prefix}.to is required")
        elif target not in node_ids and target not in terminal_targets:
            add_error(errors, f"{prefix}.to references unknown node or terminal: {target}")
        if source in adjacency and target in node_ids:
            adjacency[source].add(target)
        condition = transition.get("condition")
        if condition is not None and not str(condition).strip():
            add_error(errors, f"{prefix}.condition must not be empty when provided")

    entrypoints = workflow_graph.get("entrypoints", [])
    if not isinstance(entrypoints, list) or not entrypoints:
        add_error(errors, "workflow_graph.entrypoints must be a non-empty list")
        entrypoints = []
    registered_entrypoints = collect_registry_names(registry, {"commands", "skills"})
    entry_nodes: Set[str] = set()
    seen_entry_names: Set[str] = set()
    for idx, raw_entry in enumerate(entrypoints):
        prefix = f"workflow_graph.entrypoints[{idx}]"
        entry = require_mapping(raw_entry, prefix, errors)
        name = str(entry.get("name", "")).strip()
        node_id = str(entry.get("node", "")).strip()
        if not name:
            add_error(errors, f"{prefix}.name is required")
        elif name in seen_entry_names:
            add_error(errors, f"Duplicate workflow_graph entrypoint name: {name}")
        else:
            seen_entry_names.add(name)
        if name and name not in registered_entrypoints:
            add_error(errors, f"{prefix}.name must resolve to registry.commands or registry.skills: {name}")
        if not node_id:
            add_error(errors, f"{prefix}.node is required")
        elif node_id not in node_ids:
            add_error(errors, f"{prefix}.node references unknown node: {node_id}")
        else:
            entry_nodes.add(node_id)

    reachable: Set[str] = set()
    queue = list(entry_nodes)
    while queue:
        node_id = queue.pop(0)
        if node_id in reachable:
            continue
        reachable.add(node_id)
        queue.extend(sorted(adjacency.get(node_id, set()) - reachable))
    unreachable = sorted(node_ids - reachable)
    if unreachable and entry_nodes:
        add_error(errors, f"workflow_graph contains unreachable nodes from entrypoints: {', '.join(unreachable)}")
    if not transitions and len(node_ids) > 1:
        add_warn(warnings, "workflow_graph has multiple nodes but no transitions")


def workflow_graph_loop_nodes(workflow_graph: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return workflow_graph nodes whose loop_policy is explicitly enabled."""

    if not isinstance(workflow_graph, dict):
        return []
    nodes = workflow_graph.get("nodes", [])
    if not isinstance(nodes, list):
        return []
    enabled: List[Dict[str, Any]] = []
    for raw_node in nodes:
        if not isinstance(raw_node, dict):
            continue
        loop_policy = raw_node.get("loop_policy", {})
        if isinstance(loop_policy, dict) and loop_policy.get("enabled") is True:
            enabled.append(raw_node)
    return enabled


def workflow_graph_output_refs(workflow_graph: Dict[str, Any]) -> List[str]:
    """Return normalized output refs declared by target workflow graph nodes."""

    if not isinstance(workflow_graph, dict):
        return []
    refs: List[str] = []
    nodes = workflow_graph.get("nodes", [])
    if not isinstance(nodes, list):
        return refs
    for raw_node in nodes:
        if not isinstance(raw_node, dict):
            continue
        for item in raw_node.get("output_refs", []):
            text = str(item).strip().replace("\\", "/")
            if text:
                refs.append(text)
    return refs


def workflow_graph_input_refs(workflow_graph: Dict[str, Any]) -> List[str]:
    """Return normalized input refs declared by target workflow graph nodes."""

    if not isinstance(workflow_graph, dict):
        return []
    refs: List[str] = []
    nodes = workflow_graph.get("nodes", [])
    if not isinstance(nodes, list):
        return refs
    for raw_node in nodes:
        if not isinstance(raw_node, dict):
            continue
        for item in raw_node.get("input_refs", []):
            text = str(item).strip().replace("\\", "/")
            if text:
                refs.append(text)
    return refs


def is_runtime_file_ref(ref: str) -> bool:
    """Return true for path-like refs that should map to runtime files."""

    text = ref.strip().replace("\\", "/")
    return bool(text) and not text.startswith("$") and "/" in text


def normalize_relative_path(path_text: str) -> str:
    cleaned = path_text.strip().replace("\\", "/")
    while cleaned.startswith("./"):
        cleaned = cleaned[2:]
    return cleaned


def safe_relative_path(path_text: str) -> bool:
    cleaned = normalize_relative_path(path_text)
    return bool(cleaned) and not cleaned.startswith("/") and bool(SAFE_RELATIVE_PATH_RE.match(cleaned))


def path_under(path_text: str, parent_text: str) -> bool:
    path = normalize_relative_path(path_text).rstrip("/")
    parent = normalize_relative_path(parent_text).rstrip("/")
    return bool(path and parent) and (path == parent or path.startswith(parent + "/"))


def validate_target_runtime_policy(
    target_runtime_policy: Dict[str, Any],
    workflow_graph: Dict[str, Any],
    generated_runtime_contract: Dict[str, Any],
    errors: List[str],
    warnings: List[str],
) -> None:
    """Validate generated target workflow managed-runtime policy."""

    if not target_runtime_policy:
        if workflow_graph:
            add_warn(warnings, "target_runtime_policy is not declared; generated target workflow runtime remains legacy/advisory")
        return

    mode = str(target_runtime_policy.get("mode", "")).strip()
    if mode not in VALID_TARGET_RUNTIME_MODES:
        add_error(errors, f"target_runtime_policy.mode must be one of {sorted(VALID_TARGET_RUNTIME_MODES)}")

    entry_mode = str(target_runtime_policy.get("entry_mode", "")).strip()
    if entry_mode not in VALID_TARGET_RUNTIME_ENTRY_MODES:
        add_error(errors, f"target_runtime_policy.entry_mode must be one of {sorted(VALID_TARGET_RUNTIME_ENTRY_MODES)}")

    graph_source = str(target_runtime_policy.get("graph_source", "")).strip()
    if graph_source not in VALID_TARGET_RUNTIME_GRAPH_SOURCES:
        add_error(errors, f"target_runtime_policy.graph_source must be one of {sorted(VALID_TARGET_RUNTIME_GRAPH_SOURCES)}")
    if graph_source == "workflow_graph" and not workflow_graph:
        add_error(errors, "target_runtime_policy.graph_source=workflow_graph requires workflow_graph")

    for field in ("lifecycle_events_required", "artifact_provenance_required"):
        if not isinstance(target_runtime_policy.get(field), bool):
            add_error(errors, f"target_runtime_policy.{field} must be boolean")

    owner_failure = str(target_runtime_policy.get("owner_resolution_failure", "")).strip()
    if owner_failure not in VALID_TARGET_RUNTIME_OWNER_FAILURE:
        add_error(
            errors,
            f"target_runtime_policy.owner_resolution_failure must be one of {sorted(VALID_TARGET_RUNTIME_OWNER_FAILURE)}",
        )

    output_failure = str(target_runtime_policy.get("output_contract_failure", "")).strip()
    if output_failure not in VALID_TARGET_RUNTIME_OUTPUT_FAILURE:
        add_error(
            errors,
            f"target_runtime_policy.output_contract_failure must be one of {sorted(VALID_TARGET_RUNTIME_OUTPUT_FAILURE)}",
        )

    max_retries = target_runtime_policy.get("max_retries_per_node")
    if not isinstance(max_retries, int) or max_retries < 0:
        add_error(errors, "target_runtime_policy.max_retries_per_node must be a non-negative integer")

    immutable_patterns = target_runtime_policy.get("immutable_during_run", [])
    if not isinstance(immutable_patterns, list):
        add_error(errors, "target_runtime_policy.immutable_during_run must be a list")
        immutable_patterns = []
    normalized_patterns: List[str] = []
    for idx, raw_pattern in enumerate(immutable_patterns):
        pattern = str(raw_pattern).strip().replace("\\", "/")
        if not pattern:
            add_error(errors, f"target_runtime_policy.immutable_during_run[{idx}] must not be empty")
            continue
        # Allow glob syntax while still rejecting absolute paths and parent traversal.
        safe_probe = pattern.replace("**", "x").replace("*", "x")
        if pattern.startswith("/") or not SAFE_RELATIVE_PATH_RE.match(safe_probe):
            add_error(errors, f"target_runtime_policy.immutable_during_run[{idx}] must be a safe relative glob")
            continue
        normalized_patterns.append(pattern)

    if mode == "managed_runtime":
        capabilities = set(runtime_capabilities_from_contract(generated_runtime_contract))
        if "target_managed_runtime" not in capabilities:
            add_error(
                errors,
                "generated_runtime_contract.runtime_capabilities must include target_managed_runtime when target_runtime_policy.mode=managed_runtime",
            )
        for output_ref in workflow_graph_output_refs(workflow_graph):
            for pattern in normalized_patterns:
                if fnmatch.fnmatch(output_ref, pattern):
                    add_error(
                        errors,
                        f"workflow_graph output_ref conflicts with target_runtime_policy.immutable_during_run: {output_ref} matches {pattern}",
                    )


def validate_target_executor_policy(
    target_executor_policy: Dict[str, Any],
    errors: List[str],
    warnings: List[str],
) -> None:
    """Validate target workflow executor provider policy."""

    if not target_executor_policy:
        add_warn(warnings, "target_executor_policy is not declared; default provider is current_agent evidence mode")
        return
    default_provider = str(target_executor_policy.get("default_provider", "")).strip().replace("-", "_")
    if default_provider not in VALID_TARGET_EXECUTOR_PROVIDERS:
        add_error(errors, f"target_executor_policy.default_provider must be one of {sorted(VALID_TARGET_EXECUTOR_PROVIDERS)}")
    allowed = target_executor_policy.get("allowed_providers", [])
    if not isinstance(allowed, list) or not allowed:
        add_error(errors, "target_executor_policy.allowed_providers must be a non-empty list")
        allowed_values: List[str] = []
    else:
        allowed_values = [str(item).strip().replace("-", "_") for item in allowed if str(item).strip()]
        for idx, value in enumerate(allowed_values):
            if value not in VALID_TARGET_EXECUTOR_PROVIDERS:
                add_error(errors, f"target_executor_policy.allowed_providers[{idx}] must be one of {sorted(VALID_TARGET_EXECUTOR_PROVIDERS)}")
    if default_provider and allowed_values and default_provider not in allowed_values:
        add_error(errors, "target_executor_policy.default_provider must be listed in allowed_providers")
    evidence_dir = str(target_executor_policy.get("evidence_dir", "")).strip()
    if not safe_relative_path(evidence_dir):
        add_error(errors, "target_executor_policy.evidence_dir must be a safe relative path")
    elif not path_under(evidence_dir, "outputs/stages"):
        add_error(errors, "target_executor_policy.evidence_dir must stay under outputs/stages")
    unsupported = str(target_executor_policy.get("unsupported_provider_verdict", "")).strip()
    if unsupported not in VALID_TARGET_EXECUTOR_UNSUPPORTED_VERDICTS:
        add_error(
            errors,
            f"target_executor_policy.unsupported_provider_verdict must be one of {sorted(VALID_TARGET_EXECUTOR_UNSUPPORTED_VERDICTS)}",
        )
    if any(value in {"manual", "current_agent"} for value in allowed_values) and not evidence_dir:
        add_error(errors, "target_executor_policy.evidence_dir is required when manual/current_agent providers are allowed")


def validate_target_publish_policy(
    target_publish_policy: Dict[str, Any],
    workflow_graph: Dict[str, Any],
    generated_runtime_contract: Dict[str, Any],
    errors: List[str],
    warnings: List[str],
) -> None:
    """Validate target workflow finalizer and atomic publish policy."""

    if not target_publish_policy:
        return
    enabled = target_publish_policy.get("enabled")
    if not isinstance(enabled, bool):
        add_error(errors, "target_publish_policy.enabled must be boolean")
        return
    if enabled is False:
        return

    if target_publish_policy.get("run_scoped_outputs_required") is not True:
        add_error(errors, "target_publish_policy.run_scoped_outputs_required must be true when enabled=true")
    if target_publish_policy.get("atomic") is not True:
        add_error(errors, "target_publish_policy.atomic must be true when enabled=true")

    publish_root = normalize_relative_path(str(target_publish_policy.get("publish_root", "")))
    latest_marker = normalize_relative_path(str(target_publish_policy.get("latest_marker", "")))
    manifest_path = normalize_relative_path(str(target_publish_policy.get("manifest_path", "")))
    for field, value in (
        ("publish_root", publish_root),
        ("latest_marker", latest_marker),
        ("manifest_path", manifest_path),
    ):
        if not safe_relative_path(value):
            add_error(errors, f"target_publish_policy.{field} must be a safe relative path")
    if publish_root:
        if any(path_under(publish_root, prefix.rstrip("/")) for prefix in FORBIDDEN_TARGET_PUBLISH_PREFIXES):
            add_error(
                errors,
                "target_publish_policy.publish_root must not be under .claude/, .workflowprogram/, or config/scripts/",
            )
        for field, value in (("latest_marker", latest_marker), ("manifest_path", manifest_path)):
            if value and not path_under(value, publish_root):
                add_error(errors, f"target_publish_policy.{field} must stay under target_publish_policy.publish_root")

    required_run_artifacts = target_publish_policy.get("required_run_artifacts", [])
    if not isinstance(required_run_artifacts, list) or not required_run_artifacts:
        add_error(errors, "target_publish_policy.required_run_artifacts must be a non-empty list")
    else:
        for idx, raw_path in enumerate(required_run_artifacts):
            value = str(raw_path).strip()
            if not safe_relative_path(value):
                add_error(errors, f"target_publish_policy.required_run_artifacts[{idx}] must be a safe relative path")

    required_reports = target_publish_policy.get("required_reports", [])
    if not isinstance(required_reports, list):
        add_error(errors, "target_publish_policy.required_reports must be a list")
    else:
        for idx, raw_report in enumerate(required_reports):
            prefix = f"target_publish_policy.required_reports[{idx}]"
            report = require_mapping(raw_report, prefix, errors)
            path = str(report.get("path", "")).strip()
            status_field = str(report.get("status_field", "")).strip()
            pass_values = report.get("pass_values", [])
            if not safe_relative_path(path):
                add_error(errors, f"{prefix}.path must be a safe relative path")
            normalized_report_path = normalize_relative_path(path)
            if manifest_path and normalized_report_path == manifest_path:
                add_error(
                    errors,
                    f"{prefix}.path must not equal target_publish_policy.manifest_path because the finalizer owns that manifest",
                )
            if latest_marker and normalized_report_path == latest_marker:
                add_error(
                    errors,
                    f"{prefix}.path must not equal target_publish_policy.latest_marker because the finalizer owns that marker",
                )
            if not status_field:
                add_error(errors, f"{prefix}.status_field is required")
            if not isinstance(pass_values, list) or not [str(item).strip() for item in pass_values if str(item).strip()]:
                add_error(errors, f"{prefix}.pass_values must be a non-empty list")

    finalizer_owned_paths = {value for value in (manifest_path, latest_marker) if value}
    if finalizer_owned_paths:
        finalizer_owned_inputs = sorted(
            {
                normalize_relative_path(ref)
                for ref in workflow_graph_input_refs(workflow_graph)
                if normalize_relative_path(ref) in finalizer_owned_paths
            }
        )
        if finalizer_owned_inputs:
            add_error(
                errors,
                "workflow_graph input_refs must not depend on finalizer-owned publish artifacts before finalizer runs: "
                + ", ".join(finalizer_owned_inputs),
            )
        finalizer_owned_outputs = sorted(
            {
                normalize_relative_path(ref)
                for ref in workflow_graph_output_refs(workflow_graph)
                if normalize_relative_path(ref) in finalizer_owned_paths
            }
        )
        if finalizer_owned_outputs:
            add_error(
                errors,
                "workflow_graph output_refs must not write finalizer-owned publish artifacts: "
                + ", ".join(finalizer_owned_outputs),
            )

    publish_artifacts = target_publish_policy.get("publish_artifacts", [])
    if publish_artifacts is not None and not isinstance(publish_artifacts, list):
        add_error(errors, "target_publish_policy.publish_artifacts must be a list")
    elif isinstance(publish_artifacts, list):
        for idx, raw_item in enumerate(publish_artifacts):
            prefix = f"target_publish_policy.publish_artifacts[{idx}]"
            item = require_mapping(raw_item, prefix, errors)
            source = str(item.get("from", "")).strip()
            destination = str(item.get("to", source)).strip()
            if not safe_relative_path(source):
                add_error(errors, f"{prefix}.from must be a safe relative path")
            if destination and not safe_relative_path(destination):
                add_error(errors, f"{prefix}.to must be a safe relative path")
            if destination and publish_root and not path_under(destination, publish_root):
                add_error(errors, f"{prefix}.to must stay under target_publish_policy.publish_root")

    capabilities = set(runtime_capabilities_from_contract(generated_runtime_contract))
    if "target_atomic_publish" not in capabilities:
        add_error(
            errors,
            "generated_runtime_contract.runtime_capabilities must include target_atomic_publish when target_publish_policy.enabled=true",
        )
    if publish_root:
        outside_publish_root = [
            ref
            for ref in workflow_graph_output_refs(workflow_graph)
            if is_runtime_file_ref(ref) and not path_under(ref, publish_root)
        ]
        if outside_publish_root:
            add_error(
                errors,
                "workflow_graph output_refs must stay under target_publish_policy.publish_root when target_publish_policy.enabled=true: "
                + ", ".join(sorted(outside_publish_root)),
            )


def validate_target_claude_guard(
    target_claude_guard: Dict[str, Any],
    spec: Dict[str, Any],
    errors: List[str],
    warnings: List[str],
) -> None:
    """Validate target project CLAUDE.md runtime guard policy."""

    guard_required = guard_required_by_spec(spec)
    if not target_claude_guard:
        if guard_required:
            add_warn(warnings, "target_claude_guard is not declared; develop will apply the default CLAUDE.md runtime guard")
        return

    enabled = target_claude_guard.get("enabled")
    if not isinstance(enabled, bool):
        add_error(errors, "target_claude_guard.enabled must be boolean")
        return
    if enabled is False:
        if guard_required:
            add_error(errors, "target_claude_guard.enabled=false is not allowed for managed runtime or target publish workflows")
        return

    file_value = normalize_relative_path(str(target_claude_guard.get("file", "")))
    if file_value != "CLAUDE.md":
        add_error(errors, "target_claude_guard.file currently must be CLAUDE.md")

    mode = str(target_claude_guard.get("mode", "")).strip()
    if mode not in VALID_TARGET_CLAUDE_GUARD_MODES:
        add_error(errors, f"target_claude_guard.mode must be one of {sorted(VALID_TARGET_CLAUDE_GUARD_MODES)}")

    block_id = str(target_claude_guard.get("block_id", "")).strip()
    if not block_id:
        add_error(errors, "target_claude_guard.block_id is required")
    elif not re.match(r"^[A-Za-z0-9_.-]+$", block_id):
        add_error(errors, "target_claude_guard.block_id must contain only letters, numbers, underscore, dot, or dash")

    required_for = target_claude_guard.get("required_for", [])
    if not isinstance(required_for, list):
        add_error(errors, "target_claude_guard.required_for must be a list")
        required_values: List[str] = []
    else:
        required_values = [str(item).strip() for item in required_for if str(item).strip()]
        for idx, value in enumerate(required_values):
            if value not in VALID_REQUIRED_FOR:
                add_error(errors, f"target_claude_guard.required_for[{idx}] must be one of {sorted(VALID_REQUIRED_FOR)}")
    publish_policy = spec.get("target_publish_policy", {})
    if isinstance(publish_policy, dict) and publish_policy.get("enabled") is True and "target_publish_policy" not in required_values:
        add_error(errors, "target_claude_guard.required_for must include target_publish_policy when target_publish_policy.enabled=true")

    merge_policy = require_mapping(target_claude_guard.get("merge_policy", {}), "target_claude_guard.merge_policy", errors)
    for key, allowed_values in VALID_MERGE_VALUES.items():
        value = str(merge_policy.get(key, "")).strip()
        if value not in allowed_values:
            add_error(errors, f"target_claude_guard.merge_policy.{key} must be one of {sorted(allowed_values)}")

    content = require_mapping(target_claude_guard.get("content", {}), "target_claude_guard.content", errors)
    runtime_entry = normalize_relative_path(str(content.get("runtime_entry", "")))
    if runtime_entry != DEFAULT_RUNTIME_ENTRY:
        add_error(errors, f"target_claude_guard.content.runtime_entry must be {DEFAULT_RUNTIME_ENTRY}")

    actions = content.get("allowed_actions", [])
    if not isinstance(actions, list):
        add_error(errors, "target_claude_guard.content.allowed_actions must be a list")
        action_values: List[str] = []
    else:
        action_values = [str(item).strip() for item in actions if str(item).strip()]
        if sorted(action_values) != sorted(DEFAULT_ALLOWED_ACTIONS):
            add_error(errors, f"target_claude_guard.content.allowed_actions must be exactly {DEFAULT_ALLOWED_ACTIONS}")

    blocked_behavior = str(content.get("blocked_behavior", "")).strip()
    if blocked_behavior not in VALID_BLOCKED_BEHAVIOR:
        add_error(errors, f"target_claude_guard.content.blocked_behavior must be one of {sorted(VALID_BLOCKED_BEHAVIOR)}")

    failed_behavior = str(content.get("failed_behavior", "")).strip()
    if failed_behavior not in VALID_FAILED_BEHAVIOR:
        add_error(errors, f"target_claude_guard.content.failed_behavior must be one of {sorted(VALID_FAILED_BEHAVIOR)}")

    trusted_publisher = str(content.get("trusted_publisher", "")).strip()
    if trusted_publisher != "target-runtime-finalizer.py":
        add_error(errors, "target_claude_guard.content.trusted_publisher must be target-runtime-finalizer.py")

    forbidden = content.get("forbidden_operations", [])
    if not isinstance(forbidden, list):
        add_error(errors, "target_claude_guard.content.forbidden_operations must be a list")
    else:
        forbidden_values = {str(item).strip() for item in forbidden if str(item).strip()}
        missing = sorted(set(DEFAULT_FORBIDDEN_OPERATIONS) - forbidden_values)
        if missing:
            add_error(errors, "target_claude_guard.content.forbidden_operations missing required operations: " + ", ".join(missing))


def validate_node_loop_policy(
    node_id: str,
    raw_policy: Any,
    node_prefix: str,
    errors: List[str],
    warnings: List[str],
) -> None:
    """Validate a target workflow node-level Ralph-style loop policy."""

    prefix = f"{node_prefix}.loop_policy"
    policy = require_mapping(raw_policy, prefix, errors)
    enabled = policy.get("enabled")
    if not isinstance(enabled, bool):
        add_error(errors, f"{prefix}.enabled must be a boolean")
        return
    if enabled is False:
        return

    mode = str(policy.get("mode", "")).strip()
    if mode not in VALID_LOOP_MODES:
        add_error(errors, f"{prefix}.mode must be one of {sorted(VALID_LOOP_MODES)}")

    max_iterations = policy.get("max_iterations")
    if not isinstance(max_iterations, int) or max_iterations < 1 or max_iterations > 50:
        add_error(errors, f"{prefix}.max_iterations must be an integer between 1 and 50")

    fresh_context = policy.get("fresh_context_each_iteration")
    if not isinstance(fresh_context, bool):
        add_error(errors, f"{prefix}.fresh_context_each_iteration must be a boolean")

    prompt_package = str(policy.get("prompt_package", "")).strip()
    expected_prompt_prefix = ".workflowprogram/loops/"
    if not prompt_package:
        add_error(errors, f"{prefix}.prompt_package is required")
    elif prompt_package.startswith("/") or not SAFE_RELATIVE_PATH_RE.match(prompt_package):
        add_error(errors, f"{prefix}.prompt_package must be a safe relative path")
    elif not prompt_package.startswith(expected_prompt_prefix):
        add_error(errors, f"{prefix}.prompt_package must stay under {expected_prompt_prefix}**")

    goal_source = str(policy.get("goal_source", "user")).strip() or "user"
    if goal_source not in VALID_LOOP_GOAL_SOURCES:
        add_error(errors, f"{prefix}.goal_source must be one of {sorted(VALID_LOOP_GOAL_SOURCES)}")
    if goal_source == "model_subgoal" and not str(policy.get("parent_goal_ref", "")).strip():
        add_error(errors, f"{prefix}.parent_goal_ref is required when goal_source=model_subgoal")

    feedback_commands = policy.get("feedback_commands", [])
    if not isinstance(feedback_commands, list) or not feedback_commands:
        add_error(errors, f"{prefix}.feedback_commands must be a non-empty list")
        feedback_commands = []
    for command_idx, raw_command in enumerate(feedback_commands):
        command_prefix = f"{prefix}.feedback_commands[{command_idx}]"
        command = require_mapping(raw_command, command_prefix, errors)
        command_id = str(command.get("id", "")).strip()
        if not command_id:
            add_error(errors, f"{command_prefix}.id is required")
        kind = str(command.get("kind", "")).strip()
        if kind not in VALID_LOOP_FEEDBACK_KINDS:
            add_error(errors, f"{command_prefix}.kind must be one of {sorted(VALID_LOOP_FEEDBACK_KINDS)}")
        if "command" in command:
            add_error(errors, f"{command_prefix}.command is not allowed; use structured argv")
        argv = command.get("argv")
        if not isinstance(argv, list) or not argv or any(not str(item).strip() for item in argv):
            add_error(errors, f"{command_prefix}.argv must be a non-empty list of strings")
        timeout = command.get("timeout_seconds")
        if timeout is not None and (not isinstance(timeout, int) or timeout < 1 or timeout > 600):
            add_error(errors, f"{command_prefix}.timeout_seconds must be an integer between 1 and 600")
        failure_effect = str(command.get("failure_effect", "")).strip()
        if failure_effect not in VALID_LOOP_FAILURE_EFFECTS:
            add_error(errors, f"{command_prefix}.failure_effect must be one of {sorted(VALID_LOOP_FAILURE_EFFECTS)}")

    stop_conditions = require_mapping(policy.get("stop_conditions", {}), f"{prefix}.stop_conditions", errors)
    success_conditions = stop_conditions.get("success", [])
    if not isinstance(success_conditions, list) or not [str(item).strip() for item in success_conditions if str(item).strip()]:
        add_error(errors, f"{prefix}.stop_conditions.success must be a non-empty list")
    max_iteration_effect = str(stop_conditions.get("max_iterations", "")).strip()
    if max_iteration_effect not in VALID_LOOP_MAX_ITERATION_EFFECTS:
        add_error(errors, f"{prefix}.stop_conditions.max_iterations must be one of {sorted(VALID_LOOP_MAX_ITERATION_EFFECTS)}")
    no_progress_iterations = stop_conditions.get("no_progress_iterations")
    if no_progress_iterations is not None:
        if not isinstance(no_progress_iterations, int) or no_progress_iterations < 1:
            add_error(errors, f"{prefix}.stop_conditions.no_progress_iterations must be a positive integer")
        elif isinstance(max_iterations, int) and no_progress_iterations > max_iterations:
            add_error(errors, f"{prefix}.stop_conditions.no_progress_iterations must be <= max_iterations")
    hard_fail_on = stop_conditions.get("hard_fail_on", [])
    if hard_fail_on is not None and not isinstance(hard_fail_on, list):
        add_error(errors, f"{prefix}.stop_conditions.hard_fail_on must be a list when provided")

    tdd_policy = policy.get("tdd_policy", {})
    if tdd_policy:
        tdd = require_mapping(tdd_policy, f"{prefix}.tdd_policy", errors)
        tdd_enabled = tdd.get("enabled", False)
        if not isinstance(tdd_enabled, bool):
            add_error(errors, f"{prefix}.tdd_policy.enabled must be a boolean")
        if tdd_enabled:
            for key in ("test_first_required", "red_green_refactor"):
                if not isinstance(tdd.get(key), bool):
                    add_error(errors, f"{prefix}.tdd_policy.{key} must be a boolean when tdd_policy.enabled=true")

    evidence_outputs = policy.get("evidence_outputs", [])
    expected_evidence_prefix = f"outputs/stages/loops/{node_id}/"
    if not isinstance(evidence_outputs, list) or not evidence_outputs:
        add_error(errors, f"{prefix}.evidence_outputs must be a non-empty list")
    else:
        for output_idx, raw_output in enumerate(evidence_outputs):
            output = str(raw_output).strip()
            if not output:
                add_error(errors, f"{prefix}.evidence_outputs[{output_idx}] must not be empty")
            elif output.startswith("/") or not SAFE_RELATIVE_PATH_RE.match(output):
                add_error(errors, f"{prefix}.evidence_outputs[{output_idx}] must be a safe relative path")
            elif not output.startswith(expected_evidence_prefix):
                add_error(errors, f"{prefix}.evidence_outputs[{output_idx}] must stay under {expected_evidence_prefix}**")


def validate_intent_flows(intent_flows: Dict[str, Any], slot_map: Dict[str, str], errors: List[str]) -> None:
    """校验机器可读的 intent -> stage flow 映射。

    这些检查用于保证 HighLevel 的 intent 语义与可执行 stage flow 保持一致，
    而不是依赖自由文本描述。
    """

    missing = sorted(VALID_INTENT - set(intent_flows.keys()))
    for key in missing:
        add_error(errors, f"intent_flows.{key} is required")

    for intent in sorted(VALID_INTENT):
        prefix = f"intent_flows.{intent}"
        raw_flow = intent_flows.get(intent, {})
        if not isinstance(raw_flow, dict):
            add_error(errors, f"{prefix} must be a mapping")
            continue

        required_slots = raw_flow.get("required_stage_slots")
        optional_slots = raw_flow.get("optional_stage_slots", [])
        if not isinstance(required_slots, list) or not required_slots:
            add_error(errors, f"{prefix}.required_stage_slots must be a non-empty list")
            required_values: List[str] = []
        else:
            required_values = [str(item).strip() for item in required_slots]
        if not isinstance(optional_slots, list):
            add_error(errors, f"{prefix}.optional_stage_slots must be a list")
            optional_values: List[str] = []
        else:
            optional_values = [str(item).strip() for item in optional_slots]

        for idx, value in enumerate(required_values):
            if value not in VALID_STAGE_SLOTS:
                add_error(errors, f"{prefix}.required_stage_slots[{idx}] must be one of {REQUIRED_STAGE_SLOT_ORDER}")
            elif value not in slot_map:
                add_error(errors, f"{prefix}.required_stage_slots[{idx}] references missing stage_slot: {value}")
        for idx, value in enumerate(optional_values):
            if value not in VALID_STAGE_SLOTS:
                add_error(errors, f"{prefix}.optional_stage_slots[{idx}] must be one of {REQUIRED_STAGE_SLOT_ORDER}")
            elif value not in slot_map:
                add_error(errors, f"{prefix}.optional_stage_slots[{idx}] references missing stage_slot: {value}")
        overlap = sorted(set(required_values) & set(optional_values))
        if overlap:
            add_error(errors, f"{prefix} required/optional overlap: {', '.join(overlap)}")

        if intent == "develop":
            if required_values != REQUIRED_STAGE_SLOT_ORDER:
                add_error(errors, f"{prefix}.required_stage_slots must be exactly {REQUIRED_STAGE_SLOT_ORDER}")
            if optional_values:
                add_error(errors, f"{prefix}.optional_stage_slots must be empty")
        elif intent == "audit":
            if required_values != ["S5", "S6"]:
                add_error(errors, f"{prefix}.required_stage_slots must be exactly ['S5', 'S6']")
            if optional_values:
                add_error(errors, f"{prefix}.optional_stage_slots must be empty")
        elif intent == "iterate":
            if required_values != ["S6"]:
                add_error(errors, f"{prefix}.required_stage_slots must be exactly ['S6']")
            if set(optional_values) - {"S5"}:
                add_error(errors, f"{prefix}.optional_stage_slots may only contain S5")
        elif intent == "validate":
            if required_values != ["S5"]:
                add_error(errors, f"{prefix}.required_stage_slots must be exactly ['S5']")
            if set(optional_values) - {"S6"}:
                add_error(errors, f"{prefix}.optional_stage_slots may only contain S6")


def validate_constraints(constraints: Dict[str, Any], errors: List[str], warnings: List[str]) -> None:
    """校验未来可能沉淀为 constraints.md 的规则候选。"""

    always = constraints.get("always")
    never = constraints.get("never")
    if not isinstance(always, list):
        add_error(errors, "constraints.always must be a list")
    elif not always:
        add_warn(warnings, "constraints.always is empty")
    if not isinstance(never, list):
        add_error(errors, "constraints.never must be a list")
    elif not never:
        add_warn(warnings, "constraints.never is empty")


def validate_resource_limits(resource_limits: Dict[str, Any], errors: List[str], warnings: List[str]) -> None:
    """校验 workflow spec 携带的执行预算限制。"""

    for field in ("max_parallel_agents", "max_retries_per_stage", "max_validation_loops"):
        value = resource_limits.get(field)
        if value is None:
            add_error(errors, f"resource_limits.{field} is required")
            continue
        if not isinstance(value, int) or value <= 0:
            add_error(errors, f"resource_limits.{field} must be a positive integer")

    max_parallel = resource_limits.get("max_parallel_agents")
    if isinstance(max_parallel, int) and max_parallel > 4:
        add_warn(warnings, "resource_limits.max_parallel_agents > 4 may violate constraints.md")


def validate_runtime_contract(runtime_contract: Dict[str, Any], errors: List[str], warnings: List[str]) -> None:
    """校验 runner 消费的运行时硬契约。"""

    missing = sorted(REQUIRED_RUNTIME_CONTRACT_KEYS - set(runtime_contract.keys()))
    for key in missing:
        add_error(errors, f"runtime_contract.{key} is required")

    write_boundaries = runtime_contract.get("write_boundaries")
    if not isinstance(write_boundaries, dict):
        add_error(errors, "runtime_contract.write_boundaries must be a mapping")
    else:
        for key in ("target_root_allow", "run_root_allow", "temp_root_allow", "deny"):
            value = write_boundaries.get(key)
            if not isinstance(value, list):
                add_error(errors, f"runtime_contract.write_boundaries.{key} must be a list")
                continue
            if not value:
                add_warn(warnings, f"runtime_contract.write_boundaries.{key} is empty")
            for idx, item in enumerate(value):
                if not str(item).strip():
                    add_error(errors, f"runtime_contract.write_boundaries.{key}[{idx}] must not be empty")

    required_evidence = runtime_contract.get("required_evidence")
    if not isinstance(required_evidence, list):
        add_error(errors, "runtime_contract.required_evidence must be a list")
    else:
        if not required_evidence:
            add_error(errors, "runtime_contract.required_evidence must not be empty")
        for idx, item in enumerate(required_evidence):
            text = str(item).strip()
            if not text:
                add_error(errors, f"runtime_contract.required_evidence[{idx}] must not be empty")
            elif text.startswith("/"):
                add_error(errors, f"runtime_contract.required_evidence[{idx}] must be relative path")

    failure_kinds = runtime_contract.get("failure_kinds")
    if not isinstance(failure_kinds, list):
        add_error(errors, "runtime_contract.failure_kinds must be a list")
    else:
        values = {str(item).strip() for item in failure_kinds if str(item).strip()}
        missing_kinds = sorted(REQUIRED_FAILURE_KINDS - values)
        if missing_kinds:
            add_error(errors, f"runtime_contract.failure_kinds missing required values: {', '.join(missing_kinds)}")

    env_skip = runtime_contract.get("environment_skip")
    if not isinstance(env_skip, list):
        add_error(errors, "runtime_contract.environment_skip must be a list")
    else:
        if not env_skip:
            add_warn(warnings, "runtime_contract.environment_skip is empty")
        seen_codes: Set[str] = set()
        for idx, item in enumerate(env_skip):
            prefix = f"runtime_contract.environment_skip[{idx}]"
            if not isinstance(item, dict):
                add_error(errors, f"{prefix} must be a mapping")
                continue
            code = str(item.get("code", "")).strip()
            check = str(item.get("check", "")).strip()
            message = str(item.get("message", "")).strip()
            if not code:
                add_error(errors, f"{prefix}.code is required")
            elif code in seen_codes:
                add_error(errors, f"{prefix}.code duplicated: {code}")
            else:
                seen_codes.add(code)
            if not check:
                add_error(errors, f"{prefix}.check is required")
            elif check in DEPRECATED_ENV_SKIP_CHECKS:
                add_error(errors, f"{prefix}.check '{check}' is deprecated; use runtime_host_* checks instead")
            elif check not in VALID_ENV_SKIP_CHECKS:
                add_error(errors, f"{prefix}.check must be one of {sorted(VALID_ENV_SKIP_CHECKS)}")
            if not message:
                add_error(errors, f"{prefix}.message is required")


def resolve_runtime_ref(
    ref: Any,
    field: str,
    runtime_contract: Dict[str, Any],
    errors: List[str],
) -> str:
    """校验 `runtime_contract.<field>` 引用语法及目标字段是否存在。"""

    text = str(ref).strip()
    if not text:
        add_error(errors, f"{field} is required")
        return ""
    match = RUNTIME_REF_PATTERN.match(text)
    if not match:
        add_error(errors, f"{field} must use ref syntax runtime_contract.<field>")
        return ""
    target = match.group(1)
    if target not in runtime_contract:
        add_error(errors, f"{field} references missing runtime_contract field: {target}")
        return ""
    return target


def validate_test_contract(
    test_contract: Dict[str, Any],
    runtime_contract: Dict[str, Any],
    stage_ids: Set[str],
    slot_map: Dict[str, str],
    intent_flows: Dict[str, Any],
    registered_entries: Set[str],
    errors: List[str],
    warnings: List[str],
) -> None:
    """校验 workflow 的 S5 judgment contract。

    这里最关键的规则是：test_contract 可以引用 runtime_contract，
    但不能复制或削弱 runtime 的执行语义。
    """

    required_sections = {"entry", "boundary", "flow", "artifacts", "failure"}
    missing = sorted(required_sections - set(test_contract.keys()))
    for key in missing:
        add_error(errors, f"test_contract.{key} is required")

    # entry 检查定义了工作流应如何被调用。
    entry = require_mapping(test_contract.get("entry", {}), "test_contract.entry", errors)
    main_entry = str(entry.get("main_entry", "")).strip()
    if not main_entry:
        add_error(errors, "test_contract.entry.main_entry is required")
    elif main_entry not in registered_entries:
        add_error(errors, f"test_contract.entry.main_entry '{main_entry}' not found in registry.commands or registry.skills")
    entry_type = str(entry.get("entry_type", "")).strip()
    if entry_type not in VALID_ENTRY_TYPES:
        add_error(errors, f"test_contract.entry.entry_type must be one of {sorted(VALID_ENTRY_TYPES)}")
    required_args = entry.get("required_args")
    if not isinstance(required_args, list):
        add_error(errors, "test_contract.entry.required_args must be a list")
    else:
        for idx, item in enumerate(required_args):
            if not str(item).strip():
                add_error(errors, f"test_contract.entry.required_args[{idx}] must not be empty")
    for key in ("missing_arg_verdict", "invalid_entry_verdict"):
        verdict = str(entry.get(key, "")).strip()
        if verdict not in VALID_VERDICT:
            add_error(errors, f"test_contract.entry.{key} must be one of {sorted(VALID_VERDICT)}")

    # boundary 检查必须回指 runtime_contract，
    # 不能把同一份写入边界语义复制成第二份真源。
    boundary = require_mapping(test_contract.get("boundary", {}), "test_contract.boundary", errors)
    if "write_boundaries" in boundary:
        add_error(errors, "test_contract.boundary must not duplicate runtime_contract.write_boundaries")
    resolve_runtime_ref(boundary.get("write_boundaries_ref"), "test_contract.boundary.write_boundaries_ref", runtime_contract, errors)
    for key in ("managed_overwrite_policy", "conflict_expectation", "external_write_policy"):
        value = str(boundary.get(key, "")).strip()
        if not value:
            add_error(errors, f"test_contract.boundary.{key} is required")

    # flow 检查默认锚定到 develop intent flow。
    flow = require_mapping(test_contract.get("flow", {}), "test_contract.flow", errors)
    required_stages = flow.get("required_stages")
    if not isinstance(required_stages, list) or not required_stages:
        add_error(errors, "test_contract.flow.required_stages must be a non-empty list")
    else:
        for idx, item in enumerate(required_stages):
            stage_id = str(item).strip()
            if not stage_id:
                add_error(errors, f"test_contract.flow.required_stages[{idx}] must not be empty")
            elif stage_id not in stage_ids:
                add_error(errors, f"test_contract.flow.required_stages[{idx}] references unknown stage: {stage_id}")
    skippable_stages = flow.get("skippable_stages")
    if not isinstance(skippable_stages, list):
        add_error(errors, "test_contract.flow.skippable_stages must be a list")
    else:
        for idx, item in enumerate(skippable_stages):
            stage_id = str(item).strip()
            if not stage_id:
                add_error(errors, f"test_contract.flow.skippable_stages[{idx}] must not be empty")
            elif stage_id not in stage_ids:
                add_error(errors, f"test_contract.flow.skippable_stages[{idx}] references unknown stage: {stage_id}")
    develop_flow = intent_flows.get("develop", {}) if isinstance(intent_flows, dict) else {}
    if isinstance(develop_flow, dict):
        required_slots = develop_flow.get("required_stage_slots", [])
        optional_slots = develop_flow.get("optional_stage_slots", [])
        if isinstance(required_slots, list):
            expected_required = [slot_map[slot] for slot in required_slots if slot in slot_map]
            observed_required = [str(item).strip() for item in required_stages] if isinstance(required_stages, list) else []
            if observed_required and observed_required != expected_required:
                add_error(
                    errors,
                    f"test_contract.flow.required_stages must match develop intent_flows mapping: expected {expected_required}, got {observed_required}",
                )
        if isinstance(optional_slots, list):
            expected_optional = [slot_map[slot] for slot in optional_slots if slot in slot_map]
            observed_optional = [str(item).strip() for item in skippable_stages] if isinstance(skippable_stages, list) else []
            if observed_optional != expected_optional:
                add_error(
                    errors,
                    f"test_contract.flow.skippable_stages must match develop intent_flows mapping: expected {expected_optional}, got {observed_optional}",
                )
    failure_recovery = flow.get("failure_recovery")
    if not isinstance(failure_recovery, dict):
        add_error(errors, "test_contract.flow.failure_recovery must be a mapping")
    else:
        declared_failure_kinds = runtime_contract.get("failure_kinds", [])
        if not isinstance(declared_failure_kinds, list):
            declared_failure_kinds = []
        declared_failure_set = {str(item).strip() for item in declared_failure_kinds if str(item).strip()}
        for failure_kind, stage_id in failure_recovery.items():
            failure_name = str(failure_kind).strip()
            target_stage = str(stage_id).strip()
            if not failure_name:
                add_error(errors, "test_contract.flow.failure_recovery contains empty failure kind")
                continue
            if failure_name not in declared_failure_set:
                add_error(errors, f"test_contract.flow.failure_recovery.{failure_name} must be declared in runtime_contract.failure_kinds")
            if not target_stage:
                add_error(errors, f"test_contract.flow.failure_recovery.{failure_name} must not be empty")
                continue
            if target_stage not in stage_ids:
                add_error(errors, f"test_contract.flow.failure_recovery.{failure_name} references unknown stage: {target_stage}")
    terminal_conditions = flow.get("terminal_conditions")
    if not isinstance(terminal_conditions, dict):
        add_error(errors, "test_contract.flow.terminal_conditions must be a mapping")
    else:
        for verdict in VALID_VERDICT:
            if verdict not in terminal_conditions:
                add_error(errors, f"test_contract.flow.terminal_conditions.{verdict} is required")
                continue
            stage_status = str(terminal_conditions.get(verdict, "")).strip()
            if stage_status not in VALID_STAGE_STATUS:
                add_error(errors, f"test_contract.flow.terminal_conditions.{verdict} must be one of {sorted(VALID_STAGE_STATUS)}")

    # artifact 检查定义了 S5 在执行后期望检查的对象。
    artifacts = require_mapping(test_contract.get("artifacts", {}), "test_contract.artifacts", errors)
    if "required_evidence" in artifacts:
        add_error(errors, "test_contract.artifacts must not duplicate runtime_contract.required_evidence")
    deliverables = artifacts.get("deliverables")
    if not isinstance(deliverables, list) or not deliverables:
        add_error(errors, "test_contract.artifacts.deliverables must be a non-empty list")
    else:
        deliverable_values = [str(item).strip() for item in deliverables if str(item).strip()]
        for idx, item in enumerate(deliverables):
            if not str(item).strip():
                add_error(errors, f"test_contract.artifacts.deliverables[{idx}] must not be empty")
        develop_flow = intent_flows.get("develop", {}) if isinstance(intent_flows, dict) else {}
        required_slots = develop_flow.get("required_stage_slots", []) if isinstance(develop_flow, dict) else []
        if isinstance(required_slots, list) and "S4" in [str(item).strip() for item in required_slots]:
            if ".workflowprogram/managed-files.json" not in deliverable_values:
                add_error(
                    errors,
                    "test_contract.artifacts.deliverables must include .workflowprogram/managed-files.json for develop flows with S4",
                )
    resolve_runtime_ref(artifacts.get("evidence_ref"), "test_contract.artifacts.evidence_ref", runtime_contract, errors)
    optional_outputs = artifacts.get("optional_outputs")
    if optional_outputs is None:
        add_warn(warnings, "test_contract.artifacts.optional_outputs is missing; prefer explicit declaration")
    elif not isinstance(optional_outputs, list):
        add_error(errors, "test_contract.artifacts.optional_outputs must be a list")
    else:
        for idx, item in enumerate(optional_outputs):
            if not str(item).strip():
                add_error(errors, f"test_contract.artifacts.optional_outputs[{idx}] must not be empty")

    # failure 检查描述的是当前覆盖范围，而不是另一套运行时语义。
    failure = require_mapping(test_contract.get("failure", {}), "test_contract.failure", errors)
    for duplicated in ("failure_kinds", "environment_skip"):
        if duplicated in failure:
            add_error(errors, f"test_contract.failure must not duplicate runtime_contract.{duplicated}")
    failure_target = resolve_runtime_ref(
        failure.get("failure_kinds_ref"),
        "test_contract.failure.failure_kinds_ref",
        runtime_contract,
        errors,
    )
    env_target = resolve_runtime_ref(
        failure.get("environment_skip_ref"),
        "test_contract.failure.environment_skip_ref",
        runtime_contract,
        errors,
    )
    implemented_now = failure.get("implemented_now")
    if not isinstance(implemented_now, list) or not implemented_now:
        add_error(errors, "test_contract.failure.implemented_now must be a non-empty list")
    else:
        declared_failure_kinds = runtime_contract.get(failure_target, []) if failure_target else []
        if not isinstance(declared_failure_kinds, list):
            declared_failure_kinds = []
        declared_values = {str(item).strip() for item in declared_failure_kinds if str(item).strip()}
        for idx, item in enumerate(implemented_now):
            value = str(item).strip()
            if not value:
                add_error(errors, f"test_contract.failure.implemented_now[{idx}] must not be empty")
                continue
            if value not in declared_values:
                add_error(
                    errors,
                    f"test_contract.failure.implemented_now[{idx}]='{value}' must be a subset of runtime_contract.failure_kinds",
                )
    if env_target != "environment_skip":
        add_error(errors, "test_contract.failure.environment_skip_ref must reference runtime_contract.environment_skip")


def parse_stage_outputs(output: Any) -> List[str]:
    """把阶段 output 声明归一化为路径列表。"""

    if output is None:
        return []
    if isinstance(output, list):
        return [str(item).strip() for item in output if str(item).strip()]
    text = str(output).strip()
    if not text:
        return []
    if "\n" in text:
        return [line.strip() for line in text.splitlines() if line.strip()]
    return [text]


def validate_capability_discovery(
    capability_discovery: Dict[str, Any],
    errors: List[str],
    warnings: List[str],
) -> Dict[str, Any]:
    """校验可选的能力搜索与推荐契约。"""

    if not capability_discovery:
        return {}
    if "enabled" not in capability_discovery:
        add_error(errors, "capability_discovery.enabled is required when capability_discovery is declared")
        return capability_discovery
    enabled = capability_discovery.get("enabled")
    if not isinstance(enabled, bool):
        add_error(errors, "capability_discovery.enabled must be boolean")
        return capability_discovery
    if not enabled:
        return capability_discovery

    domains = capability_discovery.get("domains", [])
    if domains is not None and not isinstance(domains, list):
        add_error(errors, "capability_discovery.domains must be a list when provided")
        domains = []
    normalized_domains = [str(item).strip() for item in domains if str(item).strip()] if isinstance(domains, list) else []
    infer_from_request = capability_discovery.get("infer_from_request", True)
    include_local = capability_discovery.get("include_local_installed", True)
    include_curated = capability_discovery.get("include_curated_profiles", True)
    for field_name, field_value in (
        ("infer_from_request", infer_from_request),
        ("include_local_installed", include_local),
        ("include_curated_profiles", include_curated),
    ):
        if field_name in capability_discovery and not isinstance(field_value, bool):
            add_error(errors, f"capability_discovery.{field_name} must be boolean when provided")

    profile_overrides = capability_discovery.get("profile_overrides", {})
    if profile_overrides not in ({}, None) and not isinstance(profile_overrides, dict):
        add_error(errors, "capability_discovery.profile_overrides must be an object when provided")
        profile_overrides = {}
    if isinstance(profile_overrides, dict) and profile_overrides:
        exclude_capability_ids = profile_overrides.get("exclude_capability_ids", [])
        if exclude_capability_ids is not None and not isinstance(exclude_capability_ids, list):
            add_error(errors, "capability_discovery.profile_overrides.exclude_capability_ids must be a list when provided")
        elif isinstance(exclude_capability_ids, list):
            for idx, capability_id in enumerate(exclude_capability_ids):
                text = str(capability_id).strip()
                if not text:
                    add_error(errors, f"capability_discovery.profile_overrides.exclude_capability_ids[{idx}] must not be empty")
                elif not re.match(r"^[a-z0-9_]+$", text):
                    add_error(errors, f"capability_discovery.profile_overrides.exclude_capability_ids[{idx}] must use lowercase slug format")

        disable_team_default = profile_overrides.get("disable_team_default")
        if disable_team_default is not None and not isinstance(disable_team_default, bool):
            add_error(errors, "capability_discovery.profile_overrides.disable_team_default must be boolean when provided")

        replace_capabilities = profile_overrides.get("replace_capabilities", [])
        if replace_capabilities is not None and not isinstance(replace_capabilities, list):
            add_error(errors, "capability_discovery.profile_overrides.replace_capabilities must be a list when provided")
        elif isinstance(replace_capabilities, list):
            for idx, raw in enumerate(replace_capabilities):
                prefix = f"capability_discovery.profile_overrides.replace_capabilities[{idx}]"
                replacement = require_mapping(raw, prefix, errors)
                for field in ("replaces", "id", "kind", "name", "probe"):
                    if field not in replacement:
                        add_error(errors, f"{prefix}.{field} is required")
                replaces_id = str(replacement.get("replaces", "")).strip()
                replacement_id = str(replacement.get("id", "")).strip()
                if not replaces_id:
                    add_error(errors, f"{prefix}.replaces must not be empty")
                elif not re.match(r"^[a-z0-9_]+$", replaces_id):
                    add_error(errors, f"{prefix}.replaces must use lowercase slug format")
                if not replacement_id:
                    add_error(errors, f"{prefix}.id must not be empty")
                elif not re.match(r"^[a-z0-9_]+$", replacement_id):
                    add_error(errors, f"{prefix}.id must use lowercase slug format")
                kind = str(replacement.get("kind", "")).strip()
                if kind and kind not in VALID_HOST_CAPABILITY_KINDS:
                    add_error(errors, f"{prefix}.kind must be one of {sorted(VALID_HOST_CAPABILITY_KINDS)}")
                if not str(replacement.get("name", "")).strip():
                    add_error(errors, f"{prefix}.name must not be empty")
                probe = replacement.get("probe", {})
                if not isinstance(probe, dict):
                    add_error(errors, f"{prefix}.probe must be an object")
                elif kind == "external_binary" and not str(probe.get("binary", "")).strip():
                    add_error(errors, f"{prefix}.probe.binary is required for external_binary")
                elif kind == "mcp_server" and not str(probe.get("server_name", "")).strip():
                    add_error(errors, f"{prefix}.probe.server_name is required for mcp_server")
                elif kind in {"codex_skill", "claude_skill"} and not str(probe.get("skill_name", "")).strip():
                    add_error(errors, f"{prefix}.probe.skill_name is required for {kind}")

    if not normalized_domains and infer_from_request is not True:
        add_error(errors, "capability_discovery requires domains or infer_from_request=true")
    for idx, domain in enumerate(normalized_domains):
        if not re.match(r"^[a-z0-9_]+$", domain):
            add_error(errors, f"capability_discovery.domains[{idx}] must use lowercase slug format")
        elif domain not in KNOWN_CAPABILITY_DISCOVERY_DOMAINS:
            add_warn(
                warnings,
                f"capability_discovery.domains[{idx}] uses unknown curated profile '{domain}'; discovery may rely only on request inference or future profiles",
            )
    return capability_discovery


def validate_design_refs(
    design_refs: Dict[str, Any],
    workflow_graph: Dict[str, Any],
    errors: List[str],
    warnings: List[str],
) -> None:
    """校验目标工作流设计源引用、迁移兼容和复杂节点设计约束。"""

    if not design_refs:
        return

    extra = sorted(set(design_refs.keys()) - ALLOWED_DESIGN_REF_FIELDS)
    if extra:
        add_warn(warnings, f"design_refs has unknown keys: {', '.join(extra)}")

    resolved = resolve_target_design_refs(design_refs)
    errors.extend(resolved.errors)
    warnings.extend(resolved.warnings)
    if resolved.canonical:
        if resolved.schema_version != 2:
            add_error(errors, "design_refs.schema_version must be 2 when naming=target_design_v1")
        if resolved.naming != "target_design_v1":
            add_error(errors, "design_refs.naming must be target_design_v1 when schema_version=2")
        for key in REQUIRED_RUN_REF_KEYS:
            value = resolved.run_refs.get(key, "")
            if not value:
                add_error(errors, f"design_refs.{key} is required when schema_version=2")
            elif value != CANONICAL_RUN_DEFAULTS[key]:
                add_error(errors, f"design_refs.{key} must use canonical target path {CANONICAL_RUN_DEFAULTS[key]}")
        if not resolved.persistent_refs:
            add_warn(warnings, "design_refs.persistent is recommended for completed target workflows")

    node_design_policy = design_refs.get("node_design_policy", {})
    if node_design_policy is not None and not isinstance(node_design_policy, dict):
        add_error(errors, "design_refs.node_design_policy must be a mapping/object")
    elif isinstance(node_design_policy, dict):
        if "required_for_complex_nodes" in node_design_policy and not isinstance(node_design_policy.get("required_for_complex_nodes"), bool):
            add_error(errors, "design_refs.node_design_policy.required_for_complex_nodes must be boolean")
        exemption_field = str(node_design_policy.get("exemption_field", "")).strip()
        if exemption_field and exemption_field != "node_design_exemption":
            add_error(errors, "design_refs.node_design_policy.exemption_field must be node_design_exemption")

    nodes = workflow_graph.get("nodes", []) if isinstance(workflow_graph, dict) else []
    graph_node_ids: Set[str] = set()
    if isinstance(nodes, list):
        graph_node_ids = {
            str(node.get("id", "")).strip()
            for node in nodes
            if isinstance(node, dict) and str(node.get("id", "")).strip()
        }

    for node_text in sorted(resolved.node_designs):
        if graph_node_ids and node_text not in graph_node_ids:
            add_error(errors, f"design_refs.node_designs references unknown workflow_graph node: {node_text}")
        elif not graph_node_ids:
            add_warn(warnings, "design_refs.node_designs declared without workflow_graph.nodes; node references cannot be fully checked")

    if not isinstance(nodes, list):
        return
    for idx, raw_node in enumerate(nodes):
        if not isinstance(raw_node, dict):
            continue
        node_id = str(raw_node.get("id", "")).strip()
        if not node_id:
            continue
        loop_policy = raw_node.get("loop_policy", {})
        loop_enabled = isinstance(loop_policy, dict) and loop_policy.get("enabled") is True
        requires_design = (
            raw_node.get("node_design_required") is True
            or str(raw_node.get("complexity", "")).strip() == "complex"
            or str(raw_node.get("design_intensity", "")).strip() == "detailed"
            or loop_enabled
        )
        if not requires_design:
            continue
        if node_id in resolved.node_designs:
            continue
        exemption = raw_node.get("node_design_exemption")
        if isinstance(exemption, dict) and str(exemption.get("reason", "")).strip() and str(exemption.get("accepted_by", "")).strip() in VALID_NODE_DESIGN_EXEMPTION_ACCEPTED_BY:
            continue
        add_error(
            errors,
            f"workflow_graph.nodes[{idx}] requires design_refs.node_designs.{node_id} or valid node_design_exemption",
        )


def validate_generated_runtime_contract(
    generated_runtime_contract: Dict[str, Any],
    stages: List[Any],
    intent_flows: Dict[str, Any],
    test_contract: Dict[str, Any],
    workflow_graph: Dict[str, Any],
    capability_discovery: Dict[str, Any],
    host_capabilities: List[Dict[str, Any]],
    agent_team_contract: Dict[str, Any],
    errors: List[str],
    warnings: List[str],
) -> None:
    """校验目标侧 deterministic runtime 合同。"""

    missing = sorted(REQUIRED_GENERATED_RUNTIME_KEYS - set(generated_runtime_contract.keys()))
    for key in missing:
        add_error(errors, f"generated_runtime_contract.{key} is required")

    normalized: Dict[str, str] = {}
    for key in REQUIRED_GENERATED_RUNTIME_KEYS:
        if key == "runtime_capabilities":
            continue
        value = str(generated_runtime_contract.get(key, "")).strip()
        if not value:
            add_error(errors, f"generated_runtime_contract.{key} must not be empty")
            continue
        normalized[key] = value
        if key != "mode" and not value.startswith(".workflowprogram/"):
            add_error(errors, f"generated_runtime_contract.{key} must stay under .workflowprogram/: {value}")

    mode = normalized.get("mode", "")
    if mode and mode != "shared-control-plane-wrapper":
        add_warn(warnings, f"generated_runtime_contract.mode is uncommon: {mode}")
    runtime_capabilities = runtime_capabilities_from_contract(generated_runtime_contract)
    if not runtime_capabilities:
        add_error(errors, "generated_runtime_contract.runtime_capabilities must be a non-empty list")
    else:
        for idx, capability in enumerate(runtime_capabilities):
            if capability not in VALID_RUNTIME_CAPABILITIES:
                add_error(
                    errors,
                    f"generated_runtime_contract.runtime_capabilities[{idx}] must be one of {sorted(VALID_RUNTIME_CAPABILITIES)}",
                )
        if "state_transitions" not in runtime_capabilities:
            add_error(errors, "generated_runtime_contract.runtime_capabilities must include state_transitions")
        if "run_state_validation" not in runtime_capabilities:
            add_error(errors, "generated_runtime_contract.runtime_capabilities must include run_state_validation")
        if capability_discovery.get("enabled") is True and "capability_discovery" not in runtime_capabilities:
            add_error(
                errors,
                "generated_runtime_contract.runtime_capabilities must include capability_discovery when capability_discovery.enabled=true",
            )
        if host_capabilities and "host_capability_probe" not in runtime_capabilities:
            add_error(
                errors,
                "generated_runtime_contract.runtime_capabilities must include host_capability_probe when host_capabilities is declared",
            )
        if agent_team_enabled(agent_team_contract) and "team_orchestration" not in runtime_capabilities:
            add_error(
                errors,
                "generated_runtime_contract.runtime_capabilities must include team_orchestration when agent_team_contract.enabled=true",
            )
        if workflow_graph_loop_nodes(workflow_graph) and "node_loop_execution" not in runtime_capabilities:
            add_error(
                errors,
                "generated_runtime_contract.runtime_capabilities must include node_loop_execution when workflow_graph node loop_policy.enabled=true",
            )

    develop_flow = intent_flows.get("develop", {}) if isinstance(intent_flows, dict) else {}
    required_slots = develop_flow.get("required_stage_slots", []) if isinstance(develop_flow, dict) else []
    requires_s4 = isinstance(required_slots, list) and "S4" in [str(item).strip() for item in required_slots]
    if not requires_s4:
        return

    stage_list = [item for item in stages if isinstance(item, dict)]
    generate_stage = next((stage for stage in stage_list if str(stage.get("stage_slot", "")).strip() == "S4"), None)
    if generate_stage is None:
        add_error(errors, "generated_runtime_contract requires an S4 stage to persist target runtime assets")
        return

    stage_outputs = set(parse_stage_outputs(generate_stage.get("output")))
    required_stage_outputs = {
        "outputs/candidate/.workflowprogram/runtime",
        normalized.get("entry_script", ""),
        normalized.get("runner_script", ""),
        normalized.get("state_validator_script", ""),
        normalized.get("runtime_manifest", ""),
    }
    for item in sorted(path for path in required_stage_outputs if path):
        if item not in stage_outputs:
            add_error(errors, f"S4 output must declare generated runtime artifact: {item}")

    artifacts = test_contract.get("artifacts", {}) if isinstance(test_contract, dict) else {}
    deliverables = artifacts.get("deliverables", []) if isinstance(artifacts, dict) else []
    deliverable_values = {str(item).strip() for item in deliverables if str(item).strip()} if isinstance(deliverables, list) else set()
    for item in (
        normalized.get("entry_script", ""),
        normalized.get("runner_script", ""),
        normalized.get("state_validator_script", ""),
        normalized.get("runtime_manifest", ""),
    ):
        if item and item not in deliverable_values:
            add_error(errors, f"test_contract.artifacts.deliverables must include generated runtime asset: {item}")


def validate_host_capabilities(
    host_capabilities: List[Any],
    errors: List[str],
    warnings: List[str],
) -> List[Dict[str, Any]]:
    """校验可选的宿主能力契约。"""

    normalized: List[Dict[str, Any]] = []
    seen_ids: Set[str] = set()
    for idx, raw in enumerate(host_capabilities):
        prefix = f"host_capabilities[{idx}]"
        capability = require_mapping(raw, prefix, errors)
        normalized.append(capability)
        for field in ("id", "kind", "name", "required", "probe", "approval_required"):
            if field not in capability:
                add_error(errors, f"{prefix}.{field} is required")

        capability_id = str(capability.get("id", "")).strip()
        kind = str(capability.get("kind", "")).strip()
        if not capability_id:
            add_error(errors, f"{prefix}.id must not be empty")
        elif capability_id in seen_ids:
            add_error(errors, f"Duplicate host capability id: {capability_id}")
        else:
            seen_ids.add(capability_id)

        if kind not in VALID_HOST_CAPABILITY_KINDS:
            add_error(errors, f"{prefix}.kind must be one of {sorted(VALID_HOST_CAPABILITY_KINDS)}")

        if not str(capability.get("name", "")).strip():
            add_error(errors, f"{prefix}.name must not be empty")
        if not isinstance(capability.get("required"), bool):
            add_error(errors, f"{prefix}.required must be boolean")
        if not isinstance(capability.get("approval_required"), bool):
            add_error(errors, f"{prefix}.approval_required must be boolean")

        probe = require_mapping(capability.get("probe", {}), f"{prefix}.probe", errors)
        if kind == "external_binary":
            if not str(probe.get("binary", "")).strip():
                add_error(errors, f"{prefix}.probe.binary is required for external_binary")
            args = probe.get("args")
            if args is not None and not isinstance(args, list):
                add_error(errors, f"{prefix}.probe.args must be a list when provided")
        elif kind == "mcp_server":
            if not str(probe.get("server_name", "")).strip():
                add_error(errors, f"{prefix}.probe.server_name is required for mcp_server")
        elif kind in {"codex_skill", "claude_skill"}:
            if not str(probe.get("skill_name", "")).strip():
                add_error(errors, f"{prefix}.probe.skill_name is required for {kind}")

        bootstrap = require_mapping(capability.get("bootstrap", {}), f"{prefix}.bootstrap", errors)
        scope = str(bootstrap.get("scope", "")).strip()
        if scope and scope not in VALID_BOOTSTRAP_SCOPES:
            add_error(errors, f"{prefix}.bootstrap.scope must be one of {sorted(VALID_BOOTSTRAP_SCOPES)}")
        if not scope:
            add_warn(warnings, f"{prefix}.bootstrap.scope is missing; bootstrap defaults to manual-only behavior")
        if scope == "host_global" and capability.get("approval_required") is not True:
            add_error(errors, f"{prefix}.approval_required must be true when bootstrap.scope=host_global")
        adapter = bootstrap.get("adapter", {})
        if adapter is not None and not isinstance(adapter, dict):
            add_error(errors, f"{prefix}.bootstrap.adapter must be an object when provided")
            adapter = {}
        adapter_type = str(adapter.get("type", "")).strip() if isinstance(adapter, dict) else ""
        if scope != "host_global" and adapter_type:
            add_error(errors, f"{prefix}.bootstrap.adapter is only allowed for bootstrap.scope=host_global")
        if scope == "host_global":
            if not adapter_type:
                add_warn(warnings, f"{prefix}.bootstrap.adapter is missing; host-global bootstrap remains plan-only")
            elif adapter_type not in VALID_HOST_GLOBAL_ADAPTER_TYPES:
                add_error(errors, f"{prefix}.bootstrap.adapter.type must be one of {sorted(VALID_HOST_GLOBAL_ADAPTER_TYPES)}")
            elif adapter_type == "symlink_binary":
                source_binary = str(adapter.get("source_binary", "")).strip()
                target_path = str(adapter.get("target_path", "")).strip()
                if not source_binary:
                    add_error(errors, f"{prefix}.bootstrap.adapter.source_binary is required for symlink_binary")
                if not target_path:
                    add_error(errors, f"{prefix}.bootstrap.adapter.target_path is required for symlink_binary")
                elif not target_path.startswith("/"):
                    add_error(errors, f"{prefix}.bootstrap.adapter.target_path must be an absolute path for symlink_binary")
            elif adapter_type in {"uv_tool", "pipx_install", "npm_global"}:
                package_name = str(adapter.get("package", "")).strip()
                if not package_name:
                    add_error(errors, f"{prefix}.bootstrap.adapter.package is required for {adapter_type}")
                extra_args = adapter.get("extra_args")
                if extra_args is not None and not isinstance(extra_args, list):
                    add_error(errors, f"{prefix}.bootstrap.adapter.extra_args must be a list when provided")

        project_outputs = bootstrap.get("project_local_outputs", [])
        if project_outputs is not None and not isinstance(project_outputs, list):
            add_error(errors, f"{prefix}.bootstrap.project_local_outputs must be a list when provided")
            project_outputs = []
        if scope != "project_local" and string_list(project_outputs):
            add_error(errors, f"{prefix}.bootstrap.project_local_outputs is only allowed for bootstrap.scope=project_local")
        normalized_outputs = string_list(project_outputs)
        for output_idx, item in enumerate(string_list(project_outputs)):
            rel_path = ensure_relative_bootstrap_output(item)
            if rel_path.startswith("/") or rel_path.startswith(".."):
                add_error(errors, f"{prefix}.bootstrap.project_local_outputs[{output_idx}] must be a safe relative path")
                continue
            if not rel_path.startswith(".workflowprogram/bootstrap/"):
                add_error(
                    errors,
                    f"{prefix}.bootstrap.project_local_outputs[{output_idx}] must stay under .workflowprogram/bootstrap/: {rel_path}",
                )
        assets = bootstrap.get("assets", [])
        if assets is not None and not isinstance(assets, list):
            add_error(errors, f"{prefix}.bootstrap.assets must be a list when provided")
            assets = []
        if scope != "project_local" and isinstance(assets, list) and assets:
            add_error(errors, f"{prefix}.bootstrap.assets is only allowed for bootstrap.scope=project_local")
        seen_asset_paths: Set[str] = set()
        for asset_idx, raw_asset in enumerate(assets if isinstance(assets, list) else []):
            asset_prefix = f"{prefix}.bootstrap.assets[{asset_idx}]"
            asset = require_mapping(raw_asset, asset_prefix, errors)
            asset_path = ensure_relative_bootstrap_output(str(asset.get("path", "")).strip())
            asset_format = str(asset.get("format", "")).strip()
            if not asset_path:
                add_error(errors, f"{asset_prefix}.path is required")
            elif asset_path.startswith("/") or asset_path.startswith(".."):
                add_error(errors, f"{asset_prefix}.path must be a safe relative path")
            elif not asset_path.startswith(".workflowprogram/bootstrap/"):
                add_error(errors, f"{asset_prefix}.path must stay under .workflowprogram/bootstrap/: {asset_path}")
            elif asset_path in seen_asset_paths:
                add_error(errors, f"Duplicate project-local bootstrap asset path: {asset_path}")
            else:
                seen_asset_paths.add(asset_path)

            if asset_format not in VALID_BOOTSTRAP_ASSET_FORMATS:
                add_error(errors, f"{asset_prefix}.format must be one of {sorted(VALID_BOOTSTRAP_ASSET_FORMATS)}")
            if "content" not in asset:
                add_error(errors, f"{asset_prefix}.content is required")
            elif asset_format == "json":
                if asset.get("content") is None:
                    add_error(errors, f"{asset_prefix}.content must not be null for json assets")
            elif not isinstance(asset.get("content"), str):
                add_error(errors, f"{asset_prefix}.content must be a string for {asset_format or 'non-json'} assets")

            executable = asset.get("executable")
            if executable is not None and not isinstance(executable, bool):
                add_error(errors, f"{asset_prefix}.executable must be boolean when provided")
            if executable is True and asset_format != "shell":
                add_error(errors, f"{asset_prefix}.executable=true is only allowed when format=shell")

        if scope == "project_local" and not normalized_outputs and not seen_asset_paths:
            add_error(errors, f"{prefix}.bootstrap must declare project_local_outputs or bootstrap.assets when scope=project_local")
    return normalized


def validate_agent_team_contract(
    agent_team_contract: Dict[str, Any],
    errors: List[str],
    warnings: List[str],
) -> None:
    """校验可选的 agent team orchestration 契约。"""

    if not agent_team_contract:
        return
    enabled = agent_team_enabled(agent_team_contract)
    if "enabled" not in agent_team_contract:
        add_error(errors, "agent_team_contract.enabled is required when agent_team_contract is declared")
        return
    if not isinstance(agent_team_contract.get("enabled"), bool):
        add_error(errors, "agent_team_contract.enabled must be boolean")
        return
    if not enabled:
        return

    for field in ("max_fan_out", "join_policy", "roles", "execution"):
        if field not in agent_team_contract:
            add_error(errors, f"agent_team_contract.{field} is required when enabled=true")

    max_fan_out = agent_team_contract.get("max_fan_out")
    if not isinstance(max_fan_out, int) or max_fan_out <= 0:
        add_error(errors, "agent_team_contract.max_fan_out must be a positive integer")
        max_fan_out = 0
    elif max_fan_out > 4:
        add_error(errors, "agent_team_contract.max_fan_out must be <= 4")

    join_policy = str(agent_team_contract.get("join_policy", "")).strip()
    if join_policy not in VALID_TEAM_JOIN_POLICIES:
        add_error(errors, f"agent_team_contract.join_policy must be one of {sorted(VALID_TEAM_JOIN_POLICIES)}")

    roles = agent_team_contract.get("roles", [])
    if not isinstance(roles, list) or not roles:
        add_error(errors, "agent_team_contract.roles must be a non-empty list when enabled=true")
        roles = []
    role_ids: Set[str] = set()
    ownership_map: Dict[str, Set[str]] = {}
    for idx, raw_role in enumerate(roles):
        prefix = f"agent_team_contract.roles[{idx}]"
        role = require_mapping(raw_role, prefix, errors)
        role_id = str(role.get("id", "")).strip()
        if not role_id:
            add_error(errors, f"{prefix}.id is required")
        elif role_id in role_ids:
            add_error(errors, f"Duplicate agent team role id: {role_id}")
        else:
            role_ids.add(role_id)
        if not str(role.get("responsibility", "")).strip():
            add_error(errors, f"{prefix}.responsibility is required")
        if not isinstance(role.get("required"), bool):
            add_error(errors, f"{prefix}.required must be boolean")
        output_patterns = role.get("output_patterns")
        if not isinstance(output_patterns, list) or not output_patterns:
            add_error(errors, f"{prefix}.output_patterns must be a non-empty list")
        ownership = role.get("ownership_stage_slots")
        if not isinstance(ownership, list) or not ownership:
            add_error(errors, f"{prefix}.ownership_stage_slots must be a non-empty list")
            ownership_values: List[str] = []
        else:
            ownership_values = [str(item).strip() for item in ownership if str(item).strip()]
            for slot_idx, slot in enumerate(ownership_values):
                if slot not in VALID_STAGE_SLOTS:
                    add_error(errors, f"{prefix}.ownership_stage_slots[{slot_idx}] must be one of {REQUIRED_STAGE_SLOT_ORDER}")
        if role_id:
            ownership_map[role_id] = set(ownership_values)

    execution = agent_team_contract.get("execution", [])
    if not isinstance(execution, list) or not execution:
        add_error(errors, "agent_team_contract.execution must be a non-empty list when enabled=true")
        execution = []
    for idx, raw_exec in enumerate(execution):
        prefix = f"agent_team_contract.execution[{idx}]"
        item = require_mapping(raw_exec, prefix, errors)
        stage_slot = str(item.get("stage_slot", "")).strip()
        if stage_slot not in VALID_STAGE_SLOTS:
            add_error(errors, f"{prefix}.stage_slot must be one of {REQUIRED_STAGE_SLOT_ORDER}")
        role_list = item.get("role_ids")
        if not isinstance(role_list, list) or not role_list:
            add_error(errors, f"{prefix}.role_ids must be a non-empty list")
            role_values: List[str] = []
        else:
            role_values = [str(role).strip() for role in role_list if str(role).strip()]
            if max_fan_out and len(role_values) > max_fan_out:
                add_error(errors, f"{prefix}.role_ids exceeds max_fan_out={max_fan_out}")
        join_role = str(item.get("join_role", "")).strip()
        if not join_role:
            add_error(errors, f"{prefix}.join_role is required")
        elif join_role not in role_ids:
            add_error(errors, f"{prefix}.join_role references unknown role: {join_role}")
        for role_id in role_values:
            if role_id not in role_ids:
                add_error(errors, f"{prefix}.role_ids references unknown role: {role_id}")
                continue
            if stage_slot and stage_slot not in ownership_map.get(role_id, set()):
                add_error(errors, f"{prefix}.role_ids includes role '{role_id}' that does not own stage_slot {stage_slot}")
    if not execution:
        add_warn(warnings, "agent_team_contract.enabled=true without execution rules leaves team orchestration inert")


def validate_spec(spec: Dict[str, Any]) -> Dict[str, Any]:
    """运行完整 workflow-spec 校验器，并返回结构化报告。"""

    collector = DiagnosticCollector()
    errors = collector.errors
    warnings = collector.warnings

    validate_top_level(spec, errors, warnings)
    meta = require_mapping(spec.get("meta", {}), "meta", errors)
    validate_meta(meta, errors)

    agent_refs_list = require_list(spec.get("agent_refs", []), "agent_refs", errors)
    agent_refs = validate_agent_refs(agent_refs_list, errors)

    stages = require_list(spec.get("stages", []), "stages", errors)
    stage_ids = validate_stages(stages, agent_refs, errors, warnings)
    slot_map = stage_slot_id_map(stages)

    intent_flows = require_mapping(spec.get("intent_flows", {}), "intent_flows", errors)
    validate_intent_flows(intent_flows, slot_map, errors)

    skills = require_list(spec.get("skills", []), "skills", errors)
    validate_skills(skills, errors)

    registry = require_mapping(spec.get("registry", {}), "registry", errors)
    validate_registry(registry, errors)
    registered_entries = collect_registry_names(registry, {"commands", "skills"})

    workflow_graph = require_mapping(spec.get("workflow_graph", {}), "workflow_graph", errors) if "workflow_graph" in spec else {}
    validate_workflow_graph(workflow_graph, registry, spec.get("test_contract", {}), errors, warnings)

    design_refs = require_mapping(spec.get("design_refs", {}), "design_refs", errors) if "design_refs" in spec else {}
    validate_design_refs(design_refs, workflow_graph, errors, warnings)

    constraints = require_mapping(spec.get("constraints", {}), "constraints", errors)
    validate_constraints(constraints, errors, warnings)

    resource_limits = require_mapping(spec.get("resource_limits", {}), "resource_limits", errors)
    validate_resource_limits(resource_limits, errors, warnings)

    runtime_contract = require_mapping(spec.get("runtime_contract", {}), "runtime_contract", errors)
    validate_runtime_contract(runtime_contract, errors, warnings)

    capability_discovery = require_mapping(spec.get("capability_discovery", {}), "capability_discovery", errors) if "capability_discovery" in spec else {}
    validate_capability_discovery(capability_discovery, errors, warnings)

    host_capabilities = require_list(spec.get("host_capabilities", []), "host_capabilities", errors) if "host_capabilities" in spec else []
    normalized_host_capabilities = validate_host_capabilities(host_capabilities, errors, warnings)

    agent_team_contract = require_mapping(spec.get("agent_team_contract", {}), "agent_team_contract", errors) if "agent_team_contract" in spec else {}
    validate_agent_team_contract(agent_team_contract, errors, warnings)

    generated_runtime_contract = require_mapping(spec.get("generated_runtime_contract", {}), "generated_runtime_contract", errors)
    validate_generated_runtime_contract(
        generated_runtime_contract,
        stages,
        intent_flows,
        spec.get("test_contract", {}),
        workflow_graph,
        capability_discovery,
        normalized_host_capabilities,
        agent_team_contract,
        errors,
        warnings,
    )
    target_runtime_policy = (
        require_mapping(spec.get("target_runtime_policy", {}), "target_runtime_policy", errors)
        if "target_runtime_policy" in spec
        else {}
    )
    validate_target_runtime_policy(target_runtime_policy, workflow_graph, generated_runtime_contract, errors, warnings)

    target_executor_policy = (
        require_mapping(spec.get("target_executor_policy", {}), "target_executor_policy", errors)
        if "target_executor_policy" in spec
        else {}
    )
    validate_target_executor_policy(target_executor_policy, errors, warnings)

    target_publish_policy = (
        require_mapping(spec.get("target_publish_policy", {}), "target_publish_policy", errors)
        if "target_publish_policy" in spec
        else {}
    )
    validate_target_publish_policy(target_publish_policy, workflow_graph, generated_runtime_contract, errors, warnings)

    target_claude_guard = (
        require_mapping(spec.get("target_claude_guard", {}), "target_claude_guard", errors)
        if "target_claude_guard" in spec
        else {}
    )
    validate_target_claude_guard(target_claude_guard, spec, errors, warnings)

    test_contract = require_mapping(spec.get("test_contract", {}), "test_contract", errors)
    validate_test_contract(test_contract, runtime_contract, stage_ids, slot_map, intent_flows, registered_entries, errors, warnings)

    return collector.payload()


def main() -> int:
    """schema 校验的 CLI 入口。"""

    args = parse_args()
    spec_path = Path(args.spec).resolve()
    if not spec_path.exists():
        diagnostics = DiagnosticCollector()
        diagnostics.error(f"spec not found: {spec_path}")
        if args.json:
            print(json.dumps(diagnostics.payload(spec=str(spec_path)), ensure_ascii=False, indent=2))
        else:
            print(f"Error: spec not found: {spec_path}", file=sys.stderr)
        return 1

    try:
        payload = load_yaml_mapping(spec_path)
    except Exception as exc:
        diagnostics = DiagnosticCollector()
        diagnostics.error(f"failed to parse YAML: {exc}")
        if args.json:
            print(json.dumps(diagnostics.payload(spec=str(spec_path)), ensure_ascii=False, indent=2))
        else:
            print(f"Error: failed to parse YAML: {exc}", file=sys.stderr)
        return 1

    report = validate_spec(payload)
    report["spec"] = str(spec_path)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"[{report['status']}] spec={spec_path}")
        for item in report["errors"]:
            print(f"[ERROR] {item}")
        for item in report["warnings"]:
            print(f"[WARN] {item}")

    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
