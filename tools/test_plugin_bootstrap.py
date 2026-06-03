#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List


ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Test WorkflowProgram plugin-local Python bootstrap")
    parser.add_argument("--plugin-root", default=str(ROOT / "dist" / "plugin"), help="Plugin root to test")
    parser.add_argument(
        "--spec",
        default=str(ROOT / "tests" / "spec-fixtures" / "valid-minimal.yaml"),
        help="Spec path used to validate launcher-backed yaml execution",
    )
    parser.add_argument("--json", action="store_true", help="Print JSON report")
    return parser.parse_args()


def run(cmd: List[str], *, env: Dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, capture_output=True, text=True, check=False, env=env)


def main() -> int:
    args = parse_args()
    plugin_root = Path(args.plugin_root).resolve()
    spec_path = Path(args.spec).resolve()

    payload: Dict[str, Any] = {
        "status": "PASS",
        "plugin_root": str(plugin_root),
        "spec": str(spec_path),
        "checks": [],
    }

    def add(name: str, ok: bool, message: str, extra: Dict[str, Any] | None = None) -> None:
        entry = {"name": name, "ok": ok, "message": message}
        if extra:
            entry.update(extra)
        payload["checks"].append(entry)
        if not ok:
            payload["status"] = "FAIL"

    with tempfile.TemporaryDirectory(prefix="workflowprogram-plugin-data-") as temp_dir:
        plugin_data = Path(temp_dir).resolve()
        env = os.environ.copy()
        env["CLAUDE_PLUGIN_ROOT"] = str(plugin_root)
        env["CLAUDE_PLUGIN_DATA"] = str(plugin_data)
        env["PYTHONNOUSERSITE"] = "1"

        for launcher_name in ("workflowprogram-python", "workflowprogram-doctor"):
            launcher_path = plugin_root / "bin" / launcher_name
            add(
                f"{launcher_name}_executable",
                launcher_path.exists() and os.access(launcher_path, os.X_OK),
                f"{launcher_path} must exist and be executable after marketplace install",
            )

        command_wrappers = sorted((plugin_root / "skills").glob("command-*/SKILL.md"))
        add(
            "command_wrappers_not_exposed",
            not command_wrappers,
            "marketplace payload must not expose generated skills/command-* wrappers",
            {"wrappers": [str(path.relative_to(plugin_root)) for path in command_wrappers]},
        )

        markdown_frontmatter_failures = []
        for markdown_path in sorted((plugin_root / "commands").glob("*.md")) + sorted((plugin_root / "skills").glob("*/SKILL.md")):
            text = markdown_path.read_text(encoding="utf-8")
            if text.startswith("<!-- AUTO-GENERATED"):
                markdown_frontmatter_failures.append(str(markdown_path.relative_to(plugin_root)))
            elif not text.startswith("---\n"):
                markdown_frontmatter_failures.append(str(markdown_path.relative_to(plugin_root)))
        add(
            "frontmatter_precedes_generated_marker",
            not markdown_frontmatter_failures,
            "command/skill Markdown must start with frontmatter, not the AUTO-GENERATED marker",
            {"files": markdown_frontmatter_failures},
        )

        bootstrap = run(
            [
                sys.executable,
                str(plugin_root / "scripts" / "bootstrap-python-runtime.py"),
                "--plugin-root",
                str(plugin_root),
                "--plugin-data",
                str(plugin_data),
                "--json",
            ],
            env=env,
        )
        try:
            bootstrap_payload = json.loads(bootstrap.stdout or "{}")
        except json.JSONDecodeError as exc:
            add("bootstrap_json", False, f"bootstrap output is not valid JSON: {exc}")
            bootstrap_payload = {}
        else:
            add("bootstrap_json", True, "bootstrap returned valid JSON")

        add(
            "bootstrap_exit",
            bootstrap.returncode == 0 and bootstrap_payload.get("status") == "PASS",
            bootstrap.stderr.strip() or bootstrap.stdout.strip() or f"exit={bootstrap.returncode}",
        )

        doctor = run([str(plugin_root / "bin" / "workflowprogram-doctor"), "--json"], env=env)
        try:
            doctor_payload = json.loads(doctor.stdout or "{}")
        except json.JSONDecodeError as exc:
            add("doctor_json", False, f"doctor output is not valid JSON: {exc}")
            doctor_payload = {}
        else:
            add("doctor_json", True, "doctor returned valid JSON")

        add(
            "doctor_status",
            doctor.returncode == 0 and doctor_payload.get("status") == "PASS",
            doctor.stderr.strip() or doctor.stdout.strip() or f"exit={doctor.returncode}",
        )

        launcher = run(
            [
                str(plugin_root / "bin" / "workflowprogram-python"),
                "-c",
                "import yaml, json; print(json.dumps({'yaml_file': yaml.__file__}))",
            ],
            env=env,
        )
        try:
            launcher_payload = json.loads(launcher.stdout or "{}")
        except json.JSONDecodeError as exc:
            add("launcher_json", False, f"launcher output is not valid JSON: {exc}")
            launcher_payload = {}
        else:
            add("launcher_json", True, "launcher returned valid JSON")

        yaml_file = str(launcher_payload.get("yaml_file", "")).strip()
        expected_prefix = str((plugin_data / "python" / "site-packages").resolve())
        add(
            "launcher_uses_plugin_local_yaml",
            launcher.returncode == 0 and yaml_file.startswith(expected_prefix),
            launcher.stderr.strip() or yaml_file or f"exit={launcher.returncode}",
            {"yaml_file": yaml_file},
        )

        spec_validate = run(
            [
                str(plugin_root / "bin" / "workflowprogram-python"),
                str(plugin_root / "scripts" / "validate-workflow-spec.py"),
                "--spec",
                str(spec_path),
                "--json",
            ],
            env=env,
        )
        try:
            spec_payload = json.loads(spec_validate.stdout or "{}")
        except json.JSONDecodeError as exc:
            add("spec_validate_json", False, f"spec validator output is not valid JSON: {exc}")
            spec_payload = {}
        else:
            add("spec_validate_json", True, "spec validator returned valid JSON")

        add(
            "spec_validate_status",
            spec_validate.returncode == 0 and spec_payload.get("status") == "PASS",
            spec_validate.stderr.strip() or spec_validate.stdout.strip() or f"exit={spec_validate.returncode}",
        )

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
