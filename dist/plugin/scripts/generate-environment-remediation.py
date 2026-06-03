#!/usr/bin/env python3
# AUTO-GENERATED FROM .claude/ - DO NOT EDIT DIRECTLY
"""
聚合宿主能力失败的当前证据与历史运行，产出环境修复提案与用户可读指引。
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

from lib.io_utils import iso_now, write_json
from lib.reporting import redact_text, with_report_fields
from lib.yaml_utils import load_yaml_mapping


def load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate environment remediation guidance from host readiness evidence")
    parser.add_argument("--spec", required=True, help="Path to workflow-spec.yaml")
    parser.add_argument("--target-root", required=True, help="TARGET_ROOT path")
    parser.add_argument("--run-root", required=True, help="RUN_ROOT path")
    parser.add_argument("--json", action="store_true", help="Print JSON payload")
    return parser.parse_args()


def current_host_report(run_root: Path) -> Tuple[Dict[str, Any], str]:
    for name in ("host-capability-probe.json", "host-capability-report.json"):
        path = run_root / "outputs" / "stages" / name
        payload = load_json(path)
        if payload:
            return payload, str(path)
    return {}, ""


def discovery_candidate_index(run_root: Path) -> Dict[str, Dict[str, Any]]:
    report = load_json(run_root / "outputs" / "stages" / "host-capability-candidates.json")
    candidates = report.get("candidates", []) if isinstance(report.get("candidates"), list) else []
    index: Dict[str, Dict[str, Any]] = {}
    for item in candidates:
        if not isinstance(item, dict):
            continue
        capability_id = str(item.get("id", "")).strip()
        if capability_id and capability_id not in index:
            index[capability_id] = item
    return index


def bootstrap_plan_index(run_root: Path) -> Dict[str, Dict[str, Any]]:
    payload = load_json(run_root / "outputs" / "stages" / "host-bootstrap-plan.json")
    plan_items = payload.get("plan", []) if isinstance(payload.get("plan"), list) else []
    index: Dict[str, Dict[str, Any]] = {}
    for item in plan_items:
        if not isinstance(item, dict):
            continue
        capability_id = str(item.get("capability_id", "")).strip()
        if capability_id and capability_id not in index:
            index[capability_id] = item
    return index


def required_missing_capabilities(report: Dict[str, Any]) -> List[Dict[str, Any]]:
    capabilities = report.get("capabilities", []) if isinstance(report.get("capabilities"), list) else []
    return [
        item
        for item in capabilities
        if isinstance(item, dict)
        and bool(item.get("required", False))
        and str(item.get("status", "")).strip() != "ready"
    ]


def optional_not_ready_capabilities(report: Dict[str, Any]) -> List[Dict[str, Any]]:
    capabilities = report.get("capabilities", []) if isinstance(report.get("capabilities"), list) else []
    return [
        item
        for item in capabilities
        if isinstance(item, dict)
        and not bool(item.get("required", False))
        and str(item.get("status", "")).strip() != "ready"
    ]


def summarize_history(target_root: Path, current_run_root: Path) -> Dict[str, List[str]]:
    runs_root = target_root / ".workflowprogram" / "runs"
    history: Dict[str, List[str]] = {}
    if not runs_root.exists():
        return history

    for child in runs_root.iterdir():
        if not child.is_dir() or child.resolve() == current_run_root.resolve():
            continue
        state = load_json(child / "state.json")
        values = state.get("values", {}) if isinstance(state.get("values"), dict) else {}
        if str(values.get("failure_kind", "")).strip() != "environment":
            continue
        report = load_json(child / "outputs" / "stages" / "host-capability-probe.json")
        if not report:
            report = load_json(child / "outputs" / "stages" / "host-capability-report.json")
        for item in required_missing_capabilities(report):
            capability_id = str(item.get("id", "")).strip()
            if not capability_id:
                continue
            history.setdefault(capability_id, []).append(child.name)
    return history


def default_recheck_hint(spec_path: Path, target_root: Path, run_root: Path) -> str:
    return (
        f"workflowprogram-python ${{CLAUDE_PLUGIN_ROOT}}/scripts/probe-host-capabilities.py --spec {spec_path} "
        f"--target-root {target_root} --run-root {run_root} --json"
    )


def action_for_capability(
    item: Dict[str, Any],
    *,
    candidate: Dict[str, Any],
    bootstrap_entry: Dict[str, Any],
    spec_path: Path,
    target_root: Path,
    run_root: Path,
    prior_run_ids: List[str],
) -> Dict[str, Any]:
    capability_id = str(item.get("id", "")).strip()
    scope = str(item.get("bootstrap_scope", "")).strip() or str(bootstrap_entry.get("scope", "")).strip() or "manual_only"
    approval_required = bool(item.get("approval_required", False))
    adapter = bootstrap_entry.get("adapter", {}) if isinstance(bootstrap_entry.get("adapter"), dict) else {}
    occurrence_count = len(prior_run_ids) + 1

    manual_steps = candidate.get("manual_steps", []) if isinstance(candidate.get("manual_steps"), list) else []
    expected_outputs = candidate.get("expected_outputs", []) if isinstance(candidate.get("expected_outputs"), list) else []
    recheck_hint = str(candidate.get("recheck_hint", "")).strip()
    summary = str(bootstrap_entry.get("summary", "")).strip() or str(candidate.get("summary", "")).strip() or str(item.get("message", "")).strip()

    if not manual_steps:
        if scope == "project_local":
            manual_steps = ["Re-run the workflow so project-local bootstrap assets can be materialized under TARGET_ROOT/.workflowprogram/bootstrap/."]
        elif scope == "host_global" and adapter:
            manual_steps = [f"Approve or run the supported host-global adapter `{str(adapter.get('type', '')).strip() or 'adapter'}` to satisfy this capability."]
        elif scope == "host_global":
            manual_steps = ["Complete the required host-global setup manually, then rerun the workflow."]
        else:
            manual_steps = ["Follow the manual setup steps for this missing capability, then rerun the workflow."]

    if not expected_outputs:
        expected_outputs = [f"Host probe returns `ready` for capability `{capability_id}`."]
        project_outputs = item.get("project_local_outputs", [])
        if scope == "project_local" and isinstance(project_outputs, list) and project_outputs:
            expected_outputs.extend([str(output).strip() for output in project_outputs if str(output).strip()])

    if not recheck_hint:
        recheck_hint = default_recheck_hint(spec_path, target_root, run_root)

    if scope == "project_local":
        recommended_action = "apply_project_local_bootstrap"
    elif scope == "host_global" and adapter:
        recommended_action = "approve_host_global_bootstrap"
    elif scope == "host_global":
        recommended_action = "complete_host_global_setup_manually"
    else:
        recommended_action = "follow_manual_setup"

    return {
        "capability_id": capability_id,
        "name": str(item.get("name", "")).strip(),
        "kind": str(item.get("kind", "")).strip(),
        "required": bool(item.get("required", False)),
        "status": str(item.get("status", "")).strip(),
        "bootstrap_scope": scope,
        "approval_required": approval_required,
        "repeated_failure": occurrence_count >= 2,
        "occurrence_count": occurrence_count,
        "prior_environment_run_ids": prior_run_ids,
        "summary": summary,
        "recommended_action": recommended_action,
        "manual_steps": manual_steps,
        "expected_outputs": expected_outputs,
        "recheck_hint": recheck_hint,
        "adapter_type": str(adapter.get("type", "")).strip() if adapter else "",
    }


def render_guide(report: Dict[str, Any]) -> str:
    lines: List[str] = [
        "# Environment Remediation Guide",
        "",
        f"- Generated at: `{report.get('generated_at', '')}`",
        f"- Current required missing: `{', '.join(report.get('current_required_missing_ids', [])) or 'none'}`",
        f"- Prior environment runs: `{report.get('prior_environment_run_count', 0)}`",
        f"- Repeated blockers: `{', '.join(item.get('capability_id', '') for item in report.get('repeated_missing_capabilities', []) if isinstance(item, dict)) or 'none'}`",
        "",
    ]

    actions = report.get("remediation_actions", [])
    if not isinstance(actions, list) or not actions:
        lines.extend(
            [
                "## Remediation Actions",
                "",
                "No unresolved required host capability steps remain.",
                "",
            ]
        )
        return "\n".join(lines) + "\n"

    lines.extend(["## Remediation Actions", ""])
    for action in actions:
        if not isinstance(action, dict):
            continue
        lines.extend(
            [
                f"### `{str(action.get('capability_id', '')).strip() or 'unknown'}`",
                "",
                f"- Recommended action: `{str(action.get('recommended_action', '')).strip() or 'follow_manual_setup'}`",
                f"- Bootstrap scope: `{str(action.get('bootstrap_scope', '')).strip() or 'manual_only'}`",
                f"- Occurrence count: `{int(action.get('occurrence_count', 1))}`",
                f"- Summary: {str(action.get('summary', '')).strip() or 'No summary available.'}",
                "",
                "#### Manual Steps",
                "",
            ]
        )
        for step in action.get("manual_steps", []) if isinstance(action.get("manual_steps"), list) else []:
            lines.append(f"- {str(step).strip()}")
        lines.extend(["", "#### Expected Outputs", ""])
        for item in action.get("expected_outputs", []) if isinstance(action.get("expected_outputs"), list) else []:
            lines.append(f"- {str(item).strip()}")
        lines.extend(
            [
                "",
                "#### Re-check",
                "",
                f"- `{str(action.get('recheck_hint', '')).strip()}`",
                "",
            ]
        )
    return "\n".join(lines) + "\n"


def build_report(spec_path: Path, target_root: Path, run_root: Path) -> Dict[str, Any]:
    spec = load_yaml_mapping(spec_path)
    current_report, report_source = current_host_report(run_root)
    candidate_index = discovery_candidate_index(run_root)
    bootstrap_index = bootstrap_plan_index(run_root)
    history = summarize_history(target_root, run_root)

    current_required = required_missing_capabilities(current_report)
    current_optional = optional_not_ready_capabilities(current_report)
    actions = [
        action_for_capability(
            item,
            candidate=candidate_index.get(str(item.get("id", "")).strip(), {}),
            bootstrap_entry=bootstrap_index.get(str(item.get("id", "")).strip(), {}),
            spec_path=spec_path,
            target_root=target_root,
            run_root=run_root,
            prior_run_ids=history.get(str(item.get("id", "")).strip(), []),
        )
        for item in current_required
    ]
    user_followups = [
        item
        for item in actions
        if item.get("recommended_action") in {
            "approve_host_global_bootstrap",
            "complete_host_global_setup_manually",
            "follow_manual_setup",
        }
    ]
    repeated = [item for item in actions if bool(item.get("repeated_failure", False))]

    report = {
        "generated_at": iso_now(),
        "spec": str(spec_path),
        "target_root": str(target_root),
        "run_root": str(run_root),
        "report_source": report_source,
        "host_capabilities_declared": bool(spec.get("host_capabilities")) if isinstance(spec, dict) else False,
        "all_required_ready": bool(current_report.get("all_required_ready", False)),
        "current_required_missing_ids": [str(item.get("id", "")).strip() for item in current_required if str(item.get("id", "")).strip()],
        "current_optional_not_ready_ids": [str(item.get("id", "")).strip() for item in current_optional if str(item.get("id", "")).strip()],
        "prior_environment_run_count": sum(len(run_ids) for run_ids in history.values()),
        "repeated_missing_capabilities": repeated,
        "repeated_failure_count": len(repeated),
        "remediation_actions": actions,
        "user_followups": user_followups,
    }
    return with_report_fields(
        report,
        schema_name="environment-remediation-report",
        error_code="HOST_CAPABILITY_MISSING" if current_required else None,
        failure_kind="environment" if current_required else "none",
        remediation=[
            {
                "code": "COMPLETE_HOST_CAPABILITY_REMEDIATION",
                "summary": "Complete the remediation_actions and rerun host capability probe.",
            }
        ]
        if current_required
        else [],
    )


def main() -> int:
    args = parse_args()
    spec_path = Path(args.spec).resolve()
    target_root = Path(args.target_root).resolve()
    run_root = Path(args.run_root).resolve()
    report = build_report(spec_path, target_root, run_root)
    report_path = run_root / "outputs" / "stages" / "environment-remediation-report.json"
    guide_path = run_root / "outputs" / "stages" / "environment-remediation-guide.md"
    write_json(report_path, report)
    guide_path.parent.mkdir(parents=True, exist_ok=True)
    guide_path.write_text(redact_text(render_guide(report)), encoding="utf-8", newline="\n")
    payload = {
        "status": "PASS",
        "report": report,
        "report_path": str(report_path),
        "guide_path": str(guide_path),
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"[PASS] environment remediation written to {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
