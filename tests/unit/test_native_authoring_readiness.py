from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
VALIDATOR = ROOT / ".claude" / "scripts" / "validate-native-authoring-readiness.py"
GENERATOR = ROOT / ".claude" / "scripts" / "generate-native-workflow.py"


def run_script(script: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(script), *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def packet(target_root: Path) -> dict:
    return {
        "request": "Create a read-only review workflow.",
        "target_root": str(target_root),
        "confirmed_by_user": True,
        "lenses": {
            "purpose": "Find correctness and test gaps.",
            "object_model": "Read repository files and return findings.",
            "process_model": "Explore, review, and decide.",
            "decision_model": "Block on high severity findings.",
            "evidence_model": "Require file references and test evidence.",
            "acceptance_model": "PASS without blockers and BLOCKED with blockers.",
            "boundary_model": "Do not edit files.",
        },
        "success_criteria": ["Return a structured verdict."],
        "open_questions": [],
    }


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def load_json(completed: subprocess.CompletedProcess[str]) -> dict:
    return json.loads(completed.stdout)


def test_readiness_accepts_confirmed_complete_packet(tmp_path: Path) -> None:
    readiness = tmp_path / "readiness.json"
    write_json(readiness, packet(tmp_path))

    completed = run_script(VALIDATOR, "--packet", str(readiness), "--json")

    assert completed.returncode == 0, completed.stderr or completed.stdout
    assert load_json(completed)["status"] == "PASS"


@pytest.mark.parametrize(
    ("mutate", "rule"),
    [
        (lambda payload: payload.update({"confirmed_by_user": False}), "USER_CONFIRMATION_REQUIRED"),
        (lambda payload: payload.update({"target_root": ["not", "a", "path"]}), "TARGET_ROOT_REQUIRED"),
        (lambda payload: payload["lenses"].update({"evidence_model": ""}), "LENS_REQUIRED"),
        (lambda payload: payload.update({"open_questions": ["Which repositories are in scope?"]}), "OPEN_QUESTIONS_BLOCK_GENERATION"),
    ],
)
def test_readiness_blocks_incomplete_packet(tmp_path: Path, mutate, rule: str) -> None:
    readiness = tmp_path / "readiness.json"
    payload = packet(tmp_path)
    mutate(payload)
    write_json(readiness, payload)

    completed = run_script(VALIDATOR, "--packet", str(readiness), "--json")

    assert completed.returncode == 1
    assert rule in {item["rule"] for item in load_json(completed)["errors"]}


def test_readiness_blocks_packet_for_another_target_root(tmp_path: Path) -> None:
    readiness = tmp_path / "readiness.json"
    expected_target = tmp_path / "expected-target"
    write_json(readiness, packet(tmp_path / "another-target"))

    completed = run_script(
        VALIDATOR,
        "--packet",
        str(readiness),
        "--target-root",
        str(expected_target),
        "--json",
    )

    assert completed.returncode == 1
    assert "TARGET_ROOT_MISMATCH" in {item["rule"] for item in load_json(completed)["errors"]}


def test_generator_blocks_before_candidate_when_readiness_is_unconfirmed(tmp_path: Path) -> None:
    readiness = tmp_path / "readiness.json"
    spec = tmp_path / "spec.json"
    target = tmp_path / "target"
    run_root = tmp_path / "run"
    payload = packet(target)
    payload["confirmed_by_user"] = False
    write_json(readiness, payload)
    write_json(
        spec,
        {
            "name": "blocked-probe",
            "description": "Must not generate before readiness passes.",
            "phases": [{"title": "Probe"}],
            "body": "phase('Probe')\nreturn { status: 'PASS' }\n",
            "supporting_assets": [],
        },
    )

    completed = run_script(
        GENERATOR,
        "--spec",
        str(spec),
        "--readiness",
        str(readiness),
        "--target-root",
        str(target),
        "--run-root",
        str(run_root),
        "--json",
    )

    assert completed.returncode == 1
    assert "USER_CONFIRMATION_REQUIRED" in {item["rule"] for item in load_json(completed)["errors"]}
    assert not (run_root / "outputs" / "candidate").exists()


def test_generator_blocks_before_candidate_when_readiness_targets_another_project(tmp_path: Path) -> None:
    readiness = tmp_path / "readiness.json"
    spec = tmp_path / "spec.json"
    target = tmp_path / "target"
    run_root = tmp_path / "run"
    write_json(readiness, packet(tmp_path / "another-target"))
    write_json(
        spec,
        {
            "name": "blocked-probe",
            "description": "Must not generate for a different target root.",
            "phases": [{"title": "Probe"}],
            "body": "phase('Probe')\nreturn { status: 'PASS' }\n",
            "supporting_assets": [],
        },
    )

    completed = run_script(
        GENERATOR,
        "--spec",
        str(spec),
        "--readiness",
        str(readiness),
        "--target-root",
        str(target),
        "--run-root",
        str(run_root),
        "--json",
    )

    assert completed.returncode == 1
    assert "TARGET_ROOT_MISMATCH" in {item["rule"] for item in load_json(completed)["errors"]}
    assert not (run_root / "outputs" / "candidate").exists()
