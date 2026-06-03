#!/usr/bin/env python3
# AUTO-GENERATED FROM .claude/ - DO NOT EDIT DIRECTLY
"""Plan or execute GitHub publication for a staged target workflow plugin package."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List

from lib.io_utils import iso_now, write_json


PUBLISH_DIR = "outputs/stages/publish"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Publish a staged target workflow plugin to GitHub")
    parser.add_argument("--package-root", required=True)
    parser.add_argument("--run-root", required=True)
    parser.add_argument("--repository", required=True, help="GitHub repository URL or owner/name")
    parser.add_argument("--repo-mode", default="export_repo", choices=["current_repo", "export_repo", "existing_marketplace"])
    parser.add_argument("--repo-path", default="", help="Local checkout path to update when executing")
    parser.add_argument("--plugin-id", default="")
    parser.add_argument("--version", default="0.1.0")
    parser.add_argument("--execute", action="store_true", help="Perform git writes and push")
    parser.add_argument("--approved", action="store_true", help="Required for --execute")
    parser.add_argument("--dry-run", action="store_true", help="Simulate successful GitHub publication")
    parser.add_argument("--simulate-auth-missing", action="store_true", help="Force auth-missing blocked result")
    parser.add_argument("--simulate-auth-ready", action="store_true", help="Force auth-ready state for deterministic local fixtures")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def run_command(cmd: List[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=str(cwd) if cwd else None, capture_output=True, text=True, check=False)


def sanitize_auth_output(output: str) -> str:
    lines: List[str] = []
    for line in output.splitlines():
        if "Token:" in line:
            lines.append("  - Token: <redacted>")
        else:
            lines.append(line)
    return "\n".join(lines).strip()


def tree_hash(root: Path) -> str:
    """Hash relative paths and bytes of every file under root."""
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


def gh_auth_status(simulate_missing: bool, simulate_ready: bool) -> Dict[str, Any]:
    if simulate_missing:
        return {"available": bool(shutil.which("gh")), "ready": False, "message": "simulated missing GitHub auth"}
    if simulate_ready:
        return {"available": True, "ready": True, "message": "simulated ready GitHub auth"}
    gh = shutil.which("gh")
    if not gh:
        return {"available": False, "ready": False, "message": "gh CLI not found"}
    completed = run_command([gh, "auth", "status"])
    output = sanitize_auth_output(completed.stdout.strip() or completed.stderr.strip())
    return {
        "available": True,
        "ready": completed.returncode == 0,
        "message": output or f"gh auth status exited with code {completed.returncode}",
    }


def copy_package_to_checkout(package_root: Path, repo_path: Path) -> List[str]:
    dist_root = repo_path / "dist" / "plugin"
    if dist_root.exists():
        shutil.rmtree(dist_root)
    shutil.copytree(package_root, dist_root)
    source_readme = package_root / ".claude-plugin" / "README.md"
    if source_readme.exists():
        shutil.copy2(source_readme, repo_path / "README.md")
    copied: List[str] = []
    for path in sorted(dist_root.rglob("*")):
        if path.is_file():
            copied.append(path.relative_to(repo_path).as_posix())
    if (repo_path / "README.md").exists():
        copied.append("README.md")
    return copied


def copy_package_to_existing_marketplace(package_root: Path, repo_path: Path, plugin_id: str) -> List[str]:
    plugin_root = repo_path / "plugins" / plugin_id
    if plugin_root.exists():
        shutil.rmtree(plugin_root)
    shutil.copytree(package_root, plugin_root)
    copied: List[str] = []
    for path in sorted(plugin_root.rglob("*")):
        if path.is_file():
            copied.append(path.relative_to(repo_path).as_posix())
    return copied


def load_preview_manifest(run_root: Path) -> Dict[str, Any]:
    path = run_root / PUBLISH_DIR / "marketplace-manifest-preview.json"
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    marketplace_json = payload.get("marketplace_json") if isinstance(payload, dict) else None
    return marketplace_json if isinstance(marketplace_json, dict) else {}


def checkout_clean(repo_path: Path) -> bool:
    completed = run_command(["git", "status", "--porcelain"], cwd=repo_path)
    return completed.returncode == 0 and not completed.stdout.strip()


def publish_to_github(
    *,
    package_root: Path,
    run_root: Path,
    repository: str,
    repo_mode: str,
    repo_path: Path | None,
    plugin_id: str,
    version: str,
    execute: bool,
    approved: bool,
    dry_run: bool,
    simulate_auth_missing: bool,
    simulate_auth_ready: bool,
) -> Dict[str, Any]:
    package_hash = tree_hash(package_root)

    plan = {
        "schema_version": 1,
        "generated_at": iso_now(),
        "repository": repository,
        "repo_mode": repo_mode,
        "repo_path": str(repo_path) if repo_path else None,
        "version": version,
        "package_hash": package_hash,
        "package_root": str(package_root),
        "plugin_id": plugin_id or None,
        "steps": (
            [
                "verify GitHub auth",
                "verify existing marketplace checkout is clean",
                f"copy package to plugins/{plugin_id}",
                "write merged marketplace manifest",
                "commit marketplace manifest and plugin payload",
                f"tag v{version}",
                "push branch and tag",
            ]
            if repo_mode == "existing_marketplace"
            else [
                "verify GitHub auth",
                "copy package to publishing checkout",
                "commit dist/plugin payload",
                f"tag v{version}",
                "push branch and tag",
            ]
        ),
        "execute": execute,
        "dry_run": dry_run,
    }
    write_json(run_root / PUBLISH_DIR / "github-publish-plan.json", plan)

    auth = gh_auth_status(simulate_auth_missing, simulate_auth_ready)
    if dry_run:
        payload = {
            "schema_version": 1,
            "generated_at": iso_now(),
            "status": "PASS",
            "dry_run": True,
            "package_hash": package_hash,
            "repository": repository,
            "repo_mode": repo_mode,
            "version": version,
            "commit": "dry-run",
            "tag": f"v{version}",
            "auth": auth,
            "message": "GitHub publication simulated successfully.",
        }
        write_json(run_root / PUBLISH_DIR / "github-publish-result.json", payload)
        return payload

    # Prior real PASS receipt with execute+approved → idempotent short-circuit
    # before auth probing and repo-path requirement.
    if execute and approved:
        result_path = run_root / PUBLISH_DIR / "github-publish-result.json"
        if result_path.exists():
            try:
                prior = json.loads(result_path.read_text(encoding="utf-8"))
            except Exception:
                prior = None
            if isinstance(prior, dict):
                prior_status = str(prior.get("status", "")).upper()
                prior_dry_run = prior.get("dry_run", False)
                prior_hash = prior.get("package_hash", "")
                if prior_status == "PASS" and not prior_dry_run:
                    if (prior_hash == package_hash
                            and prior.get("repository", "") == repository
                            and prior.get("repo_mode", "") == repo_mode
                            and prior.get("version", "") == version):
                        payload = {
                            "schema_version": 1,
                            "generated_at": iso_now(),
                            "status": "PASS",
                            "idempotent": True,
                            "package_hash": package_hash,
                            "repository": repository,
                            "repo_mode": repo_mode,
                            "version": version,
                            "message": "Prior PASS receipt for same package_hash, repository, repo_mode, and version — external apply already completed.",
                        }
                        write_json(result_path, payload)
                        return payload

    if not auth["ready"]:
        payload = {
            "schema_version": 1,
            "generated_at": iso_now(),
            "status": "BLOCKED",
            "failure_kind": "environment",
            "block_reason": "github_auth_missing",
            "package_hash": package_hash,
            "repository": repository,
            "repo_mode": repo_mode,
            "version": version,
            "auth": auth,
            "message": "GitHub authentication is not ready; run gh auth login/status outside WorkflowProgram.",
        }
        write_json(run_root / PUBLISH_DIR / "github-publish-result.json", payload)
        return payload

    if not execute or not approved:
        payload = {
            "schema_version": 1,
            "generated_at": iso_now(),
            "status": "BLOCKED",
            "failure_kind": "design",
            "block_reason": "approval_required",
            "package_hash": package_hash,
            "repository": repository,
            "repo_mode": repo_mode,
            "version": version,
            "auth": auth,
            "message": "GitHub publish execution requires explicit approval.",
        }
        write_json(run_root / PUBLISH_DIR / "github-publish-result.json", payload)
        return payload

    if repo_path is None:
        payload = {
            "schema_version": 1,
            "generated_at": iso_now(),
            "status": "BLOCKED",
            "failure_kind": "environment",
            "block_reason": "repo_path_required",
            "package_hash": package_hash,
            "repository": repository,
            "repo_mode": repo_mode,
            "version": version,
            "auth": auth,
            "message": "Executing publish requires --repo-path pointing to a clean checkout.",
        }
        write_json(run_root / PUBLISH_DIR / "github-publish-result.json", payload)
        return payload

    repo_path.mkdir(parents=True, exist_ok=True)

    if repo_mode == "existing_marketplace":
        if not plugin_id.strip():
            payload = {
                "schema_version": 1,
                "generated_at": iso_now(),
                "status": "BLOCKED",
                "failure_kind": "conflict",
                "block_reason": "existing_marketplace_plugin_id_required",
                "package_hash": package_hash,
                "repository": repository,
                "repo_mode": repo_mode,
                "version": version,
                "auth": auth,
                "message": "Executing existing marketplace publish requires --plugin-id.",
            }
            write_json(run_root / PUBLISH_DIR / "github-publish-result.json", payload)
            return payload
        if not checkout_clean(repo_path):
            payload = {
                "schema_version": 1,
                "generated_at": iso_now(),
                "status": "BLOCKED",
                "failure_kind": "conflict",
                "block_reason": "existing_marketplace_checkout_dirty",
                "package_hash": package_hash,
                "repository": repository,
                "repo_mode": repo_mode,
                "version": version,
                "repo_path": str(repo_path),
                "auth": auth,
                "message": "Existing marketplace checkout must be clean before publish execution.",
            }
            write_json(run_root / PUBLISH_DIR / "github-publish-result.json", payload)
            return payload
        preview_manifest = load_preview_manifest(run_root)
        if not preview_manifest:
            payload = {
                "schema_version": 1,
                "generated_at": iso_now(),
                "status": "BLOCKED",
                "failure_kind": "conflict",
                "block_reason": "existing_marketplace_preview_missing",
                "package_hash": package_hash,
                "repository": repository,
                "repo_mode": repo_mode,
                "version": version,
                "repo_path": str(repo_path),
                "auth": auth,
                "message": "Existing marketplace merge preview is missing.",
            }
            write_json(run_root / PUBLISH_DIR / "github-publish-result.json", payload)
            return payload
        copied = copy_package_to_existing_marketplace(package_root, repo_path, plugin_id)
        write_json(repo_path / ".claude-plugin" / "marketplace.json", preview_manifest)
        run_command(["git", "add", ".claude-plugin/marketplace.json", f"plugins/{plugin_id}"], cwd=repo_path)
    else:
        copied = copy_package_to_checkout(package_root, repo_path)
        run_command(["git", "add", "README.md", "dist/plugin"], cwd=repo_path)
    commit = run_command(["git", "commit", "-m", f"Publish target workflow plugin v{version}"], cwd=repo_path)
    if commit.returncode != 0:
        payload = {
            "schema_version": 1,
            "generated_at": iso_now(),
            "status": "FAIL",
            "failure_kind": "conflict",
            "package_hash": package_hash,
            "repository": repository,
            "repo_mode": repo_mode,
            "version": version,
            "copied_files": copied,
            "message": commit.stderr.strip() or commit.stdout.strip() or "git commit failed",
        }
        write_json(run_root / PUBLISH_DIR / "github-publish-result.json", payload)
        return payload
    tag = run_command(["git", "tag", f"v{version}"], cwd=repo_path)
    if tag.returncode != 0:
        payload = {
            "schema_version": 1,
            "generated_at": iso_now(),
            "status": "FAIL",
            "failure_kind": "conflict",
            "package_hash": package_hash,
            "repository": repository,
            "repo_mode": repo_mode,
            "version": version,
            "copied_files": copied,
            "commit_stdout": commit.stdout.strip(),
            "message": tag.stderr.strip() or tag.stdout.strip() or f"git tag v{version} failed",
        }
        write_json(run_root / PUBLISH_DIR / "github-publish-result.json", payload)
        return payload
    push = run_command(["git", "push"], cwd=repo_path)
    push_tag = run_command(["git", "push", "origin", f"v{version}"], cwd=repo_path)
    push_succeeded = push.returncode == 0 and push_tag.returncode == 0
    payload = {
        "schema_version": 1,
        "generated_at": iso_now(),
        "status": "PASS" if push_succeeded else "FAIL",
        "failure_kind": "none" if push_succeeded else "environment",
        "package_hash": package_hash,
        "repository": repository,
        "repo_mode": repo_mode,
        "version": version,
        "repo_path": str(repo_path),
        "copied_files": copied,
        "commit_stdout": commit.stdout.strip(),
        "tag_stdout": tag.stdout.strip(),
        "push_stdout": push.stdout.strip(),
        "push_stderr": push.stderr.strip(),
        "push_tag_stdout": push_tag.stdout.strip(),
        "push_tag_stderr": push_tag.stderr.strip(),
    }
    write_json(run_root / PUBLISH_DIR / "github-publish-result.json", payload)
    return payload


def main() -> int:
    args = parse_args()
    payload = publish_to_github(
        package_root=Path(args.package_root).resolve(),
        run_root=Path(args.run_root).resolve(),
        repository=args.repository,
        repo_mode=args.repo_mode,
        repo_path=Path(args.repo_path).resolve() if args.repo_path.strip() else None,
        plugin_id=args.plugin_id,
        version=args.version,
        execute=args.execute,
        approved=args.approved,
        dry_run=args.dry_run,
        simulate_auth_missing=args.simulate_auth_missing,
        simulate_auth_ready=args.simulate_auth_ready,
    )
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"[{payload['status']}] {payload.get('message', payload.get('repository'))}")
    return 0 if payload["status"] == "PASS" else (2 if payload["status"] == "BLOCKED" else 1)


if __name__ == "__main__":
    raise SystemExit(main())
