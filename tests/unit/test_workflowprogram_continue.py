from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / ".claude" / "scripts" / "workflowprogram-continue.py"


def run_continue(workflow_result: Path, target: Path, run_root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--workflow-result",
            str(workflow_result),
            "--target-root",
            str(target),
            "--run-root",
            str(run_root),
            "--json",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def authoring_spec() -> dict:
    return {
        "name": "generated-probe",
        "description": "Generated probe workflow.",
        "phases": [{"title": "Probe"}],
        "body": "phase('Probe')\nreturn { status: 'PASS', runId: args?.runId || '' }\n",
        "supporting_assets": [],
        "asset_disposition": [],
        "task_model_policy": {"agent_task_models": {}},
    }


def pass_design_evidence() -> dict:
    return {
        "status": "PASS",
        "summary": "Design is complete.",
        "highLevelDesign": "Use one Native JS control plane.",
        "lowLevelDesign": "Return structured handoffs for external effects.",
        "traceability": ["REQ-001 -> Probe -> generation evidence"],
        "assetDisposition": [],
        "blockingIssues": [],
    }


def pass_review_evidence() -> dict:
    return {
        "status": "PASS",
        "summary": "Design review is closed.",
        "blockingIssues": [],
        "requiredRevisions": [],
        "assetDispositionReviewed": True,
    }


def ready_for_generation_result(target: Path, run_root: Path, *, status: str = "READY_FOR_GENERATION") -> dict:
    spec = authoring_spec()
    return {
        "summary": "Workflow tool wrapper",
        "result": {
            "status": status,
            "workflow": "workflowprogram-develop",
            "launchMode": "plugin-script-path",
            "runId": "run-001",
            "targetRoot": str(target),
            "runRoot": str(run_root),
            "requirementSummary": {
                "request": "Generate a probe workflow.",
                "targetRoot": str(target),
                "runRoot": str(run_root),
                "operation": "create",
            },
            "designEvidence": pass_design_evidence(),
            "reviewEvidence": pass_review_evidence(),
            "authoringSpec": spec,
            "generationRequest": {
                "targetRoot": str(target),
                "runRoot": str(run_root),
                "operation": "create",
                "rule": "Generate under run root only.",
            },
            "generationHandoff": {
                "status": "READY_FOR_GENERATION",
                "workflow": "workflowprogram-develop",
                "launchMode": "plugin-script-path",
                "runId": "run-001",
                "targetRoot": str(target),
                "runRoot": str(run_root),
                "requirementSummary": {
                    "request": "Generate a probe workflow.",
                    "targetRoot": str(target),
                    "runRoot": str(run_root),
                    "operation": "create",
                },
                "designEvidence": pass_design_evidence(),
                "reviewEvidence": pass_review_evidence(),
                "authoringSpec": spec,
                "generationRequest": {
                    "targetRoot": str(target),
                    "runRoot": str(run_root),
                    "operation": "create",
                    "rule": "Generate under run root only.",
                },
            },
            "nextAction": "RUN_CONTROLLED_GENERATION",
        },
    }


def load_stdout(completed: subprocess.CompletedProcess[str]) -> dict:
    return json.loads(completed.stdout)


def test_continue_runs_generation_pipeline_from_saved_workflow_result(tmp_path: Path) -> None:
    target = tmp_path / "target"
    run_root = tmp_path / "run"
    target.mkdir()
    workflow_result = run_root / "outputs" / "stages" / "latest-workflow-result.json"
    write_json(workflow_result, ready_for_generation_result(target, run_root))

    completed = run_continue(workflow_result, target, run_root)

    assert completed.returncode == 0, completed.stderr or completed.stdout
    payload = load_stdout(completed)
    assert payload["status"] == "PASS"
    assert payload["generationEvidence"]["status"] == "PASS"
    assert payload["generationEvidence"]["workflowScriptPath"].endswith(".claude\\workflows\\generated-probe.js") or payload[
        "generationEvidence"
    ]["workflowScriptPath"].endswith(".claude/workflows/generated-probe.js")

    handoff = run_root / "outputs" / "stages" / "native-workflow-generation-handoff-input.json"
    authoring = run_root / "native-workflow-authoring.json"
    continuation = run_root / "outputs" / "stages" / "workflowprogram-continuation-generation.json"
    candidate = run_root / "outputs" / "candidate" / ".claude" / "workflows" / "generated-probe.js"
    assert handoff.exists()
    assert authoring.exists()
    assert continuation.exists()
    assert candidate.exists()
    assert json.loads(authoring.read_text(encoding="utf-8")) == authoring_spec()
    assert json.loads(handoff.read_text(encoding="utf-8"))["authoringSpec"] == authoring_spec()


def test_continue_blocks_non_generation_status_before_candidate_write(tmp_path: Path) -> None:
    target = tmp_path / "target"
    run_root = tmp_path / "run"
    target.mkdir()
    workflow_result = run_root / "outputs" / "stages" / "latest-workflow-result.json"
    write_json(workflow_result, ready_for_generation_result(target, run_root, status="BLOCKED_GENERATION"))

    completed = run_continue(workflow_result, target, run_root)

    assert completed.returncode == 1
    payload = load_stdout(completed)
    assert payload["status"] == "FAIL"
    assert "READY_FOR_GENERATION" in str(payload["blockingIssues"])
    assert not (run_root / "outputs" / "candidate").exists()
