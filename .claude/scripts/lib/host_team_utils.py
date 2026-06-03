from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable, List


VALID_RUNTIME_CAPABILITIES = {
    "state_transitions",
    "run_state_validation",
    "host_capability_probe",
    "capability_discovery",
    "team_orchestration",
    "node_loop_execution",
    "target_managed_runtime",
    "target_atomic_publish",
}
VALID_HOST_CAPABILITY_KINDS = {
    "mcp_server",
    "codex_skill",
    "claude_skill",
    "external_binary",
}
VALID_BOOTSTRAP_SCOPES = {
    "project_local",
    "host_global",
    "manual_only",
}
VALID_BOOTSTRAP_ASSET_FORMATS = {
    "json",
    "text",
    "markdown",
    "shell",
}
VALID_HOST_GLOBAL_ADAPTER_TYPES = {
    "symlink_binary",
    "uv_tool",
    "pipx_install",
    "npm_global",
}
VALID_TEAM_JOIN_POLICIES = {
    "all_must_pass",
    "majority",
    "any",
}
TEAM_EVENT_TYPES = {
    "TeamFanOutStart",
    "TeamRoleStarted",
    "TeamRoleCompleted",
    "TeamJoinCompleted",
}
LOOP_EVENT_TYPES = {
    "LoopStart",
    "LoopIterationStart",
    "LoopFeedbackCommandCompleted",
    "LoopAgentCompleted",
    "LoopVerifierCompleted",
    "LoopStop",
}


def string_list(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def generated_runtime_contract_from_spec(spec: Dict[str, Any]) -> Dict[str, Any]:
    contract = spec.get("generated_runtime_contract", {})
    return contract if isinstance(contract, dict) else {}


def runtime_capabilities_from_contract(contract: Dict[str, Any]) -> List[str]:
    return string_list(contract.get("runtime_capabilities", []))


def host_capabilities_from_spec(spec: Dict[str, Any]) -> List[Dict[str, Any]]:
    value = spec.get("host_capabilities", [])
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def capability_discovery_from_spec(spec: Dict[str, Any]) -> Dict[str, Any]:
    value = spec.get("capability_discovery", {})
    return value if isinstance(value, dict) else {}


def agent_team_contract_from_spec(spec: Dict[str, Any]) -> Dict[str, Any]:
    contract = spec.get("agent_team_contract", {})
    return contract if isinstance(contract, dict) else {}


def agent_team_enabled(contract: Dict[str, Any]) -> bool:
    return bool(contract.get("enabled", False))


def node_loop_enabled(spec: Dict[str, Any]) -> bool:
    graph = spec.get("workflow_graph", {})
    if not isinstance(graph, dict):
        return False
    nodes = graph.get("nodes", [])
    if not isinstance(nodes, list):
        return False
    for raw_node in nodes:
        if not isinstance(raw_node, dict):
            continue
        policy = raw_node.get("loop_policy", {})
        if isinstance(policy, dict) and policy.get("enabled") is True:
            return True
    return False


def deterministic_runtime_provider(provider: str) -> bool:
    return provider in {"fixture_host", "command_adapter"}


def ensure_relative_bootstrap_output(path_text: str) -> str:
    cleaned = path_text.strip().replace("\\", "/")
    if cleaned.startswith("./"):
        cleaned = cleaned[2:]
    return cleaned


def project_local_outputs(capability: Dict[str, Any]) -> List[str]:
    bootstrap = capability.get("bootstrap", {})
    if not isinstance(bootstrap, dict):
        return []
    outputs: List[str] = []
    for item in string_list(bootstrap.get("project_local_outputs", [])):
        cleaned = ensure_relative_bootstrap_output(item)
        if cleaned and cleaned not in outputs:
            outputs.append(cleaned)
    for asset in bootstrap_assets(capability):
        path = str(asset.get("path", "")).strip()
        if path and path not in outputs:
            outputs.append(path)
    return outputs


def bootstrap_assets(capability: Dict[str, Any]) -> List[Dict[str, Any]]:
    bootstrap = capability.get("bootstrap", {})
    if not isinstance(bootstrap, dict):
        return []
    assets = bootstrap.get("assets", [])
    if not isinstance(assets, list):
        return []
    normalized: List[Dict[str, Any]] = []
    for raw in assets:
        if not isinstance(raw, dict):
            continue
        item = dict(raw)
        item["path"] = ensure_relative_bootstrap_output(str(item.get("path", "")).strip())
        normalized.append(item)
    return normalized


def host_global_adapter(capability: Dict[str, Any]) -> Dict[str, Any]:
    bootstrap = capability.get("bootstrap", {})
    if not isinstance(bootstrap, dict):
        return {}
    value = bootstrap.get("adapter", {})
    return value if isinstance(value, dict) else {}


def project_local_output_paths(target_root: Path, capability: Dict[str, Any]) -> List[Path]:
    return [(target_root / rel).resolve() for rel in project_local_outputs(capability)]


def project_local_outputs_ready(target_root: Path, capability: Dict[str, Any]) -> bool:
    outputs = project_local_output_paths(target_root, capability)
    return bool(outputs) and all(path.exists() for path in outputs)


def stage_slot_values(items: Iterable[Any]) -> List[str]:
    values: List[str] = []
    for item in items:
        text = str(item).strip()
        if text:
            values.append(text)
    return values
