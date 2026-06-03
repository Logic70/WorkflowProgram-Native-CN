from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / ".claude" / "scripts" / "build-native-publish-evidence.py"


def run_subcommand(stage: str, **kwargs: str) -> subprocess.CompletedProcess[str]:
    args = [sys.executable, str(SCRIPT), stage, "--json"]
    for key, value in kwargs.items():
        args.extend([f"--{key.replace('_', '-')}", value])
    return subprocess.run(args, cwd=ROOT, capture_output=True, text=True, check=False)


def load_json(completed: subprocess.CompletedProcess[str]) -> dict:
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise AssertionError(f"invalid JSON\nstdout={completed.stdout}\nstderr={completed.stderr}") from exc


def write_report(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload) + "\n", encoding="utf-8")


def write_files(root: Path, files: dict[str, str]) -> None:
    for rel, content in files.items():
        full = root / rel
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(content, encoding="utf-8")


# ── qualification ────────────────────────────────────────────────

def test_qualification_pass(tmp_path: Path) -> None:
    target = tmp_path / "target"
    write_files(target, {"a.txt": "hello"})
    report_path = tmp_path / "report.json"
    write_report(report_path, {"status": "PASS"})

    completed = run_subcommand("qualification", report=str(report_path), target_root=str(target))
    assert completed.returncode == 0
    payload = load_json(completed)
    assert payload["status"] == "PASS"
    assert payload["targetHash"].startswith("sha256:")
    assert len(payload["targetHash"]) > len("sha256:")
    assert len(payload["evidence"]) > 0
    assert payload["blockingIssues"] == []


def test_qualification_fail_report_status(tmp_path: Path) -> None:
    target = tmp_path / "target"
    write_files(target, {"a.txt": "hello"})
    report_path = tmp_path / "report.json"
    write_report(report_path, {"status": "FAIL", "blockingIssues": ["Missing required files."]})

    completed = run_subcommand("qualification", report=str(report_path), target_root=str(target))
    assert completed.returncode == 1
    payload = load_json(completed)
    assert payload["status"] == "FAIL"
    assert len(payload["blockingIssues"]) > 0


def test_qualification_missing_report(tmp_path: Path) -> None:
    target = tmp_path / "target"
    write_files(target, {"a.txt": "hello"})

    completed = run_subcommand("qualification", report=str(tmp_path / "nonexistent.json"), target_root=str(target))
    assert completed.returncode == 1
    payload = load_json(completed)
    assert payload["status"] == "FAIL"


def test_qualification_malformed_json(tmp_path: Path) -> None:
    target = tmp_path / "target"
    write_files(target, {"a.txt": "hello"})
    report_path = tmp_path / "report.json"
    report_path.write_text("not json", encoding="utf-8")

    completed = run_subcommand("qualification", report=str(report_path), target_root=str(target))
    assert completed.returncode == 1
    payload = load_json(completed)
    assert payload["status"] == "FAIL"


def test_qualification_non_object_report(tmp_path: Path) -> None:
    target = tmp_path / "target"
    write_files(target, {"a.txt": "hello"})
    report_path = tmp_path / "report.json"
    report_path.write_text("[]", encoding="utf-8")

    completed = run_subcommand("qualification", report=str(report_path), target_root=str(target))
    assert completed.returncode == 1
    payload = load_json(completed)
    assert payload["status"] == "FAIL"


def test_qualification_tree_hash_changes(tmp_path: Path) -> None:
    target = tmp_path / "target"
    write_files(target, {"a.txt": "hello"})
    report_path = tmp_path / "report.json"
    write_report(report_path, {"status": "PASS"})

    first = load_json(run_subcommand("qualification", report=str(report_path), target_root=str(target)))
    # Change a file
    (target / "a.txt").write_text("world", encoding="utf-8")
    second = load_json(run_subcommand("qualification", report=str(report_path), target_root=str(target)))

    assert first["targetHash"] != second["targetHash"]


def test_qualification_empty_target_root(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    report_path = tmp_path / "report.json"
    write_report(report_path, {"status": "PASS"})

    completed = run_subcommand("qualification", report=str(report_path), target_root=str(target))
    assert completed.returncode == 1
    payload = load_json(completed)
    assert payload["status"] == "FAIL"


# ── package ──────────────────────────────────────────────────────

def test_package_pass(tmp_path: Path) -> None:
    target = tmp_path / "target"
    package = tmp_path / "package"
    write_files(target, {"spec.yaml": "name: test"})
    write_files(package, {"plugin.json": "{}"})
    report_path = tmp_path / "report.json"
    write_report(report_path, {"status": "PASS"})

    completed = run_subcommand("package", report=str(report_path), package_root=str(package), target_root=str(target))
    assert completed.returncode == 0
    payload = load_json(completed)
    assert payload["status"] == "PASS"
    assert payload["targetHash"].startswith("sha256:")
    assert payload["packageHash"].startswith("sha256:")
    assert payload["targetHash"] != payload["packageHash"]
    assert len(payload["evidence"]) > 0
    assert payload["blockingIssues"] == []


def test_package_fail_report_status(tmp_path: Path) -> None:
    target = tmp_path / "target"
    package = tmp_path / "package"
    write_files(target, {"spec.yaml": "name: test"})
    write_files(package, {"plugin.json": "{}"})
    report_path = tmp_path / "report.json"
    write_report(report_path, {"status": "FAIL", "blockingIssues": ["Missing plugin metadata."]})

    completed = run_subcommand("package", report=str(report_path), package_root=str(package), target_root=str(target))
    assert completed.returncode == 1
    payload = load_json(completed)
    assert payload["status"] == "FAIL"
    assert len(payload["blockingIssues"]) > 0


def test_package_missing_report(tmp_path: Path) -> None:
    target = tmp_path / "target"
    package = tmp_path / "package"
    write_files(target, {"spec.yaml": "name: test"})
    write_files(package, {"plugin.json": "{}"})

    completed = run_subcommand("package", report=str(tmp_path / "nonexistent.json"), package_root=str(package), target_root=str(target))
    assert completed.returncode == 1


def test_package_malformed_json(tmp_path: Path) -> None:
    target = tmp_path / "target"
    package = tmp_path / "package"
    write_files(target, {"spec.yaml": "name: test"})
    write_files(package, {"plugin.json": "{}"})
    report_path = tmp_path / "report.json"
    report_path.write_text("{invalid", encoding="utf-8")

    completed = run_subcommand("package", report=str(report_path), package_root=str(package), target_root=str(target))
    assert completed.returncode == 1


def test_package_non_object_report(tmp_path: Path) -> None:
    target = tmp_path / "target"
    package = tmp_path / "package"
    write_files(target, {"spec.yaml": "name: test"})
    write_files(package, {"plugin.json": "{}"})
    report_path = tmp_path / "report.json"
    report_path.write_text('"not an object"', encoding="utf-8")

    completed = run_subcommand("package", report=str(report_path), package_root=str(package), target_root=str(target))
    assert completed.returncode == 1


def test_package_empty_package_root(tmp_path: Path) -> None:
    target = tmp_path / "target"
    package = tmp_path / "package"
    write_files(target, {"spec.yaml": "name: test"})
    package.mkdir()
    report_path = tmp_path / "report.json"
    write_report(report_path, {"status": "PASS"})

    completed = run_subcommand("package", report=str(report_path), package_root=str(package), target_root=str(target))
    assert completed.returncode == 1


def test_package_hash_changes_on_file_change(tmp_path: Path) -> None:
    target = tmp_path / "target"
    package = tmp_path / "package"
    write_files(target, {"spec.yaml": "name: test"})
    write_files(package, {"plugin.json": "{}"})
    report_path = tmp_path / "report.json"
    write_report(report_path, {"status": "PASS"})

    first = load_json(run_subcommand("package", report=str(report_path), package_root=str(package), target_root=str(target)))
    (package / "plugin.json").write_text('{"version": "2.0"}', encoding="utf-8")
    second = load_json(run_subcommand("package", report=str(report_path), package_root=str(package), target_root=str(target)))

    assert first["packageHash"] != second["packageHash"]


# ── verification ─────────────────────────────────────────────────

def test_verification_pass(tmp_path: Path) -> None:
    package = tmp_path / "package"
    write_files(package, {"plugin.json": "{}"})
    report_path = tmp_path / "report.json"
    write_report(report_path, {"status": "PASS"})

    completed = run_subcommand("verification", report=str(report_path), package_root=str(package))
    assert completed.returncode == 0
    payload = load_json(completed)
    assert payload["status"] == "PASS"
    assert payload["packageHash"].startswith("sha256:")
    assert len(payload["evidence"]) > 0
    assert payload["blockingIssues"] == []


def test_verification_fail(tmp_path: Path) -> None:
    package = tmp_path / "package"
    write_files(package, {"plugin.json": "{}"})
    report_path = tmp_path / "report.json"
    write_report(report_path, {"status": "FAIL", "blockingIssues": ["Broken refs."]})

    completed = run_subcommand("verification", report=str(report_path), package_root=str(package))
    assert completed.returncode == 1
    payload = load_json(completed)
    assert payload["status"] == "FAIL"


def test_verification_missing_report(tmp_path: Path) -> None:
    package = tmp_path / "package"
    write_files(package, {"plugin.json": "{}"})

    completed = run_subcommand("verification", report=str(tmp_path / "nonexistent.json"), package_root=str(package))
    assert completed.returncode == 1


# ── local-delivery ───────────────────────────────────────────────

def test_local_delivery_creates_outputs(tmp_path: Path) -> None:
    package = tmp_path / "package"
    run = tmp_path / "run"
    write_files(package, {"plugin.json": "{}"})

    completed = run_subcommand(
        "local-delivery",
        package_root=str(package),
        run_root=str(run),
        repository="https://github.com/example/repo",
        marketplace_name="my-marketplace",
        plugin_id="my-plugin",
        version="0.1.0",
        runtime_mode="workflowprogram_dependency",
        repo_mode="export_repo",
    )
    assert completed.returncode == 0
    payload = load_json(completed)
    assert payload["status"] == "PASS"
    assert payload["packageHash"].startswith("sha256:")
    assert payload["blockingIssues"] == []
    assert len(payload["evidence"]) == 2

    install_path = run / "outputs" / "stages" / "publish" / "install-instructions.md"
    delivery_path = run / "outputs" / "stages" / "publish" / "native-local-delivery.json"
    assert install_path.exists()
    assert delivery_path.exists()
    assert "my-plugin" in install_path.read_text(encoding="utf-8")
    delivery = json.loads(delivery_path.read_text(encoding="utf-8"))
    assert delivery["status"] == "PASS"
    assert delivery["packageHash"] == payload["packageHash"]
    assert delivery["pluginId"] == "my-plugin"
    assert delivery["version"] == "0.1.0"


def test_local_delivery_empty_package_root(tmp_path: Path) -> None:
    package = tmp_path / "package"
    package.mkdir()
    run = tmp_path / "run"

    completed = run_subcommand(
        "local-delivery",
        package_root=str(package),
        run_root=str(run),
        repository="https://github.com/example/repo",
        plugin_id="my-plugin",
        version="0.1.0",
        runtime_mode="workflowprogram_dependency",
        repo_mode="export_repo",
    )
    assert completed.returncode == 1


# ── target_hash stability ────────────────────────────────────────

def test_target_hash_stable_when_runs_change(tmp_path: Path) -> None:
    target = tmp_path / "target"
    write_files(target, {"spec.yaml": "name: test"})

    runs_dir = target / ".workflowprogram" / "runs" / "run-001"
    runs_dir.mkdir(parents=True)
    (runs_dir / "evidence.json").write_text('{"status": "PASS"}', encoding="utf-8")

    git_dir = target / ".git"
    git_dir.mkdir()
    (git_dir / "HEAD").write_text("ref: refs/heads/main", encoding="utf-8")

    report_path = tmp_path / "report.json"
    write_report(report_path, {"status": "PASS"})

    first = load_json(run_subcommand("qualification", report=str(report_path), target_root=str(target)))

    (runs_dir / "evidence.json").write_text('{"status": "CHANGED"}', encoding="utf-8")
    (git_dir / "HEAD").write_text("ref: refs/heads/feature", encoding="utf-8")

    second = load_json(run_subcommand("qualification", report=str(report_path), target_root=str(target)))

    assert first["targetHash"] == second["targetHash"]


def test_target_hash_changes_when_real_asset_changes(tmp_path: Path) -> None:
    target = tmp_path / "target"
    write_files(target, {"spec.yaml": "name: test"})

    report_path = tmp_path / "report.json"
    write_report(report_path, {"status": "PASS"})

    first = load_json(run_subcommand("qualification", report=str(report_path), target_root=str(target)))

    (target / "spec.yaml").write_text("name: changed", encoding="utf-8")

    second = load_json(run_subcommand("qualification", report=str(report_path), target_root=str(target)))

    assert first["targetHash"] != second["targetHash"]


# ── marketplace ──────────────────────────────────────────────────

def test_marketplace_pass(tmp_path: Path) -> None:
    package = tmp_path / "package"
    write_files(package, {"plugin.json": "{}"})
    report_path = tmp_path / "report.json"
    write_report(report_path, {"status": "PASS"})

    completed = run_subcommand("marketplace", report=str(report_path), package_root=str(package))
    assert completed.returncode == 0
    payload = load_json(completed)
    assert payload["status"] == "PASS"
    assert payload["packageHash"].startswith("sha256:")
    assert payload["blockingIssues"] == []


def test_marketplace_fail(tmp_path: Path) -> None:
    package = tmp_path / "package"
    write_files(package, {"plugin.json": "{}"})
    report_path = tmp_path / "report.json"
    write_report(report_path, {"status": "FAIL", "blockingIssues": ["Conflict with existing entry."]})

    completed = run_subcommand("marketplace", report=str(report_path), package_root=str(package))
    assert completed.returncode == 1


def test_marketplace_missing_report(tmp_path: Path) -> None:
    package = tmp_path / "package"
    write_files(package, {"plugin.json": "{}"})

    completed = run_subcommand("marketplace", report=str(tmp_path / "nonexistent.json"), package_root=str(package))
    assert completed.returncode == 1


# ── external-apply ───────────────────────────────────────────────

def test_external_apply_pass(tmp_path: Path) -> None:
    package = tmp_path / "package"
    write_files(package, {"plugin.json": "{}"})

    import hashlib
    files = sorted(path for path in package.rglob("*") if path.is_file())
    digest = hashlib.sha256()
    for path in files:
        relative = path.relative_to(package).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    expected_hash = f"sha256:{digest.hexdigest()}"

    report_path = tmp_path / "report.json"
    write_report(report_path, {"status": "PASS", "package_hash": expected_hash})

    completed = run_subcommand("external-apply", report=str(report_path), package_root=str(package))
    assert completed.returncode == 0
    payload = load_json(completed)
    assert payload["status"] == "PASS"
    assert payload["packageHash"].startswith("sha256:")


def test_external_apply_preserves_blocked(tmp_path: Path) -> None:
    package = tmp_path / "package"
    write_files(package, {"plugin.json": "{}"})
    report_path = tmp_path / "report.json"
    write_report(report_path, {"status": "BLOCKED", "blockingIssues": ["Auth missing."]})

    completed = run_subcommand("external-apply", report=str(report_path), package_root=str(package))
    assert completed.returncode == 1
    payload = load_json(completed)
    assert payload["status"] == "BLOCKED"
    assert payload["blockingIssues"] == ["Auth missing."]


def test_external_apply_preserves_fail(tmp_path: Path) -> None:
    package = tmp_path / "package"
    write_files(package, {"plugin.json": "{}"})
    report_path = tmp_path / "report.json"
    write_report(report_path, {"status": "FAIL", "blockingIssues": ["Push rejected."]})

    completed = run_subcommand("external-apply", report=str(report_path), package_root=str(package))
    assert completed.returncode == 1
    payload = load_json(completed)
    assert payload["status"] == "FAIL"
    assert payload["blockingIssues"] == ["Push rejected."]


def test_external_apply_missing_report(tmp_path: Path) -> None:
    package = tmp_path / "package"
    write_files(package, {"plugin.json": "{}"})

    completed = run_subcommand("external-apply", report=str(tmp_path / "nonexistent.json"), package_root=str(package))
    assert completed.returncode == 1


def test_external_apply_malformed_report(tmp_path: Path) -> None:
    package = tmp_path / "package"
    write_files(package, {"plugin.json": "{}"})
    report_path = tmp_path / "report.json"
    report_path.write_text("{bad", encoding="utf-8")

    completed = run_subcommand("external-apply", report=str(report_path), package_root=str(package))
    assert completed.returncode == 1


# ── external-apply package_hash validation ─────────────────────────

def test_external_apply_pass_rejects_missing_package_hash(tmp_path: Path) -> None:
    """A PASS report without package_hash must be rejected as FAIL."""
    package = tmp_path / "package"
    write_files(package, {"plugin.json": "{}"})
    report_path = tmp_path / "report.json"
    write_report(report_path, {"status": "PASS"})

    completed = run_subcommand("external-apply", report=str(report_path), package_root=str(package))
    assert completed.returncode == 1
    payload = load_json(completed)
    assert payload["status"] == "FAIL"
    assert any("package_hash" in issue.lower() for issue in payload["blockingIssues"])


def test_external_apply_pass_rejects_mismatched_package_hash(tmp_path: Path) -> None:
    """A PASS report with a stale package_hash must be rejected as FAIL."""
    package = tmp_path / "package"
    write_files(package, {"plugin.json": "{}"})
    report_path = tmp_path / "report.json"
    write_report(report_path, {"status": "PASS", "package_hash": "sha256:0000deadbeef"})

    completed = run_subcommand("external-apply", report=str(report_path), package_root=str(package))
    assert completed.returncode == 1
    payload = load_json(completed)
    assert payload["status"] == "FAIL"
    assert any("stale" in issue.lower() for issue in payload["blockingIssues"])


def test_external_apply_pass_accepts_matching_package_hash(tmp_path: Path) -> None:
    """A PASS report with a correct package_hash must be accepted."""
    package = tmp_path / "package"
    write_files(package, {"plugin.json": "{}"})

    import hashlib
    files = sorted(path for path in package.rglob("*") if path.is_file())
    digest = hashlib.sha256()
    for path in files:
        relative = path.relative_to(package).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    expected_hash = f"sha256:{digest.hexdigest()}"

    report_path = tmp_path / "report.json"
    write_report(report_path, {"status": "PASS", "package_hash": expected_hash})

    completed = run_subcommand("external-apply", report=str(report_path), package_root=str(package))
    assert completed.returncode == 0
    payload = load_json(completed)
    assert payload["status"] == "PASS"
    assert payload["packageHash"] == expected_hash


def test_external_apply_blocked_skips_hash_validation(tmp_path: Path) -> None:
    """A BLOCKED report without package_hash is preserved as BLOCKED."""
    package = tmp_path / "package"
    write_files(package, {"plugin.json": "{}"})
    report_path = tmp_path / "report.json"
    write_report(report_path, {"status": "BLOCKED", "blockingIssues": ["Auth missing."]})

    completed = run_subcommand("external-apply", report=str(report_path), package_root=str(package))
    assert completed.returncode == 1
    payload = load_json(completed)
    assert payload["status"] == "BLOCKED"
    assert payload["packageHash"].startswith("sha256:")


def test_external_apply_rejects_dry_run_pass(tmp_path: Path) -> None:
    """A PASS report with dry_run=true must be rejected as FAIL — simulation is not a real external apply."""
    package = tmp_path / "package"
    write_files(package, {"plugin.json": "{}"})

    import hashlib
    files = sorted(path for path in package.rglob("*") if path.is_file())
    digest = hashlib.sha256()
    for path in files:
        relative = path.relative_to(package).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    expected_hash = f"sha256:{digest.hexdigest()}"

    report_path = tmp_path / "report.json"
    write_report(report_path, {"status": "PASS", "package_hash": expected_hash, "dry_run": True})

    completed = run_subcommand("external-apply", report=str(report_path), package_root=str(package))
    assert completed.returncode == 1
    payload = load_json(completed)
    assert payload["status"] == "FAIL"
    assert any("dry_run" in issue.lower() for issue in payload["blockingIssues"])
