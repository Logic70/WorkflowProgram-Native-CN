from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / ".claude" / "scripts" / "build-native-product-smoke-evidence.py"


def write_eval(
    path: Path,
    workflow: str,
    evidence: dict,
    *,
    expected_status: str = "PASS",
    evidence_profile: str = "full",
) -> None:
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "schema_name": "native-workflow-interactive-smoke",
                "status": "PASS",
                "return_code": 0,
                "workflow": workflow,
                "scriptPath": str((path.parent / f"{workflow}.js").resolve()),
                "expectedStatus": expected_status,
                "scenario": path.stem,
                "evidenceProfile": evidence_profile,
                "runIds": ["wf_test"],
                "jsonl": str(path.with_suffix(".jsonl")),
                "journalJsonl": None,
                "evidence": evidence,
                "blockingIssues": [],
            }
        ),
        encoding="utf-8",
    )


def run_aggregate(tmp_path: Path, *paths: Path) -> subprocess.CompletedProcess[str]:
    out = tmp_path / "native-product-interactive-smoke.json"
    cmd = [sys.executable, str(SCRIPT), "--out", str(out), "--json"]
    for path in paths:
        cmd.extend(["--evaluation", str(path)])
    return subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, check=False)


def test_complete_evaluator_reports_close_product_smoke_gate(tmp_path: Path) -> None:
    common = {
        "skill_listing": True,
        "workflow_invoked": True,
        "async_launched": True,
        "agent_started": False,
        "schema_result": False,
        "completed_pass": False,
        "completed_blocked": False,
        "environment_disabled": False,
    }
    paths = []
    for name in ["develop", "validate", "audit", "iterate", "publish"]:
        path = tmp_path / f"{name}.json"
        evidence = dict(common)
        if name == "develop":
            evidence["agent_started"] = True
            evidence["schema_result"] = True
        if name != "validate":
            evidence["completed_pass"] = True
        if name == "validate":
            evidence["completed_blocked"] = True
        write_eval(
            path,
            f"workflowprogram-{name}",
            evidence,
            expected_status="BLOCKED" if name == "validate" else "PASS",
            evidence_profile=(
                "early-blocker"
                if name == "validate"
                else "full"
                if name == "develop"
                else "completion"
            ),
        )
        paths.append(path)

    completed = run_aggregate(tmp_path, *paths)
    payload = json.loads(completed.stdout)

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert payload["declaredComplete"] is True
    assert payload["status"] == "PASS"
    assert payload["missingCoverage"] == []
    assert payload["develop"] is True
    assert payload["publish"] is True
    assert payload["agent"] is True
    assert payload["schema"] is True
    assert payload["pass"] is True
    assert payload["blocked_path"] is True


def test_incomplete_reports_do_not_declare_complete(tmp_path: Path) -> None:
    path = tmp_path / "develop.json"
    write_eval(
        path,
        "workflowprogram-develop",
        {
            "skill_listing": True,
            "workflow_invoked": True,
            "async_launched": True,
            "agent_started": True,
            "schema_result": True,
            "completed_pass": True,
            "completed_blocked": False,
            "environment_disabled": False,
        },
    )

    completed = run_aggregate(tmp_path, path)
    payload = json.loads(completed.stdout)

    assert completed.returncode == 1
    assert payload["declaredComplete"] is False
    assert payload["status"] == "FAIL"
    assert "validate" in payload["missingCoverage"]
    assert "blocked_path" in payload["missingCoverage"]


def test_rejects_non_evaluator_reports(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text(json.dumps({"schema_name": "other", "status": "PASS"}), encoding="utf-8")

    completed = run_aggregate(tmp_path, path)
    payload = json.loads(completed.stdout)

    assert completed.returncode == 1
    assert payload["sourceEvaluations"] == []
    assert payload["rejectedEvaluations"][0]["path"] == str(path)


def test_rejects_shallow_evaluator_pass_report(tmp_path: Path) -> None:
    path = tmp_path / "shallow.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "schema_name": "native-workflow-interactive-smoke",
                "status": "PASS",
                "workflow": "workflowprogram-develop",
            }
        ),
        encoding="utf-8",
    )

    completed = run_aggregate(tmp_path, path)
    payload = json.loads(completed.stdout)

    assert completed.returncode == 1
    assert payload["sourceEvaluations"] == []
    assert "return_code" in payload["rejectedEvaluations"][0]["reason"]


def test_rejects_unknown_evaluator_schema_version(tmp_path: Path) -> None:
    path = tmp_path / "wrong-version.json"
    write_eval(
        path,
        "workflowprogram-develop",
        {
            "skill_listing": True,
            "workflow_invoked": True,
            "async_launched": True,
            "agent_started": True,
            "schema_result": True,
            "completed_pass": True,
            "completed_blocked": False,
            "environment_disabled": False,
        },
    )
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["schema_version"] = 2
    path.write_text(json.dumps(payload), encoding="utf-8")

    completed = run_aggregate(tmp_path, path)
    aggregate_payload = json.loads(completed.stdout)

    assert completed.returncode == 1
    assert "schema_version" in aggregate_payload["rejectedEvaluations"][0]["reason"]


def test_rejects_early_blocker_profile_for_pass_status(tmp_path: Path) -> None:
    path = tmp_path / "early-blocker-pass.json"
    write_eval(
        path,
        "workflowprogram-develop",
        {
            "skill_listing": True,
            "workflow_invoked": True,
            "async_launched": True,
            "agent_started": False,
            "schema_result": False,
            "completed_pass": True,
            "completed_blocked": False,
            "environment_disabled": False,
        },
        expected_status="PASS",
        evidence_profile="early-blocker",
    )

    completed = run_aggregate(tmp_path, path)
    aggregate_payload = json.loads(completed.stdout)

    assert completed.returncode == 1
    assert "early-blocker" in aggregate_payload["rejectedEvaluations"][0]["reason"]


def test_rejects_report_when_workflow_does_not_match_script_path(tmp_path: Path) -> None:
    path = tmp_path / "mismatched-script.json"
    write_eval(
        path,
        "workflowprogram-develop",
        {
            "skill_listing": True,
            "workflow_invoked": True,
            "async_launched": True,
            "agent_started": True,
            "schema_result": True,
            "completed_pass": True,
            "completed_blocked": False,
            "environment_disabled": False,
        },
    )
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["scriptPath"] = str((tmp_path / "workflowprogram-validate.js").resolve())
    path.write_text(json.dumps(payload), encoding="utf-8")

    completed = run_aggregate(tmp_path, path)
    aggregate_payload = json.loads(completed.stdout)

    assert completed.returncode == 1
    assert aggregate_payload["sourceEvaluations"] == []
    assert "scriptPath" in aggregate_payload["rejectedEvaluations"][0]["reason"]


def test_accepts_utf8_bom_evaluator_report(tmp_path: Path) -> None:
    path = tmp_path / "develop-bom.json"
    evidence = {
        "skill_listing": True,
        "workflow_invoked": True,
        "async_launched": True,
        "agent_started": True,
        "schema_result": True,
        "completed_pass": True,
        "completed_blocked": False,
        "environment_disabled": False,
    }
    payload = {
        "schema_version": 1,
        "schema_name": "native-workflow-interactive-smoke",
        "status": "PASS",
        "return_code": 0,
        "workflow": "workflowprogram-develop",
        "scriptPath": str((tmp_path / "workflowprogram-develop.js").resolve()),
        "expectedStatus": "PASS",
        "scenario": "bom",
        "evidenceProfile": "completion",
        "runIds": ["wf_bom"],
        "jsonl": str(path.with_suffix(".jsonl")),
        "journalJsonl": None,
        "evidence": evidence,
        "blockingIssues": [],
    }
    path.write_text("\ufeff" + json.dumps(payload), encoding="utf-8")

    completed = run_aggregate(tmp_path, path)
    aggregate_payload = json.loads(completed.stdout)

    assert aggregate_payload["rejectedEvaluations"] == []
    assert aggregate_payload["sourceEvaluations"][0]["workflow"] == "workflowprogram-develop"
