#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_ROOT = ROOT / ".claude" / "scripts"


def run_json(*args: str, expect: int = 0) -> dict:
    completed = subprocess.run(
        [sys.executable, *args, "--json"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != expect:
        raise AssertionError(
            f"expected exit {expect}, got {completed.returncode}\nstdout={completed.stdout}\nstderr={completed.stderr}"
        )
    payload = json.loads(completed.stdout)
    if not isinstance(payload, dict):
        raise AssertionError("expected JSON object")
    return payload


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def valid_policy(target_state: str = "existing_managed_workflow") -> dict:
    return {
        "schema_version": 1,
        "mode": "incremental",
        "scope": "node",
        "target_state": target_state,
        "affected_nodes": ["review"],
        "affected_artifacts": [
            ".workflowprogram/design/workflow-spec.yaml",
            ".claude/skills/review/SKILL.md",
        ],
        "allowed_derived_artifacts": [
            ".workflowprogram/design/workflow-view.md",
            ".workflowprogram/design/workflow-maintenance.md",
            ".workflowprogram/runtime/**",
        ],
        "preserve_user_edits": True,
        "requires_approval": True,
        "approval_reason": "Existing workflow assets are being modified.",
        "escalate_to_redesign": False,
        "reason": "User requested an incremental node change.",
    }


def valid_impact() -> dict:
    return {
        "old_design_sources_read": [".workflowprogram/design/workflow-spec.yaml"],
        "readback_evidence_path": "outputs/stages/existing-workflow-readback.json",
        "existing_managed_manifest_status": "present",
        "changed_requirement_ids": ["REQ-1"],
        "affected_spec_sections": ["workflow_graph.nodes.review"],
        "spec_change_required": True,
        "affected_design_source_sections": ["review node"],
        "test_contract_change_required": False,
        "test_contract_change_reason": "Acceptance categories remain unchanged.",
        "affected_test_contract_categories": ["flow", "artifacts"],
        "affected_target_assets": [".claude/skills/review/SKILL.md"],
        "risks": ["policy drift"],
        "verification_plan": ["run validate-change-policy", "run S5 judge"],
    }


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="workflow-change-policy-unit-") as temp_dir:
        temp = Path(temp_dir)
        target = temp / "target"
        run_root = temp / "run"
        stages = run_root / "outputs" / "stages"
        target.mkdir()

        route = run_json(
            str(SCRIPT_ROOT / "route-intent.py"),
            "--request",
            "修改已有工作流的 review 节点并应用",
            "--target-root",
            str(target),
        )
        assert route["intent"] == "develop"
        assert route["request_kind"] == "modify_existing"

        empty_context = run_json(
            str(SCRIPT_ROOT / "resolve-change-context.py"),
            "--request",
            "创建一个新工作流",
            "--target-root",
            str(target),
        )
        assert empty_context["target_state"] == "empty_target"
        assert empty_context["change_policy_required"] is False

        (target / ".workflowprogram" / "design").mkdir(parents=True)
        (target / ".workflowprogram" / "design" / "workflow-spec.yaml").write_text("name: demo\n", encoding="utf-8")
        route_path = stages / "route-intent.json"
        write_json(route_path, route)
        managed_context = run_json(
            str(SCRIPT_ROOT / "resolve-change-context.py"),
            "--request",
            "修改已有工作流的 review 节点并应用",
            "--target-root",
            str(target),
            "--route",
            str(route_path),
        )
        assert managed_context["target_state"] == "existing_managed_workflow"
        assert managed_context["change_policy_required"] is True

        context_path = stages / "change-context.json"
        policy_path = stages / "change-policy.json"
        impact_path = stages / "impact-analysis.json"
        readback_path = stages / "existing-workflow-readback.json"
        write_json(context_path, managed_context)
        write_json(policy_path, valid_policy())
        write_json(impact_path, valid_impact())
        write_json(readback_path, {"sources": [{"path": ".workflowprogram/design/workflow-spec.yaml"}]})

        pending = run_json(
            str(SCRIPT_ROOT / "validate-change-policy.py"),
            "--policy",
            str(policy_path),
            "--impact",
            str(impact_path),
            "--change-context",
            str(context_path),
            "--readback",
            str(readback_path),
            "--run-root",
            str(run_root),
            expect=2,
        )
        assert pending["status"] == "FAIL"
        assert pending["block_reason"] == "change_approval_missing"

        approved = run_json(
            str(SCRIPT_ROOT / "validate-change-policy.py"),
            "--policy",
            str(policy_path),
            "--impact",
            str(impact_path),
            "--change-context",
            str(context_path),
            "--readback",
            str(readback_path),
            "--run-root",
            str(run_root),
            "--approval-status",
            "approved",
        )
        assert approved["status"] == "PASS"
        assert approved["approval_mode"] == "approved"
        assert ".workflowprogram/runtime/**" in approved["expanded_allowed_artifacts"]

        stale_context = dict(managed_context)
        stale_context["fingerprints"] = dict(stale_context["fingerprints"])
        stale_context["fingerprints"]["design_spec_sha256"] = "stale"
        stale_path = stages / "change-context-current.json"
        write_json(stale_path, stale_context)
        stale = run_json(
            str(SCRIPT_ROOT / "validate-change-policy.py"),
            "--policy",
            str(policy_path),
            "--impact",
            str(impact_path),
            "--change-context",
            str(context_path),
            "--current-context",
            str(stale_path),
            "--readback",
            str(readback_path),
            "--run-root",
            str(run_root),
            "--approval-status",
            "approved",
            expect=2,
        )
        assert stale["block_reason"] == "change_context_stale"
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
