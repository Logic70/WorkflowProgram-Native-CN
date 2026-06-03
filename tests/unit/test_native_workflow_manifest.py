"""Focused tests for build-native-workflow-manifest.py.

Covers:
- PASS manifest with all six gates.
- Missing report, gate, or stale candidate hash.
- Empty candidate root, workflow script outside candidate tree.
- Asset checksum drift.
- Adversarial: empty run-id, empty workflow-name, nonexistent script,
  script not in assets, missing/non-list blockingIssues, manifest-gate gating.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
MANIFEST_BUILDER = ROOT / ".claude" / "scripts" / "build-native-workflow-manifest.py"


def run_manifest(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(MANIFEST_BUILDER), *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def make_pass_report(
    report_path: Path,
    candidate_hash: str,
    *,
    extra: dict | None = None,
) -> dict:
    report = {
        "status": "PASS",
        "candidateHash": candidate_hash,
        "evidence": [str(report_path.resolve())],
        "blockingIssues": [],
    }
    if extra:
        report.update(extra)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def _compute_ch(candidate: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(candidate.rglob("*")):
        if path.is_file():
            relative = path.relative_to(candidate).as_posix()
            digest.update(relative.encode("utf-8"))
            digest.update(b"\0")
            digest.update(path.read_bytes())
            digest.update(b"\0")
    return f"sha256:{digest.hexdigest()}"


def test_manifest_pass_with_all_six_gates(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate"
    workflow = candidate / ".claude" / "workflows" / "probe.js"
    workflow.parent.mkdir(parents=True)
    workflow.write_text("export const meta = { name: 'probe', description: 'T' }\n", encoding="utf-8")

    ch = _compute_ch(candidate)

    reports = tmp_path / "reports"
    make_pass_report(reports / "design-review.json", ch)
    make_pass_report(reports / "static-validation.json", ch)
    make_pass_report(reports / "interactive-smoke.json", ch, extra={"interactiveEvidence": [{"step": "launch", "status": "ok"}]})
    make_pass_report(reports / "drift.json", ch, extra={"driftCheck": "PASS"})

    out_path = tmp_path / "manifest.json"
    r = run_manifest([
        "--run-id", "run-001",
        "--candidate-root", str(candidate),
        "--workflow-name", "probe",
        "--workflow-script", str(workflow),
        "--design-review-report", str(reports / "design-review.json"),
        "--static-validation-report", str(reports / "static-validation.json"),
        "--interactive-smoke-report", str(reports / "interactive-smoke.json"),
        "--drift-report", str(reports / "drift.json"),
        "--out", str(out_path),
        "--json",
    ])
    assert r.returncode == 0, r.stderr or r.stdout
    payload = json.loads(r.stdout)
    assert payload["status"] == "PASS"
    assert payload["schemaName"] == "native-workflow-manifest"
    assert payload["workflowName"] == "probe"
    assert payload["candidateHash"] == ch
    assert len(payload["assets"]) >= 1
    gates = {g["name"]: g["status"] for g in payload["gates"]}
    expected = {"designReview", "staticValidation", "interactiveSmoke", "assetScope", "driftCheck", "manifest"}
    assert set(gates.keys()) == expected
    assert all(s == "PASS" for s in gates.values())
    assert payload["blockingIssues"] == []


def test_manifest_rejects_empty_candidate_root(tmp_path: Path) -> None:
    candidate = tmp_path / "empty-candidate"
    candidate.mkdir()

    r = run_manifest([
        "--run-id", "run-001",
        "--candidate-root", str(candidate),
        "--workflow-name", "probe",
        "--workflow-script", str(candidate / ".claude" / "workflows" / "probe.js"),
        "--design-review-report", str(tmp_path / "nope.json"),
        "--static-validation-report", str(tmp_path / "nope.json"),
        "--interactive-smoke-report", str(tmp_path / "nope.json"),
        "--drift-report", str(tmp_path / "nope.json"),
        "--out", str(tmp_path / "out.json"),
        "--json",
    ])
    assert r.returncode != 0, r.stdout
    payload = json.loads(r.stdout)
    assert payload["status"] == "BLOCKED_PUBLISH"


def test_manifest_rejects_workflow_script_outside_candidate_tree(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    (candidate / ".claude" / "workflows").mkdir(parents=True)
    (candidate / ".claude" / "workflows" / "probe.js").write_text(
        "export const meta = { name: 'probe', description: 'T' }\n", encoding="utf-8"
    )

    outside_script = tmp_path / "outside.js"
    outside_script.write_text("// outside\n", encoding="utf-8")

    r = run_manifest([
        "--run-id", "run-001",
        "--candidate-root", str(candidate),
        "--workflow-name", "probe",
        "--workflow-script", str(outside_script),
        "--design-review-report", str(tmp_path / "nope.json"),
        "--static-validation-report", str(tmp_path / "nope.json"),
        "--interactive-smoke-report", str(tmp_path / "nope.json"),
        "--drift-report", str(tmp_path / "nope.json"),
        "--out", str(tmp_path / "out.json"),
        "--json",
    ])
    assert r.returncode != 0, r.stdout
    payload = json.loads(r.stdout)
    assert payload["status"] == "BLOCKED_PUBLISH"


def test_manifest_blocks_stale_candidate_hash_in_report(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate"
    workflow = candidate / ".claude" / "workflows" / "probe.js"
    workflow.parent.mkdir(parents=True)
    workflow.write_text("export const meta = { name: 'probe', description: 'T' }\n", encoding="utf-8")

    reports = tmp_path / "reports"
    make_pass_report(reports / "design-review.json", "sha256:stale-hash")

    out_path = tmp_path / "manifest.json"
    r = run_manifest([
        "--run-id", "run-001",
        "--candidate-root", str(candidate),
        "--workflow-name", "probe",
        "--workflow-script", str(workflow),
        "--design-review-report", str(reports / "design-review.json"),
        "--static-validation-report", str(reports / "design-review.json"),
        "--interactive-smoke-report", str(reports / "design-review.json"),
        "--drift-report", str(reports / "design-review.json"),
        "--out", str(out_path),
        "--json",
    ])
    assert r.returncode != 0, r.stdout
    payload = json.loads(r.stdout)
    assert payload["status"] == "BLOCKED_PUBLISH"


def test_manifest_blocks_missing_design_review_report(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate"
    workflow = candidate / ".claude" / "workflows" / "probe.js"
    workflow.parent.mkdir(parents=True)
    workflow.write_text("export const meta = { name: 'probe', description: 'T' }\n", encoding="utf-8")

    r = run_manifest([
        "--run-id", "run-001",
        "--candidate-root", str(candidate),
        "--workflow-name", "probe",
        "--workflow-script", str(workflow),
        "--design-review-report", str(tmp_path / "nope.json"),
        "--static-validation-report", str(tmp_path / "nope.json"),
        "--interactive-smoke-report", str(tmp_path / "nope.json"),
        "--drift-report", str(tmp_path / "nope.json"),
        "--out", str(tmp_path / "out.json"),
        "--json",
    ])
    assert r.returncode != 0, r.stdout
    payload = json.loads(r.stdout)
    assert payload["status"] == "BLOCKED_PUBLISH"


def test_manifest_blocks_non_pass_report_status(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate"
    workflow = candidate / ".claude" / "workflows" / "probe.js"
    workflow.parent.mkdir(parents=True)
    workflow.write_text("export const meta = { name: 'probe', description: 'T' }\n", encoding="utf-8")

    ch = _compute_ch(candidate)

    reports = tmp_path / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    fail_report = {
        "status": "FAIL",
        "candidateHash": ch,
        "evidence": [],
        "blockingIssues": ["Validation failed."],
    }
    (reports / "design-review.json").write_text(json.dumps(fail_report, indent=2) + "\n", encoding="utf-8")

    r = run_manifest([
        "--run-id", "run-001",
        "--candidate-root", str(candidate),
        "--workflow-name", "probe",
        "--workflow-script", str(workflow),
        "--design-review-report", str(reports / "design-review.json"),
        "--static-validation-report", str(reports / "design-review.json"),
        "--interactive-smoke-report", str(reports / "design-review.json"),
        "--drift-report", str(reports / "design-review.json"),
        "--out", str(tmp_path / "out.json"),
        "--json",
    ])
    assert r.returncode != 0, r.stdout
    payload = json.loads(r.stdout)
    assert payload["status"] == "BLOCKED_PUBLISH"


def test_manifest_blocks_missing_interactive_smoke_evidence(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate"
    workflow = candidate / ".claude" / "workflows" / "probe.js"
    workflow.parent.mkdir(parents=True)
    workflow.write_text("export const meta = { name: 'probe', description: 'T' }\n", encoding="utf-8")

    ch = _compute_ch(candidate)

    reports = tmp_path / "reports"
    make_pass_report(reports / "design-review.json", ch)
    make_pass_report(reports / "static-validation.json", ch)
    # Interactive smoke without evidence array
    bad_smoke = {
        "status": "PASS",
        "candidateHash": ch,
        "evidence": [],
        "blockingIssues": [],
    }
    (reports / "interactive-smoke.json").write_text(json.dumps(bad_smoke, indent=2) + "\n", encoding="utf-8")
    make_pass_report(reports / "drift.json", ch, extra={"driftCheck": "PASS"})

    r = run_manifest([
        "--run-id", "run-001",
        "--candidate-root", str(candidate),
        "--workflow-name", "probe",
        "--workflow-script", str(workflow),
        "--design-review-report", str(reports / "design-review.json"),
        "--static-validation-report", str(reports / "static-validation.json"),
        "--interactive-smoke-report", str(reports / "interactive-smoke.json"),
        "--drift-report", str(reports / "drift.json"),
        "--out", str(tmp_path / "out.json"),
        "--json",
    ])
    assert r.returncode != 0, r.stdout
    payload = json.loads(r.stdout)
    assert payload["status"] == "BLOCKED_PUBLISH"


def test_manifest_blocks_missing_drift_check_pass(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate"
    workflow = candidate / ".claude" / "workflows" / "probe.js"
    workflow.parent.mkdir(parents=True)
    workflow.write_text("export const meta = { name: 'probe', description: 'T' }\n", encoding="utf-8")

    ch = _compute_ch(candidate)

    reports = tmp_path / "reports"
    make_pass_report(reports / "design-review.json", ch)
    make_pass_report(reports / "static-validation.json", ch)
    make_pass_report(reports / "interactive-smoke.json", ch, extra={"interactiveEvidence": [{"step": "x", "status": "ok"}]})
    # Drift without driftCheck PASS
    bad_drift = {
        "status": "PASS",
        "candidateHash": ch,
        "evidence": ["/tmp/e.json"],
        "blockingIssues": [],
        "driftCheck": "FAIL",
    }
    (reports / "drift.json").write_text(json.dumps(bad_drift, indent=2) + "\n", encoding="utf-8")

    r = run_manifest([
        "--run-id", "run-001",
        "--candidate-root", str(candidate),
        "--workflow-name", "probe",
        "--workflow-script", str(workflow),
        "--design-review-report", str(reports / "design-review.json"),
        "--static-validation-report", str(reports / "static-validation.json"),
        "--interactive-smoke-report", str(reports / "interactive-smoke.json"),
        "--drift-report", str(reports / "drift.json"),
        "--out", str(tmp_path / "out.json"),
        "--json",
    ])
    assert r.returncode != 0, r.stdout
    payload = json.loads(r.stdout)
    assert payload["status"] == "BLOCKED_PUBLISH"


def test_manifest_asset_scope_rejects_external_path(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate"
    workflow = candidate / ".claude" / "workflows" / "probe.js"
    workflow.parent.mkdir(parents=True)
    workflow.write_text("export const meta = { name: 'probe', description: 'T' }\n", encoding="utf-8")
    # Create a file outside managed prefixes
    (candidate / "unmanaged.txt").write_text("bad", encoding="utf-8")

    r = run_manifest([
        "--run-id", "run-001",
        "--candidate-root", str(candidate),
        "--workflow-name", "probe",
        "--workflow-script", str(workflow),
        "--design-review-report", str(tmp_path / "nope.json"),
        "--static-validation-report", str(tmp_path / "nope.json"),
        "--interactive-smoke-report", str(tmp_path / "nope.json"),
        "--drift-report", str(tmp_path / "nope.json"),
        "--out", str(tmp_path / "out.json"),
        "--json",
    ])
    assert r.returncode != 0, r.stdout
    payload = json.loads(r.stdout)
    assert payload["status"] == "BLOCKED_PUBLISH"


def test_manifest_blocks_workflow_script_inside_candidate_but_outside_managed_assets(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate"
    workflow = candidate / "probe.js"
    workflow.parent.mkdir(parents=True)
    workflow.write_text("export const meta = { name: 'probe', description: 'T' }\n", encoding="utf-8")
    managed_asset = candidate / ".claude" / "skills" / "probe" / "SKILL.md"
    managed_asset.parent.mkdir(parents=True)
    managed_asset.write_text("# Probe\n", encoding="utf-8")

    r = run_manifest([
        "--run-id", "run-001",
        "--candidate-root", str(candidate),
        "--workflow-name", "probe",
        "--workflow-script", str(workflow),
        "--design-review-report", str(tmp_path / "nope.json"),
        "--static-validation-report", str(tmp_path / "nope.json"),
        "--interactive-smoke-report", str(tmp_path / "nope.json"),
        "--drift-report", str(tmp_path / "nope.json"),
        "--out", str(tmp_path / "out.json"),
        "--json",
    ])

    assert r.returncode == 1
    payload = json.loads(r.stdout)
    assert payload["status"] == "BLOCKED_PUBLISH"
    assert any("not in managed assets list" in issue for issue in payload["blockingIssues"])


# ── Adversarial: builder input validation ──────────────────────────

def test_manifest_rejects_empty_run_id(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate"
    workflow = candidate / ".claude" / "workflows" / "probe.js"
    workflow.parent.mkdir(parents=True)
    workflow.write_text("export const meta = { name: 'probe', description: 'T' }\n", encoding="utf-8")

    r = run_manifest([
        "--run-id", "",
        "--candidate-root", str(candidate),
        "--workflow-name", "probe",
        "--workflow-script", str(workflow),
        "--design-review-report", str(tmp_path / "nope.json"),
        "--static-validation-report", str(tmp_path / "nope.json"),
        "--interactive-smoke-report", str(tmp_path / "nope.json"),
        "--drift-report", str(tmp_path / "nope.json"),
        "--out", str(tmp_path / "out.json"),
        "--json",
    ])
    assert r.returncode != 0, r.stdout
    payload = json.loads(r.stdout)
    assert payload["status"] == "BLOCKED_PUBLISH"


def test_manifest_rejects_whitespace_run_id(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate"
    workflow = candidate / ".claude" / "workflows" / "probe.js"
    workflow.parent.mkdir(parents=True)
    workflow.write_text("export const meta = { name: 'probe', description: 'T' }\n", encoding="utf-8")

    r = run_manifest([
        "--run-id", "   ",
        "--candidate-root", str(candidate),
        "--workflow-name", "probe",
        "--workflow-script", str(workflow),
        "--design-review-report", str(tmp_path / "nope.json"),
        "--static-validation-report", str(tmp_path / "nope.json"),
        "--interactive-smoke-report", str(tmp_path / "nope.json"),
        "--drift-report", str(tmp_path / "nope.json"),
        "--out", str(tmp_path / "out.json"),
        "--json",
    ])
    assert r.returncode != 0, r.stdout
    payload = json.loads(r.stdout)
    assert payload["status"] == "BLOCKED_PUBLISH"


def test_manifest_rejects_empty_workflow_name(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate"
    workflow = candidate / ".claude" / "workflows" / "probe.js"
    workflow.parent.mkdir(parents=True)
    workflow.write_text("export const meta = { name: 'probe', description: 'T' }\n", encoding="utf-8")

    r = run_manifest([
        "--run-id", "run-001",
        "--candidate-root", str(candidate),
        "--workflow-name", "",
        "--workflow-script", str(workflow),
        "--design-review-report", str(tmp_path / "nope.json"),
        "--static-validation-report", str(tmp_path / "nope.json"),
        "--interactive-smoke-report", str(tmp_path / "nope.json"),
        "--drift-report", str(tmp_path / "nope.json"),
        "--out", str(tmp_path / "out.json"),
        "--json",
    ])
    assert r.returncode != 0, r.stdout
    payload = json.loads(r.stdout)
    assert payload["status"] == "BLOCKED_PUBLISH"


def test_manifest_rejects_nonexistent_workflow_script(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    (candidate / ".claude" / "workflows").mkdir(parents=True)
    (candidate / ".claude" / "workflows" / "probe.js").write_text(
        "export const meta = { name: 'probe', description: 'T' }\n", encoding="utf-8"
    )

    r = run_manifest([
        "--run-id", "run-001",
        "--candidate-root", str(candidate),
        "--workflow-name", "probe",
        "--workflow-script", str(candidate / ".claude" / "workflows" / "ghost.js"),
        "--design-review-report", str(tmp_path / "nope.json"),
        "--static-validation-report", str(tmp_path / "nope.json"),
        "--interactive-smoke-report", str(tmp_path / "nope.json"),
        "--drift-report", str(tmp_path / "nope.json"),
        "--out", str(tmp_path / "out.json"),
        "--json",
    ])
    assert r.returncode != 0, r.stdout
    payload = json.loads(r.stdout)
    assert payload["status"] == "BLOCKED_PUBLISH"


def test_manifest_rejects_workflow_script_not_in_assets(tmp_path: Path) -> None:
    """Workflow script inside candidate root but outside managed prefixes."""
    candidate = tmp_path / "candidate"
    workflow = candidate / "orphan.js"
    workflow.parent.mkdir(parents=True, exist_ok=True)
    workflow.write_text("export const meta = { name: 'orphan', description: 'T' }\n", encoding="utf-8")

    r = run_manifest([
        "--run-id", "run-001",
        "--candidate-root", str(candidate),
        "--workflow-name", "orphan",
        "--workflow-script", str(workflow),
        "--design-review-report", str(tmp_path / "nope.json"),
        "--static-validation-report", str(tmp_path / "nope.json"),
        "--interactive-smoke-report", str(tmp_path / "nope.json"),
        "--drift-report", str(tmp_path / "nope.json"),
        "--out", str(tmp_path / "out.json"),
        "--json",
    ])
    assert r.returncode != 0, r.stdout
    payload = json.loads(r.stdout)
    assert payload["status"] == "BLOCKED_PUBLISH"


def test_manifest_blocks_missing_blocking_issues_in_report(tmp_path: Path) -> None:
    """Report without blockingIssues field must fail."""
    candidate = tmp_path / "candidate"
    workflow = candidate / ".claude" / "workflows" / "probe.js"
    workflow.parent.mkdir(parents=True)
    workflow.write_text("export const meta = { name: 'probe', description: 'T' }\n", encoding="utf-8")

    ch = _compute_ch(candidate)

    reports = tmp_path / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    bad_report = {"status": "PASS", "candidateHash": ch, "evidence": ["/tmp/e.json"]}
    (reports / "design-review.json").write_text(json.dumps(bad_report, indent=2) + "\n", encoding="utf-8")

    r = run_manifest([
        "--run-id", "run-001",
        "--candidate-root", str(candidate),
        "--workflow-name", "probe",
        "--workflow-script", str(workflow),
        "--design-review-report", str(reports / "design-review.json"),
        "--static-validation-report", str(reports / "design-review.json"),
        "--interactive-smoke-report", str(reports / "design-review.json"),
        "--drift-report", str(reports / "design-review.json"),
        "--out", str(tmp_path / "out.json"),
        "--json",
    ])
    assert r.returncode != 0, r.stdout
    payload = json.loads(r.stdout)
    assert payload["status"] == "BLOCKED_PUBLISH"


def test_manifest_blocks_non_list_blocking_issues(tmp_path: Path) -> None:
    """Report with blockingIssues as non-list must fail."""
    candidate = tmp_path / "candidate"
    workflow = candidate / ".claude" / "workflows" / "probe.js"
    workflow.parent.mkdir(parents=True)
    workflow.write_text("export const meta = { name: 'probe', description: 'T' }\n", encoding="utf-8")

    ch = _compute_ch(candidate)

    reports = tmp_path / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    bad_report = {"status": "PASS", "candidateHash": ch, "evidence": ["/tmp/e.json"], "blockingIssues": "not-a-list"}
    (reports / "design-review.json").write_text(json.dumps(bad_report, indent=2) + "\n", encoding="utf-8")

    r = run_manifest([
        "--run-id", "run-001",
        "--candidate-root", str(candidate),
        "--workflow-name", "probe",
        "--workflow-script", str(workflow),
        "--design-review-report", str(reports / "design-review.json"),
        "--static-validation-report", str(reports / "design-review.json"),
        "--interactive-smoke-report", str(reports / "design-review.json"),
        "--drift-report", str(reports / "design-review.json"),
        "--out", str(tmp_path / "out.json"),
        "--json",
    ])
    assert r.returncode != 0, r.stdout
    payload = json.loads(r.stdout)
    assert payload["status"] == "BLOCKED_PUBLISH"


def test_manifest_gate_blocks_when_manifest_incomplete(tmp_path: Path) -> None:
    """Manifest gate must not PASS when candidate root is empty."""
    candidate = tmp_path / "empty-candidate"
    candidate.mkdir()

    r = run_manifest([
        "--run-id", "run-001",
        "--candidate-root", str(candidate),
        "--workflow-name", "probe",
        "--workflow-script", str(candidate / ".claude" / "workflows" / "probe.js"),
        "--design-review-report", str(tmp_path / "nope.json"),
        "--static-validation-report", str(tmp_path / "nope.json"),
        "--interactive-smoke-report", str(tmp_path / "nope.json"),
        "--drift-report", str(tmp_path / "nope.json"),
        "--out", str(tmp_path / "out.json"),
        "--json",
    ])
    assert r.returncode != 0, r.stdout
    payload = json.loads(r.stdout)
    gates = payload.get("gates", [])
    manifest_gates = [g for g in gates if g.get("name") == "manifest"]
    assert len(manifest_gates) == 0 or manifest_gates[0]["status"] != "PASS", (
        "Manifest gate must not be PASS when manifest is structurally incomplete"
    )
