from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / ".claude" / "scripts" / "github-publish-target-plugin.py"


# Boolean flags that should not receive a value argument
_BOOLEAN_FLAGS = frozenset({
    "execute", "approved", "dry_run", "simulate_auth_missing",
    "simulate_auth_ready", "json",
})


def run_publish(**kwargs) -> subprocess.CompletedProcess[str]:
    args = [sys.executable, str(SCRIPT), "--json"]
    for key, value in kwargs.items():
        flag = f"--{key.replace('_', '-')}"
        if key in _BOOLEAN_FLAGS:
            args.append(flag)
        else:
            args.extend([flag, str(value)])
    return subprocess.run(args, cwd=ROOT, capture_output=True, text=True, check=False)


def load_json(completed: subprocess.CompletedProcess[str]) -> dict:
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise AssertionError(
            f"invalid JSON\nstdout={completed.stdout}\nstderr={completed.stderr}"
        ) from exc


def write_files(root: Path, files: dict[str, str]) -> None:
    for rel, content in files.items():
        full = root / rel
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(content, encoding="utf-8")


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def make_git_repo(repo_path: Path) -> None:
    """Initialize a minimal git repo with an initial commit."""
    repo_path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init"], cwd=repo_path, capture_output=True, text=True, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=repo_path, capture_output=True, text=True, check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=repo_path, capture_output=True, text=True, check=True,
    )
    (repo_path / "README.md").write_text("# Test\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=repo_path, capture_output=True, text=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", "initial commit"],
        cwd=repo_path, capture_output=True, text=True, check=True,
    )


# ── tree_hash unit tests ──────────────────────────────────────────

def test_tree_hash_stable(tmp_path: Path) -> None:
    pkg = tmp_path / "package"
    write_files(pkg, {"a.json": "{}", "b.md": "# hello"})

    h1 = _tree_hash(pkg)
    h2 = _tree_hash(pkg)
    assert h1 == h2
    assert h1.startswith("sha256:")


def test_tree_hash_changes_on_file_change(tmp_path: Path) -> None:
    pkg = tmp_path / "package"
    write_files(pkg, {"a.json": "{}"})

    h1 = _tree_hash(pkg)
    (pkg / "a.json").write_text('{"v":2}', encoding="utf-8")
    h2 = _tree_hash(pkg)

    assert h1 != h2


def test_tree_hash_empty_dir_raises(tmp_path: Path) -> None:
    pkg = tmp_path / "package"
    pkg.mkdir()
    with pytest.raises(ValueError):
        _tree_hash(pkg)


def test_tree_hash_missing_root_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        _tree_hash(tmp_path / "nonexistent")


def _tree_hash(root: Path) -> str:
    import hashlib
    if not root.is_dir():
        raise FileNotFoundError(f"Root not found: {root}")
    files = sorted(path for path in root.rglob("*") if path.is_file())
    if not files:
        raise ValueError(f"Root is empty: {root}")
    digest = hashlib.sha256()
    for path in files:
        relative = path.relative_to(root).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return f"sha256:{digest.hexdigest()}"


# ── plan payload includes package_hash ─────────────────────────────

def test_plan_includes_package_hash(tmp_path: Path) -> None:
    pkg = tmp_path / "package"
    run_root = tmp_path / "run"
    repo = tmp_path / "repo"
    make_git_repo(repo)
    write_files(pkg, {"plugin.json": "{}"})

    # dry-run writes plan + result, no git ops needed
    completed = run_publish(
        package_root=str(pkg),
        run_root=str(run_root),
        repository="https://github.com/test/repo",
        repo_mode="export_repo",
        repo_path=str(repo),
        version="0.1.0",
        dry_run="",
    )
    assert completed.returncode == 0

    plan_path = run_root / "outputs" / "stages" / "publish" / "github-publish-plan.json"
    assert plan_path.exists()
    plan = read_json(plan_path)
    assert "package_hash" in plan
    assert plan["package_hash"].startswith("sha256:")


# ── idempotency: prior PASS with matching keys short-circuits ──────

def test_idempotent_pass_return(tmp_path: Path) -> None:
    pkg = tmp_path / "package"
    run_root = tmp_path / "run"
    repo = tmp_path / "repo"
    make_git_repo(repo)
    write_files(pkg, {"plugin.json": "{}"})

    from hashlib import sha256 as _sha256
    files = sorted(path for path in pkg.rglob("*") if path.is_file())
    digest = _sha256()
    for path in files:
        r = path.relative_to(pkg).as_posix()
        digest.update(r.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    expected_hash = f"sha256:{digest.hexdigest()}"

    # Pre-create a PASS receipt with matching keys (not dry-run)
    result_dir = run_root / "outputs" / "stages" / "publish"
    result_dir.mkdir(parents=True)
    prior = {
        "schema_version": 1,
        "generated_at": "2026-01-01T00:00:00Z",
        "status": "PASS",
        "package_hash": expected_hash,
        "repository": "https://github.com/test/repo",
        "repo_mode": "export_repo",
        "version": "0.1.0",
        "message": "Prior success.",
    }
    (result_dir / "github-publish-result.json").write_text(
        json.dumps(prior) + "\n", encoding="utf-8"
    )

    completed = run_publish(
        package_root=str(pkg),
        run_root=str(run_root),
        repository="https://github.com/test/repo",
        repo_mode="export_repo",
        repo_path=str(repo),
        version="0.1.0",
        execute="",
        approved="",
        simulate_auth_ready="",
    )
    assert completed.returncode == 0
    payload = load_json(completed)
    assert payload["status"] == "PASS"
    assert payload.get("idempotent") is True
    assert "already completed" in payload.get("message", "")


def test_prior_pass_mismatched_hash_proceeds(tmp_path: Path) -> None:
    pkg = tmp_path / "package"
    run_root = tmp_path / "run"
    repo = tmp_path / "repo"
    make_git_repo(repo)
    write_files(pkg, {"plugin.json": "{}"})

    # Pre-create a PASS receipt with a WRONG hash
    result_dir = run_root / "outputs" / "stages" / "publish"
    result_dir.mkdir(parents=True)
    prior = {
        "schema_version": 1,
        "status": "PASS",
        "package_hash": "sha256:0000deadbeef",
        "repository": "https://github.com/test/repo",
        "repo_mode": "export_repo",
        "version": "0.1.0",
    }
    (result_dir / "github-publish-result.json").write_text(
        json.dumps(prior) + "\n", encoding="utf-8"
    )

    # Should NOT short-circuit; will proceed to git ops and fail (not a clean checkout
    # with the right structure, but we just verify it's NOT an idempotent PASS)
    completed = run_publish(
        package_root=str(pkg),
        run_root=str(run_root),
        repository="https://github.com/test/repo",
        repo_mode="export_repo",
        repo_path=str(repo),
        version="0.1.0",
        execute="",
        approved="",
        simulate_auth_ready="",
    )
    # Will fail at git commit because the repo doesn't have dist/plugin staged,
    # but the key point is it did NOT return 0 (idempotent PASS)
    payload = load_json(completed)
    assert not (payload["status"] == "PASS" and payload.get("idempotent"))


def test_prior_pass_mismatched_repo_proceeds(tmp_path: Path) -> None:
    pkg = tmp_path / "package"
    run_root = tmp_path / "run"
    repo = tmp_path / "repo"
    make_git_repo(repo)
    write_files(pkg, {"plugin.json": "{}"})

    from hashlib import sha256 as _sha256
    files = sorted(path for path in pkg.rglob("*") if path.is_file())
    digest = _sha256()
    for path in files:
        r = path.relative_to(pkg).as_posix()
        digest.update(r.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    expected_hash = f"sha256:{digest.hexdigest()}"

    result_dir = run_root / "outputs" / "stages" / "publish"
    result_dir.mkdir(parents=True)
    prior = {
        "schema_version": 1,
        "status": "PASS",
        "package_hash": expected_hash,
        "repository": "https://github.com/other/repo",  # different
        "repo_mode": "export_repo",
        "version": "0.1.0",
    }
    (result_dir / "github-publish-result.json").write_text(
        json.dumps(prior) + "\n", encoding="utf-8"
    )

    completed = run_publish(
        package_root=str(pkg),
        run_root=str(run_root),
        repository="https://github.com/test/repo",
        repo_mode="export_repo",
        repo_path=str(repo),
        version="0.1.0",
        execute="",
        approved="",
        simulate_auth_ready="",
    )
    payload = load_json(completed)
    assert not (payload["status"] == "PASS" and payload.get("idempotent"))


def test_dry_run_receipt_does_not_authorize_real_execute(tmp_path: Path) -> None:
    pkg = tmp_path / "package"
    run_root = tmp_path / "run"
    repo = tmp_path / "repo"
    make_git_repo(repo)
    write_files(pkg, {"plugin.json": "{}"})

    from hashlib import sha256 as _sha256
    files = sorted(path for path in pkg.rglob("*") if path.is_file())
    digest = _sha256()
    for path in files:
        r = path.relative_to(pkg).as_posix()
        digest.update(r.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    expected_hash = f"sha256:{digest.hexdigest()}"

    # Pre-create a dry-run PASS receipt with matching keys
    result_dir = run_root / "outputs" / "stages" / "publish"
    result_dir.mkdir(parents=True)
    prior = {
        "schema_version": 1,
        "status": "PASS",
        "dry_run": True,
        "package_hash": expected_hash,
        "repository": "https://github.com/test/repo",
        "repo_mode": "export_repo",
        "version": "0.1.0",
    }
    (result_dir / "github-publish-result.json").write_text(
        json.dumps(prior) + "\n", encoding="utf-8"
    )

    completed = run_publish(
        package_root=str(pkg),
        run_root=str(run_root),
        repository="https://github.com/test/repo",
        repo_mode="export_repo",
        repo_path=str(repo),
        version="0.1.0",
        execute="",
        approved="",
        simulate_auth_ready="",
    )
    payload = load_json(completed)
    # Must NOT be an idempotent PASS — dry_run receipt does not authorize real execute
    assert not (payload["status"] == "PASS" and payload.get("idempotent"))


def test_prior_fail_no_shortcut(tmp_path: Path) -> None:
    pkg = tmp_path / "package"
    run_root = tmp_path / "run"
    repo = tmp_path / "repo"
    make_git_repo(repo)
    write_files(pkg, {"plugin.json": "{}"})

    from hashlib import sha256 as _sha256
    files = sorted(path for path in pkg.rglob("*") if path.is_file())
    digest = _sha256()
    for path in files:
        r = path.relative_to(pkg).as_posix()
        digest.update(r.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    expected_hash = f"sha256:{digest.hexdigest()}"

    result_dir = run_root / "outputs" / "stages" / "publish"
    result_dir.mkdir(parents=True)
    prior = {
        "schema_version": 1,
        "status": "FAIL",
        "package_hash": expected_hash,
        "repository": "https://github.com/test/repo",
        "repo_mode": "export_repo",
        "version": "0.1.0",
    }
    (result_dir / "github-publish-result.json").write_text(
        json.dumps(prior) + "\n", encoding="utf-8"
    )

    completed = run_publish(
        package_root=str(pkg),
        run_root=str(run_root),
        repository="https://github.com/test/repo",
        repo_mode="export_repo",
        repo_path=str(repo),
        version="0.1.0",
        execute="",
        approved="",
        simulate_auth_ready="",
    )
    payload = load_json(completed)
    assert payload["status"] != "PASS" or payload.get("idempotent") is not True


def test_prior_blocked_no_shortcut(tmp_path: Path) -> None:
    pkg = tmp_path / "package"
    run_root = tmp_path / "run"
    repo = tmp_path / "repo"
    make_git_repo(repo)
    write_files(pkg, {"plugin.json": "{}"})

    from hashlib import sha256 as _sha256
    files = sorted(path for path in pkg.rglob("*") if path.is_file())
    digest = _sha256()
    for path in files:
        r = path.relative_to(pkg).as_posix()
        digest.update(r.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    expected_hash = f"sha256:{digest.hexdigest()}"

    result_dir = run_root / "outputs" / "stages" / "publish"
    result_dir.mkdir(parents=True)
    prior = {
        "schema_version": 1,
        "status": "BLOCKED",
        "package_hash": expected_hash,
        "repository": "https://github.com/test/repo",
        "repo_mode": "export_repo",
        "version": "0.1.0",
    }
    (result_dir / "github-publish-result.json").write_text(
        json.dumps(prior) + "\n", encoding="utf-8"
    )

    completed = run_publish(
        package_root=str(pkg),
        run_root=str(run_root),
        repository="https://github.com/test/repo",
        repo_mode="export_repo",
        repo_path=str(repo),
        version="0.1.0",
        execute="",
        approved="",
        simulate_auth_ready="",
    )
    payload = load_json(completed)
    assert payload["status"] != "PASS" or payload.get("idempotent") is not True


def test_idempotent_pass_with_auth_missing_and_no_repo_path(tmp_path: Path) -> None:
    """Matching prior real PASS + execute/approved returns idempotent PASS even when
    auth is currently missing and repo_path is omitted."""
    pkg = tmp_path / "package"
    run_root = tmp_path / "run"
    write_files(pkg, {"plugin.json": "{}"})

    from hashlib import sha256 as _sha256
    files = sorted(path for path in pkg.rglob("*") if path.is_file())
    digest = _sha256()
    for path in files:
        r = path.relative_to(pkg).as_posix()
        digest.update(r.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    expected_hash = f"sha256:{digest.hexdigest()}"

    # Pre-create a real PASS receipt with matching keys (not dry-run)
    result_dir = run_root / "outputs" / "stages" / "publish"
    result_dir.mkdir(parents=True)
    prior = {
        "schema_version": 1,
        "status": "PASS",
        "package_hash": expected_hash,
        "repository": "https://github.com/test/repo",
        "repo_mode": "export_repo",
        "version": "0.1.0",
    }
    (result_dir / "github-publish-result.json").write_text(
        json.dumps(prior) + "\n", encoding="utf-8"
    )

    # execute+approved, but simulate_auth_missing and no repo_path
    # Should still get idempotent PASS — short-circuit fires before auth/repo checks
    completed = run_publish(
        package_root=str(pkg),
        run_root=str(run_root),
        repository="https://github.com/test/repo",
        repo_mode="export_repo",
        repo_path="",
        version="0.1.0",
        execute="",
        approved="",
        simulate_auth_missing="",
    )
    assert completed.returncode == 0
    payload = load_json(completed)
    assert payload["status"] == "PASS"
    assert payload.get("idempotent") is True


def test_prior_pass_without_execute_does_not_bypass_approval(tmp_path: Path) -> None:
    """Matching prior PASS without execute/approved does not bypass approval
    — returns BLOCKED (approval_required)."""
    pkg = tmp_path / "package"
    run_root = tmp_path / "run"
    repo = tmp_path / "repo"
    make_git_repo(repo)
    write_files(pkg, {"plugin.json": "{}"})

    from hashlib import sha256 as _sha256
    files = sorted(path for path in pkg.rglob("*") if path.is_file())
    digest = _sha256()
    for path in files:
        r = path.relative_to(pkg).as_posix()
        digest.update(r.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    expected_hash = f"sha256:{digest.hexdigest()}"

    # Pre-create a real PASS receipt with matching keys
    result_dir = run_root / "outputs" / "stages" / "publish"
    result_dir.mkdir(parents=True)
    prior = {
        "schema_version": 1,
        "status": "PASS",
        "package_hash": expected_hash,
        "repository": "https://github.com/test/repo",
        "repo_mode": "export_repo",
        "version": "0.1.0",
    }
    (result_dir / "github-publish-result.json").write_text(
        json.dumps(prior) + "\n", encoding="utf-8"
    )

    # No --execute flag (default), but --approved and --simulate-auth-ready
    # Should NOT short-circuit; should go through normal flow → BLOCKED approval_required
    completed = run_publish(
        package_root=str(pkg),
        run_root=str(run_root),
        repository="https://github.com/test/repo",
        repo_mode="export_repo",
        repo_path=str(repo),
        version="0.1.0",
        approved="",
        simulate_auth_ready="",
    )
    payload = load_json(completed)
    assert payload["status"] != "PASS" or payload.get("idempotent") is not True


# ── package_hash in result payloads ────────────────────────────────

def test_result_payloads_include_package_hash(tmp_path: Path) -> None:
    """Verify that dry-run, auth-blocked, and approval-blocked payloads all include package_hash."""
    pkg = tmp_path / "package"
    write_files(pkg, {"plugin.json": "{}"})

    # Dry-run
    r = run_publish(
        package_root=str(pkg),
        run_root=str(tmp_path / "run1"),
        repository="https://github.com/test/repo",
        repo_path=str(tmp_path / "repo1"),
        version="0.1.0",
        dry_run="",
    )
    assert load_json(r).get("package_hash", "").startswith("sha256:")

    # Auth missing
    r = run_publish(
        package_root=str(pkg),
        run_root=str(tmp_path / "run2"),
        repository="https://github.com/test/repo",
        repo_path=str(tmp_path / "repo2"),
        version="0.1.0",
        simulate_auth_missing="",
    )
    assert load_json(r).get("package_hash", "").startswith("sha256:")

    # Approval required (execute but not approved)
    r = run_publish(
        package_root=str(pkg),
        run_root=str(tmp_path / "run3"),
        repository="https://github.com/test/repo",
        repo_path=str(tmp_path / "repo3"),
        version="0.1.0",
        execute="",
        simulate_auth_ready="",
    )
    assert load_json(r).get("package_hash", "").startswith("sha256:")

    # Repo path required (execute + approved but no repo-path)
    r = run_publish(
        package_root=str(pkg),
        run_root=str(tmp_path / "run4"),
        repository="https://github.com/test/repo",
        repo_path="",
        version="0.1.0",
        execute="",
        approved="",
        simulate_auth_ready="",
    )
    assert load_json(r).get("package_hash", "").startswith("sha256:")
