"""Focused tests for validate-publish-qualification.py.

Covers:
- PASS qualification with valid manifest and clean target.
- Missing manifest.
- Gate not all PASS.
- Stale candidate hash (checksum mismatch).
- Target managed drift conflict.
- Target managed clean.
- Target unmanaged existing conflict.
- Target does not exist (allowed).
- Adversarial: empty assets, missing/duplicate/traversal/absolute assets,
  missing/non-empty blockingIssues, empty evidence, missing target root,
  duplicate gates, asset coverage mismatch.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
QUALIFICATION = ROOT / ".claude" / "scripts" / "validate-publish-qualification.py"
MANIFEST_BUILDER = ROOT / ".claude" / "scripts" / "build-native-workflow-manifest.py"


def run_qualification(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(QUALIFICATION), *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def make_manifest(
    out_path: Path,
    candidate: Path,
    workflow_name: str = "probe",
    *,
    override_gates: list[dict] | None = None,
    override_candidate_hash: str | None = None,
) -> dict:
    """Build a manifest via the builder script and return its dict."""
    workflow = candidate / ".claude" / "workflows" / f"{workflow_name}.js"
    workflow.parent.mkdir(parents=True, exist_ok=True)
    if not workflow.exists():
        workflow.write_text(f"export const meta = {{ name: '{workflow_name}', description: 'T' }}\n", encoding="utf-8")

    # Compute candidateHash
    digest = hashlib.sha256()
    files = sorted(p for p in candidate.rglob("*") if p.is_file())
    for path in files:
        relative = path.relative_to(candidate).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    ch = override_candidate_hash or f"sha256:{digest.hexdigest()}"

    reports = out_path.parent / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    for name in ("design-review", "static-validation", "interactive-smoke", "drift"):
        rp = reports / f"{name}.json"
        rp.parent.mkdir(parents=True, exist_ok=True)
        report = {
            "status": "PASS",
            "candidateHash": ch,
            "evidence": [str(rp.resolve())],
            "blockingIssues": [],
        }
        if name == "interactive-smoke":
            report["interactiveEvidence"] = [{"step": "launch", "status": "ok"}]
        if name == "drift":
            report["driftCheck"] = "PASS"
        rp.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    r = subprocess.run(
        [
            sys.executable, str(MANIFEST_BUILDER),
            "--run-id", "run-001",
            "--candidate-root", str(candidate),
            "--workflow-name", workflow_name,
            "--workflow-script", str(workflow),
            "--design-review-report", str(reports / "design-review.json"),
            "--static-validation-report", str(reports / "static-validation.json"),
            "--interactive-smoke-report", str(reports / "interactive-smoke.json"),
            "--drift-report", str(reports / "drift.json"),
            "--out", str(out_path),
            "--json",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    manifest = json.loads(r.stdout)

    if override_gates is not None:
        manifest["gates"] = override_gates
        out_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    return manifest


def setup_target_managed_files(target: Path, entries: list[dict]) -> None:
    mf_dir = target / ".workflowprogram"
    mf_dir.mkdir(parents=True, exist_ok=True)
    mf_path = mf_dir / "managed-files.json"
    mf_path.write_text(json.dumps({
        "manifest_version": 1,
        "updated_at": "2026-01-01T00:00:00Z",
        "entries": entries,
    }, indent=2) + "\n", encoding="utf-8")


# ── PASS ──────────────────────────────────────────────────────────

def test_qualification_pass_with_valid_manifest(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    manifest_path = tmp_path / "manifest.json"
    make_manifest(manifest_path, candidate)

    target = tmp_path / "target"
    target.mkdir()

    r = run_qualification([
        "--manifest", str(manifest_path),
        "--candidate-root", str(candidate),
        "--target-root", str(target),
        "--json",
    ])
    assert r.returncode == 0, r.stderr or r.stdout
    payload = json.loads(r.stdout)
    assert payload["status"] == "PASS"
    assert payload["schemaName"] == "native-publish-qualification"


# ── Missing manifest ───────────────────────────────────────────────

def test_qualification_blocks_missing_manifest(tmp_path: Path) -> None:
    r = run_qualification([
        "--manifest", str(tmp_path / "nope.json"),
        "--candidate-root", str(tmp_path / "c"),
        "--target-root", str(tmp_path / "t"),
        "--json",
    ])
    assert r.returncode == 1
    payload = json.loads(r.stdout)
    assert payload["status"] == "BLOCKED_PUBLISH"


# ── Gate not all PASS ──────────────────────────────────────────────

def test_qualification_blocks_failed_gate(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    manifest_path = tmp_path / "manifest.json"
    make_manifest(manifest_path, candidate, override_gates=[
        {"name": "designReview", "status": "PASS"},
        {"name": "staticValidation", "status": "PASS"},
        {"name": "interactiveSmoke", "status": "FAIL", "reason": "Smoke failed."},
        {"name": "assetScope", "status": "PASS"},
        {"name": "driftCheck", "status": "PASS"},
        {"name": "manifest", "status": "PASS"},
    ])

    target = tmp_path / "target"
    target.mkdir()

    r = run_qualification([
        "--manifest", str(manifest_path),
        "--candidate-root", str(candidate),
        "--target-root", str(target),
        "--json",
    ])
    assert r.returncode == 1
    payload = json.loads(r.stdout)
    assert payload["status"] == "BLOCKED_PUBLISH"


# ── Stale candidate hash ───────────────────────────────────────────

def test_qualification_blocks_stale_candidate_hash(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    manifest_path = tmp_path / "manifest.json"
    make_manifest(manifest_path, candidate, override_candidate_hash="sha256:ffff")

    target = tmp_path / "target"
    target.mkdir()

    r = run_qualification([
        "--manifest", str(manifest_path),
        "--candidate-root", str(candidate),
        "--target-root", str(target),
        "--json",
    ])
    assert r.returncode == 1
    payload = json.loads(r.stdout)
    assert payload["status"] == "BLOCKED_PUBLISH"


# ── Target drift ───────────────────────────────────────────────────

def test_qualification_blocks_target_managed_drift(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    manifest_path = tmp_path / "manifest.json"
    manifest = make_manifest(manifest_path, candidate)

    target = tmp_path / "target"
    target.mkdir()
    # Install target file with content different from managed entry
    target_script = target / ".claude" / "workflows" / "probe.js"
    target_script.parent.mkdir(parents=True, exist_ok=True)
    target_script.write_text("// user-modified content\n", encoding="utf-8")

    target_hash_val = hashlib.sha256(target_script.read_bytes()).hexdigest()

    setup_target_managed_files(target, [
        {
            "relative_path": ".claude/workflows/probe.js",
            "producer_version": "0.1.0",
            "last_applied_hash": "different-hash",
            "ownership": "managed",
            "last_applied_at": "2026-01-01T00:00:00Z",
            "last_run_id": "old-run",
        },
    ])

    r = run_qualification([
        "--manifest", str(manifest_path),
        "--candidate-root", str(candidate),
        "--target-root", str(target),
        "--json",
    ])
    assert r.returncode == 2
    payload = json.loads(r.stdout)
    assert payload["status"] == "BLOCKED_CONFLICT"


# ── Target clean ───────────────────────────────────────────────────

def test_qualification_pass_target_managed_clean(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    manifest_path = tmp_path / "manifest.json"
    make_manifest(manifest_path, candidate)

    target = tmp_path / "target"
    target.mkdir()
    target_script = target / ".claude" / "workflows" / "probe.js"
    target_script.parent.mkdir(parents=True, exist_ok=True)
    target_script.write_text("export const meta = { name: 'probe', description: 'T' }\n", encoding="utf-8")

    target_hash_val = hashlib.sha256(target_script.read_bytes()).hexdigest()

    setup_target_managed_files(target, [
        {
            "relative_path": ".claude/workflows/probe.js",
            "producer_version": "0.1.0",
            "last_applied_hash": target_hash_val,
            "ownership": "managed",
            "last_applied_at": "2026-01-01T00:00:00Z",
            "last_run_id": "old-run",
        },
    ])

    r = run_qualification([
        "--manifest", str(manifest_path),
        "--candidate-root", str(candidate),
        "--target-root", str(target),
        "--json",
    ])
    assert r.returncode == 0, r.stderr or r.stdout
    payload = json.loads(r.stdout)
    assert payload["status"] == "PASS"


# ── Target unmanaged conflict ──────────────────────────────────────

def test_qualification_blocks_target_unmanaged_conflict(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    manifest_path = tmp_path / "manifest.json"
    make_manifest(manifest_path, candidate)

    target = tmp_path / "target"
    target.mkdir()
    target_script = target / ".claude" / "workflows" / "probe.js"
    target_script.parent.mkdir(parents=True, exist_ok=True)
    target_script.write_text("// unmanaged user file\n", encoding="utf-8")
    # No managed-files.json — target exists but is unmanaged

    r = run_qualification([
        "--manifest", str(manifest_path),
        "--candidate-root", str(candidate),
        "--target-root", str(target),
        "--json",
    ])
    assert r.returncode == 2
    payload = json.loads(r.stdout)
    assert payload["status"] == "BLOCKED_CONFLICT"


# ── Target does not exist ──────────────────────────────────────────

def test_qualification_pass_target_does_not_exist(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    manifest_path = tmp_path / "manifest.json"
    make_manifest(manifest_path, candidate)

    target = tmp_path / "target"
    target.mkdir()
    # Target asset does not exist ─ allowed (will be created on apply)

    r = run_qualification([
        "--manifest", str(manifest_path),
        "--candidate-root", str(candidate),
        "--target-root", str(target),
        "--json",
    ])
    assert r.returncode == 0, r.stderr or r.stdout
    payload = json.loads(r.stdout)
    assert payload["status"] == "PASS"


# ── Adversarial: anti-forged manifest ──────────────────────────────

def test_qualification_blocks_empty_assets(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    manifest_path = tmp_path / "manifest.json"
    manifest = make_manifest(manifest_path, candidate)
    manifest["assets"] = []
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    target = tmp_path / "target"
    target.mkdir()

    r = run_qualification([
        "--manifest", str(manifest_path),
        "--candidate-root", str(candidate),
        "--target-root", str(target),
        "--json",
    ])
    assert r.returncode == 1, f"Expected exit 1, got {r.returncode}: {r.stdout}"
    payload = json.loads(r.stdout)
    assert payload["status"] == "BLOCKED_PUBLISH"


def test_qualification_blocks_missing_declared_asset(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    manifest_path = tmp_path / "manifest.json"
    manifest = make_manifest(manifest_path, candidate)
    # Inject a declared asset not present in candidate root
    manifest["assets"].append({"relativePath": ".claude/ghost.js", "sha256": "deadbeef"})
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    target = tmp_path / "target"
    target.mkdir()

    r = run_qualification([
        "--manifest", str(manifest_path),
        "--candidate-root", str(candidate),
        "--target-root", str(target),
        "--json",
    ])
    assert r.returncode == 1, f"Expected exit 1, got {r.returncode}: {r.stdout}"
    payload = json.loads(r.stdout)
    assert payload["status"] == "BLOCKED_PUBLISH"


def test_qualification_blocks_duplicate_asset_path(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    manifest_path = tmp_path / "manifest.json"
    manifest = make_manifest(manifest_path, candidate)
    # Duplicate the first asset entry
    if manifest["assets"]:
        dup = dict(manifest["assets"][0])
        manifest["assets"].append(dup)
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    target = tmp_path / "target"
    target.mkdir()

    r = run_qualification([
        "--manifest", str(manifest_path),
        "--candidate-root", str(candidate),
        "--target-root", str(target),
        "--json",
    ])
    assert r.returncode == 1, f"Expected exit 1, got {r.returncode}: {r.stdout}"
    payload = json.loads(r.stdout)
    assert payload["status"] == "BLOCKED_PUBLISH"


def test_qualification_blocks_path_traversal_asset(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    manifest_path = tmp_path / "manifest.json"
    manifest = make_manifest(manifest_path, candidate)
    manifest["assets"] = [{"relativePath": "../outside/evil.js", "sha256": "deadbeef"}]
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    target = tmp_path / "target"
    target.mkdir()

    r = run_qualification([
        "--manifest", str(manifest_path),
        "--candidate-root", str(candidate),
        "--target-root", str(target),
        "--json",
    ])
    assert r.returncode == 1, f"Expected exit 1, got {r.returncode}: {r.stdout}"
    payload = json.loads(r.stdout)
    assert payload["status"] == "BLOCKED_PUBLISH"


def test_qualification_blocks_absolute_asset_path(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    manifest_path = tmp_path / "manifest.json"
    manifest = make_manifest(manifest_path, candidate)
    manifest["assets"] = [{"relativePath": "/etc/passwd", "sha256": "deadbeef"}]
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    target = tmp_path / "target"
    target.mkdir()

    r = run_qualification([
        "--manifest", str(manifest_path),
        "--candidate-root", str(candidate),
        "--target-root", str(target),
        "--json",
    ])
    assert r.returncode == 1, f"Expected exit 1, got {r.returncode}: {r.stdout}"
    payload = json.loads(r.stdout)
    assert payload["status"] == "BLOCKED_PUBLISH"


def test_qualification_blocks_non_prefixed_asset_path(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    manifest_path = tmp_path / "manifest.json"
    manifest = make_manifest(manifest_path, candidate)
    manifest["assets"] = [{"relativePath": "random/file.js", "sha256": "deadbeef"}]
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    target = tmp_path / "target"
    target.mkdir()

    r = run_qualification([
        "--manifest", str(manifest_path),
        "--candidate-root", str(candidate),
        "--target-root", str(target),
        "--json",
    ])
    assert r.returncode == 1, f"Expected exit 1, got {r.returncode}: {r.stdout}"
    payload = json.loads(r.stdout)
    assert payload["status"] == "BLOCKED_PUBLISH"


def test_qualification_blocks_missing_blocking_issues(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    manifest_path = tmp_path / "manifest.json"
    manifest = make_manifest(manifest_path, candidate)
    del manifest["blockingIssues"]
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    target = tmp_path / "target"
    target.mkdir()

    r = run_qualification([
        "--manifest", str(manifest_path),
        "--candidate-root", str(candidate),
        "--target-root", str(target),
        "--json",
    ])
    assert r.returncode == 1, f"Expected exit 1, got {r.returncode}: {r.stdout}"
    payload = json.loads(r.stdout)
    assert payload["status"] == "BLOCKED_PUBLISH"


def test_qualification_blocks_non_empty_blocking_issues(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    manifest_path = tmp_path / "manifest.json"
    manifest = make_manifest(manifest_path, candidate)
    manifest["blockingIssues"] = ["something is wrong"]
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    target = tmp_path / "target"
    target.mkdir()

    r = run_qualification([
        "--manifest", str(manifest_path),
        "--candidate-root", str(candidate),
        "--target-root", str(target),
        "--json",
    ])
    assert r.returncode == 1, f"Expected exit 1, got {r.returncode}: {r.stdout}"
    payload = json.loads(r.stdout)
    assert payload["status"] == "BLOCKED_PUBLISH"


def test_qualification_blocks_empty_evidence(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    manifest_path = tmp_path / "manifest.json"
    manifest = make_manifest(manifest_path, candidate)
    manifest["evidence"] = []
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    target = tmp_path / "target"
    target.mkdir()

    r = run_qualification([
        "--manifest", str(manifest_path),
        "--candidate-root", str(candidate),
        "--target-root", str(target),
        "--json",
    ])
    assert r.returncode == 1, f"Expected exit 1, got {r.returncode}: {r.stdout}"
    payload = json.loads(r.stdout)
    assert payload["status"] == "BLOCKED_PUBLISH"


def test_qualification_blocks_missing_target_root(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    manifest_path = tmp_path / "manifest.json"
    make_manifest(manifest_path, candidate)

    r = run_qualification([
        "--manifest", str(manifest_path),
        "--candidate-root", str(candidate),
        "--target-root", str(tmp_path / "nonexistent"),
        "--json",
    ])
    assert r.returncode == 1, f"Expected exit 1, got {r.returncode}: {r.stdout}"
    payload = json.loads(r.stdout)
    assert payload["status"] == "BLOCKED_PUBLISH"


def test_qualification_blocks_duplicate_gate(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    manifest_path = tmp_path / "manifest.json"
    make_manifest(manifest_path, candidate, override_gates=[
        {"name": "designReview", "status": "PASS"},
        {"name": "designReview", "status": "PASS"},  # duplicate
        {"name": "staticValidation", "status": "PASS"},
        {"name": "interactiveSmoke", "status": "PASS"},
        {"name": "assetScope", "status": "PASS"},
        {"name": "driftCheck", "status": "PASS"},
        {"name": "manifest", "status": "PASS"},
    ])

    target = tmp_path / "target"
    target.mkdir()

    r = run_qualification([
        "--manifest", str(manifest_path),
        "--candidate-root", str(candidate),
        "--target-root", str(target),
        "--json",
    ])
    assert r.returncode == 1, f"Expected exit 1, got {r.returncode}: {r.stdout}"
    payload = json.loads(r.stdout)
    assert payload["status"] == "BLOCKED_PUBLISH"


def test_qualification_blocks_missing_asset_in_coverage(tmp_path: Path) -> None:
    """Declared assets must exactly match candidate root's allowed-prefix
    files. Omitting an asset that exists in candidate root must block.
    """
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    # Create two assets but delete one from manifest
    wf = candidate / ".claude" / "workflows" / "probe.js"
    wf.parent.mkdir(parents=True)
    wf.write_text("export const meta = { name: 'probe', description: 'T' }\n", encoding="utf-8")
    extra = candidate / ".claude" / "workflows" / "extra.js"
    extra.write_text("// extra asset\n", encoding="utf-8")

    manifest_path = tmp_path / "manifest.json"
    manifest = make_manifest(manifest_path, candidate)
    # Remove extra asset from declared assets
    manifest["assets"] = [a for a in manifest["assets"] if a["relativePath"] != ".claude/workflows/extra.js"]
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    target = tmp_path / "target"
    target.mkdir()

    r = run_qualification([
        "--manifest", str(manifest_path),
        "--candidate-root", str(candidate),
        "--target-root", str(target),
        "--json",
    ])
    assert r.returncode == 1, f"Expected exit 1 BLOCKED_PUBLISH, got {r.returncode}: {r.stdout}"
    payload = json.loads(r.stdout)
    assert payload["status"] == "BLOCKED_PUBLISH"


def test_qualification_blocks_extra_undeclared_asset(tmp_path: Path) -> None:
    """Declaring an asset not present in candidate root must block."""
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    manifest_path = tmp_path / "manifest.json"
    manifest = make_manifest(manifest_path, candidate)
    # Add a phantom asset entry
    manifest["assets"].append({"relativePath": ".claude/phantom.js", "sha256": "aaaa"})
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    target = tmp_path / "target"
    target.mkdir()

    r = run_qualification([
        "--manifest", str(manifest_path),
        "--candidate-root", str(candidate),
        "--target-root", str(target),
        "--json",
    ])
    assert r.returncode == 1, f"Expected exit 1, got {r.returncode}: {r.stdout}"
    payload = json.loads(r.stdout)
    assert payload["status"] == "BLOCKED_PUBLISH"
