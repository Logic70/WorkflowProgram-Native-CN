#!/usr/bin/env python3
"""Narrow deterministic host adapter for Native publish evidence.

Subcommands:
  qualification  Normalize publish-eligibility.json and bind targetHash.
  package        Normalize plugin-package-plan.json and compute packageHash.
  verification   Normalize plugin-validation-report.json and bind packageHash.
  local-delivery Normalize local delivery refs/install instructions.
  marketplace    Normalize marketplace merge plan (repoMode=existing_marketplace).
  external-apply Normalize github-publish-result.json; preserve BLOCKED/FAIL.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


EXCLUDE_PREFIXES = (".workflowprogram/runs/", ".git/")


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


def target_tree_hash(root: Path) -> str:
    """Hash relative paths and bytes of every file under root, excluding mutable runtime material."""
    if not root.is_dir():
        raise FileNotFoundError(f"Root not found: {root}")
    files = sorted(
        path for path in root.rglob("*")
        if path.is_file()
        and not path.relative_to(root).as_posix().startswith(EXCLUDE_PREFIXES)
    )
    if not files:
        raise ValueError(f"Root is empty (after exclusions): {root}")
    digest = hashlib.sha256()
    for path in files:
        relative = path.relative_to(root).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return f"sha256:{digest.hexdigest()}"


def load_report(path: Path) -> dict[str, Any]:
    """Load and validate a JSON object report. Rejects non-objects."""
    if not path.exists():
        raise FileNotFoundError(f"Report not found: {path}")
    raw = path.read_text(encoding="utf-8")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Malformed JSON in report {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"Report must be a JSON object, got {type(payload).__name__}: {path}")
    return payload


def extract_issues(payload: dict[str, Any], fallback: str) -> list[str]:
    """Extract blocking issues from known report shapes."""
    issues: list[str] = []
    for key in ("blockingIssues", "errors", "conflicts"):
        value = payload.get(key)
        if not isinstance(value, list):
            continue
        for item in value:
            if isinstance(item, dict):
                issues.append(str(item.get("message") or item.get("reason") or item))
            else:
                issues.append(str(item))
    return issues or [fallback]


def report_status(payload: dict[str, Any]) -> str:
    """Normalize status to uppercase, defaulting to FAIL."""
    raw = str(payload.get("status", "")).upper()
    return raw if raw else "FAIL"


def cmd_qualification(args: argparse.Namespace) -> dict[str, Any]:
    report = load_report(Path(args.report))
    target_root = Path(args.target_root).resolve()
    target_hash_val = target_tree_hash(target_root)
    status = report_status(report)
    evidence_refs = [str(Path(args.report).resolve())]
    return {
        "status": "PASS" if status == "PASS" else status,
        "targetHash": target_hash_val,
        "evidence": evidence_refs,
        "blockingIssues": [] if status == "PASS" else extract_issues(report, "Qualification report did not pass."),
    }


def cmd_package(args: argparse.Namespace) -> dict[str, Any]:
    report = load_report(Path(args.report))
    package_root = Path(args.package_root).resolve()
    target_root = Path(args.target_root).resolve()
    package_hash_val = tree_hash(package_root)
    target_hash_val = target_tree_hash(target_root)
    status = report_status(report)
    evidence_refs = [str(Path(args.report).resolve())]
    return {
        "status": "PASS" if status == "PASS" else status,
        "targetHash": target_hash_val,
        "packageHash": package_hash_val,
        "evidence": evidence_refs,
        "blockingIssues": [] if status == "PASS" else extract_issues(report, "Package report did not pass."),
    }


def cmd_verification(args: argparse.Namespace) -> dict[str, Any]:
    report = load_report(Path(args.report))
    package_root = Path(args.package_root).resolve()
    package_hash_val = tree_hash(package_root)
    status = report_status(report)
    evidence_refs = [str(Path(args.report).resolve())]
    return {
        "status": "PASS" if status == "PASS" else status,
        "packageHash": package_hash_val,
        "evidence": evidence_refs,
        "blockingIssues": [] if status == "PASS" else extract_issues(report, "Verification report did not pass."),
    }


def cmd_local_delivery(args: argparse.Namespace) -> dict[str, Any]:
    package_root = Path(args.package_root).resolve()
    run_root = Path(args.run_root).resolve()
    package_hash_val = tree_hash(package_root)

    outputs_dir = run_root / "outputs" / "stages" / "publish"
    outputs_dir.mkdir(parents=True, exist_ok=True)

    install_path = outputs_dir / "install-instructions.md"
    install_md = (
        f"# Install Instructions\n\n"
        f"## Plugin: {args.plugin_id}\n\n"
        f"- **Version**: {args.version}\n"
        f"- **Repository**: {args.repository}\n"
        f"- **Runtime Mode**: {args.runtime_mode}\n"
        f"- **Repo Mode**: {args.repo_mode}\n"
    )
    if args.marketplace_name:
        install_md += f"- **Marketplace**: {args.marketplace_name}\n"
    install_md += (
        f"\n## Local Installation\n\n"
        f"Copy the plugin directory to the target project:\n\n"
        f"```\ncp -r {package_root} TARGET_ROOT/.claude/\n```\n\n"
        f"Or use Claude Code's plugin discovery:\n\n"
        f"```\nclaude --plugin-dir {package_root}\n```\n"
    )
    install_path.write_text(install_md, encoding="utf-8")

    delivery_path = outputs_dir / "native-local-delivery.json"
    delivery: dict[str, Any] = {
        "status": "PASS",
        "packageHash": package_hash_val,
        "repository": args.repository,
        "pluginId": args.plugin_id,
        "version": args.version,
        "runtimeMode": args.runtime_mode,
        "repoMode": args.repo_mode,
        "packageRoot": str(package_root),
    }
    if args.marketplace_name:
        delivery["marketplaceName"] = args.marketplace_name
    delivery_path.write_text(json.dumps(delivery, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    evidence_refs = [str(install_path), str(delivery_path)]
    return {
        "status": "PASS",
        "packageHash": package_hash_val,
        "evidence": evidence_refs,
        "blockingIssues": [],
    }


def cmd_marketplace(args: argparse.Namespace) -> dict[str, Any]:
    report = load_report(Path(args.report))
    package_root = Path(args.package_root).resolve()
    package_hash_val = tree_hash(package_root)
    status = report_status(report)
    evidence_refs = [str(Path(args.report).resolve())]
    return {
        "status": "PASS" if status == "PASS" else status,
        "packageHash": package_hash_val,
        "evidence": evidence_refs,
        "blockingIssues": [] if status == "PASS" else extract_issues(report, "Marketplace merge report did not pass."),
    }


def cmd_external_apply(args: argparse.Namespace) -> dict[str, Any]:
    report = load_report(Path(args.report))
    package_root = Path(args.package_root).resolve()
    package_hash_val = tree_hash(package_root)
    status = report_status(report)
    evidence_refs = [str(Path(args.report).resolve())]
    # Reject PASS report without matching package_hash (stale or forged)
    if status == "PASS":
        report_hash = report.get("package_hash", "")
        if not report_hash or report_hash != package_hash_val:
            return {
                "status": "FAIL",
                "packageHash": package_hash_val,
                "evidence": evidence_refs,
                "blockingIssues": [
                    "PASS report missing or stale package_hash; report does not match current package root."
                ],
            }
        # Reject PASS report with dry_run=true — simulation is not a real external apply
        if report.get("dry_run"):
            return {
                "status": "FAIL",
                "packageHash": package_hash_val,
                "evidence": evidence_refs,
                "blockingIssues": [
                    "PASS report with dry_run=true; simulation is not a real external apply."
                ],
            }
    # Preserve BLOCKED/FAIL without converting to PASS
    if status in ("BLOCKED", "FAIL"):
        return {
            "status": status,
            "packageHash": package_hash_val,
            "evidence": evidence_refs,
            "blockingIssues": extract_issues(report, f"External apply is {status}."),
        }
    return {
        "status": "PASS" if status == "PASS" else status,
        "packageHash": package_hash_val,
        "evidence": evidence_refs,
        "blockingIssues": [] if status == "PASS" else extract_issues(report, "External apply report did not pass."),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build WorkflowProgram Native publish evidence")
    subparsers = parser.add_subparsers(dest="stage", required=True)

    qual = subparsers.add_parser("qualification")
    qual.add_argument("--report", required=True)
    qual.add_argument("--target-root", required=True)
    qual.add_argument("--json", action="store_true")

    pkg = subparsers.add_parser("package")
    pkg.add_argument("--report", required=True)
    pkg.add_argument("--package-root", required=True)
    pkg.add_argument("--target-root", required=True)
    pkg.add_argument("--json", action="store_true")

    ver = subparsers.add_parser("verification")
    ver.add_argument("--report", required=True)
    ver.add_argument("--package-root", required=True)
    ver.add_argument("--json", action="store_true")

    ld = subparsers.add_parser("local-delivery")
    ld.add_argument("--package-root", required=True)
    ld.add_argument("--run-root", required=True)
    ld.add_argument("--repository", required=True)
    ld.add_argument("--marketplace-name", default="")
    ld.add_argument("--plugin-id", required=True)
    ld.add_argument("--version", required=True)
    ld.add_argument("--runtime-mode", required=True)
    ld.add_argument("--repo-mode", required=True)
    ld.add_argument("--json", action="store_true")

    mp = subparsers.add_parser("marketplace")
    mp.add_argument("--report", required=True)
    mp.add_argument("--package-root", required=True)
    mp.add_argument("--json", action="store_true")

    ea = subparsers.add_parser("external-apply")
    ea.add_argument("--report", required=True)
    ea.add_argument("--package-root", required=True)
    ea.add_argument("--json", action="store_true")

    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.stage == "qualification":
            payload = cmd_qualification(args)
        elif args.stage == "package":
            payload = cmd_package(args)
        elif args.stage == "verification":
            payload = cmd_verification(args)
        elif args.stage == "local-delivery":
            payload = cmd_local_delivery(args)
        elif args.stage == "marketplace":
            payload = cmd_marketplace(args)
        elif args.stage == "external-apply":
            payload = cmd_external_apply(args)
        else:
            raise ValueError(f"Unknown stage: {args.stage}")
    except Exception as exc:
        payload = {
            "status": "FAIL",
            "targetHash": "",
            "packageHash": "",
            "evidence": [],
            "blockingIssues": [str(exc)],
        }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"{payload['status']}: {payload.get('targetHash', '')}{payload.get('packageHash', '')}")
    return 0 if payload["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
