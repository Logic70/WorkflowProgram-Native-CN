#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="WorkflowProgram plugin installation doctor")
    parser.add_argument("--plugin-root", default="", help="Override CLAUDE_PLUGIN_ROOT")
    parser.add_argument("--plugin-data", default="", help="Override CLAUDE_PLUGIN_DATA")
    parser.add_argument("--json", action="store_true", help="Print JSON report")
    return parser.parse_args()


def resolve_path(value: str, env_name: str) -> Path | None:
    raw = value.strip() or os.environ.get(env_name, "").strip()
    if not raw:
        return None
    return Path(raw).resolve()


def run(cmd: List[str], *, env: Dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, capture_output=True, text=True, check=False, env=env)


def main() -> int:
    args = parse_args()
    plugin_root = resolve_path(args.plugin_root, "CLAUDE_PLUGIN_ROOT")
    plugin_data = resolve_path(args.plugin_data, "CLAUDE_PLUGIN_DATA")

    checks: List[Dict[str, Any]] = []

    def add(name: str, ok: bool, message: str) -> None:
        checks.append({"name": name, "ok": ok, "message": message})

    if plugin_root and plugin_root.exists():
        add("plugin_root", True, str(plugin_root))
    else:
        add("plugin_root", False, "CLAUDE_PLUGIN_ROOT is missing or invalid")

    if plugin_data and plugin_data.exists():
        add("plugin_data", True, str(plugin_data))
    else:
        add("plugin_data", False, "CLAUDE_PLUGIN_DATA is missing or invalid")

    site_packages = plugin_data / "python" / "site-packages" if plugin_data else None
    bootstrap_state = plugin_data / "python" / "bootstrap-state.json" if plugin_data else None

    if site_packages and site_packages.exists():
        add("site_packages", True, str(site_packages))
    else:
        add("site_packages", False, "plugin-local site-packages directory is missing")

    if bootstrap_state and bootstrap_state.exists():
        add("bootstrap_state", True, str(bootstrap_state))
    else:
        add("bootstrap_state", False, "bootstrap-state.json is missing")

    if site_packages and site_packages.exists():
        env = os.environ.copy()
        env["PYTHONPATH"] = str(site_packages) + (f":{env['PYTHONPATH']}" if env.get("PYTHONPATH") else "")
        probe = run([sys.executable, "-c", "import yaml; print(getattr(yaml, '__version__', 'ok'))"], env=env)
        if probe.returncode == 0:
            add("yaml_import", True, probe.stdout.strip() or "yaml import succeeded")
        else:
            add("yaml_import", False, (probe.stderr or probe.stdout or "yaml import failed").strip())
    else:
        add("yaml_import", False, "cannot test yaml import without plugin-local site-packages")

    ok = all(item["ok"] for item in checks)
    payload = {"status": "PASS" if ok else "FAIL", "checks": checks}
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        for item in checks:
            print(f"{'[PASS]' if item['ok'] else '[FAIL]'} {item['name']}: {item['message']}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
