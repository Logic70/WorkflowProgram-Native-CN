from __future__ import annotations

import json
import hashlib
import subprocess
import sys
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / ".claude" / "scripts" / "target-workflow-runner.py"
VALIDATOR = ROOT / ".claude" / "scripts" / "validate-target-runtime-state.py"
FINALIZER = ROOT / ".claude" / "scripts" / "target-runtime-finalizer.py"
GENERATE_RUNTIME = ROOT / ".claude" / "scripts" / "generate-target-runtime.py"
GENERATED_RUNTIME_VALIDATOR = ROOT / ".claude" / "scripts" / "validate-generated-runtime.py"
PUBLISH_STATE_VALIDATOR = ROOT / ".claude" / "scripts" / "validate-target-publish-state.py"
APPLY_CLAUDE_GUARD = ROOT / ".claude" / "scripts" / "apply-target-claude-guard.py"
SPEC_VALIDATOR = ROOT / ".claude" / "scripts" / "validate-workflow-spec.py"
SPEC = ROOT / "tests" / "spec-fixtures" / "valid-minimal.yaml"


def write_target_fixture(tmp_path: Path, *, include_owner: bool = True) -> Path:
    target = tmp_path / "target"
    target.mkdir(parents=True)
    if include_owner:
        skill = target / ".claude" / "skills" / "example" / "SKILL.md"
        skill.parent.mkdir(parents=True)
        skill.write_text("---\nname: example-skill\n---\n", encoding="utf-8")
    return target


def write_persistent_spec(target: Path, spec_path: Path = SPEC) -> Path:
    destination = target / ".workflowprogram" / "design" / "workflow-spec.yaml"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(spec_path.read_text(encoding="utf-8"), encoding="utf-8")
    return destination


def generate_runtime_for_target(target: Path, spec_path: Path) -> None:
    out_root = target / ".workflowprogram" / "runtime"
    completed = subprocess.run(
        [
            sys.executable,
            str(GENERATE_RUNTIME),
            "--spec",
            str(spec_path),
            "--out-root",
            str(out_root),
            "--json",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout


def write_wrapper_command(target: Path) -> None:
    command_path = target / ".claude" / "commands" / "example.md"
    command_path.parent.mkdir(parents=True, exist_ok=True)
    command_path.write_text(
        """---
description: Wrapper-only command
---

Run `.workflowprogram/runtime/workflow-entry.py run --request "$ARGUMENTS"`.
""",
        encoding="utf-8",
    )


def apply_claude_guard(target: Path, spec_path: Path, run_root: Path) -> dict:
    completed = subprocess.run(
        [
            sys.executable,
            str(APPLY_CLAUDE_GUARD),
            "--spec",
            str(spec_path),
            "--target-root",
            str(target),
            "--run-root",
            str(run_root),
            "--json",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout
    return json.loads(completed.stdout)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_manual_evidence(
    run_root: Path,
    node_id: str,
    *,
    input_refs: list[str],
    output_refs: list[str],
    outputs: list[str],
    provider: str = "current_agent",
    operator: str = "deepseek-current-session",
) -> None:
    evidence_dir = run_root / "outputs" / "stages" / "executor-evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1,
        "provider": provider,
        "node_id": node_id,
        "status": "PASS",
        "operator": operator,
        "started_at": "2026-05-24T00:00:00Z",
        "completed_at": "2026-05-24T00:00:01Z",
        "input_refs": input_refs,
        "output_refs": output_refs,
        "outputs": [
            {"path": rel, "sha256": sha256_file(run_root / rel)}
            for rel in outputs
        ],
    }
    (evidence_dir / f"{node_id}.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def test_target_managed_runtime_passes(tmp_path: Path) -> None:
    target = write_target_fixture(tmp_path)
    run_root = tmp_path / "run"
    completed = subprocess.run(
        [
            sys.executable,
            str(RUNNER),
            "run",
            "--spec",
            str(SPEC),
            "--run-root",
            str(run_root),
            "--target-root",
            str(target),
            "--entry-skill",
            "example",
            "--runtime-provider",
            "fixture_host",
            "--json",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout
    payload = json.loads(completed.stdout)
    assert payload["status"] == "PASS"
    assert (run_root / "target-state.json").exists()
    assert (run_root / "target-events.jsonl").exists()
    assert (run_root / "artifact-provenance.json").exists()
    assert (run_root / "outputs" / "target-workflow" / "implementation-summary.md").exists()
    assert not (target / "outputs" / "target-workflow" / "implementation-summary.md").exists()

    validation = subprocess.run(
        [sys.executable, str(VALIDATOR), "--state", str(run_root / "target-state.json"), "--json"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert validation.returncode == 0, validation.stderr or validation.stdout
    assert json.loads(validation.stdout)["status"] == "PASS"


def test_unsupported_executor_provider_fails_without_publish(tmp_path: Path) -> None:
    target = write_target_fixture(tmp_path)
    run_root = tmp_path / "run"
    completed = subprocess.run(
        [
            sys.executable,
            str(RUNNER),
            "run",
            "--spec",
            str(SPEC),
            "--run-root",
            str(run_root),
            "--target-root",
            str(target),
            "--entry-skill",
            "example",
            "--runtime-provider",
            "claude_cli",
            "--json",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 1
    payload = json.loads(completed.stdout)
    assert payload["status"] == "FAIL"
    assert payload["failure_kind"] == "environment"
    assert "unsupported executor provider" in payload["failure_reason"]
    assert not (target / "outputs" / "target-workflow").exists()


def test_default_current_agent_provider_blocks_for_executor_evidence(tmp_path: Path) -> None:
    target = write_target_fixture(tmp_path)
    run_root = tmp_path / "run"
    completed = subprocess.run(
        [
            sys.executable,
            str(RUNNER),
            "run",
            "--spec",
            str(SPEC),
            "--run-root",
            str(run_root),
            "--target-root",
            str(target),
            "--entry-skill",
            "example",
            "--json",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 2
    payload = json.loads(completed.stdout)
    assert payload["status"] == "BLOCKED"
    assert payload["failure_kind"] == "none"
    assert payload["blocked_phase"] == "executor_evidence"
    assert payload["current_node"]["node_id"] == "intake"
    assert payload["current_node"]["executor_evidence_path"] == "outputs/stages/executor-evidence/intake.json"
    assert payload["current_node"]["input_refs"] == ["$ARGUMENTS"]
    assert payload["current_node"]["output_refs"] == ["outputs/target-workflow/intake-summary.md"]
    state = json.loads((run_root / "target-state.json").read_text(encoding="utf-8"))
    assert state["status"] == "BLOCKED"
    assert state["blocked_phase"] == "executor_evidence"
    node_payload = json.loads((run_root / "node-results.json").read_text(encoding="utf-8"))
    assert node_payload["nodes"][0]["status"] == "BLOCKED"

    validation = subprocess.run(
        [sys.executable, str(VALIDATOR), "--state", str(run_root / "target-state.json"), "--json"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert validation.returncode == 0, validation.stderr or validation.stdout
    assert not (target / "outputs" / "target-workflow").exists()


def test_current_agent_evidence_requires_finalizer_before_pass(tmp_path: Path) -> None:
    target = write_target_fixture(tmp_path)
    run_root = tmp_path / "run"
    (run_root / "outputs" / "target-workflow").mkdir(parents=True)
    intake = run_root / "outputs" / "target-workflow" / "intake-summary.md"
    implementation = run_root / "outputs" / "target-workflow" / "implementation-summary.md"
    intake.write_text("# Intake\n", encoding="utf-8")
    implementation.write_text("# Implementation\n", encoding="utf-8")
    write_manual_evidence(
        run_root,
        "intake",
        input_refs=["$ARGUMENTS"],
        output_refs=["outputs/target-workflow/intake-summary.md"],
        outputs=["outputs/target-workflow/intake-summary.md"],
    )
    write_manual_evidence(
        run_root,
        "implement",
        input_refs=["outputs/target-workflow/intake-summary.md"],
        output_refs=["outputs/target-workflow/implementation-summary.md"],
        outputs=["outputs/target-workflow/implementation-summary.md"],
    )

    completed = subprocess.run(
        [
            sys.executable,
            str(RUNNER),
            "run",
            "--spec",
            str(SPEC),
            "--run-root",
            str(run_root),
            "--target-root",
            str(target),
            "--entry-skill",
            "example",
            "--runtime-provider",
            "current_agent",
            "--json",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 2, completed.stderr or completed.stdout
    payload = json.loads(completed.stdout)
    assert payload["status"] == "BLOCKED"
    state = json.loads((run_root / "target-state.json").read_text(encoding="utf-8"))
    assert state["status"] == "BLOCKED"
    assert state["manual_finalizer_required"] is True

    validation = subprocess.run(
        [sys.executable, str(VALIDATOR), "--state", str(run_root / "target-state.json"), "--json"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert validation.returncode == 0, validation.stderr or validation.stdout

    finalized = subprocess.run(
        [
            sys.executable,
            str(FINALIZER),
            "--spec",
            str(SPEC),
            "--run-root",
            str(run_root),
            "--target-root",
            str(target),
            "--state",
            str(run_root / "target-state.json"),
            "--json",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert finalized.returncode == 0, finalized.stderr or finalized.stdout
    final_state = json.loads((run_root / "target-state.json").read_text(encoding="utf-8"))
    assert final_state["status"] == "PASS"
    assert final_state["finalizer_status"] == "PASS"
    assert (target / "outputs" / "target-workflow" / "implementation-summary.md").exists()


def test_target_runtime_finalizer_publishes_current_run_outputs(tmp_path: Path) -> None:
    target = write_target_fixture(tmp_path)
    run_root = tmp_path / "run"
    completed = subprocess.run(
        [
            sys.executable,
            str(RUNNER),
            "run",
            "--spec",
            str(SPEC),
            "--run-root",
            str(run_root),
            "--target-root",
            str(target),
            "--entry-skill",
            "example",
            "--runtime-provider",
            "fixture_host",
            "--json",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout

    finalized = subprocess.run(
        [
            sys.executable,
            str(FINALIZER),
            "--spec",
            str(SPEC),
            "--run-root",
            str(run_root),
            "--target-root",
            str(target),
            "--state",
            str(run_root / "target-state.json"),
            "--json",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert finalized.returncode == 0, finalized.stderr or finalized.stdout
    payload = json.loads(finalized.stdout)
    assert payload["status"] == "PASS"
    assert (target / "outputs" / "target-workflow" / "implementation-summary.md").exists()
    manifest = json.loads((target / "outputs" / "target-workflow" / "run-manifest.json").read_text(encoding="utf-8"))
    latest = json.loads((target / "outputs" / "target-workflow" / ".workflowprogram-latest.json").read_text(encoding="utf-8"))
    assert manifest["run_id"] == run_root.name
    assert latest["run_id"] == run_root.name
    assert json.loads((run_root / "target-state.json").read_text(encoding="utf-8"))["finalizer_status"] == "PASS"
    publish_validation = subprocess.run(
        [
            sys.executable,
            str(PUBLISH_STATE_VALIDATOR),
            "--spec",
            str(SPEC),
            "--target-root",
            str(target),
            "--run-root",
            str(run_root),
            "--json",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert publish_validation.returncode == 0, publish_validation.stderr or publish_validation.stdout
    assert json.loads(publish_validation.stdout)["status"] == "PASS"


def test_target_runtime_finalizer_blocks_report_mismatch(tmp_path: Path) -> None:
    target = write_target_fixture(tmp_path)
    run_root = tmp_path / "run"
    completed = subprocess.run(
        [
            sys.executable,
            str(RUNNER),
            "run",
            "--spec",
            str(SPEC),
            "--run-root",
            str(run_root),
            "--target-root",
            str(target),
            "--entry-skill",
            "example",
            "--runtime-provider",
            "fixture_host",
            "--json",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout
    summary_path = run_root / "outputs" / "stages" / "target-runtime-summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["status"] = "FAIL"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    finalized = subprocess.run(
        [
            sys.executable,
            str(FINALIZER),
            "--spec",
            str(SPEC),
            "--run-root",
            str(run_root),
            "--target-root",
            str(target),
            "--state",
            str(run_root / "target-state.json"),
            "--json",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert finalized.returncode == 1
    payload = json.loads(finalized.stdout)
    assert payload["status"] == "FAIL"
    state = json.loads((run_root / "target-state.json").read_text(encoding="utf-8"))
    assert state["status"] == "FAIL"
    assert state["finalizer_status"] == "FAIL"
    assert not (target / "outputs" / "target-workflow" / "run-manifest.json").exists()


def test_target_runtime_finalizer_blocks_doctor_contract_failure(tmp_path: Path) -> None:
    spec = yaml.safe_load(SPEC.read_text(encoding="utf-8"))
    spec["target_publish_policy"]["required_reports"].append(
        {
            "path": "outputs/stages/doctor.json",
            "status_field": "status",
            "pass_values": ["PASS"],
        }
    )
    spec_path = tmp_path / "doctor-required.yaml"
    spec_path.write_text(yaml.safe_dump(spec, allow_unicode=True, sort_keys=False), encoding="utf-8")
    target = write_target_fixture(tmp_path)
    run_root = tmp_path / "run"
    completed = subprocess.run(
        [
            sys.executable,
            str(RUNNER),
            "run",
            "--spec",
            str(spec_path),
            "--run-root",
            str(run_root),
            "--target-root",
            str(target),
            "--entry-skill",
            "example",
            "--runtime-provider",
            "fixture_host",
            "--json",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout
    doctor_path = run_root / "outputs" / "stages" / "doctor.json"
    doctor_path.write_text(json.dumps({"status": "FAIL"}, indent=2) + "\n", encoding="utf-8")

    finalized = subprocess.run(
        [
            sys.executable,
            str(FINALIZER),
            "--spec",
            str(spec_path),
            "--run-root",
            str(run_root),
            "--target-root",
            str(target),
            "--state",
            str(run_root / "target-state.json"),
            "--json",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert finalized.returncode == 1
    payload = json.loads(finalized.stdout)
    assert payload["status"] == "FAIL"
    state = json.loads((run_root / "target-state.json").read_text(encoding="utf-8"))
    assert state["status"] == "FAIL"
    assert state["finalizer_status"] == "FAIL"
    assert not (target / "outputs" / "target-workflow" / "run-manifest.json").exists()


def test_target_managed_runtime_missing_owner_fails(tmp_path: Path) -> None:
    target = write_target_fixture(tmp_path, include_owner=False)
    run_root = tmp_path / "run"
    completed = subprocess.run(
        [
            sys.executable,
            str(RUNNER),
            "run",
            "--spec",
            str(SPEC),
            "--run-root",
            str(run_root),
            "--target-root",
            str(target),
            "--entry-skill",
            "example",
            "--runtime-provider",
            "fixture_host",
            "--json",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 1
    payload = json.loads(completed.stdout)
    assert payload["status"] == "FAIL"
    assert "owner not found" in payload["failure_reason"]


def test_target_runtime_policy_requires_capability(tmp_path: Path) -> None:
    spec = yaml.safe_load(SPEC.read_text(encoding="utf-8"))
    spec["generated_runtime_contract"]["runtime_capabilities"] = ["state_transitions", "run_state_validation"]
    invalid = tmp_path / "invalid.yaml"
    invalid.write_text(yaml.safe_dump(spec, allow_unicode=True, sort_keys=False), encoding="utf-8")
    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / ".claude" / "scripts" / "validate-workflow-spec.py"),
            "--spec",
            str(invalid),
            "--json",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 1
    payload = json.loads(completed.stdout)
    assert any("target_managed_runtime" in item for item in payload["errors"])


def test_target_publish_policy_requires_capability(tmp_path: Path) -> None:
    spec = yaml.safe_load(SPEC.read_text(encoding="utf-8"))
    spec["generated_runtime_contract"]["runtime_capabilities"] = [
        item
        for item in spec["generated_runtime_contract"]["runtime_capabilities"]
        if item != "target_atomic_publish"
    ]
    invalid = tmp_path / "invalid-publish.yaml"
    invalid.write_text(yaml.safe_dump(spec, allow_unicode=True, sort_keys=False), encoding="utf-8")
    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / ".claude" / "scripts" / "validate-workflow-spec.py"),
            "--spec",
            str(invalid),
            "--json",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 1
    payload = json.loads(completed.stdout)
    assert any("target_atomic_publish" in item for item in payload["errors"])


def test_target_publish_policy_rejects_finalizer_owned_required_report(tmp_path: Path) -> None:
    spec = yaml.safe_load(SPEC.read_text(encoding="utf-8"))
    spec["target_publish_policy"]["required_reports"].append(
        {
            "path": spec["target_publish_policy"]["manifest_path"],
            "status_field": "status",
            "pass_values": ["COMPLETE"],
        }
    )
    invalid = tmp_path / "invalid-finalizer-owned-report.yaml"
    invalid.write_text(yaml.safe_dump(spec, allow_unicode=True, sort_keys=False), encoding="utf-8")
    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / ".claude" / "scripts" / "validate-workflow-spec.py"),
            "--spec",
            str(invalid),
            "--json",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 1
    payload = json.loads(completed.stdout)
    assert any("finalizer owns that manifest" in item for item in payload["errors"])


def test_target_publish_policy_rejects_finalizer_owned_graph_refs(tmp_path: Path) -> None:
    spec = yaml.safe_load(SPEC.read_text(encoding="utf-8"))
    manifest_path = spec["target_publish_policy"]["manifest_path"]
    latest_marker = spec["target_publish_policy"]["latest_marker"]
    spec["workflow_graph"]["nodes"][0]["input_refs"].append(manifest_path)
    spec["workflow_graph"]["nodes"][0]["output_refs"].append(latest_marker)
    invalid = tmp_path / "invalid-finalizer-owned-graph-refs.yaml"
    invalid.write_text(yaml.safe_dump(spec, allow_unicode=True, sort_keys=False), encoding="utf-8")
    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / ".claude" / "scripts" / "validate-workflow-spec.py"),
            "--spec",
            str(invalid),
            "--json",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 1
    payload = json.loads(completed.stdout)
    assert any("input_refs must not depend on finalizer-owned" in item for item in payload["errors"])
    assert any("output_refs must not write finalizer-owned" in item for item in payload["errors"])


def test_target_managed_runtime_exception_writes_failure_evidence(tmp_path: Path) -> None:
    spec = yaml.safe_load(SPEC.read_text(encoding="utf-8"))
    spec.pop("workflow_graph", None)
    invalid = tmp_path / "missing-graph.yaml"
    invalid.write_text(yaml.safe_dump(spec, allow_unicode=True, sort_keys=False), encoding="utf-8")
    target = write_target_fixture(tmp_path)
    run_root = tmp_path / "run"
    completed = subprocess.run(
        [
            sys.executable,
            str(RUNNER),
            "run",
            "--spec",
            str(invalid),
            "--run-root",
            str(run_root),
            "--target-root",
            str(target),
            "--entry-skill",
            "example",
            "--runtime-provider",
            "fixture_host",
            "--json",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 1
    payload = json.loads(completed.stdout)
    assert payload["status"] == "FAIL"
    assert (run_root / "target-state.json").exists()
    assert (run_root / "target-events.jsonl").exists()
    assert (run_root / "outputs" / "stages" / "target-runtime-summary.json").exists()

    validation = subprocess.run(
        [sys.executable, str(VALIDATOR), "--state", str(run_root / "target-state.json"), "--json"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert validation.returncode == 1
    validation_payload = json.loads(validation.stdout)
    assert validation_payload["status"] == "FAIL"


def test_generated_runtime_rejects_prompt_heavy_managed_command(tmp_path: Path) -> None:
    target = write_target_fixture(tmp_path)
    spec_path = write_persistent_spec(target)
    generate_runtime_for_target(target, spec_path)
    apply_claude_guard(target, spec_path, tmp_path / "guard-run")
    command_path = target / ".claude" / "commands" / "example.md"
    command_path.parent.mkdir(parents=True, exist_ok=True)
    command_path.write_text(
        """---
description: Prompt-heavy command that must be rejected
---

Run `.workflowprogram/runtime/workflow-entry.py run --request "$ARGUMENTS"`.

Step 1: manually execute each workflow node if the runtime reports FAIL.
Step 2: write `run_manifest.json` with status `COMPLETE` after copying reports.
""",
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            sys.executable,
            str(GENERATED_RUNTIME_VALIDATOR),
            "--spec",
            str(spec_path),
            "--target-root",
            str(target),
            "--json",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 1
    payload = json.loads(completed.stdout)
    assert payload["status"] == "FAIL"
    assert any("wrapper-only" in error for error in payload["errors"])


def test_generated_runtime_rejects_local_shared_control_plane_script(tmp_path: Path) -> None:
    target = write_target_fixture(tmp_path)
    spec_path = write_persistent_spec(target)
    generate_runtime_for_target(target, spec_path)
    write_wrapper_command(target)
    apply_claude_guard(target, spec_path, tmp_path / "guard-run")
    stale_runner = target / ".workflowprogram" / "runtime" / "target-workflow-runner.py"
    stale_runner.write_text("# stale local control plane\n", encoding="utf-8")

    completed = subprocess.run(
        [
            sys.executable,
            str(GENERATED_RUNTIME_VALIDATOR),
            "--spec",
            str(spec_path),
            "--target-root",
            str(target),
            "--json",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 1
    payload = json.loads(completed.stdout)
    assert payload["status"] == "FAIL"
    assert any("shared control-plane script" in error for error in payload["errors"])


def test_generated_runtime_requires_publish_state_validation_marker(tmp_path: Path) -> None:
    target = write_target_fixture(tmp_path)
    spec_path = write_persistent_spec(target)
    generate_runtime_for_target(target, spec_path)
    write_wrapper_command(target)
    apply_claude_guard(target, spec_path, tmp_path / "guard-run")
    entry_path = target / ".workflowprogram" / "runtime" / "workflow-entry.py"
    entry_path.write_text(
        entry_path.read_text(encoding="utf-8").replace("validate_target_publish_state", "skip_publish_state_validation"),
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            sys.executable,
            str(GENERATED_RUNTIME_VALIDATOR),
            "--spec",
            str(spec_path),
            "--target-root",
            str(target),
            "--json",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 1
    payload = json.loads(completed.stdout)
    assert payload["status"] == "FAIL"
    assert any("validate-target-publish-state.py execution marker" in error for error in payload["errors"])


def test_generated_runtime_requires_executor_evidence_blocked_finalizer_skip_marker(tmp_path: Path) -> None:
    target = write_target_fixture(tmp_path)
    spec_path = write_persistent_spec(target)
    generate_runtime_for_target(target, spec_path)
    write_wrapper_command(target)
    apply_claude_guard(target, spec_path, tmp_path / "guard-run")
    entry_path = target / ".workflowprogram" / "runtime" / "workflow-entry.py"
    entry_path.write_text(
        entry_path.read_text(encoding="utf-8").replace("runner_blocked_phase", "runner_phase_without_blocked_marker"),
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            sys.executable,
            str(GENERATED_RUNTIME_VALIDATOR),
            "--spec",
            str(spec_path),
            "--target-root",
            str(target),
            "--json",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 1
    payload = json.loads(completed.stdout)
    assert payload["status"] == "FAIL"
    assert any("executor-evidence BLOCKED finalizer skip marker" in error for error in payload["errors"])


def test_generated_runtime_rejects_node_owner_prompt_publish_bypass(tmp_path: Path) -> None:
    target = write_target_fixture(tmp_path)
    spec_path = write_persistent_spec(target)
    generate_runtime_for_target(target, spec_path)
    write_wrapper_command(target)
    apply_claude_guard(target, spec_path, tmp_path / "guard-run")
    owner_prompt = target / ".claude" / "skills" / "example" / "SKILL.md"
    owner_prompt.write_text(
        """---
name: example-skill
---

Write outputs/target-workflow/intake-summary.md directly, then update
run-manifest.json with status COMPLETE.
""",
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            sys.executable,
            str(GENERATED_RUNTIME_VALIDATOR),
            "--spec",
            str(spec_path),
            "--target-root",
            str(target),
            "--json",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 1
    payload = json.loads(completed.stdout)
    assert payload["status"] == "FAIL"
    assert any("finalizer-owned publish artifact" in error for error in payload["errors"])
    assert any("active-run-root/WORKFLOWPROGRAM_OUTPUT_ROOT guidance" in error for error in payload["errors"])


def test_target_claude_guard_create_append_replace_and_conflict(tmp_path: Path) -> None:
    target = write_target_fixture(tmp_path)
    spec_path = write_persistent_spec(target)

    created = apply_claude_guard(target, spec_path, tmp_path / "guard-create")
    assert created["status"] == "PASS"
    assert created["action"] == "create"
    assert "WorkflowProgram Runtime Guard" in (target / "CLAUDE.md").read_text(encoding="utf-8")
    assert (target / ".workflowprogram" / "claude-guard-manifest.json").exists()

    target2 = write_target_fixture(tmp_path / "append")
    spec_path2 = write_persistent_spec(target2)
    (target2 / "CLAUDE.md").write_text("# Existing Project\n\nKeep this project rule.\n", encoding="utf-8")
    appended = apply_claude_guard(target2, spec_path2, tmp_path / "guard-append")
    text2 = (target2 / "CLAUDE.md").read_text(encoding="utf-8")
    assert appended["action"] == "append"
    assert "Keep this project rule." in text2
    assert "WorkflowProgram Runtime Guard" in text2

    replaced = apply_claude_guard(target2, spec_path2, tmp_path / "guard-replace")
    assert replaced["action"] == "replace"

    target3 = write_target_fixture(tmp_path / "conflict")
    spec_path3 = write_persistent_spec(target3)
    (target3 / "CLAUDE.md").write_text("<!-- BEGIN WORKFLOWPROGRAM RUNTIME GUARD: workflowprogram-runtime-guard -->\n", encoding="utf-8")
    conflicted = subprocess.run(
        [
            sys.executable,
            str(APPLY_CLAUDE_GUARD),
            "--spec",
            str(spec_path3),
            "--target-root",
            str(target3),
            "--run-root",
            str(tmp_path / "guard-conflict"),
            "--json",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert conflicted.returncode == 2
    assert json.loads(conflicted.stdout)["status"] == "CONFLICT"


def test_validate_workflow_spec_rejects_invalid_target_claude_guard(tmp_path: Path) -> None:
    payload = yaml.safe_load(SPEC.read_text(encoding="utf-8"))
    payload["target_claude_guard"]["file"] = "docs/CLAUDE.md"
    invalid = tmp_path / "invalid-claude-guard.yaml"
    invalid.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")

    completed = subprocess.run(
        [sys.executable, str(SPEC_VALIDATOR), "--spec", str(invalid), "--json"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 1
    result = json.loads(completed.stdout)
    assert result["status"] == "FAIL"
    assert any("target_claude_guard.file" in error for error in result["errors"])


def test_generated_runtime_requires_target_claude_guard(tmp_path: Path) -> None:
    target = write_target_fixture(tmp_path)
    spec_path = write_persistent_spec(target)
    generate_runtime_for_target(target, spec_path)
    write_wrapper_command(target)

    completed = subprocess.run(
        [
            sys.executable,
            str(GENERATED_RUNTIME_VALIDATOR),
            "--spec",
            str(spec_path),
            "--target-root",
            str(target),
            "--json",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 1
    payload = json.loads(completed.stdout)
    assert any("target CLAUDE guard is missing" in error for error in payload["errors"])


def test_generated_runtime_accepts_target_claude_guard(tmp_path: Path) -> None:
    target = write_target_fixture(tmp_path)
    spec_path = write_persistent_spec(target)
    generate_runtime_for_target(target, spec_path)
    write_wrapper_command(target)
    apply_claude_guard(target, spec_path, tmp_path / "guard-run")

    completed = subprocess.run(
        [
            sys.executable,
            str(GENERATED_RUNTIME_VALIDATOR),
            "--spec",
            str(spec_path),
            "--target-root",
            str(target),
            "--json",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout
    assert json.loads(completed.stdout)["status"] == "PASS"


def test_publish_state_validator_rejects_forged_complete_manifest(tmp_path: Path) -> None:
    target = write_target_fixture(tmp_path)
    spec_path = write_persistent_spec(target)
    run_root = tmp_path / "run"
    run_root.mkdir()
    (run_root / "target-state.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "schema_name": "target-workflow-runtime-state",
                "run_id": run_root.name,
                "status": "FAIL",
                "failure_kind": "implementation",
                "failure_reason": "runtime failed",
                "finalizer_status": "FAIL",
                "published": False,
                "node_results_path": "node-results.json",
                "artifact_provenance_path": "artifact-provenance.json",
                "events_path": "target-events.jsonl",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (run_root / "node-results.json").write_text(json.dumps({"schema_version": 1, "nodes": []}) + "\n", encoding="utf-8")
    (run_root / "artifact-provenance.json").write_text(json.dumps({"schema_version": 1, "artifacts": []}) + "\n", encoding="utf-8")
    final_root = target / "outputs" / "target-workflow"
    final_root.mkdir(parents=True)
    (final_root / "run-manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "status": "COMPLETE",
                "verdict": "PASS",
                "run_id": run_root.name,
                "run_root": str(run_root),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (final_root / ".workflowprogram-latest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "status": "COMPLETE",
                "run_id": run_root.name,
                "run_root": str(run_root),
                "manifest": "outputs/target-workflow/run-manifest.json",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            sys.executable,
            str(PUBLISH_STATE_VALIDATOR),
            "--spec",
            str(spec_path),
            "--target-root",
            str(target),
            "--run-root",
            str(run_root),
            "--json",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 1
    payload = json.loads(completed.stdout)
    assert payload["status"] == "FAIL"
    assert any("producer" in error or "target-state status" in error for error in payload["errors"])


def test_publish_state_validator_rejects_stale_latest_marker(tmp_path: Path) -> None:
    target = write_target_fixture(tmp_path)
    spec_path = write_persistent_spec(target)
    run_root = tmp_path / "run"
    completed = subprocess.run(
        [
            sys.executable,
            str(RUNNER),
            "run",
            "--spec",
            str(spec_path),
            "--run-root",
            str(run_root),
            "--target-root",
            str(target),
            "--entry-skill",
            "example",
            "--runtime-provider",
            "fixture_host",
            "--json",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout

    finalized = subprocess.run(
        [
            sys.executable,
            str(FINALIZER),
            "--spec",
            str(spec_path),
            "--run-root",
            str(run_root),
            "--target-root",
            str(target),
            "--state",
            str(run_root / "target-state.json"),
            "--json",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert finalized.returncode == 0, finalized.stderr or finalized.stdout
    latest_path = target / "outputs" / "target-workflow" / ".workflowprogram-latest.json"
    latest = json.loads(latest_path.read_text(encoding="utf-8"))
    latest["run_id"] = "older-run"
    latest_path.write_text(json.dumps(latest, indent=2) + "\n", encoding="utf-8")

    completed = subprocess.run(
        [
            sys.executable,
            str(PUBLISH_STATE_VALIDATOR),
            "--spec",
            str(spec_path),
            "--target-root",
            str(target),
            "--run-root",
            str(run_root),
            "--json",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 1
    payload = json.loads(completed.stdout)
    assert payload["status"] == "FAIL"
    assert any("latest marker" in error for error in payload["errors"])
