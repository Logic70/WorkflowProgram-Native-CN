#!/usr/bin/env python3
"""Normalize host-side Native develop reports into re-entrant Workflow JS evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


def load_json(path: Path) -> dict[str, Any]:
    """Load one report object."""

    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Report must be a JSON object: {path}")
    return payload


def candidate_files(root: Path) -> list[Path]:
    """Return candidate files in stable relative-path order."""

    if not root.is_dir():
        raise FileNotFoundError(f"Candidate root not found: {root}")
    files = sorted(path for path in root.rglob("*") if path.is_file())
    if not files:
        raise ValueError(f"Candidate root is empty: {root}")
    return files


def candidate_hash(root: Path, files: list[Path]) -> str:
    """Hash relative paths and bytes so supporting-asset changes invalidate evidence."""

    digest = hashlib.sha256()
    for path in files:
        relative = path.relative_to(root).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return f"sha256:{digest.hexdigest()}"


def report_issues(payload: dict[str, Any], fallback: str) -> list[str]:
    """Extract readable blocking issues from known report shapes."""

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


def build_report_evidence(stage: str, candidate_root: Path, report_path: Path) -> dict[str, Any]:
    """Normalize generation, validation, or apply reports."""

    files = candidate_files(candidate_root)
    digest = candidate_hash(candidate_root, files)
    payload = load_json(report_path)
    status = str(payload.get("status", "")).upper()
    evidence: dict[str, Any] = {
        "status": "PASS" if status == "PASS" else status or "FAIL",
        "candidateHash": digest,
        "evidence": [str(report_path.resolve())],
        "blockingIssues": [] if status == "PASS" else report_issues(payload, f"{stage} report did not pass."),
    }
    if stage == "generation":
        evidence["candidateRefs"] = [str(path.resolve()) for path in files]
    if stage == "apply":
        conflicts = payload.get("conflicts")
        if isinstance(conflicts, list) and conflicts:
            evidence["status"] = "CONFLICT"
            evidence["blockingIssues"] = report_issues(payload, "Managed apply reported conflicts.")
        evidence["applyManifest"] = str(payload.get("manifest_path") or report_path.resolve())
    return evidence


def build_smoke_evidence(candidate_root: Path, status: str, evidence_paths: list[Path]) -> dict[str, Any]:
    """Normalize interactive smoke evidence supplied by the host-side harness."""

    files = candidate_files(candidate_root)
    missing = [str(path) for path in evidence_paths if not path.exists()]
    normalized_status = status.upper()
    if missing:
        normalized_status = "FAIL"
    blocking_issues = [f"Smoke evidence path not found: {path}" for path in missing]
    if normalized_status != "PASS" and not blocking_issues:
        blocking_issues = ["Interactive smoke did not pass."]
    return {
        "status": "PASS" if normalized_status == "PASS" else normalized_status,
        "candidateHash": candidate_hash(candidate_root, files),
        "evidence": [str(path.resolve()) for path in evidence_paths if path.exists()],
        "blockingIssues": blocking_issues,
    }


def build_parser() -> argparse.ArgumentParser:
    """Build CLI parser."""

    parser = argparse.ArgumentParser(description="Build WorkflowProgram Native develop evidence")
    subparsers = parser.add_subparsers(dest="stage", required=True)
    for stage in ("generation", "validation", "apply"):
        sub = subparsers.add_parser(stage)
        sub.add_argument("--candidate-root", required=True)
        sub.add_argument("--report", required=True)
        sub.add_argument("--json", action="store_true")
    smoke = subparsers.add_parser("smoke")
    smoke.add_argument("--candidate-root", required=True)
    smoke.add_argument("--status", required=True, choices=("PASS", "FAIL"))
    smoke.add_argument("--evidence", required=True, nargs="+")
    smoke.add_argument("--json", action="store_true")
    return parser


def main() -> int:
    """Normalize evidence and return a stable status code."""

    args = build_parser().parse_args()
    try:
        candidate_root = Path(args.candidate_root).resolve()
        if args.stage == "smoke":
            payload = build_smoke_evidence(candidate_root, args.status, [Path(item).resolve() for item in args.evidence])
        else:
            payload = build_report_evidence(args.stage, candidate_root, Path(args.report).resolve())
    except Exception as exc:
        payload = {
            "status": "FAIL",
            "candidateHash": "",
            "evidence": [],
            "blockingIssues": [str(exc)],
        }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"{payload['status']}: {payload.get('candidateHash', '')}")
    return 0 if payload["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
