from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / ".claude" / "scripts" / "build-native-iterate-evidence.py"


def run_script(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args, "--json"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def load_json(completed: subprocess.CompletedProcess[str]) -> dict:
    return json.loads(completed.stdout)


def write_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def setup_target(tmp_path: Path) -> tuple[Path, Path, Path]:
    """Create a minimal target with lessons.md and constraints.md."""
    target = tmp_path / "target"
    lessons = target / "lessons.md"
    constraints = target / ".claude" / "rules" / "constraints.md"
    lessons.parent.mkdir(parents=True, exist_ok=True)
    constraints.parent.mkdir(parents=True, exist_ok=True)
    lessons.write_text("# Lessons\n\nInitial lessons content.\n", encoding="utf-8")
    constraints.write_text("# Constraints\n\n- ALWAYS keep README.md present.\n", encoding="utf-8")
    return target, lessons, constraints


# readback

def test_readback_passes_with_valid_target(tmp_path: Path) -> None:
    target, lessons, constraints = setup_target(tmp_path)
    completed = run_script("readback", "--target-root", str(target), "--run-id", "run-001")
    assert completed.returncode == 0, completed.stderr or completed.stdout
    payload = load_json(completed)
    assert payload["status"] == "PASS"
    assert payload["stateHash"].startswith("sha256:")
    assert len(payload["evidence"]) == 2
    assert str(lessons) in payload["evidence"]
    assert str(constraints) in payload["evidence"]
    assert payload["blockingIssues"] == []


def test_readback_hash_changes_when_lessons_change(tmp_path: Path) -> None:
    target, lessons, constraints = setup_target(tmp_path)
    first = load_json(run_script("readback", "--target-root", str(target)))
    lessons.write_text("# Lessons\nUpdated content.\n", encoding="utf-8")
    second = load_json(run_script("readback", "--target-root", str(target)))
    assert first["stateHash"] != second["stateHash"]


def test_readback_hash_changes_when_constraints_change(tmp_path: Path) -> None:
    target, lessons, constraints = setup_target(tmp_path)
    first = load_json(run_script("readback", "--target-root", str(target)))
    constraints.write_text("# Constraints\n- NEVER write main directly.\n", encoding="utf-8")
    second = load_json(run_script("readback", "--target-root", str(target)))
    assert first["stateHash"] != second["stateHash"]


def test_readback_fails_on_missing_target(tmp_path: Path) -> None:
    completed = run_script("readback", "--target-root", str(tmp_path / "nonexistent"))
    assert completed.returncode == 1
    payload = load_json(completed)
    assert payload["status"] == "FAIL"
    assert len(payload["blockingIssues"]) > 0


def test_readback_fails_on_missing_lessons(tmp_path: Path) -> None:
    target, lessons, _ = setup_target(tmp_path)
    lessons.unlink()
    completed = run_script("readback", "--target-root", str(target))
    assert completed.returncode == 1
    payload = load_json(completed)
    assert payload["status"] == "FAIL"
    assert any("lessons.md" in issue for issue in payload["blockingIssues"])


def test_readback_fails_on_empty_lessons(tmp_path: Path) -> None:
    target, lessons, _ = setup_target(tmp_path)
    lessons.write_text("", encoding="utf-8")
    completed = run_script("readback", "--target-root", str(target))
    assert completed.returncode == 1
    payload = load_json(completed)
    assert payload["status"] == "FAIL"
    assert any("empty" in issue.lower() for issue in payload["blockingIssues"])


# validate-delta

def write_delta_file(path: Path, delta: list[dict], run_id: str = "run-001") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"delta": delta, "runId": run_id}), encoding="utf-8")


def test_validate_delta_passes(tmp_path: Path) -> None:
    target, _, _ = setup_target(tmp_path)
    state_hash = load_json(run_script("readback", "--target-root", str(target)))["stateHash"]
    delta_file = tmp_path / "delta.json"
    write_delta_file(delta_file, [{"type": "lesson", "summary": "Test", "body": "Test body."}])

    completed = run_script(
        "validate-delta",
        "--target-root", str(target),
        "--state-hash", state_hash,
        "--delta-file", str(delta_file),
        "--run-id", "run-001",
        "--run-root", str(tmp_path / "run"),
        "--failure-kind", "test",
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout
    payload = load_json(completed)
    assert payload["status"] == "PASS"
    assert payload["stateHash"] == state_hash
    assert payload["deltaHash"].startswith("sha256:")
    assert len(payload["evidence"]) >= 1


def test_validate_delta_fails_on_state_hash_drift(tmp_path: Path) -> None:
    target, lessons, _ = setup_target(tmp_path)
    state_hash = load_json(run_script("readback", "--target-root", str(target)))["stateHash"]
    delta_file = tmp_path / "delta.json"
    write_delta_file(delta_file, [{"type": "lesson", "summary": "Test", "body": "Test."}])

    lessons.write_text("# Lessons\nDrifted content.\n", encoding="utf-8")
    completed = run_script(
        "validate-delta",
        "--target-root", str(target),
        "--state-hash", state_hash,
        "--delta-file", str(delta_file),
        "--run-id", "run-001",
        "--run-root", str(tmp_path / "run"),
        "--failure-kind", "test",
    )
    assert completed.returncode == 1
    payload = load_json(completed)
    assert payload["status"] == "FAIL"
    assert any("drift" in issue.lower() for issue in payload["blockingIssues"])


def test_validate_delta_fails_on_missing_delta_file(tmp_path: Path) -> None:
    target, _, _ = setup_target(tmp_path)
    completed = run_script(
        "validate-delta",
        "--target-root", str(target),
        "--delta-file", str(tmp_path / "missing-delta.json"),
        "--run-id", "run-001",
        "--run-root", str(tmp_path / "run"),
        "--failure-kind", "test",
    )
    assert completed.returncode == 1
    payload = load_json(completed)
    assert payload["status"] == "FAIL"


def test_validate_delta_fails_on_unknown_stage(tmp_path: Path) -> None:
    completed = run_script("unknown-stage", "--target-root", str(tmp_path / "target"))
    assert completed.returncode != 0


def test_validate_delta_rejects_malformed_json(tmp_path: Path) -> None:
    target, _, _ = setup_target(tmp_path)
    state_hash = load_json(run_script("readback", "--target-root", str(target)))["stateHash"]
    delta_file = tmp_path / "delta.json"
    delta_file.write_text("not valid {{ json", encoding="utf-8")

    completed = run_script(
        "validate-delta",
        "--target-root", str(target),
        "--state-hash", state_hash,
        "--delta-file", str(delta_file),
        "--run-id", "run-001",
        "--run-root", str(tmp_path / "run"),
        "--failure-kind", "test",
    )
    assert completed.returncode == 1
    payload = load_json(completed)
    assert payload["status"] == "FAIL"


def test_validate_delta_rejects_non_object_payload(tmp_path: Path) -> None:
    target, _, _ = setup_target(tmp_path)
    state_hash = load_json(run_script("readback", "--target-root", str(target)))["stateHash"]
    delta_file = tmp_path / "delta.json"
    delta_file.write_text('"just a string, not an object"', encoding="utf-8")

    completed = run_script(
        "validate-delta",
        "--target-root", str(target),
        "--state-hash", state_hash,
        "--delta-file", str(delta_file),
        "--run-id", "run-001",
        "--run-root", str(tmp_path / "run"),
        "--failure-kind", "test",
    )
    assert completed.returncode == 1
    payload = load_json(completed)
    assert payload["status"] == "FAIL"


def test_validate_delta_materializes_s6_evidence(tmp_path: Path) -> None:
    target, _, _ = setup_target(tmp_path)
    state_hash = load_json(run_script("readback", "--target-root", str(target)))["stateHash"]
    delta_file = tmp_path / "delta.json"
    run_root = tmp_path / "run"
    write_delta_file(delta_file, [{"type": "lesson", "summary": "Test", "body": "Test body."}])

    completed = run_script(
        "validate-delta",
        "--target-root", str(target),
        "--state-hash", state_hash,
        "--delta-file", str(delta_file),
        "--run-id", "run-001",
        "--run-root", str(run_root),
        "--failure-kind", "test",
    )
    payload = load_json(completed)
    # Check S6 evidence was materialized
    s6_delta = run_root / "outputs" / "stages" / "s6-lessons-delta.md"
    assert s6_delta.exists()
    delta_text = s6_delta.read_text(encoding="utf-8")
    assert "run-001" in delta_text
    assert "test" in delta_text
    # Check user progress summary — milestone bullet must be present
    progress = run_root / "outputs" / "progress" / "user-progress.md"
    assert progress.exists()
    progress_text = progress.read_text(encoding="utf-8")
    assert "[lesson] Test" in progress_text, "Milestone bullet should be emitted"
    # Check delta validation evidence persisted
    evidence_json = run_root / "outputs" / "stages" / "delta-validation.json"
    assert evidence_json.exists()


# append-lessons

def test_append_lessons_idempotent(tmp_path: Path) -> None:
    target, lessons, _ = setup_target(tmp_path)
    state_hash = load_json(run_script("readback", "--target-root", str(target)))["stateHash"]
    delta_file = tmp_path / "delta.json"
    write_delta_file(delta_file, [{"type": "lesson", "summary": "New Rule", "body": "Always test before commit."}])

    # Get delta-hash from validate-delta
    run_root = tmp_path / "run"
    delta_hash = load_json(run_script(
        "validate-delta", "--target-root", str(target),
        "--state-hash", state_hash, "--delta-file", str(delta_file),
        "--run-id", "run-001", "--run-root", str(run_root), "--failure-kind", "test",
    ))["deltaHash"]

    first = load_json(run_script(
        "append-lessons", "--target-root", str(target),
        "--delta-file", str(delta_file), "--delta-hash", delta_hash,
        "--state-hash", state_hash, "--run-id", "run-001",
    ))
    assert first["status"] == "PASS"
    assert first["receipt"]["idempotent"] is False
    # baselineHash equals the pre-write hash; stateHash is the post-write hash
    assert first["baselineHash"] == state_hash
    assert first["stateHash"] != state_hash
    assert first["deltaHash"].startswith("sha256:")
    assert "New Rule" in lessons.read_text(encoding="utf-8")

    # Second call: same delta, same runId — idempotent retry
    second = load_json(run_script(
        "append-lessons", "--target-root", str(target),
        "--delta-file", str(delta_file), "--delta-hash", delta_hash,
        "--state-hash", first["stateHash"], "--run-id", "run-001",
    ))
    assert second["status"] == "PASS"
    assert second["receipt"]["idempotent"] is True
    # On idempotent retry, baselineHash must be the ORIGINAL stored hash (not the post-write hash)
    assert second["baselineHash"] == state_hash
    # stateHash must be the current actual state
    current_state = load_json(run_script("readback", "--target-root", str(target)))["stateHash"]
    assert second["stateHash"] == current_state


def test_append_lessons_rejects_drifted_baseline(tmp_path: Path) -> None:
    target, lessons, _ = setup_target(tmp_path)
    state_hash = load_json(run_script("readback", "--target-root", str(target)))["stateHash"]
    delta_file = tmp_path / "delta.json"
    write_delta_file(delta_file, [{"type": "lesson", "summary": "Test", "body": "Body."}])

    # Get delta-hash from validate-delta before drifting
    run_root = tmp_path / "run"
    delta_hash = load_json(run_script(
        "validate-delta", "--target-root", str(target),
        "--state-hash", state_hash, "--delta-file", str(delta_file),
        "--run-id", "run-001", "--run-root", str(run_root), "--failure-kind", "test",
    ))["deltaHash"]

    lessons.write_text("# Lessons\nModified externally.\n", encoding="utf-8")
    completed = run_script(
        "append-lessons", "--target-root", str(target),
        "--delta-file", str(delta_file), "--delta-hash", delta_hash,
        "--state-hash", state_hash, "--run-id", "run-001",
    )
    assert completed.returncode == 1
    payload = load_json(completed)
    assert payload["status"] == "FAIL"
    assert any("drift" in issue.lower() for issue in payload["blockingIssues"])


def test_append_lessons_rejects_same_run_different_delta(tmp_path: Path) -> None:
    """Idempotency must reject same runId with different delta content."""
    target, lessons, _ = setup_target(tmp_path)
    state_hash = load_json(run_script("readback", "--target-root", str(target)))["stateHash"]

    # First append with delta A
    delta_a = tmp_path / "delta_a.json"
    write_delta_file(delta_a, [{"type": "lesson", "summary": "Rule A", "body": "Body A."}])
    run_root = tmp_path / "run"
    delta_hash_a = load_json(run_script(
        "validate-delta", "--target-root", str(target),
        "--state-hash", state_hash, "--delta-file", str(delta_a),
        "--run-id", "run-001", "--run-root", str(run_root), "--failure-kind", "test",
    ))["deltaHash"]
    first = load_json(run_script(
        "append-lessons", "--target-root", str(target),
        "--delta-file", str(delta_a), "--delta-hash", delta_hash_a,
        "--state-hash", state_hash, "--run-id", "run-001",
    ))
    assert first["status"] == "PASS"

    # Try to append with delta B but same runId — must reject
    delta_b = tmp_path / "delta_b.json"
    write_delta_file(delta_b, [{"type": "lesson", "summary": "Rule B", "body": "Body B."}])
    delta_hash_b = load_json(run_script(
        "validate-delta", "--target-root", str(target),
        "--state-hash", first["stateHash"], "--delta-file", str(delta_b),
        "--run-id", "run-001", "--run-root", str(run_root), "--failure-kind", "test",
    ))["deltaHash"]
    completed = run_script(
        "append-lessons", "--target-root", str(target),
        "--delta-file", str(delta_b), "--delta-hash", delta_hash_b,
        "--state-hash", first["stateHash"], "--run-id", "run-001",
    )
    assert completed.returncode == 1
    payload = load_json(completed)
    assert payload["status"] == "FAIL"
    assert any("conflict" in issue.lower() for issue in payload["blockingIssues"])


def test_append_lessons_rejects_malformed_json(tmp_path: Path) -> None:
    target, _, _ = setup_target(tmp_path)
    state_hash = load_json(run_script("readback", "--target-root", str(target)))["stateHash"]
    delta_file = tmp_path / "delta.json"
    delta_file.write_text("not valid json {{{", encoding="utf-8")

    completed = run_script(
        "append-lessons", "--target-root", str(target),
        "--delta-file", str(delta_file), "--delta-hash", "sha256:deadbeef",
        "--state-hash", state_hash, "--run-id", "run-001",
    )
    assert completed.returncode == 1
    payload = load_json(completed)
    assert payload["status"] == "FAIL"


def test_append_lessons_rejects_wrong_delta_hash(tmp_path: Path) -> None:
    """Delta hash mismatch must block before any write."""
    target, _, _ = setup_target(tmp_path)
    delta_file = tmp_path / "delta.json"
    write_delta_file(delta_file, [{"type": "lesson", "summary": "Test", "body": "Body."}])

    completed = run_script(
        "append-lessons", "--target-root", str(target),
        "--delta-file", str(delta_file), "--delta-hash", "sha256:0000000000000000000000000000000000000000000000000000000000000000",
        "--run-id", "run-001",
    )
    assert completed.returncode == 1
    payload = load_json(completed)
    assert payload["status"] == "FAIL"
    assert any("hash mismatch" in issue.lower() for issue in payload["blockingIssues"])


# apply-constraints

def write_proposal_file(path: Path, approved: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"approvedCandidates": approved}), encoding="utf-8")


def test_apply_constraints_dedup_and_idempotence(tmp_path: Path) -> None:
    target, _, constraints = setup_target(tmp_path)
    state_hash = load_json(run_script("readback", "--target-root", str(target)))["stateHash"]
    proposal = tmp_path / "proposal.json"
    write_proposal_file(proposal, [
        {"rule": "ALWAYS keep README.md present.", "reason": "Redundant; already exists."},
        {"rule": "NEVER commit secrets.", "reason": "Security requirement."},
    ])

    first = load_json(run_script(
        "apply-constraints", "--target-root", str(target),
        "--proposal-file", str(proposal), "--state-hash", state_hash, "--run-id", "run-001",
    ))
    assert first["status"] == "PASS"
    assert first["receipt"]["idempotent"] is False
    # baselineHash equals the pre-write hash; stateHash is the post-write hash
    assert first["baselineHash"] == state_hash
    assert first["stateHash"] != state_hash
    assert first["proposalHash"].startswith("sha256:")
    assert "NEVER commit secrets" in constraints.read_text(encoding="utf-8")

    # Verify dedup: ALWAYS keep README.md was already there
    text = constraints.read_text(encoding="utf-8")
    assert text.count("ALWAYS keep README.md present") == 1

    second = load_json(run_script(
        "apply-constraints", "--target-root", str(target),
        "--proposal-file", str(proposal), "--state-hash", first["stateHash"], "--run-id", "run-001",
    ))
    assert second["status"] == "PASS"
    assert second["receipt"]["idempotent"] is True
    # On idempotent retry, baselineHash must be the ORIGINAL stored hash (not the post-write hash)
    assert second["baselineHash"] == state_hash
    # stateHash must be the current actual state
    current_state = load_json(run_script("readback", "--target-root", str(target)))["stateHash"]
    assert second["stateHash"] == current_state


def test_apply_constraints_rejects_drifted_baseline(tmp_path: Path) -> None:
    target, lessons, _ = setup_target(tmp_path)
    state_hash = load_json(run_script("readback", "--target-root", str(target)))["stateHash"]
    proposal = tmp_path / "proposal.json"
    write_proposal_file(proposal, [{"rule": "NEVER commit secrets.", "reason": "Security."}])

    lessons.write_text("# Lessons\nExternally changed.\n", encoding="utf-8")
    completed = run_script(
        "apply-constraints", "--target-root", str(target),
        "--proposal-file", str(proposal), "--state-hash", state_hash, "--run-id", "run-001",
    )
    assert completed.returncode == 1
    payload = load_json(completed)
    assert payload["status"] == "FAIL"
    assert any("drift" in issue.lower() for issue in payload["blockingIssues"])


def test_apply_constraints_all_present_is_idempotent(tmp_path: Path) -> None:
    target, _, _ = setup_target(tmp_path)
    state_hash = load_json(run_script("readback", "--target-root", str(target)))["stateHash"]
    proposal = tmp_path / "proposal.json"
    write_proposal_file(proposal, [
        {"rule": "ALWAYS keep README.md present.", "reason": "Already there."},
    ])

    completed = run_script(
        "apply-constraints", "--target-root", str(target),
        "--proposal-file", str(proposal), "--state-hash", state_hash, "--run-id", "run-001",
    )
    assert completed.returncode == 0
    payload = load_json(completed)
    assert payload["status"] == "PASS"
    assert payload["receipt"]["idempotent"] is True
    assert payload["receipt"]["reason"] == "All candidates already present; nothing added."


def test_apply_constraints_empty_candidates_fails(tmp_path: Path) -> None:
    target, _, _ = setup_target(tmp_path)
    state_hash = load_json(run_script("readback", "--target-root", str(target)))["stateHash"]
    proposal = tmp_path / "proposal.json"
    write_proposal_file(proposal, [])

    completed = run_script(
        "apply-constraints", "--target-root", str(target),
        "--proposal-file", str(proposal), "--state-hash", state_hash, "--run-id", "run-001",
    )
    assert completed.returncode == 1
    payload = load_json(completed)
    assert payload["status"] == "FAIL"


def test_apply_constraints_rejects_same_run_different_proposal(tmp_path: Path) -> None:
    """Idempotency must reject same runId with different proposal content."""
    target, _, _ = setup_target(tmp_path)
    state_hash = load_json(run_script("readback", "--target-root", str(target)))["stateHash"]

    # First apply with proposal A
    proposal_a = tmp_path / "proposal_a.json"
    write_proposal_file(proposal_a, [{"rule": "ALWAYS run tests before commit.", "reason": "Quality."}])
    first = load_json(run_script(
        "apply-constraints", "--target-root", str(target),
        "--proposal-file", str(proposal_a), "--state-hash", state_hash, "--run-id", "run-001",
    ))
    assert first["status"] == "PASS"

    # Try to apply with proposal B but same runId — must reject
    proposal_b = tmp_path / "proposal_b.json"
    write_proposal_file(proposal_b, [{"rule": "NEVER skip code review.", "reason": "Quality."}])
    completed = run_script(
        "apply-constraints", "--target-root", str(target),
        "--proposal-file", str(proposal_b), "--state-hash", first["stateHash"], "--run-id", "run-001",
    )
    assert completed.returncode == 1
    payload = load_json(completed)
    assert payload["status"] == "FAIL"
    assert any("conflict" in issue.lower() for issue in payload["blockingIssues"])


def test_apply_constraints_rejects_malformed_json(tmp_path: Path) -> None:
    target, _, _ = setup_target(tmp_path)
    state_hash = load_json(run_script("readback", "--target-root", str(target)))["stateHash"]
    proposal = tmp_path / "proposal.json"
    proposal.write_text("not valid json @@@", encoding="utf-8")

    completed = run_script(
        "apply-constraints", "--target-root", str(target),
        "--proposal-file", str(proposal), "--state-hash", state_hash, "--run-id", "run-001",
    )
    assert completed.returncode == 1
    payload = load_json(completed)
    assert payload["status"] == "FAIL"


# Boolean precedence fix in _deduplicate_constraints

def _import_dedup_helper():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "build_native_iterate_evidence",
        str(ROOT / ".claude" / "scripts" / "build-native-iterate-evidence.py"),
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module._deduplicate_constraints


def test_deduplicate_constraints_boolean_precedence() -> None:
    """Lines with NEVER but not starting with '- ' should NOT be treated as existing rules."""
    _deduplicate_constraints = _import_dedup_helper()

    # Line with NEVER that does NOT start with "- " should not be deduplicated away
    existing = "# Constraints\n\n  NEVER do x  # indented, not a bullet\n"
    candidates = [{"rule": "NEVER do x", "reason": "Important."}]

    new_content, added = _deduplicate_constraints(existing, candidates)
    assert added == ["NEVER do x"], f"Should have added the rule, but added={added}"
    assert "NEVER do x" in new_content


def test_deduplicate_constraints_correct_bullet_detection() -> None:
    """Lines starting with '- ' and containing ALWAYS or NEVER should be deduplicated."""
    _deduplicate_constraints = _import_dedup_helper()

    existing = "# Constraints\n\n- ALWAYS run tests.\n"
    candidates = [
        {"rule": "ALWAYS run tests.", "reason": "Already exists."},
        {"rule": "NEVER skip review.", "reason": "New rule."},
    ]

    new_content, added = _deduplicate_constraints(existing, candidates)
    assert added == ["NEVER skip review."], f"Should only add the new rule, but added={added}"
    assert "ALWAYS run tests." in new_content
    # Ensure ALWAYS is not duplicated
    assert new_content.count("ALWAYS run tests.") == 1
