from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / ".claude" / "scripts" / "build-native-develop-evidence.py"
MANAGED_ASSETS = ROOT / ".claude" / "scripts" / "managed-assets.py"


def run_script(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args, "--json"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def run_managed_assets(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(MANAGED_ASSETS), *args, "--json"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def write_candidate(root: Path, content: str = "return { status: 'PASS' }\n") -> Path:
    script = root / ".claude" / "workflows" / "probe.js"
    script.parent.mkdir(parents=True)
    script.write_text(content, encoding="utf-8")
    return script


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def generation_report(candidate_file: Path, **overrides: object) -> dict:
    payload: dict[str, object] = {
        "schema_version": 1,
        "schema_name": "native-workflow-js-generation",
        "status": "PASS",
        "candidate_script": str(candidate_file.resolve()),
        "errors": [],
    }
    payload.update(overrides)
    return payload


def validation_report(candidate_file: Path, **overrides: object) -> dict:
    payload: dict[str, object] = {
        "schema_version": 1,
        "schema_name": "native-workflow-js-validation",
        "status": "PASS",
        "script": str(candidate_file.resolve()),
        "errors": [],
    }
    payload.update(overrides)
    return payload


def load_json(completed: subprocess.CompletedProcess[str]) -> dict:
    return json.loads(completed.stdout)


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def candidate_hash(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return f"sha256:{digest.hexdigest()}"


def smoke_report(candidate_root: Path, script_path: Path, **overrides: object) -> dict:
    payload: dict[str, object] = {
        "schema_name": "native-workflow-interactive-smoke",
        "schema_version": 1,
        "status": "PASS",
        "return_code": 0,
        "workflow": "probe",
        "scriptPath": str(script_path.resolve()),
        "scriptHash": f"sha256:{file_hash(script_path)}",
        "candidateHash": candidate_hash(candidate_root),
        "expectedStatus": "PASS",
        "scenario": "pass-smoke-001",
        "evidenceProfile": "full",
        "runIds": ["wf_c719aa99-826"],
        "evidence": {
            "workflow_invoked": True,
            "async_launched": True,
            "agent_started": True,
            "schema_result": True,
            "completed_pass": True,
            "completed_blocked": False,
        },
        "blockingIssues": [],
    }
    payload.update(overrides)
    return payload


def managed_report(
    candidate_file: Path,
    manifest_file: Path,
    target_root: Path,
    run_root: Path,
    **overrides: object,
) -> dict:
    relative_path = ".claude/workflows/probe.js"
    digest = file_hash(candidate_file)
    payload: dict[str, object] = {
        "schema_version": 1,
        "schema_name": "managed-change-result",
        "status": "PASS",
        "target_root": str(target_root.resolve()),
        "source_root": str(candidate_file.parents[2].resolve()),
        "run_root": str(run_root.resolve()),
        "manifest_path": str(manifest_file.resolve()),
        "applied": [
            {
                "relative_path": relative_path,
                "action": "create",
                "applied_sha256": digest,
            }
        ],
        "skipped": [],
        "conflicts": [],
    }
    payload.update(overrides)
    return payload


def write_target_copy(target_root: Path, candidate_file: Path, content: str | None = None) -> Path:
    target_file = target_root / ".claude" / "workflows" / "probe.js"
    target_file.parent.mkdir(parents=True, exist_ok=True)
    target_file.write_text(content if content is not None else candidate_file.read_text(encoding="utf-8"), encoding="utf-8")
    return target_file


def write_actual_managed_report(run_root: Path, payload: dict) -> Path:
    report = run_root / "outputs" / "managed-change-result.json"
    write_json(report, payload)
    return report


def write_managed_manifest(path: Path, candidate_file: Path, digest: str | None = None) -> None:
    write_json(
        path,
        {
            "manifest_version": 1,
            "entries": [
                {
                    "relative_path": ".claude/workflows/probe.js",
                    "last_applied_hash": digest or file_hash(candidate_file),
                }
            ],
        },
    )


def test_generation_evidence_includes_candidate_tree_hash_and_refs(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate"
    report = tmp_path / "generation.json"
    script = write_candidate(candidate)
    write_json(report, generation_report(script))

    completed = run_script("generation", "--candidate-root", str(candidate), "--report", str(report))

    assert completed.returncode == 0
    payload = load_json(completed)
    assert payload["status"] == "PASS"
    assert payload["candidateHash"].startswith("sha256:")
    assert payload["candidateRefs"] == [str(script.resolve())]
    assert payload["workflowScriptPath"] == str(script.resolve())


def test_candidate_tree_hash_changes_when_supporting_asset_changes(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate"
    report = tmp_path / "generation.json"
    script = write_candidate(candidate)
    write_json(report, generation_report(script))
    first = load_json(run_script("generation", "--candidate-root", str(candidate), "--report", str(report)))
    supporting = candidate / ".claude" / "skills" / "probe" / "SKILL.md"
    supporting.parent.mkdir(parents=True)
    supporting.write_text("# Probe\n", encoding="utf-8")

    second = load_json(run_script("generation", "--candidate-root", str(candidate), "--report", str(report)))

    assert first["candidateHash"] != second["candidateHash"]


@pytest.mark.parametrize(
    ("stage", "payload", "expected_text"),
    [
        ("generation", {"status": "PASS"}, "native-workflow-js-generation"),
        ("validation", {"status": "PASS"}, "native-workflow-js-validation"),
    ],
)
def test_report_evidence_rejects_arbitrary_pass_json(
    tmp_path: Path,
    stage: str,
    payload: dict,
    expected_text: str,
) -> None:
    candidate = tmp_path / "candidate"
    report = tmp_path / f"{stage}.json"
    write_candidate(candidate)
    write_json(report, payload)

    completed = run_script(stage, "--candidate-root", str(candidate), "--report", str(report))

    assert completed.returncode == 1
    assert expected_text in " ".join(load_json(completed)["blockingIssues"])


def test_validation_evidence_rejects_script_outside_candidate(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate"
    report = tmp_path / "validation.json"
    write_candidate(candidate)
    other = tmp_path / "other.js"
    other.write_text("return { status: 'PASS' }\n", encoding="utf-8")
    write_json(report, validation_report(other))

    completed = run_script("validation", "--candidate-root", str(candidate), "--report", str(report))

    assert completed.returncode == 1
    assert "candidate tree" in " ".join(load_json(completed)["blockingIssues"])


def test_validation_evidence_rejects_non_workflow_script_inside_candidate(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate"
    report = tmp_path / "validation.json"
    write_candidate(candidate)
    supporting = candidate / ".claude" / "scripts" / "probe.js"
    supporting.parent.mkdir(parents=True)
    supporting.write_text("return { status: 'PASS' }\n", encoding="utf-8")
    write_json(report, validation_report(supporting))

    completed = run_script("validation", "--candidate-root", str(candidate), "--report", str(report))

    assert completed.returncode == 1
    assert ".claude/workflows" in " ".join(load_json(completed)["blockingIssues"])


def test_smoke_evidence_fails_when_report_is_missing(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate"
    write_candidate(candidate)

    completed = run_script(
        "smoke",
        "--candidate-root",
        str(candidate),
        "--status",
        "PASS",
        "--evidence",
        str(tmp_path / "missing.json"),
    )

    assert completed.returncode == 1
    assert "not found" in load_json(completed)["blockingIssues"][0]


def test_smoke_evidence_rejects_raw_transcript(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate"
    transcript = tmp_path / "raw.jsonl"
    write_candidate(candidate)
    transcript.write_text('{"type":"notification","content":"PASS"}\n', encoding="utf-8")

    completed = run_script(
        "smoke",
        "--candidate-root",
        str(candidate),
        "--status",
        "PASS",
        "--evidence",
        str(transcript),
    )

    assert completed.returncode == 1
    assert "evaluator report" in load_json(completed)["blockingIssues"][0]


@pytest.mark.parametrize(
    ("mutation", "expected_text"),
    [
        ({"return_code": 1}, "did not pass"),
        ({"runIds": []}, "runIds"),
        ({"scriptPath": ""}, "scriptPath"),
        ({"scriptHash": "sha256:bad"}, "scriptHash"),
        ({"candidateHash": "sha256:bad"}, "candidateHash"),
        ({"expectedStatus": "BLOCKED"}, "expectedStatus"),
        ({"scenario": ""}, "scenario"),
        ({"evidenceProfile": "unknown"}, "evidenceProfile"),
        ({"evidenceProfile": "early-blocker"}, "early-blocker"),
        ({"evidence": {"async_launched": True, "agent_started": True, "schema_result": True, "completed_pass": True}}, "workflow_invoked"),
        ({"evidence": {"workflow_invoked": True, "async_launched": True, "schema_result": True, "completed_pass": True}}, "agent_started"),
        ({"evidence": {"workflow_invoked": True, "async_launched": True, "agent_started": True, "completed_pass": True}}, "schema_result"),
        ({"evidence": {"workflow_invoked": True, "async_launched": True, "agent_started": True, "schema_result": True}}, "completed_pass"),
    ],
)
def test_smoke_evidence_rejects_incomplete_evaluator_report(
    tmp_path: Path,
    mutation: dict,
    expected_text: str,
) -> None:
    candidate = tmp_path / "candidate"
    report = tmp_path / "smoke-eval.json"
    candidate_file = write_candidate(candidate)
    write_json(report, smoke_report(candidate, candidate_file, **mutation))

    completed = run_script(
        "smoke",
        "--candidate-root",
        str(candidate),
        "--status",
        "PASS",
        "--evidence",
        str(report),
    )

    assert completed.returncode == 1
    assert expected_text in " ".join(load_json(completed)["blockingIssues"])


def test_smoke_evidence_accepts_complete_evaluator_pass_report(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate"
    report = tmp_path / "smoke-eval.json"
    candidate_file = write_candidate(candidate)
    write_json(report, smoke_report(candidate, candidate_file))

    completed = run_script(
        "smoke",
        "--candidate-root",
        str(candidate),
        "--status",
        "PASS",
        "--evidence",
        str(report),
    )

    assert completed.returncode == 0, completed.stderr or completed.stdout
    payload = load_json(completed)
    assert payload["status"] == "PASS"
    assert payload["smokeReports"][0]["reportPath"] == str(report.resolve())
    assert payload["smokeReports"][0]["reportHash"].startswith("sha256:")
    assert payload["smokeReports"][0]["scriptPath"] == str(candidate_file.resolve())
    assert payload["smokeReports"][0]["evidence"]["completed_pass"] is True


def test_smoke_evidence_rejects_report_for_different_script_path(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate"
    report = tmp_path / "smoke-eval.json"
    write_candidate(candidate)
    write_json(report, smoke_report(candidate, candidate / ".claude" / "workflows" / "probe.js", scriptPath=str((tmp_path / "other" / ".claude" / "workflows" / "probe.js").resolve())))

    completed = run_script(
        "smoke",
        "--candidate-root",
        str(candidate),
        "--status",
        "PASS",
        "--evidence",
        str(report),
    )

    assert completed.returncode == 1
    assert "scriptPath" in " ".join(load_json(completed)["blockingIssues"])


def test_apply_evidence_rejects_empty_manifest_path(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate"
    target = tmp_path / "target"
    run_root = tmp_path / "run"
    candidate_file = write_candidate(candidate)
    write_target_copy(target, candidate_file)
    report = write_actual_managed_report(
        run_root,
        managed_report(candidate_file, tmp_path / "unused.json", target, run_root, manifest_path=""),
    )

    completed = run_script("apply", "--candidate-root", str(candidate), "--target-root", str(target), "--report", str(report))

    assert completed.returncode == 1
    assert "manifest_path" in load_json(completed)["blockingIssues"][0]


def test_apply_evidence_rejects_uncovered_candidate(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate"
    target = tmp_path / "target"
    run_root = tmp_path / "run"
    manifest = target / ".workflowprogram" / "managed-files.json"
    candidate_file = write_candidate(candidate)
    write_target_copy(target, candidate_file)
    write_managed_manifest(manifest, candidate_file)
    report = write_actual_managed_report(run_root, managed_report(candidate_file, manifest, target, run_root, applied=[]))

    completed = run_script("apply", "--candidate-root", str(candidate), "--target-root", str(target), "--report", str(report))

    assert completed.returncode == 1
    assert "does not cover" in load_json(completed)["blockingIssues"][0]


def test_apply_evidence_rejects_hash_mismatch(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate"
    target = tmp_path / "target"
    run_root = tmp_path / "run"
    manifest = target / ".workflowprogram" / "managed-files.json"
    candidate_file = write_candidate(candidate)
    write_target_copy(target, candidate_file)
    write_managed_manifest(manifest, candidate_file)
    bad_entry = {
        "relative_path": ".claude/workflows/probe.js",
        "action": "create",
        "applied_sha256": "bad-hash",
    }
    report = write_actual_managed_report(
        run_root,
        managed_report(candidate_file, manifest, target, run_root, applied=[bad_entry]),
    )

    completed = run_script("apply", "--candidate-root", str(candidate), "--target-root", str(target), "--report", str(report))

    assert completed.returncode == 1
    assert "hash does not match" in load_json(completed)["blockingIssues"][0]


def test_apply_evidence_rejects_manifest_outside_target_root(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate"
    target = tmp_path / "target"
    run_root = tmp_path / "run"
    manifest = tmp_path / "forged" / "managed-files.json"
    candidate_file = write_candidate(candidate)
    write_target_copy(target, candidate_file)
    write_managed_manifest(manifest, candidate_file)
    report = write_actual_managed_report(run_root, managed_report(candidate_file, manifest, target, run_root))

    completed = run_script("apply", "--candidate-root", str(candidate), "--target-root", str(target), "--report", str(report))

    assert completed.returncode == 1
    assert "manifest_path" in " ".join(load_json(completed)["blockingIssues"])


def test_apply_evidence_rejects_target_file_drift(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate"
    target = tmp_path / "target"
    run_root = tmp_path / "run"
    manifest = target / ".workflowprogram" / "managed-files.json"
    candidate_file = write_candidate(candidate)
    write_target_copy(target, candidate_file, "return { status: 'DRIFTED' }\n")
    write_managed_manifest(manifest, candidate_file)
    report = write_actual_managed_report(run_root, managed_report(candidate_file, manifest, target, run_root))

    completed = run_script("apply", "--candidate-root", str(candidate), "--target-root", str(target), "--report", str(report))

    assert completed.returncode == 1
    assert "target file" in " ".join(load_json(completed)["blockingIssues"])


def test_apply_evidence_rejects_source_root_mismatch(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate"
    target = tmp_path / "target"
    run_root = tmp_path / "run"
    manifest = target / ".workflowprogram" / "managed-files.json"
    candidate_file = write_candidate(candidate)
    write_target_copy(target, candidate_file)
    write_managed_manifest(manifest, candidate_file)
    report = write_actual_managed_report(
        run_root,
        managed_report(candidate_file, manifest, target, run_root, source_root=str((tmp_path / "other").resolve())),
    )

    completed = run_script("apply", "--candidate-root", str(candidate), "--target-root", str(target), "--report", str(report))

    assert completed.returncode == 1
    assert "source_root" in " ".join(load_json(completed)["blockingIssues"])


def test_apply_evidence_rejects_nested_result_without_matching_persisted_report(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate"
    target = tmp_path / "target"
    run_root = tmp_path / "run"
    wrapper = tmp_path / "generation.json"
    manifest = target / ".workflowprogram" / "managed-files.json"
    candidate_file = write_candidate(candidate)
    write_target_copy(target, candidate_file)
    write_managed_manifest(manifest, candidate_file)
    managed = managed_report(candidate_file, manifest, target, run_root)
    write_actual_managed_report(run_root, {**managed, "producer_version": "different"})
    write_json(wrapper, {"schema_name": "native-workflow-js-generation", "status": "PASS", "managed_result": managed})

    completed = run_script("apply", "--candidate-root", str(candidate), "--target-root", str(target), "--report", str(wrapper))

    assert completed.returncode == 1
    assert "persisted managed-change-result" in " ".join(load_json(completed)["blockingIssues"])


def test_apply_evidence_accepts_actual_managed_assets_result(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate"
    target = tmp_path / "target"
    run_root = target / ".workflowprogram" / "runs" / "run-001"
    write_candidate(candidate)

    applied = run_managed_assets(
        "apply-staged",
        "--target-root", str(target),
        "--source-root", str(candidate),
        "--run-root", str(run_root),
    )

    assert applied.returncode == 0, applied.stderr or applied.stdout
    report = run_root / "outputs" / "managed-change-result.json"
    completed = run_script("apply", "--candidate-root", str(candidate), "--target-root", str(target), "--report", str(report))

    assert completed.returncode == 0, completed.stderr or completed.stdout
    payload = load_json(completed)
    assert payload["status"] == "PASS"
    assert payload["targetRoot"] == str(target.resolve())
    assert payload["applyManifest"]["manifestPath"] == str((target / ".workflowprogram" / "managed-files.json").resolve())


def test_apply_evidence_accepts_nested_managed_result(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate"
    report = tmp_path / "generation.json"
    target = tmp_path / "target"
    run_root = tmp_path / "run"
    manifest = target / ".workflowprogram" / "managed-files.json"
    candidate_file = write_candidate(candidate)
    write_target_copy(target, candidate_file)
    write_managed_manifest(manifest, candidate_file)
    managed = managed_report(candidate_file, manifest, target, run_root)
    actual_report = write_actual_managed_report(run_root, managed)
    write_json(
        report,
        {
            "schema_name": "native-workflow-js-generation",
            "status": "PASS",
            "managed_result": managed,
        },
    )

    completed = run_script("apply", "--candidate-root", str(candidate), "--target-root", str(target), "--report", str(report))

    assert completed.returncode == 0, completed.stderr or completed.stdout
    assert load_json(completed)["applyManifest"]["reportPath"] == str(actual_report.resolve())
