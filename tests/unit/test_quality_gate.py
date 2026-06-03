from __future__ import annotations

import json
import importlib.util
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
QUALITY_GATE = ROOT / ".claude" / "scripts" / "quality-gate.py"


def load_quality_gate_module():
    spec = importlib.util.spec_from_file_location("workflowprogram_quality_gate", QUALITY_GATE)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def run_gate(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(QUALITY_GATE), *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def load_json(completed: subprocess.CompletedProcess[str]) -> dict:
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise AssertionError(f"invalid JSON\nstdout={completed.stdout}\nstderr={completed.stderr}") from exc


def test_commit_gate_dry_run_is_fast_layer() -> None:
    completed = run_gate("commit", "--dry-run", "--json")
    assert completed.returncode == 0, completed.stderr or completed.stdout
    payload = load_json(completed)

    assert payload["status"] == "DRY_RUN"
    step_names = [item["name"] for item in payload["steps"]]
    assert "diff_added_line_check" in step_names
    assert "metadata_json_parse" in step_names
    assert "runtime_smoke_matrix" not in step_names
    assert "build_plugin" not in step_names


def test_release_gate_dry_run_keeps_heavy_release_checks() -> None:
    completed = run_gate("release", "--dry-run", "--json")
    assert completed.returncode == 0, completed.stderr or completed.stdout
    payload = load_json(completed)

    step_names = [item["name"] for item in payload["steps"]]
    assert "build_plugin" in step_names
    assert "version_consistency" in step_names
    assert "repository_validator" in step_names
    assert "plugin_bootstrap" in step_names
    assert "runtime_smoke_matrix" in step_names


def test_version_consistency_accepts_current_metadata() -> None:
    module = load_quality_gate_module()

    ok, message, extra = module.version_consistency()

    assert ok, message
    assert len(set(extra["versions"].values())) == 1


def test_unknown_gate_returns_structured_failure() -> None:
    completed = run_gate("unknown", "--json")
    assert completed.returncode == 2
    payload = load_json(completed)

    assert payload["status"] == "FAIL"
    assert "commit, integration, release" in payload["error"]


def test_run_command_uses_utf8_and_accepts_empty_output(monkeypatch) -> None:
    module = load_quality_gate_module()
    captured: dict = {}

    def fake_run(*args, **kwargs):
        captured.update(kwargs)
        return subprocess.CompletedProcess(args=args, returncode=0, stdout=None, stderr=None)

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    ok, output, extra = module.run_command(module.step("probe", "probe", ["probe"]))

    assert ok
    assert output == ""
    assert extra == {"returncode": 0}
    assert captured["encoding"] == "utf-8"
    assert captured["errors"] == "replace"


def test_diff_added_line_check_accepts_empty_stdout(monkeypatch) -> None:
    module = load_quality_gate_module()

    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(args=args, returncode=0, stdout=None, stderr=None)

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    ok, message, extra = module.diff_added_line_check()

    assert ok, message
    assert extra == {"failure_count": 0}


def test_diff_added_line_check_rejects_conflict_marker(monkeypatch) -> None:
    module = load_quality_gate_module()

    def fake_run(*args, **kwargs):
        marker = "<" * 7
        return subprocess.CompletedProcess(
            args=args,
            returncode=0,
            stdout=f"+++ b/example.txt\n@@ -0,0 +1 @@\n+{marker} branch\n",
            stderr=None,
        )

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    ok, message, extra = module.diff_added_line_check()

    assert not ok
    assert "example.txt:1" in message
    assert extra == {"failure_count": 1}
