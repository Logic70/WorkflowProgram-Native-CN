# AUTO-GENERATED FROM .claude/ - DO NOT EDIT DIRECTLY
from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List

from lib.host_team_utils import string_list


KNOWN_CAPABILITY_DISCOVERY_DOMAINS = {
    "reverse_engineering",
}

REQUEST_DOMAIN_KEYWORDS = {
    "reverse_engineering": [
        "reverse engineering",
        "reverse-engineering",
        "binary analysis",
        "malware analysis",
        "firmware analysis",
        "逆向",
        "二进制",
        "固件分析",
        "样本分析",
    ]
}

CURATED_DOMAIN_PROFILES: Dict[str, Dict[str, Any]] = {
    "reverse_engineering": {
        "summary": "Baseline reverse-engineering profile covering disassembly, firmware extraction, and review-oriented analysis.",
        "capabilities": [
            {
                "id": "ghidra_mcp",
                "kind": "mcp_server",
                "name": "Ghidra MCP",
                "probe": {"server_name": "ghidra"},
                "summary": "Use a Ghidra MCP bridge for structured navigation and decompilation support.",
                "manual_steps": [
                    "Install and register a Ghidra MCP server in your Codex or project MCP config.",
                    "Re-run the workflow after the MCP server appears in config files.",
                ],
            },
            {
                "id": "ghidra_cli",
                "kind": "external_binary",
                "name": "Ghidra Launcher",
                "probe": {"binary": "ghidraRun", "args": ["-help"]},
                "summary": "Use Ghidra locally for interactive disassembly and decompilation.",
                "manual_steps": [
                    "Install Ghidra and ensure `ghidraRun` is available on PATH.",
                    "Re-run capability discovery or host probe after installation.",
                ],
            },
            {
                "id": "radare2_cli",
                "kind": "external_binary",
                "name": "radare2",
                "probe": {"binary": "r2", "args": ["-v"]},
                "summary": "Use radare2 for lightweight binary inspection and scripting.",
                "manual_steps": [
                    "Install `radare2` and expose `r2` on PATH.",
                    "Re-run capability discovery or host probe after installation.",
                ],
            },
            {
                "id": "binwalk_cli",
                "kind": "external_binary",
                "name": "binwalk",
                "probe": {"binary": "binwalk", "args": ["--help"]},
                "summary": "Use binwalk for firmware and packed binary extraction.",
                "manual_steps": [
                    "Install `binwalk` and expose it on PATH.",
                    "Re-run capability discovery or host probe after installation.",
                ],
            },
        ],
        "suggested_agent_team_contract": {
            "enabled": True,
            "max_fan_out": 3,
            "join_policy": "all_must_pass",
            "roles": [
                {
                    "id": "triage_analyst",
                    "responsibility": "Triage the sample, identify format, packers, and initial analysis path.",
                    "ownership_stage_slots": ["S2"],
                    "output_patterns": ["outputs/stages/team/S2/triage_analyst/triage-report.md"],
                    "required": True,
                },
                {
                    "id": "static_analyst",
                    "responsibility": "Perform static reverse engineering and annotate key routines.",
                    "ownership_stage_slots": ["S2", "S3"],
                    "output_patterns": ["outputs/stages/team/S3/static_analyst/static-analysis-report.md"],
                    "required": True,
                },
                {
                    "id": "dynamic_analyst",
                    "responsibility": "Validate runtime behavior, unpacking, or dynamic indicators when relevant.",
                    "ownership_stage_slots": ["S5"],
                    "output_patterns": ["outputs/stages/team/S5/dynamic_analyst/dynamic-analysis-report.md"],
                    "required": False,
                },
                {
                    "id": "report_reviewer",
                    "responsibility": "Join findings into a reviewer-facing reverse-engineering report.",
                    "ownership_stage_slots": ["S5"],
                    "output_patterns": ["outputs/stages/team/S5/report_reviewer/review-report.md"],
                    "required": True,
                },
            ],
            "execution": [
                {
                    "stage_slot": "S2",
                    "role_ids": ["triage_analyst", "static_analyst"],
                    "join_role": "triage_analyst",
                },
                {
                    "stage_slot": "S5",
                    "role_ids": ["dynamic_analyst", "report_reviewer"],
                    "join_role": "report_reviewer",
                },
            ],
        },
    },
}


def capability_discovery_from_spec(spec: Dict[str, Any]) -> Dict[str, Any]:
    value = spec.get("capability_discovery", {})
    return value if isinstance(value, dict) else {}


def capability_discovery_enabled(config: Dict[str, Any]) -> bool:
    return bool(config.get("enabled", False))


def configured_discovery_domains(config: Dict[str, Any]) -> List[str]:
    return [item for item in string_list(config.get("domains", []))]


def infer_discovery_domains(request_text: str) -> List[str]:
    lowered = request_text.casefold()
    domains: List[str] = []
    for domain, keywords in REQUEST_DOMAIN_KEYWORDS.items():
        if any(keyword.casefold() in lowered for keyword in keywords):
            domains.append(domain)
    return domains


def curated_candidates_for_domains(domains: List[str]) -> List[Dict[str, Any]]:
    candidates: List[Dict[str, Any]] = []
    seen_ids = set()
    for domain in domains:
        profile = CURATED_DOMAIN_PROFILES.get(domain, {})
        for raw in profile.get("capabilities", []) if isinstance(profile, dict) else []:
            item = deepcopy(raw)
            item["domain"] = domain
            capability_id = str(item.get("id", "")).strip()
            if not capability_id or capability_id in seen_ids:
                continue
            seen_ids.add(capability_id)
            candidates.append(item)
    return candidates


def capability_discovery_overrides(config: Dict[str, Any]) -> Dict[str, Any]:
    value = config.get("profile_overrides", {})
    return value if isinstance(value, dict) else {}


def _replacement_items(overrides: Dict[str, Any]) -> List[Dict[str, Any]]:
    raw = overrides.get("replace_capabilities", [])
    return [item for item in raw if isinstance(item, dict)] if isinstance(raw, list) else []


def discovery_profiles_for_domains(domains: List[str], overrides: Dict[str, Any]) -> List[Dict[str, Any]]:
    excluded_ids = set(string_list(overrides.get("exclude_capability_ids", [])))
    replacements = _replacement_items(overrides)
    replacements_by_target: Dict[str, Dict[str, Any]] = {}
    for replacement in replacements:
        replaces_id = str(replacement.get("replaces", "")).strip()
        if replaces_id:
            replacements_by_target[replaces_id] = deepcopy(replacement)

    profiles: List[Dict[str, Any]] = []
    for domain in domains:
        base_profile = CURATED_DOMAIN_PROFILES.get(domain)
        if not isinstance(base_profile, dict):
            continue
        suggested_capabilities: List[Dict[str, Any]] = []
        replaced_ids: List[str] = []
        excluded_profile_ids: List[str] = []
        seen_ids = set()
        for raw in base_profile.get("capabilities", []):
            capability = deepcopy(raw)
            capability_id = str(capability.get("id", "")).strip()
            if not capability_id:
                continue
            if capability_id in excluded_ids:
                excluded_profile_ids.append(capability_id)
                continue
            replacement = replacements_by_target.get(capability_id)
            if replacement:
                replaced_ids.append(capability_id)
                capability = deepcopy(replacement)
                capability.pop("replaces", None)
            capability["domain"] = domain
            normalized_id = str(capability.get("id", "")).strip()
            if not normalized_id or normalized_id in seen_ids:
                continue
            seen_ids.add(normalized_id)
            suggested_capabilities.append(capability)

        team_default = deepcopy(base_profile.get("suggested_agent_team_contract"))
        team_default_enabled = not bool(overrides.get("disable_team_default", False))
        if not team_default_enabled:
            team_default = None

        profiles.append(
            {
                "domain": domain,
                "summary": str(base_profile.get("summary", "")).strip(),
                "suggested_host_capabilities": suggested_capabilities,
                "suggested_agent_team_contract": team_default,
                "team_default_recommended": bool(team_default),
                "excluded_capability_ids": excluded_profile_ids,
                "replaced_capability_ids": replaced_ids,
            }
        )
    return profiles
