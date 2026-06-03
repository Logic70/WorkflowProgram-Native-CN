#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import shutil
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


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def seed_design_inputs(run_root: Path) -> None:
    stages = run_root / "outputs" / "stages"
    write_text(stages / "s1-requirements.yaml", "requirements:\n  - id: REQ-001\n    text: demo\n")
    write_text(stages / "s2-context-findings.yaml", "findings:\n  - id: CTX-001\n    text: demo\n")
    write_text(stages / "s3-design-highlevel.md", "# Highlevel\n\n- REQ-001 is covered.\n")
    write_text(stages / "s3-design-lowlevel.md", "# Lowlevel\n\n- Implement deterministic checks.\n")
    write_text(stages / "acceptance-tests.yaml", "tests:\n  - id: AT-001\n    requirement: REQ-001\n")
    write_json(
        stages / "traceability-matrix.json",
        {"links": [{"requirement_id": "REQ-001", "design_nodes": ["demo"], "acceptance_tests": ["AT-001"]}]},
    )
    write_text(stages / "s3-implementation-plan.md", "# Plan\n\n1. Implement.\n")
    write_text(run_root / "workflow-spec.yaml", "name: demo\n")


def write_review(run_root: Path, *, issues: list[dict], closure_status: str = "PASS") -> None:
    review_root = run_root / "outputs" / "stages" / "design-review"
    packet = json.loads((review_root / "design-review-packet.json").read_text(encoding="utf-8"))
    open_blocking = [item for item in issues if item.get("blocking") and item.get("status") == "open"]
    write_json(review_root / "issues.json", {"schema_version": 1, "issues": issues})
    write_json(review_root / "round-1.json", {"schema_version": 1, "round": 1, "status": closure_status, "issues": issues})
    write_text(review_root / "report.md", "# Design Review Report\n")
    write_json(
        review_root / "closure.json",
        {
            "schema_version": 1,
            "schema_name": "design-review-closure",
            "status": closure_status,
            "packet_path": "outputs/stages/design-review/design-review-packet.json",
            "packet_sha256": sha256_file(review_root / "design-review-packet.json"),
            "artifact_fingerprints": packet["artifact_fingerprints"],
            "issue_count": len(issues),
            "open_blocking_count": len(open_blocking),
            "accepted_risk_count": len([item for item in issues if item.get("status") == "accepted_risk"]),
        },
    )


def blocker_issue() -> dict:
    return {
        "id": "DRV-001",
        "round_found": 1,
        "status": "open",
        "severity": "blocker",
        "blocking": True,
        "lens": "spec_projection",
        "affected_requirements": ["REQ-001"],
        "affected_artifacts": ["workflow-spec.yaml"],
        "problem": "Spec projection is stale.",
        "why_it_matters": "S4 would implement the wrong control plane.",
        "required_fix": "Update workflow-spec.yaml.",
        "resolved_by": "",
        "resolution_evidence": [],
        "residual_risk": "",
    }


def accepted_risk_issue() -> dict:
    issue = blocker_issue()
    issue.update(
        {
            "status": "accepted_risk",
            "severity": "minor",
            "blocking": False,
            "lens": "complexity_control",
            "problem": "Docs are more verbose than ideal.",
            "residual_risk": "Accepted because runtime behavior is unchanged.",
        }
    )
    return issue


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="workflow-design-review-gate-unit-") as temp_dir:
        temp = Path(temp_dir)

        pass_run = temp / "pass"
        seed_design_inputs(pass_run)
        packet = run_json(str(SCRIPT_ROOT / "generate-design-review-packet.py"), "--run-root", str(pass_run), "--request", "demo")
        assert packet["status"] == "PASS"
        write_review(pass_run, issues=[])
        assert run_json(str(SCRIPT_ROOT / "validate-design-review-gate.py"), "--run-root", str(pass_run))["status"] == "PASS"

        missing_closure = temp / "missing-closure"
        seed_design_inputs(missing_closure)
        run_json(str(SCRIPT_ROOT / "generate-design-review-packet.py"), "--run-root", str(missing_closure), "--request", "demo")
        write_json(missing_closure / "outputs" / "stages" / "design-review" / "issues.json", {"schema_version": 1, "issues": []})
        assert run_json(
            str(SCRIPT_ROOT / "validate-design-review-gate.py"),
            "--run-root",
            str(missing_closure),
            expect=2,
        )["block_reason"] == "design_review_unresolved"

        blocker_run = temp / "blocker"
        seed_design_inputs(blocker_run)
        run_json(str(SCRIPT_ROOT / "generate-design-review-packet.py"), "--run-root", str(blocker_run), "--request", "demo")
        write_review(blocker_run, issues=[blocker_issue()], closure_status="FAIL")
        blocker = run_json(str(SCRIPT_ROOT / "validate-design-review-gate.py"), "--run-root", str(blocker_run), expect=2)
        assert blocker["open_blocking_count"] == 1

        stale_run = temp / "stale"
        seed_design_inputs(stale_run)
        run_json(str(SCRIPT_ROOT / "generate-design-review-packet.py"), "--run-root", str(stale_run), "--request", "demo")
        write_review(stale_run, issues=[])
        write_text(stale_run / "outputs" / "stages" / "s3-design-lowlevel.md", "# Lowlevel\n\nChanged after review.\n")
        stale = run_json(str(SCRIPT_ROOT / "validate-design-review-gate.py"), "--run-root", str(stale_run), expect=2)
        assert stale["stale_artifacts"]

        accepted_run = temp / "accepted"
        seed_design_inputs(accepted_run)
        run_json(str(SCRIPT_ROOT / "generate-design-review-packet.py"), "--run-root", str(accepted_run), "--request", "demo")
        write_review(accepted_run, issues=[accepted_risk_issue()])
        accepted = run_json(str(SCRIPT_ROOT / "validate-design-review-gate.py"), "--run-root", str(accepted_run))
        assert accepted["status"] == "PASS"
        assert accepted["accepted_risk_count"] == 1

        entry_run = temp / "entry-block"
        target = temp / "target"
        target.mkdir()
        seed_design_inputs(entry_run)
        shutil.copy2(ROOT / "tests" / "spec-fixtures" / "valid-minimal.yaml", entry_run / "workflow-spec.yaml")
        write_text(entry_run / "outputs" / "candidate" / ".claude" / "rules" / "constraints.md", "# Constraints\n")
        blocked = run_json(
            str(SCRIPT_ROOT / "workflow-entry.py"),
            "run",
            "--spec",
            str(entry_run / "workflow-spec.yaml"),
            "--run-root",
            str(entry_run),
            "--target-root",
            str(target),
            "--entry-skill",
            "workflowprogram-develop",
            "--request",
            "demo",
            "--runtime-provider",
            "command_adapter",
            "--provider-command",
            "python3 tools/mock_runtime_host.py",
            expect=2,
        )
        assert blocked["status"] == "BLOCKED"
        assert blocked["block_reason"] == "design_review_unresolved"
        assert blocked["stopped_before_runner"] is True
        assert blocked["managed_plan_path"] is None
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
