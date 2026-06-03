#!/usr/bin/env python3
"""
根据 workflow 目标和可选 capability_discovery 契约生成候选能力推荐与人工指引。
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List

from lib.capability_discovery import (
    capability_discovery_enabled,
    capability_discovery_from_spec,
    capability_discovery_overrides,
    configured_discovery_domains,
    discovery_profiles_for_domains,
    infer_discovery_domains,
)
from lib.host_probe_utils import detect_ready_status
from lib.host_team_utils import host_capabilities_from_spec
from lib.io_utils import iso_now, write_json
from lib.yaml_utils import load_yaml_mapping


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Discover candidate host capabilities for a workflow")
    parser.add_argument("--spec", required=True, help="Path to workflow-spec.yaml")
    parser.add_argument("--target-root", required=True, help="TARGET_ROOT path")
    parser.add_argument("--run-root", required=True, help="RUN_ROOT path")
    parser.add_argument("--request", default="", help="Original request text for domain inference")
    parser.add_argument("--json", action="store_true", help="Print JSON payload")
    return parser.parse_args()


def manual_instruction_lines(candidates: List[Dict[str, Any]], *, run_root: Path, profiles: List[Dict[str, Any]]) -> List[str]:
    lines: List[str] = [
        "# Host Capability Setup Instructions",
        "",
        f"- generated_at: `{iso_now()}`",
        f"- run_root: `{run_root}`",
        "",
        "## What WorkflowProgram Already Did",
        "",
        "- Searched local install state and curated capability hints.",
        "- Distinguished installed, missing, and recommended capabilities.",
        "- Preserved manual-only work instead of pretending host setup is complete.",
        "",
        "## Manual Follow-Up",
        "",
    ]
    suggested_team_profiles = [
        item
        for item in profiles
        if isinstance(item, dict) and bool(item.get("team_default_recommended", False)) and isinstance(item.get("suggested_agent_team_contract"), dict)
    ]
    if suggested_team_profiles:
        lines.extend(["## Suggested Team Defaults", ""])
        for profile in suggested_team_profiles:
            lines.append(f"### {profile.get('domain', 'profile')}")
            lines.append("")
            lines.append(f"- summary: {profile.get('summary', '')}")
            team_contract = profile.get("suggested_agent_team_contract", {})
            if isinstance(team_contract, dict):
                lines.append(f"- max_fan_out: `{team_contract.get('max_fan_out', '')}`")
                lines.append(f"- join_policy: `{team_contract.get('join_policy', '')}`")
                role_ids = [str(role.get('id', '')).strip() for role in team_contract.get("roles", []) if isinstance(role, dict)]
                lines.append(f"- suggested_roles: `{', '.join([item for item in role_ids if item])}`")
            lines.append("- This team contract is only a default suggestion; you may edit, remove, or replace it before finalizing the workflow.")
            lines.append("")
    unresolved = [item for item in candidates if str(item.get("status", "")).strip() in {"missing", "recommended"}]
    if not unresolved:
        lines.extend(["- No unresolved capability recommendations.", ""])
        return lines
    for item in unresolved:
        lines.append(f"### {item.get('name', item.get('id', 'candidate'))}")
        lines.append("")
        lines.append(f"- id: `{item.get('id', '')}`")
        lines.append(f"- kind: `{item.get('kind', '')}`")
        lines.append(f"- domain: `{item.get('domain', 'general')}`")
        lines.append(f"- status: `{item.get('status', '')}`")
        lines.append(f"- reason: {item.get('message', '') or item.get('summary', '')}")
        steps = item.get("manual_steps", [])
        if isinstance(steps, list) and steps:
            lines.append("- manual_steps:")
            for step in steps:
                lines.append(f"  - {step}")
        expected_outputs = item.get("expected_outputs", [])
        if isinstance(expected_outputs, list) and expected_outputs:
            lines.append("- expected_outputs:")
            for output in expected_outputs:
                lines.append(f"  - {output}")
        recheck = item.get("recheck_hint", "")
        if recheck:
            lines.append(f"- recheck: `{recheck}`")
        lines.append("")
    return lines


def expected_outputs_for_candidate(candidate: Dict[str, Any]) -> List[str]:
    kind = str(candidate.get("kind", "")).strip()
    probe = candidate.get("probe", {}) if isinstance(candidate.get("probe"), dict) else {}
    if kind == "external_binary":
        binary = str(probe.get("binary", "")).strip() or str(candidate.get("id", "")).strip()
        return [
            f"`{binary}` is resolvable on PATH.",
            f"Host probe returns `ready` for capability `{candidate.get('id', '')}`.",
        ]
    if kind == "mcp_server":
        server_name = str(probe.get("server_name", "")).strip() or str(candidate.get("id", "")).strip()
        return [
            f"MCP config registers server `{server_name}`.",
            f"Host probe returns `ready` for capability `{candidate.get('id', '')}`.",
        ]
    skill_name = str(probe.get("skill_name", "")).strip() or str(candidate.get("name", "")).strip() or str(candidate.get("id", "")).strip()
    return [
        f"Skill `{skill_name}` exists at the expected install location.",
        f"Host probe returns `ready` for capability `{candidate.get('id', '')}`.",
    ]


def recommended_host_capability(candidate: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": str(candidate.get("id", "")).strip(),
        "kind": str(candidate.get("kind", "")).strip(),
        "name": str(candidate.get("name", "")).strip(),
        "required": False,
        "probe": candidate.get("probe", {}),
        "bootstrap": {
            "scope": "manual_only",
            "summary": candidate.get("summary", "") or f"Install or configure {candidate.get('id', '')}",
            "project_local_outputs": [],
        },
        "approval_required": True,
    }


def build_candidate_report(spec_path: Path, target_root: Path, run_root: Path, request_text: str) -> Dict[str, Any]:
    spec = load_yaml_mapping(spec_path)
    discovery = capability_discovery_from_spec(spec)
    discovery_enabled = capability_discovery_enabled(discovery)
    explicit_domains = configured_discovery_domains(discovery)
    infer_from_request = bool(discovery.get("infer_from_request", True)) if isinstance(discovery, dict) else True
    include_local_installed = bool(discovery.get("include_local_installed", True)) if isinstance(discovery, dict) else True
    include_curated_profiles = bool(discovery.get("include_curated_profiles", True)) if isinstance(discovery, dict) else True
    overrides = capability_discovery_overrides(discovery)
    inferred_domains = infer_discovery_domains(request_text) if infer_from_request else []
    effective_domains: List[str] = []
    for item in [*explicit_domains, *inferred_domains]:
        if item and item not in effective_domains:
            effective_domains.append(item)

    declared_ids = {
        str(item.get("id", "")).strip(): item
        for item in host_capabilities_from_spec(spec)
        if isinstance(item, dict) and str(item.get("id", "")).strip()
    }

    profile_suggestions = discovery_profiles_for_domains(effective_domains, overrides) if include_curated_profiles else []
    report_candidates: List[Dict[str, Any]] = []
    profile_reports: List[Dict[str, Any]] = []

    for profile in profile_suggestions:
        domain = str(profile.get("domain", "")).strip()
        suggested_capabilities = profile.get("suggested_host_capabilities", [])
        suggested_team = profile.get("suggested_agent_team_contract")
        profile_reports.append(
            {
                "domain": domain,
                "summary": str(profile.get("summary", "")).strip(),
                "suggested_host_capabilities": [
                    recommended_host_capability(item)
                    for item in suggested_capabilities
                    if isinstance(item, dict)
                ],
                "suggested_agent_team_contract": suggested_team if isinstance(suggested_team, dict) else None,
                "team_default_recommended": bool(profile.get("team_default_recommended", False)),
                "excluded_capability_ids": profile.get("excluded_capability_ids", []),
                "replaced_capability_ids": profile.get("replaced_capability_ids", []),
            }
        )
        for candidate in suggested_capabilities if isinstance(suggested_capabilities, list) else []:
            if not isinstance(candidate, dict):
                continue
            capability_id = str(candidate.get("id", "")).strip()
            declared = declared_ids.get(capability_id)
            probe_source = declared if isinstance(declared, dict) else recommended_host_capability(candidate)
            ready, status, message = detect_ready_status(target_root, probe_source)
            if not include_local_installed and ready:
                continue
            report_candidates.append(
                {
                    "id": capability_id,
                    "domain": candidate.get("domain", "") or domain,
                    "kind": candidate.get("kind", ""),
                    "name": candidate.get("name", ""),
                    "source": "declared_host_capability" if declared else "curated_profile",
                    "status": "installed" if ready else ("missing" if declared else "recommended"),
                    "message": message if ready or declared else (candidate.get("summary", "") or message),
                    "summary": candidate.get("summary", ""),
                    "probe": candidate.get("probe", {}),
                    "manual_steps": candidate.get("manual_steps", []),
                    "expected_outputs": expected_outputs_for_candidate(candidate),
                    "recheck_hint": f"workflowprogram-python ${'{'}CLAUDE_PLUGIN_ROOT{'}'}/scripts/probe-host-capabilities.py --spec {spec_path} --target-root {target_root} --run-root {run_root} --json",
                    "recommended_host_capability": recommended_host_capability(candidate),
                }
            )

    report = {
        "generated_at": iso_now(),
        "spec": str(spec_path),
        "target_root": str(target_root),
        "run_root": str(run_root),
        "enabled": discovery_enabled or bool(effective_domains),
        "explicit_domains": explicit_domains,
        "inferred_domains": inferred_domains,
        "effective_domains": effective_domains,
        "include_local_installed": include_local_installed,
        "include_curated_profiles": include_curated_profiles,
        "infer_from_request": infer_from_request,
        "profile_overrides": overrides,
        "profiles": profile_reports,
        "candidates": report_candidates,
    }
    return report


def main() -> int:
    args = parse_args()
    spec_path = Path(args.spec).resolve()
    target_root = Path(args.target_root).resolve()
    run_root = Path(args.run_root).resolve()
    run_root.mkdir(parents=True, exist_ok=True)

    report = build_candidate_report(spec_path, target_root, run_root, args.request)
    report_path = run_root / "outputs" / "stages" / "host-capability-candidates.json"
    write_json(report_path, report)
    instructions_path = run_root / "outputs" / "stages" / "host-bootstrap-instructions.md"
    instructions_path.parent.mkdir(parents=True, exist_ok=True)
    instructions_path.write_text(
        "\n".join(manual_instruction_lines(report.get("candidates", []), run_root=run_root, profiles=report.get("profiles", []))) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    payload = {
        "status": "PASS",
        "report": report,
        "report_path": str(report_path),
        "instructions_path": str(instructions_path),
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"[PASS] host capability discovery written to {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
