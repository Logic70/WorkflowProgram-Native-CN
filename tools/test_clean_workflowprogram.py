#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / ".claude" / "scripts" / "clean-workflowprogram.py"


def run(cmd: List[str], *, env: Dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, check=False, env=env)


def load_payload(completed: subprocess.CompletedProcess[str]) -> Dict[str, Any]:
    try:
        return json.loads(completed.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise AssertionError(f"invalid JSON output: {exc}\nstdout={completed.stdout}\nstderr={completed.stderr}") from exc


def assert_check(payload: Dict[str, Any], condition: bool, name: str, failures: List[str], detail: str = "") -> None:
    if not condition:
        failures.append(f"{name}: {detail or payload}")


def make_run(path: Path, completed_at: str) -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / "runner-summary.json").write_text(json.dumps({"completed_at": completed_at}) + "\n", encoding="utf-8")
    (path / "state.json").write_text(json.dumps({"run_id": path.name}) + "\n", encoding="utf-8")


def main() -> int:
    failures: List[str] = []
    with tempfile.TemporaryDirectory(prefix="workflowprogram-clean-test-") as temp:
        temp_root = Path(temp)
        plugin_data = temp_root / "plugin-data"
        python_root = plugin_data / "python"
        site_packages = python_root / "site-packages"
        tmp_packages = python_root / "site-packages.tmp"
        site_packages.mkdir(parents=True)
        tmp_packages.mkdir(parents=True)
        (python_root / "bootstrap-state.json").write_text("{}\n", encoding="utf-8")
        (python_root / "requirements.lock.txt").write_text("PyYAML==6.0.2\n", encoding="utf-8")

        target_root = temp_root / "target"
        runs_root = target_root / ".workflowprogram" / "runs"
        make_run(runs_root / "run-old", "2026-01-01T00:00:00Z")
        make_run(runs_root / "run-middle", "2026-02-01T00:00:00Z")
        make_run(runs_root / "run-new", "2026-03-01T00:00:00Z")

        fake_repo = temp_root / "repo"
        transcript = fake_repo / "tests" / "transcripts" / "2099-clean-test"
        transcript.mkdir(parents=True)
        (transcript / "transcript.md").write_text("temporary\n", encoding="utf-8")
        pycache = fake_repo / "pkg" / "__pycache__"
        pycache.mkdir(parents=True)
        (pycache / "module.cpython-313.pyc").write_bytes(b"cache")

        env = os.environ.copy()
        env["CLAUDE_PLUGIN_DATA"] = str(plugin_data)

        dry = run(
            [
                sys.executable,
                str(SCRIPT),
                "--plugin-data",
                str(plugin_data),
                "--target-root",
                str(target_root),
                "--repo-root",
                str(fake_repo),
                "--python-runtime",
                "--test-artifacts",
                "--run-history",
                "--keep-last",
                "1",
                "--json",
            ],
            env=env,
        )
        dry_payload = load_payload(dry)
        assert_check(dry_payload, dry.returncode == 0, "dry_run_exit", failures, dry.stderr)
        assert_check(dry_payload, dry_payload.get("dry_run") is True, "dry_run_flag", failures)
        assert_check(dry_payload, site_packages.exists(), "dry_run_keeps_python_cache", failures)
        assert_check(dry_payload, transcript.exists(), "dry_run_keeps_transcript", failures)
        assert_check(dry_payload, (runs_root / "run-old").exists(), "dry_run_keeps_old_run", failures)
        assert_check(
            dry_payload,
            dry_payload.get("summary", {}).get("planned_delete_count", 0) >= 4,
            "dry_run_plans_deletes",
            failures,
        )

        no_scope_apply = run(
            [
                sys.executable,
                str(SCRIPT),
                "--plugin-data",
                str(plugin_data),
                "--target-root",
                str(target_root),
                "--repo-root",
                str(fake_repo),
                "--apply",
                "--json",
            ],
            env=env,
        )
        no_scope_payload = load_payload(no_scope_apply)
        assert_check(no_scope_payload, no_scope_apply.returncode == 0, "no_scope_apply_exit", failures, no_scope_apply.stderr)
        assert_check(no_scope_payload, no_scope_payload.get("dry_run") is True, "no_scope_apply_is_still_dry_run", failures)
        assert_check(no_scope_payload, site_packages.exists(), "no_scope_apply_keeps_python_cache", failures)
        assert_check(no_scope_payload, transcript.exists(), "no_scope_apply_keeps_transcript", failures)
        assert_check(no_scope_payload, (runs_root / "run-old").exists(), "no_scope_apply_keeps_old_run", failures)

        apply = run(
            [
                sys.executable,
                str(SCRIPT),
                "--plugin-data",
                str(plugin_data),
                "--target-root",
                str(target_root),
                "--repo-root",
                str(fake_repo),
                "--python-runtime",
                "--test-artifacts",
                "--run-history",
                "--keep-last",
                "1",
                "--apply",
                "--json",
            ],
            env=env,
        )
        apply_payload = load_payload(apply)
        assert_check(apply_payload, apply.returncode == 0, "apply_exit", failures, apply.stderr)
        assert_check(apply_payload, apply_payload.get("dry_run") is False, "apply_flag", failures)
        assert_check(apply_payload, not site_packages.exists(), "apply_deletes_site_packages", failures)
        assert_check(apply_payload, not tmp_packages.exists(), "apply_deletes_tmp_site_packages", failures)
        assert_check(apply_payload, not transcript.exists(), "apply_deletes_test_transcript", failures)
        assert_check(apply_payload, not pycache.exists(), "apply_deletes_pycache", failures)
        assert_check(apply_payload, not (runs_root / "run-old").exists(), "apply_deletes_old_run", failures)
        assert_check(apply_payload, not (runs_root / "run-middle").exists(), "apply_deletes_middle_run", failures)
        assert_check(apply_payload, (runs_root / "run-new").exists(), "apply_keeps_newest_run", failures)

        run_root = temp_root / "run-root"
        env["RUN_ROOT"] = str(run_root)
        report = run(
            [
                sys.executable,
                str(SCRIPT),
                "--plugin-data",
                str(plugin_data),
                "--python-runtime",
                "--json",
            ],
            env=env,
        )
        report_payload = load_payload(report)
        report_path = run_root / "outputs" / "stages" / "cache-cleanup-report.json"
        assert_check(report_payload, report.returncode == 0, "run_root_report_exit", failures, report.stderr)
        assert_check(report_payload, report_path.exists(), "run_root_report_written", failures)

    payload = {"status": "PASS" if not failures else "FAIL", "failures": failures}
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
