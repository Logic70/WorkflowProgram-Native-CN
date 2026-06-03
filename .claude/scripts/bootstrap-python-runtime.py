#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ensurepip
import hashlib
import json
import os
import shutil
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Bootstrap WorkflowProgram plugin-local Python runtime")
    parser.add_argument("--plugin-root", default="", help="Override CLAUDE_PLUGIN_ROOT")
    parser.add_argument("--plugin-data", default="", help="Override CLAUDE_PLUGIN_DATA")
    parser.add_argument("--quiet", action="store_true", help="Suppress success output")
    parser.add_argument("--sessionstart", action="store_true", help="Always exit 0 and emit only concise failure guidance")
    parser.add_argument("--json", action="store_true", help="Print JSON payload")
    return parser.parse_args()


def resolve_plugin_root(value: str) -> Path:
    raw = value.strip() or os.environ.get("CLAUDE_PLUGIN_ROOT", "").strip()
    if not raw:
        raise RuntimeError("CLAUDE_PLUGIN_ROOT is required")
    return Path(raw).resolve()


def resolve_plugin_data(value: str) -> Path:
    raw = value.strip() or os.environ.get("CLAUDE_PLUGIN_DATA", "").strip()
    if not raw:
        raise RuntimeError("CLAUDE_PLUGIN_DATA is required")
    return Path(raw).resolve()


def sha256_text(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(cmd: list[str], *, env: Dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, capture_output=True, text=True, check=False, env=env)


@contextmanager
def bundled_pip_wheel() -> Any:
    with ensurepip._get_pip_whl_path_ctx() as pip_wheel:  # type: ignore[attr-defined]
        yield Path(pip_wheel)


def run_pip_module(args: list[str], additional_paths: list[str]) -> subprocess.CompletedProcess[str]:
    code = (
        "import runpy\n"
        "import sys\n"
        f"sys.path = {additional_paths!r} + sys.path\n"
        f"sys.argv[1:] = {args!r}\n"
        'runpy.run_module("pip", run_name="__main__", alter_sys=True)\n'
    )
    cmd = [sys.executable, "-W", "ignore::DeprecationWarning", "-c", code]
    if sys.flags.isolated:
        cmd.insert(1, "-I")
    return subprocess.run(cmd, capture_output=True, text=True, check=False)


def pip_install_target(requirements_path: Path, target: Path) -> None:
    with bundled_pip_wheel() as pip_wheel:
        completed = run_pip_module(
            [
                "install",
                "--disable-pip-version-check",
                "--no-input",
                "--upgrade",
                "--target",
                str(target),
                "-r",
                str(requirements_path),
            ],
            [os.fsdecode(pip_wheel)],
        )
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "pip install failed").strip()
            raise RuntimeError(f"plugin-local pip install failed: {detail}")


def import_yaml_ok(site_packages: Path) -> bool:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(site_packages) + (f":{env['PYTHONPATH']}" if env.get("PYTHONPATH") else "")
    probe = run([sys.executable, "-c", "import yaml; print(getattr(yaml, '__version__', 'ok'))"], env=env)
    return probe.returncode == 0


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def main() -> int:
    args = parse_args()
    try:
        plugin_root = resolve_plugin_root(args.plugin_root)
        plugin_data = resolve_plugin_data(args.plugin_data)
        requirements_path = plugin_root / "requirements.lock.txt"
        runtime_manifest = plugin_root / "runtime-manifest.json"
        python_root = plugin_data / "python"
        site_packages = python_root / "site-packages"
        tmp_site_packages = python_root / "site-packages.tmp"
        copied_requirements = python_root / "requirements.lock.txt"
        bootstrap_state = python_root / "bootstrap-state.json"

        if not requirements_path.exists():
            raise RuntimeError(f"Missing plugin dependency manifest: {requirements_path}")
        if not runtime_manifest.exists():
            raise RuntimeError(f"Missing plugin runtime manifest: {runtime_manifest}")

        python_root.mkdir(parents=True, exist_ok=True)

        manifest_sha = sha256_text(requirements_path)
        install_required = (
            not site_packages.exists()
            or not copied_requirements.exists()
            or copied_requirements.read_text(encoding="utf-8") != requirements_path.read_text(encoding="utf-8")
            or not import_yaml_ok(site_packages)
        )

        installed = False
        if install_required:
            if tmp_site_packages.exists():
                shutil.rmtree(tmp_site_packages)
            tmp_site_packages.mkdir(parents=True, exist_ok=True)
            pip_install_target(requirements_path, tmp_site_packages)
            if not import_yaml_ok(tmp_site_packages):
                raise RuntimeError("PyYAML import check failed after plugin-local install")
            if site_packages.exists():
                shutil.rmtree(site_packages)
            tmp_site_packages.rename(site_packages)
            copied_requirements.write_text(requirements_path.read_text(encoding="utf-8"), encoding="utf-8", newline="\n")
            installed = True
        elif tmp_site_packages.exists():
            shutil.rmtree(tmp_site_packages)

        payload: Dict[str, Any] = {
            "status": "PASS",
            "plugin_root": str(plugin_root),
            "plugin_data": str(plugin_data),
            "requirements_path": str(requirements_path),
            "runtime_manifest": str(runtime_manifest),
            "site_packages": str(site_packages),
            "bootstrap_state": str(bootstrap_state),
            "requirements_sha256": manifest_sha,
            "bootstrap_required": install_required,
            "installed": installed,
            "yaml_ready": import_yaml_ok(site_packages),
        }
        write_json(bootstrap_state, payload)

        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        elif not args.quiet:
            print("WorkflowProgram Python runtime installed." if installed else "WorkflowProgram Python runtime is ready.")
        return 0
    except Exception as exc:
        payload = {
            "status": "FAIL",
            "error": str(exc),
        }
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        elif args.sessionstart:
            print("WorkflowProgram Python runtime bootstrap failed. Run workflowprogram-doctor.")
        elif not args.quiet:
            print(payload["error"], file=sys.stderr)
        return 0 if args.sessionstart else 1


if __name__ == "__main__":
    raise SystemExit(main())
