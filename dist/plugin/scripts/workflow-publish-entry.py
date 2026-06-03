#!/usr/bin/env python3
# AUTO-GENERATED FROM .claude/ - DO NOT EDIT DIRECTLY
"""Deterministic entry for publishing completed target workflows as Claude Code plugins."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List

from lib.io_utils import iso_now, write_json


PUBLISH_DIR = "outputs/stages/publish"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run WorkflowProgram target workflow publish lifecycle")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run")
    run.add_argument("--target-root", required=True)
    run.add_argument("--run-root", required=True)
    run.add_argument("--develop-run-root", default="")
    run.add_argument("--plugin-id", required=True)
    run.add_argument("--plugin-name", default="")
    run.add_argument("--version", default="0.1.0")
    run.add_argument("--description", default="WorkflowProgram generated Claude Code workflow plugin")
    run.add_argument("--repository", required=True)
    run.add_argument("--repo-mode", default="export_repo", choices=["current_repo", "export_repo", "existing_marketplace"])
    run.add_argument("--repo-path", default="")
    run.add_argument("--marketplace-name", default="target-workflow-plugins")
    run.add_argument("--update-existing-entry", action="store_true")
    run.add_argument("--runtime-mode", default="workflowprogram_dependency", choices=["workflowprogram_dependency", "vendored_runtime"])
    run.add_argument("--workflowprogram-plugin-root", default="")
    run.add_argument("--allow-warn", action="store_true")
    run.add_argument("--dry-run", action="store_true")
    run.add_argument("--execute-github", action="store_true")
    run.add_argument("--approve-github", action="store_true")
    run.add_argument("--simulate-github-auth-missing", action="store_true")
    run.add_argument("--simulate-github-auth-ready", action="store_true")
    run.add_argument("--require-claude-validate", action="store_true")
    run.add_argument("--skip-claude-validate", action="store_true")
    run.add_argument("--claude-bin", default="claude")
    run.add_argument("--json", action="store_true")
    return parser.parse_args()


def script_root() -> Path:
    return Path(__file__).resolve().parent


def run_json(script_name: str, args: List[str], allowed: set[int] | None = None) -> tuple[int, Dict[str, Any], str]:
    cmd = [sys.executable, str(script_root() / script_name), *args, "--json"]
    completed = subprocess.run(cmd, capture_output=True, text=True, check=False)
    allowed_codes = allowed or {0}
    output = completed.stdout.strip() or completed.stderr.strip()
    try:
        payload = json.loads(output) if output else {}
    except json.JSONDecodeError:
        payload = {}
    if completed.returncode not in allowed_codes and not payload:
        payload = {"status": "FAIL", "errors": [output or f"{script_name} exited {completed.returncode}"]}
    return completed.returncode, payload if isinstance(payload, dict) else {}, output


def append_event(run_root: Path, event_type: str, status: str, message: str) -> None:
    path = run_root / "events.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(
            json.dumps(
                {
                    "ts": iso_now(),
                    "type": event_type,
                    "stage": "publish",
                    "source": "workflow-publish-entry.py",
                    "status": status,
                    "message": message,
                },
                ensure_ascii=False,
            )
            + "\n"
        )


def write_summary(
    run_root: Path,
    *,
    status: str,
    failure_kind: str,
    block_reason: str = "",
    message: str,
    extra: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    payload = {
        "schema_version": 1,
        "generated_at": iso_now(),
        "status": status,
        "failure_kind": failure_kind,
        "block_reason": block_reason or None,
        "message": message,
        **(extra or {}),
    }
    write_json(run_root / PUBLISH_DIR / "publish-summary.json", payload)
    write_json(
        run_root / "state.json",
        {
            "schema_version": 1,
            "schema_name": "workflowprogram-publish-state",
            "run_id": run_root.name,
            "status": "completed" if status != "BLOCKED" else "blocked",
            "stage": "publish",
            "result": "PASS" if status == "PASS" else "FAIL",
            "category": failure_kind,
            "values": {"stage_history": ["publish"], "publish_status": status},
            "updated_at": iso_now(),
        },
    )
    return payload


def write_install_instructions(
    run_root: Path,
    *,
    repository: str,
    marketplace_name: str,
    plugin_id: str,
    version: str,
    runtime_mode: str,
    github_status: str,
    repo_mode: str,
    package_root: str = "",
) -> Path:
    lines = [
        "# Target Workflow Plugin Install Instructions",
        "",
        f"- Repository: `{repository}`",
        f"- Marketplace: `{marketplace_name}`",
        f"- Plugin: `{plugin_id}`",
        f"- Version: `{version}`",
        f"- Runtime mode: `{runtime_mode}`",
        f"- GitHub publish status: `{github_status}`",
        "",
        "## Install",
        "",
    ]
    if runtime_mode == "workflowprogram_dependency":
        lines.extend(
            [
                "Install WorkflowProgram first:",
                "",
                "```text",
                "/plugin marketplace add logic70-plugins https://github.com/Logic70/WorkflowProgram.git",
                "/plugin install workflowprogram-cn@logic70-plugins",
                "```",
                "",
            ]
        )
    requirements_path = Path(package_root) / "requirements.txt" if package_root else Path()
    if requirements_path.exists():
        packages = [line.strip() for line in requirements_path.read_text(encoding="utf-8").splitlines() if line.strip() and not line.strip().startswith("#")]
        lines.extend(
            [
                "Install target workflow Python dependencies when report rendering or deterministic scripts require them:",
                "",
                "```text",
                "python3 -m pip install -r <installed-plugin-root>/requirements.txt",
                "```",
                "",
            ]
        )
        if packages:
            lines.extend(["Declared packages:", "", *[f"- `{package}`" for package in packages], ""])
    lines.extend(
        [
            "Install the target workflow plugin:",
            "",
            "```text",
            f"/plugin marketplace add {marketplace_name} {repository}",
            f"/plugin install {plugin_id}@{marketplace_name}",
            "```",
            "",
            "## Update",
            "",
            "```text",
        ]
    )
    if repo_mode == "existing_marketplace":
        lines.append(f"/plugin marketplace update {marketplace_name}")
    lines.extend(
        [
            f"/plugin update {plugin_id}@{marketplace_name}",
            "```",
        ]
    )
    path = run_root / PUBLISH_DIR / "install-instructions.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return path


def main() -> int:
    args = parse_args()
    target_root = Path(args.target_root).resolve()
    run_root = Path(args.run_root).resolve()
    run_root.mkdir(parents=True, exist_ok=True)
    append_event(run_root, "PublishStarted", "running", "Target workflow publish lifecycle started.")

    write_json(
        run_root / PUBLISH_DIR / "publish-intent.json",
        {
            "schema_version": 1,
            "generated_at": iso_now(),
            "target_root": str(target_root),
            "plugin_id": args.plugin_id,
            "plugin_name": args.plugin_name,
            "version": args.version,
            "repository": args.repository,
            "repo_mode": args.repo_mode,
            "marketplace_name": args.marketplace_name,
            "runtime_mode": args.runtime_mode,
            "dry_run": args.dry_run,
        },
    )
    write_json(
        run_root / PUBLISH_DIR / "publish-options.json",
        {
            "schema_version": 1,
            "allow_warn": args.allow_warn,
            "execute_github": args.execute_github,
            "approve_github": args.approve_github,
            "update_existing_entry": args.update_existing_entry,
            "simulate_github_auth_ready": args.simulate_github_auth_ready,
            "require_claude_validate": args.require_claude_validate,
            "skip_claude_validate": args.skip_claude_validate,
        },
    )

    eligibility_args = ["--target-root", str(target_root), "--run-root", str(run_root)]
    if args.develop_run_root.strip():
        eligibility_args.extend(["--develop-run-root", args.develop_run_root])
    if args.allow_warn:
        eligibility_args.append("--allow-warn")
    eligibility_code, eligibility, _ = run_json("validate-publish-eligibility.py", eligibility_args, allowed={0, 1})
    if eligibility_code != 0 or eligibility.get("status") != "PASS":
        append_event(run_root, "PublishEligibilityFailed", "error", "Target workflow is not publishable.")
        summary = write_summary(
            run_root,
            status="FAIL",
            failure_kind="design",
            message="Target workflow is not eligible for publishing.",
            extra={"eligibility": eligibility},
        )
        if args.json:
            print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 1

    package_args = [
        "--target-root",
        str(target_root),
        "--run-root",
        str(run_root),
        "--plugin-id",
        args.plugin_id,
        "--plugin-name",
        args.plugin_name,
        "--version",
        args.version,
        "--description",
        args.description,
        "--repository-url",
        args.repository,
        "--marketplace-name",
        args.marketplace_name,
        "--repo-mode",
        args.repo_mode,
        "--runtime-mode",
        args.runtime_mode,
    ]
    if args.workflowprogram_plugin_root.strip():
        package_args.extend(["--workflowprogram-plugin-root", args.workflowprogram_plugin_root])
    package_code, package, _ = run_json("package-target-plugin.py", package_args, allowed={0, 1})
    if package_code != 0 or package.get("status") != "PASS":
        append_event(run_root, "PublishPackageFailed", "error", "Plugin package creation failed.")
        summary = write_summary(
            run_root,
            status="FAIL",
            failure_kind="implementation",
            message="Target workflow plugin package creation failed.",
            extra={"package": package},
        )
        if args.json:
            print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 1

    package_root = str(package.get("package_root", ""))
    validation_args = [
        "--package-root",
        package_root,
        "--run-root",
        str(run_root),
        "--repo-mode",
        args.repo_mode,
        "--claude-bin",
        args.claude_bin,
    ]
    if args.require_claude_validate:
        validation_args.append("--require-claude-validate")
    if args.skip_claude_validate:
        validation_args.append("--skip-claude-validate")
    validation_code, validation, _ = run_json("validate-target-plugin-package.py", validation_args, allowed={0, 1})
    if validation_code != 0 or validation.get("status") != "PASS":
        append_event(run_root, "PublishValidationFailed", "error", "Plugin package validation failed.")
        summary = write_summary(
            run_root,
            status="FAIL",
            failure_kind="implementation",
            message="Target workflow plugin package validation failed.",
            extra={"validation": validation},
        )
        if args.json:
            print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 1

    merge: Dict[str, Any] = {}
    resolved_marketplace_name = args.marketplace_name
    if args.repo_mode == "existing_marketplace":
        merge_args = [
            "--package-root",
            package_root,
            "--run-root",
            str(run_root),
            "--repo-path",
            args.repo_path,
            "--plugin-id",
            str(package.get("plugin_id", args.plugin_id)),
            "--version",
            args.version,
            "--marketplace-name",
            args.marketplace_name,
        ]
        if args.update_existing_entry:
            merge_args.append("--update-existing-entry")
        merge_code, merge, _ = run_json("merge-target-marketplace.py", merge_args, allowed={0, 1, 2})
        resolved_marketplace_name = str(merge.get("marketplace_name", args.marketplace_name) or args.marketplace_name)
        if merge_code != 0 or merge.get("status") != "PASS":
            status = "BLOCKED" if merge.get("status") == "BLOCKED" else "FAIL"
            append_event(run_root, "PublishMarketplaceMergeBlocked", "warn" if status == "BLOCKED" else "error", "Existing marketplace merge did not pass.")
            summary = write_summary(
                run_root,
                status=status,
                failure_kind="conflict" if status == "BLOCKED" else "implementation",
                block_reason=str(merge.get("block_reason", "existing_marketplace_merge_failed")),
                message="Existing marketplace merge did not pass.",
                extra={"marketplace_merge": merge},
            )
            if args.json:
                print(json.dumps(summary, ensure_ascii=False, indent=2))
            return 2 if status == "BLOCKED" else 1

    github_args = [
        "--package-root",
        package_root,
        "--run-root",
        str(run_root),
        "--repository",
        args.repository,
        "--repo-mode",
        args.repo_mode,
        "--plugin-id",
        str(package.get("plugin_id", args.plugin_id)),
        "--version",
        args.version,
    ]
    if args.repo_path.strip():
        github_args.extend(["--repo-path", args.repo_path])
    if args.execute_github:
        github_args.append("--execute")
    if args.approve_github:
        github_args.append("--approved")
    if args.dry_run:
        github_args.append("--dry-run")
    if args.simulate_github_auth_missing:
        github_args.append("--simulate-auth-missing")
    if args.simulate_github_auth_ready:
        github_args.append("--simulate-auth-ready")
    github_code, github, _ = run_json("github-publish-target-plugin.py", github_args, allowed={0, 1, 2})

    install_path = write_install_instructions(
        run_root,
        repository=args.repository,
        marketplace_name=resolved_marketplace_name,
        plugin_id=str(package.get("plugin_id", args.plugin_id)),
        version=args.version,
        runtime_mode=args.runtime_mode,
        github_status=str(github.get("status", "UNKNOWN")),
        repo_mode=args.repo_mode,
        package_root=package_root,
    )
    if github.get("status") == "PASS":
        append_event(run_root, "PublishCompleted", "ok", "Target workflow plugin publish completed.")
        summary = write_summary(
            run_root,
            status="PASS",
            failure_kind="none",
            message="Target workflow plugin package validated and GitHub publish completed.",
            extra={"github": github, "install_instructions": str(install_path)},
        )
        if args.json:
            print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0

    append_event(run_root, "PublishBlocked", "warn", "Target workflow plugin publish is blocked before GitHub completion.")
    failure_kind = str(github.get("failure_kind", "environment")).strip() or "environment"
    summary = write_summary(
        run_root,
        status="BLOCKED",
        failure_kind=failure_kind,
        block_reason=str(github.get("block_reason", "github_publish_blocked")),
        message=str(github.get("message", "GitHub publish did not complete.")),
        extra={"github": github, "install_instructions": str(install_path)},
    )
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 2 if github_code == 2 or github.get("status") == "BLOCKED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
