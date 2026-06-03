#!/usr/bin/env python3
"""
Run layered WorkflowProgram quality gates.

The gates intentionally separate fast commit checks from heavier integration
and release checks. Release remains the strongest gate because it validates the
built marketplace payload, not only the source tree.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable


ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class GateStep:
    name: str
    description: str
    kind: str
    argv: tuple[str, ...] = ()
    timeout: int = 120
    runner: Callable[[], tuple[bool, str, dict[str, Any]]] | None = None

    def display_command(self) -> str:
        if self.kind == "internal":
            return f"<internal:{self.name}>"
        return " ".join(self.argv)


def rel(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


def completed_output(completed: subprocess.CompletedProcess[str]) -> str:
    stdout = completed.stdout or ""
    stderr = completed.stderr or ""
    return "\n".join(part for part in (stdout.strip(), stderr.strip()) if part)


def run_command(step: GateStep) -> tuple[bool, str, dict[str, Any]]:
    completed = subprocess.run(
        list(step.argv),
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        timeout=step.timeout,
    )
    output = completed_output(completed)
    return completed.returncode == 0, output, {"returncode": completed.returncode}


def diff_added_line_check() -> tuple[bool, str, dict[str, Any]]:
    completed = subprocess.run(
        ["git", "-c", "core.autocrlf=false", "diff", "--unified=0", "--no-ext-diff", "--"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if completed.returncode != 0:
        output = completed_output(completed)
        return False, output or f"git diff exited {completed.returncode}", {"returncode": completed.returncode}

    failures: list[str] = []
    current_file = "<unknown>"
    line_number = 0
    for line in (completed.stdout or "").splitlines():
        if line.startswith("+++ b/"):
            current_file = line[len("+++ b/") :]
            continue
        if line.startswith("@@"):
            match = re.search(r"\+(\d+)(?:,(\d+))?", line)
            line_number = int(match.group(1)) - 1 if match else 0
            continue
        if line.startswith("+") and not line.startswith("+++"):
            line_number += 1
            text = line[1:]
            if text.rstrip(" \t") != text:
                failures.append(f"{current_file}:{line_number}: added line has trailing whitespace")
            conflict_markers = ("<" * 7, "=" * 7, ">" * 7)
            if any(marker in text for marker in conflict_markers):
                failures.append(f"{current_file}:{line_number}: added line contains a conflict marker")

    if failures:
        return False, "\n".join(failures), {"failure_count": len(failures)}
    return True, "no added-line whitespace or conflict-marker issues", {"failure_count": 0}


def parse_json_files(paths: Iterable[Path]) -> tuple[bool, str, dict[str, Any]]:
    checked: list[str] = []
    failures: list[str] = []
    for path in paths:
        if not path.exists():
            continue
        checked.append(rel(path))
        try:
            json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            failures.append(f"{rel(path)}: {exc}")
    if failures:
        return False, "\n".join(failures), {"checked": checked, "failures": failures}
    return True, f"parsed {len(checked)} JSON files", {"checked": checked}


def metadata_json_parse() -> tuple[bool, str, dict[str, Any]]:
    return parse_json_files(
        [
            ROOT / ".claude" / "settings.json",
            ROOT / ".claude-plugin" / "plugin.json",
            ROOT / ".claude-plugin" / "marketplace.json",
            ROOT / "dist" / "plugin" / ".claude-plugin" / "plugin.json",
            ROOT / "dist" / "plugin" / ".claude-plugin" / "marketplace.json",
            ROOT / "dist" / "plugin" / "build-manifest.json",
        ]
    )


def plugin_version(path: Path) -> str:
    data = json.loads(path.read_text(encoding="utf-8"))
    if "plugins" in data:
        plugins = data.get("plugins")
        if not isinstance(plugins, list) or not plugins:
            raise ValueError(f"{rel(path)} must contain a non-empty plugins list")
        version = plugins[0].get("version")
    elif "plugin_version" in data:
        version = data.get("plugin_version")
    else:
        version = data.get("version")
    if not isinstance(version, str) or not version.strip():
        raise ValueError(f"{rel(path)} does not contain a plugin version")
    return version.strip()


def version_consistency() -> tuple[bool, str, dict[str, Any]]:
    paths = [
        ROOT / ".claude-plugin" / "plugin.json",
        ROOT / ".claude-plugin" / "marketplace.json",
        ROOT / "dist" / "plugin" / ".claude-plugin" / "plugin.json",
        ROOT / "dist" / "plugin" / ".claude-plugin" / "marketplace.json",
        ROOT / "dist" / "plugin" / "build-manifest.json",
    ]
    versions: dict[str, str] = {}
    failures: list[str] = []
    for path in paths:
        try:
            versions[rel(path)] = plugin_version(path)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            failures.append(f"{rel(path)}: {exc}")
    unique_versions = sorted(set(versions.values()))
    if failures:
        return False, "\n".join(failures), {"versions": versions, "failures": failures}
    if len(unique_versions) != 1:
        return False, f"version mismatch: {versions}", {"versions": versions}
    return True, f"plugin version {unique_versions[0]}", {"versions": versions}


def step(name: str, description: str, argv: list[str], timeout: int = 120) -> GateStep:
    return GateStep(name=name, description=description, kind="command", argv=tuple(argv), timeout=timeout)


def internal_step(
    name: str,
    description: str,
    runner: Callable[[], tuple[bool, str, dict[str, Any]]],
) -> GateStep:
    return GateStep(name=name, description=description, kind="internal", runner=runner)


def commit_steps() -> list[GateStep]:
    return [
        internal_step("diff_added_line_check", "Reject added-line trailing whitespace and conflict markers without CRLF false positives.", diff_added_line_check),
        internal_step("metadata_json_parse", "Parse core JSON metadata without running the full repository validator.", metadata_json_parse),
        step(
            "valid_minimal_spec",
            "Exercise the workflow-spec schema on the minimal fixture.",
            [sys.executable, ".claude/scripts/validate-workflow-spec.py", "--spec", "tests/spec-fixtures/valid-minimal.yaml", "--json"],
        ),
        step(
            "template_spec",
            "Exercise the workflow-spec schema on the authoring template.",
            [sys.executable, ".claude/scripts/validate-workflow-spec.py", "--spec", ".claude/skills/workflow-spec-support/yaml-spec-template.md", "--json"],
        ),
    ]


def integration_steps() -> list[GateStep]:
    return [
        *commit_steps(),
        step("unit_tests", "Run deterministic unit tests for changed runtime and validators.", [sys.executable, "-m", "pytest", "tests/unit", "-q"], timeout=300),
        step(
            "fixture_host_smoke",
            "Run a deterministic fixture-host smoke without invoking a real Claude CLI executor.",
            [sys.executable, "tools/runtime_smoke.py", "--fixture", "empty-project", "--runtime-provider", "fixture_host", "--json"],
            timeout=180,
        ),
    ]


def release_steps(include_claude_cli: bool) -> list[GateStep]:
    matrix_cmd = [sys.executable, "tools/runtime_smoke_matrix.py", "--json"]
    if include_claude_cli:
        matrix_cmd.append("--include-claude-cli")
    return [
        step("build_plugin", "Rebuild dist/plugin from the canonical source tree.", [sys.executable, "tools/build_plugin.py"], timeout=300),
        internal_step("version_consistency", "Verify source and dist plugin version metadata agree.", version_consistency),
        internal_step("diff_added_line_check", "Reject added-line trailing whitespace and conflict markers after the build.", diff_added_line_check),
        step("repository_validator", "Run the full WorkflowProgram repository validator.", [sys.executable, ".claude/scripts/validate-workflow.py"], timeout=300),
        step("plugin_bootstrap", "Verify the built marketplace payload can bootstrap its local Python runtime.", [sys.executable, "tools/test_plugin_bootstrap.py", "--json"], timeout=300),
        step("runtime_smoke_matrix", "Run the deterministic runtime smoke matrix before release.", matrix_cmd, timeout=1800),
    ]


def gate_steps(gate: str, include_claude_cli: bool = False) -> list[GateStep]:
    if gate == "commit":
        return commit_steps()
    if gate == "integration":
        return integration_steps()
    if gate == "release":
        return release_steps(include_claude_cli)
    raise ValueError(f"unknown gate: {gate}")


def execute_gate(gate: str, *, dry_run: bool, include_claude_cli: bool) -> dict[str, Any]:
    steps = gate_steps(gate, include_claude_cli=include_claude_cli)
    results: list[dict[str, Any]] = []
    status = "DRY_RUN" if dry_run else "PASS"

    for item in steps:
        entry: dict[str, Any] = {
            "name": item.name,
            "description": item.description,
            "kind": item.kind,
            "command": item.display_command(),
        }
        if dry_run:
            entry["status"] = "SKIPPED"
        else:
            try:
                if item.runner is not None:
                    ok, output, extra = item.runner()
                else:
                    ok, output, extra = run_command(item)
            except subprocess.TimeoutExpired as exc:
                ok = False
                output = f"timed out after {exc.timeout}s"
                extra = {"returncode": None, "timeout": exc.timeout}
            except Exception as exc:  # noqa: BLE001 - gate reports should preserve unexpected context.
                ok = False
                output = str(exc)
                extra = {"returncode": None}
            entry.update(extra)
            entry["status"] = "PASS" if ok else "FAIL"
            entry["output"] = output
            if not ok:
                status = "FAIL"
        results.append(entry)

    return {
        "schema_version": 1,
        "schema_name": "workflowprogram-quality-gate",
        "gate": gate,
        "status": status,
        "steps": results,
    }


def print_text(payload: dict[str, Any]) -> None:
    print(f"{payload['status']} {payload['gate']} gate")
    for item in payload["steps"]:
        print(f"- {item['status']}: {item['name']} :: {item['command']}")
        if item.get("status") == "FAIL" and item.get("output"):
            print(item["output"])


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run layered WorkflowProgram quality gates")
    parser.add_argument("gate", help="Gate level: commit, integration, or release")
    parser.add_argument("--dry-run", action="store_true", help="List gate steps without executing them")
    parser.add_argument("--include-claude-cli", action="store_true", help="Include optional real claude_cli smoke in release gate")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.gate not in {"commit", "integration", "release"}:
        payload = {
            "schema_version": 1,
            "schema_name": "workflowprogram-quality-gate",
            "gate": args.gate,
            "status": "FAIL",
            "error": "gate must be one of: commit, integration, release",
        }
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(payload["error"], file=sys.stderr)
        return 2

    payload = execute_gate(args.gate, dry_run=args.dry_run, include_claude_cli=args.include_claude_cli)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print_text(payload)
    return 0 if payload["status"] in {"PASS", "DRY_RUN"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
