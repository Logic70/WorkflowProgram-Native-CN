"""Focused tests for managed-assets no-op idempotency protection.

Covers:
- Same candidate applied twice produces noop (applied empty, skipped non-empty).
- File mtime_ns unchanged after noop.
- Modified target after first apply returns conflict.
- Noop count in summarize.
- Skipped entries in result.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
MANAGED_ASSETS = ROOT / ".claude" / "scripts" / "managed-assets.py"


def run_managed(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(MANAGED_ASSETS), *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def make_candidate_tree(candidate_root: Path, files: dict[str, str]) -> None:
    """Write files into a candidate tree under managed prefixes."""
    for relative_path, content in files.items():
        full = candidate_root / relative_path
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(content, encoding="utf-8")


def read_managed_result(run_root: Path) -> dict:
    return json.loads(
        (run_root / "outputs" / "managed-change-result.json").read_text(encoding="utf-8")
    )


class TestManagedAssetsIdempotency:
    """Same-candidate replay must be a safe no-op."""

    def test_same_candidate_applied_twice_produces_noop(self, tmp_path: Path) -> None:
        target = tmp_path / "target"
        candidate = tmp_path / "candidate"
        run1 = tmp_path / "run1"
        run2 = tmp_path / "run2"
        target.mkdir()

        workflow_content = "export const meta = { name: 'v1', description: 'v1' }\n"
        make_candidate_tree(candidate, {".claude/workflows/v1.js": workflow_content})

        # First apply
        r1 = run_managed([
            "apply-staged",
            "--target-root", str(target),
            "--source-root", str(candidate),
            "--run-root", str(run1),
            "--json",
        ])
        assert r1.returncode == 0, r1.stderr or r1.stdout
        result1 = read_managed_result(run1)
        assert len(result1["applied"]) == 1
        assert result1["applied"][0]["relative_path"] == ".claude/workflows/v1.js"

        # Second apply ─ same candidate
        r2 = run_managed([
            "apply-staged",
            "--target-root", str(target),
            "--source-root", str(candidate),
            "--run-root", str(run2),
            "--json",
        ])
        assert r2.returncode == 0, r2.stderr or r2.stdout
        result2 = read_managed_result(run2)
        assert len(result2["applied"]) == 0, "Same candidate replay must produce zero applied"
        assert "skipped" in result2, "Result must have a skipped array"
        skipped_paths = [item["relative_path"] for item in result2["skipped"]]
        assert ".claude/workflows/v1.js" in skipped_paths

    def test_noop_preserves_file_mtime(self, tmp_path: Path) -> None:
        target = tmp_path / "target"
        candidate = tmp_path / "candidate"
        run1 = tmp_path / "run1"
        run2 = tmp_path / "run2"
        target.mkdir()

        workflow_content = "export const meta = { name: 'v1', description: 'v1' }\n"
        make_candidate_tree(candidate, {".claude/workflows/v1.js": workflow_content})

        # First apply
        r1 = run_managed([
            "apply-staged",
            "--target-root", str(target),
            "--source-root", str(candidate),
            "--run-root", str(run1),
            "--json",
        ])
        assert r1.returncode == 0, r1.stderr or r1.stdout

        target_file = target / ".claude" / "workflows" / "v1.js"
        mtime_before = target_file.stat().st_mtime_ns

        # Second apply ─ noop
        r2 = run_managed([
            "apply-staged",
            "--target-root", str(target),
            "--source-root", str(candidate),
            "--run-root", str(run2),
            "--json",
        ])
        assert r2.returncode == 0, r2.stderr or r2.stdout

        mtime_after = target_file.stat().st_mtime_ns
        assert mtime_after == mtime_before, (
            f"Noop must preserve mtime_ns: before={mtime_before} after={mtime_after}"
        )

    def test_modified_target_after_first_apply_returns_conflict(self, tmp_path: Path) -> None:
        target = tmp_path / "target"
        candidate = tmp_path / "candidate"
        run1 = tmp_path / "run1"
        run2 = tmp_path / "run2"
        target.mkdir()

        v1_content = "export const meta = { name: 'v1', description: 'v1' }\n"
        v2_content = "export const meta = { name: 'v2', description: 'v2' }\n"
        make_candidate_tree(candidate, {".claude/workflows/v1.js": v1_content})

        # First apply
        r1 = run_managed([
            "apply-staged",
            "--target-root", str(target),
            "--source-root", str(candidate),
            "--run-root", str(run1),
            "--json",
        ])
        assert r1.returncode == 0, r1.stderr or r1.stdout

        # User modifies target file
        target_file = target / ".claude" / "workflows" / "v1.js"
        target_file.write_text("// user-modified\n", encoding="utf-8")

        # Second apply ─ different candidate (v2), target has user drift
        make_candidate_tree(candidate, {".claude/workflows/v1.js": v2_content})
        r2 = run_managed([
            "apply-staged",
            "--target-root", str(target),
            "--source-root", str(candidate),
            "--run-root", str(run2),
            "--json",
        ])
        assert r2.returncode == 2, "Drift detection must exit 2"
        result2 = read_managed_result(run2)
        assert len(result2["conflicts"]) >= 1
        assert result2["conflicts"][0]["decision"] == "conflict-managed-drift"

    def test_noop_count_in_summarize(self, tmp_path: Path) -> None:
        target = tmp_path / "target"
        candidate = tmp_path / "candidate"
        run1 = tmp_path / "run1"
        run2 = tmp_path / "run2"
        target.mkdir()

        workflow_content = "export const meta = { name: 'v1', description: 'v1' }\n"
        make_candidate_tree(candidate, {".claude/workflows/v1.js": workflow_content})

        # First apply
        r1 = run_managed([
            "apply-staged",
            "--target-root", str(target),
            "--source-root", str(candidate),
            "--run-root", str(run1),
            "--json",
        ])
        assert r1.returncode == 0, r1.stderr or r1.stdout

        # Plan to see noop count
        r2 = run_managed([
            "plan",
            "--target-root", str(target),
            "--source-root", str(candidate),
            "--run-root", str(run2),
            "--json",
        ])
        assert r2.returncode == 0, r2.stderr or r2.stdout
        plan = json.loads(r2.stdout)
        assert plan["summary"].get("noop", 0) >= 1

    def test_noop_preserves_managed_files_json_mtime_and_bytes(self, tmp_path: Path) -> None:
        """After second same-candidate apply, both target workflow file and
        managed-files.json mtime_ns and bytes must be unchanged.
        """
        target = tmp_path / "target"
        candidate = tmp_path / "candidate"
        run1 = tmp_path / "run1"
        run2 = tmp_path / "run2"
        target.mkdir()

        workflow_content = "export const meta = { name: 'v1', description: 'v1' }\n"
        make_candidate_tree(candidate, {".claude/workflows/v1.js": workflow_content})

        # First apply
        r1 = run_managed([
            "apply-staged",
            "--target-root", str(target),
            "--source-root", str(candidate),
            "--run-root", str(run1),
            "--json",
        ])
        assert r1.returncode == 0, r1.stderr or r1.stdout
        result1 = read_managed_result(run1)
        assert len(result1["applied"]) == 1

        target_file = target / ".claude" / "workflows" / "v1.js"
        managed_json = target / ".workflowprogram" / "managed-files.json"
        assert target_file.exists()
        assert managed_json.exists()

        mtime_file_before = target_file.stat().st_mtime_ns
        mtime_json_before = managed_json.stat().st_mtime_ns
        bytes_file_before = target_file.read_bytes()
        bytes_json_before = managed_json.read_bytes()

        # Second apply ─ must be pure noop
        r2 = run_managed([
            "apply-staged",
            "--target-root", str(target),
            "--source-root", str(candidate),
            "--run-root", str(run2),
            "--json",
        ])
        assert r2.returncode == 0, r2.stderr or r2.stdout
        result2 = read_managed_result(run2)
        assert len(result2["applied"]) == 0, "Same candidate replay must produce zero applied"

        mtime_file_after = target_file.stat().st_mtime_ns
        mtime_json_after = managed_json.stat().st_mtime_ns
        bytes_file_after = target_file.read_bytes()
        bytes_json_after = managed_json.read_bytes()

        assert mtime_file_after == mtime_file_before, (
            f"Noop must preserve workflow file mtime_ns: "
            f"before={mtime_file_before} after={mtime_file_after}"
        )
        assert mtime_json_after == mtime_json_before, (
            f"Noop must preserve managed-files.json mtime_ns: "
            f"before={mtime_json_before} after={mtime_json_after}"
        )
        assert bytes_file_after == bytes_file_before, (
            "Noop must preserve workflow file bytes"
        )
        assert bytes_json_after == bytes_json_before, (
            "Noop must preserve managed-files.json bytes"
        )

    def test_skipped_entries_in_result(self, tmp_path: Path) -> None:
        target = tmp_path / "target"
        candidate = tmp_path / "candidate"
        run1 = tmp_path / "run1"
        run2 = tmp_path / "run2"
        target.mkdir()

        workflow_content = "export const meta = { name: 'v1', description: 'v1' }\n"
        make_candidate_tree(candidate, {".claude/workflows/v1.js": workflow_content})

        # First apply
        r1 = run_managed([
            "apply-staged",
            "--target-root", str(target),
            "--source-root", str(candidate),
            "--run-root", str(run1),
            "--json",
        ])
        assert r1.returncode == 0, r1.stderr or r1.stdout

        # Second apply
        r2 = run_managed([
            "apply-staged",
            "--target-root", str(target),
            "--source-root", str(candidate),
            "--run-root", str(run2),
            "--json",
        ])
        assert r2.returncode == 0, r2.stderr or r2.stdout
        result2 = read_managed_result(run2)
        assert "skipped" in result2
        assert isinstance(result2["skipped"], list)
        assert len(result2["skipped"]) >= 1
        skipped_item = result2["skipped"][0]
        assert "relative_path" in skipped_item
        assert skipped_item["action"] == "noop"
        # applied and conflicts still present for backward compatibility
        assert "applied" in result2
        assert "conflicts" in result2
