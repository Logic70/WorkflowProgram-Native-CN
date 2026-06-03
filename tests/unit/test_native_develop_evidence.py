from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / ".claude" / "scripts" / "build-native-develop-evidence.py"


def run_script(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args, "--json"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def write_candidate(root: Path, content: str = "return { status: 'PASS' }\n") -> None:
    script = root / ".claude" / "workflows" / "probe.js"
    script.parent.mkdir(parents=True)
    script.write_text(content, encoding="utf-8")


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def load_json(completed: subprocess.CompletedProcess[str]) -> dict:
    return json.loads(completed.stdout)


def test_generation_evidence_includes_candidate_tree_hash_and_refs(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate"
    report = tmp_path / "generation.json"
    write_candidate(candidate)
    write_json(report, {"status": "PASS"})

    completed = run_script("generation", "--candidate-root", str(candidate), "--report", str(report))

    assert completed.returncode == 0
    payload = load_json(completed)
    assert payload["status"] == "PASS"
    assert payload["candidateHash"].startswith("sha256:")
    assert payload["candidateRefs"] == [str((candidate / ".claude" / "workflows" / "probe.js").resolve())]


def test_candidate_tree_hash_changes_when_supporting_asset_changes(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate"
    report = tmp_path / "generation.json"
    write_candidate(candidate)
    write_json(report, {"status": "PASS"})
    first = load_json(run_script("generation", "--candidate-root", str(candidate), "--report", str(report)))
    supporting = candidate / ".claude" / "skills" / "probe" / "SKILL.md"
    supporting.parent.mkdir(parents=True)
    supporting.write_text("# Probe\n", encoding="utf-8")

    second = load_json(run_script("generation", "--candidate-root", str(candidate), "--report", str(report)))

    assert first["candidateHash"] != second["candidateHash"]


def test_smoke_evidence_fails_when_transcript_is_missing(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate"
    write_candidate(candidate)

    completed = run_script(
        "smoke",
        "--candidate-root",
        str(candidate),
        "--status",
        "PASS",
        "--evidence",
        str(tmp_path / "missing.jsonl"),
    )

    assert completed.returncode == 1
    payload = load_json(completed)
    assert payload["status"] == "FAIL"
    assert "not found" in payload["blockingIssues"][0]


def test_smoke_evidence_explicit_failure_has_blocking_issue(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate"
    transcript = tmp_path / "smoke.jsonl"
    write_candidate(candidate)
    transcript.write_text("{}\n", encoding="utf-8")

    completed = run_script(
        "smoke",
        "--candidate-root",
        str(candidate),
        "--status",
        "FAIL",
        "--evidence",
        str(transcript),
    )

    assert completed.returncode == 1
    payload = load_json(completed)
    assert payload["status"] == "FAIL"
    assert payload["blockingIssues"] == ["Interactive smoke did not pass."]


def test_apply_evidence_reports_conflict_and_manifest(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate"
    report = tmp_path / "managed-change-result.json"
    write_candidate(candidate)
    write_json(
        report,
        {
            "status": "PASS",
            "manifest_path": str(tmp_path / "managed-files.json"),
            "conflicts": [{"reason": "target drift"}],
        },
    )

    completed = run_script("apply", "--candidate-root", str(candidate), "--report", str(report))

    assert completed.returncode == 1
    payload = load_json(completed)
    assert payload["status"] == "CONFLICT"
    assert payload["applyManifest"] == str((tmp_path / "managed-files.json").resolve())
    assert payload["blockingIssues"] == ["target drift"]
