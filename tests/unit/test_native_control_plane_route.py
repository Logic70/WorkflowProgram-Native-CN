from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
ROUTER = ROOT / ".claude" / "scripts" / "route-native-control-plane.py"


def run_router(target_root: Path, *args: str) -> dict:
    completed = subprocess.run(
        [sys.executable, str(ROUTER), "--target-root", str(target_root), "--json", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout
    return json.loads(completed.stdout)


def run_router_raw(target_root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(ROUTER), "--target-root", str(target_root), "--json", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_new_target_defaults_to_native(tmp_path: Path) -> None:
    payload = run_router(tmp_path)

    assert payload["control_plane_mode"] == "native"
    assert payload["entry_skill"] == "workflowprogram-native-develop"
    assert payload["reason"] == "default-native"
    assert payload["automatic_rewrite"] is False


def test_existing_retired_runtime_target_stays_native_with_migration_notice(tmp_path: Path) -> None:
    (tmp_path / ".workflowprogram" / "runtime").mkdir(parents=True)

    payload = run_router(tmp_path)

    assert payload["control_plane_mode"] == "native"
    assert payload["entry_skill"] == "workflowprogram-native-develop"
    assert payload["reason"] == "existing-retired-runtime-native-default"
    assert payload["retired_runtime_markers"] == [".workflowprogram/runtime"]
    assert payload["manual_migration_required"] is True
    assert payload["automatic_rewrite"] is False


def test_existing_legacy_target_can_be_explicitly_routed_to_native(tmp_path: Path) -> None:
    (tmp_path / ".workflowprogram" / "runtime").mkdir(parents=True)

    payload = run_router(tmp_path, "--mode", "native")

    assert payload["control_plane_mode"] == "native"
    assert payload["reason"] == "explicit-native"
    assert payload["automatic_rewrite"] is False


def test_explicit_legacy_mode_is_no_longer_supported(tmp_path: Path) -> None:
    completed = run_router_raw(tmp_path, "--mode", "legacy")

    assert completed.returncode == 2
    assert "invalid choice" in completed.stderr
