from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / ".claude" / "scripts" / "build-native-product-smoke-evidence.py"


def write_eval(path: Path, workflow: str, evidence: dict) -> None:
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "schema_name": "native-workflow-interactive-smoke",
                "status": "PASS",
                "workflow": workflow,
                "scenario": path.stem,
                "evidenceProfile": "full",
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
            evidence["completed_pass"] = True
        if name == "validate":
            evidence["completed_blocked"] = True
        write_eval(path, f"workflowprogram-{name}", evidence)
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


def test_accepts_utf8_bom_evaluator_report(tmp_path: Path) -> None:
    path = tmp_path / "develop-bom.json"
    evidence = {
        "skill_listing": True,
        "workflow_invoked": True,
        "async_launched": True,
        "agent_started": True,
        "schema_result": True,
        "completed_pass": True,
        "completed_blocked": True,
        "environment_disabled": False,
    }
    payload = {
        "schema_version": 1,
        "schema_name": "native-workflow-interactive-smoke",
        "status": "PASS",
        "workflow": "workflowprogram-develop",
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
