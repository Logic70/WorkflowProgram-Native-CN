#!/usr/bin/env python3
"""Narrow deterministic host adapter for Native iterate evidence.

Subcommands:
  readback        Bind target lessons.md and constraints.md to a stable state hash.
  validate-delta  Validate a lessons delta file deterministically.
  append-lessons  Append validated delta to lessons.md once per runId.
  apply-constraints  Apply approved proposal to constraints.md once per runId.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import sys
from pathlib import Path
from typing import Any


INDENT = "  "


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def state_hash(lessons_path: Path, constraints_path: Path) -> str:
    """Compute a stable hash binding lessons.md and constraints.md content."""
    digest = hashlib.sha256()
    for path in (lessons_path, constraints_path):
        digest.update(path.name.encode("utf-8"))
        digest.update(b"\0")
        if path.exists():
            digest.update(path.read_bytes())
        digest.update(b"\0")
    return f"sha256:{digest.hexdigest()}"


def sha256_for_content(content: str) -> str:
    return f"sha256:{hashlib.sha256(content.encode('utf-8')).hexdigest()}"


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _append_delta_body(delta: list[dict[str, str]]) -> str:
    """Render delta entries as markdown ready to append to lessons.md."""
    lines: list[str] = []
    for entry in delta:
        entry_type = str(entry.get("type", "")).strip()
        summary = str(entry.get("summary", "")).strip()
        body = str(entry.get("body", "")).strip()
        if not entry_type or not summary or not body:
            continue
        lines.append(f"## {entry_type}: {summary}")
        lines.append("")
        lines.append(body)
        lines.append("")
    return "\n".join(lines)


def _delta_to_markdown(delta_entries: list[dict[str, str]], run_id: str, failure_kind: str) -> str:
    """Materialize structured delta entries as S6 markdown delta."""
    lines: list[str] = []
    lines.append(f"<!-- WFPM-S6 run_id={run_id} failure_kind={failure_kind} -->")
    lines.append("")
    body = _append_delta_body(delta_entries)
    lines.append(body)
    # Include constraint candidates section if entries suggest constraints
    constraint_entries = [e for e in delta_entries if str(e.get("type", "")).strip() == "constraint-candidate"]
    if constraint_entries:
        lines.append("## Constraint Candidates")
        lines.append("")
        for e in constraint_entries:
            summary = str(e.get("summary", "")).strip()
            if summary:
                lines.append(f"- {summary}")
            body_text = str(e.get("body", "")).strip()
            if body_text and body_text not in lines:
                lines.append(f"- {body_text}")
        lines.append("")
    else:
        lines.append("## Constraint Candidates")
        lines.append("")
        lines.append("- 无新增约束")
        lines.append("")
    lines.append("")
    return "\n".join(lines)


def _user_progress_summary(delta_entries: list[dict[str, str]], run_id: str) -> str:
    """Materialize user progress summary markdown."""
    lines: list[str] = []
    lines.append(f"<!-- WFPM-S6-PROGRESS run_id={run_id} -->")
    lines.append("")
    lines.append("历史关键节点结果")
    lines.append("")
    bullet_emitted = False
    for i, entry in enumerate(delta_entries, 1):
        entry_type = str(entry.get("type", "")).strip()
        summary = str(entry.get("summary", "")).strip()
        if entry_type and summary:
            lines.append(f"- [{entry_type}] {summary}")
            bullet_emitted = True
    if not bullet_emitted:
        lines.append("- Iteration completed.")
    lines.append("")
    return "\n".join(lines)


def _import_validator():
    """Import validate_lessons from validate-lessons-delta.py."""
    script_path = _repo_root() / ".claude" / "scripts" / "validate-lessons-delta.py"
    spec = importlib.util.spec_from_file_location("validate_lessons_delta", str(script_path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.validate_lessons


def _parse_json_payload(path: Path, label: str) -> dict[str, Any]:
    """Parse and validate JSON payload. Returns FAIL envelope on malformed input."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return {"_malformed": True, "error": f"Cannot read {label}: {exc}"}
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        return {"_malformed": True, "error": f"Malformed JSON in {label}: {exc}"}
    if not isinstance(payload, dict):
        return {"_malformed": True, "error": f"{label} must be a JSON object, got {type(payload).__name__}"}
    return payload


def _deduplicate_constraints(existing_text: str, candidates: list[dict[str, str]]) -> tuple[str, list[str]]:
    """Produce the file content after deduplication. Returns (new_content, added_rules)."""
    existing_rules: set[str] = set()
    for line in existing_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("- ") and ("ALWAYS" in stripped or "NEVER" in stripped):
            existing_rules.add(stripped)

    tail = existing_text.rstrip()
    added: list[str] = []
    for candidate in candidates:
        rule = str(candidate.get("rule", "")).strip()
        if not rule:
            continue
        bullet = f"- {rule}"
        if bullet not in existing_rules:
            existing_rules.add(bullet)
            reason = str(candidate.get("reason", "")).strip()
            if tail:
                tail += "\n"
            tail += f"\n{bullet}"
            if reason:
                tail += f"  Reason: {reason}"
            added.append(rule)

    if not tail.endswith("\n"):
        tail += "\n"
    return tail, added


def cmd_readback(args: argparse.Namespace) -> dict[str, Any]:
    target = Path(args.target_root).resolve()
    if not target.is_dir():
        return {
            "status": "FAIL",
            "stateHash": "",
            "evidence": [],
            "blockingIssues": [f"Target root not found: {target}"],
        }
    lessons = target / "lessons.md"
    constraints = target / ".claude" / "rules" / "constraints.md"
    if not lessons.exists():
        return {
            "status": "FAIL",
            "stateHash": "",
            "evidence": [],
            "blockingIssues": [f"lessons.md not found at {lessons}"],
        }
    if lessons.stat().st_size == 0:
        return {
            "status": "FAIL",
            "stateHash": "",
            "evidence": [],
            "blockingIssues": [f"lessons.md is empty at {lessons}"],
        }
    evidence_refs = [str(lessons), str(constraints)]
    return {
        "status": "PASS",
        "stateHash": state_hash(lessons, constraints),
        "evidence": evidence_refs,
        "blockingIssues": [],
    }


def cmd_validate_delta(args: argparse.Namespace) -> dict[str, Any]:
    target = Path(args.target_root).resolve()
    lessons = target / "lessons.md"
    constraints = target / ".claude" / "rules" / "constraints.md"
    delta_file = Path(args.delta_file).resolve()
    run_id = args.run_id or ""
    run_root = Path(args.run_root).resolve()
    failure_kind = args.failure_kind

    if not delta_file.exists():
        return {
            "status": "FAIL",
            "stateHash": state_hash(lessons, constraints),
            "deltaHash": "",
            "evidence": [],
            "blockingIssues": [f"Delta file not found: {delta_file}"],
        }

    current_hash = state_hash(lessons, constraints)
    expected_hash = args.state_hash or ""
    if expected_hash and current_hash != expected_hash:
        return {
            "status": "FAIL",
            "stateHash": current_hash,
            "deltaHash": "",
            "evidence": [],
            "blockingIssues": [f"State hash drift: expected {expected_hash} but current is {current_hash}. Baseline changed."],
        }

    # Parse and validate delta payload
    parsed = _parse_json_payload(delta_file, "delta payload")
    if parsed.get("_malformed"):
        return {
            "status": "FAIL",
            "stateHash": current_hash,
            "deltaHash": "",
            "evidence": [],
            "blockingIssues": [parsed["error"]],
        }

    delta_entries: list[dict[str, str]] = parsed.get("delta", [])
    if not isinstance(delta_entries, list):
        return {
            "status": "FAIL",
            "stateHash": current_hash,
            "deltaHash": "",
            "evidence": [],
            "blockingIssues": ["delta field must be an array"],
        }

    # Compute deltaHash from structured entries
    delta_text = json.dumps(delta_entries, sort_keys=True, ensure_ascii=False)
    delta_hash = sha256_for_content(delta_text)

    blocking_issues: list[str] = []
    evidence: list[str] = [str(delta_file)]

    # Materialize S6 markdown delta and user progress summary
    s6_delta_dir = run_root / "outputs" / "stages"
    s6_delta_dir.mkdir(parents=True, exist_ok=True)
    s6_delta_path = s6_delta_dir / "s6-lessons-delta.md"

    md_body = _delta_to_markdown(delta_entries, run_id, failure_kind)
    s6_delta_path.write_text(md_body, encoding="utf-8")

    progress_dir = run_root / "outputs" / "progress"
    progress_dir.mkdir(parents=True, exist_ok=True)
    progress_path = progress_dir / "user-progress.md"

    progress_body = _user_progress_summary(delta_entries, run_id)
    progress_path.write_text(progress_body, encoding="utf-8")

    # Invoke the existing validator
    validate_lessons = _import_validator()
    result = validate_lessons(run_root, run_id, failure_kind)
    blocking_issues.extend(result.get("errors", []))

    evidence.append(str(s6_delta_path))
    evidence.append(str(progress_path))

    # Persist validation JSON evidence under RUN_ROOT
    evidence_payload = {
        "status": "PASS" if not blocking_issues else "FAIL",
        "stateHash": current_hash,
        "deltaHash": delta_hash,
        "evidence": list(evidence),
        "blockingIssues": list(blocking_issues),
    }
    evidence_path = s6_delta_dir / "delta-validation.json"
    evidence_path.write_text(json.dumps(evidence_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    evidence.append(str(evidence_path))

    return {
        "status": "PASS" if not blocking_issues else "FAIL",
        "stateHash": current_hash,
        "deltaHash": delta_hash,
        "evidence": evidence,
        "blockingIssues": blocking_issues,
    }


def cmd_append_lessons(args: argparse.Namespace) -> dict[str, Any]:
    target = Path(args.target_root).resolve()
    lessons = target / "lessons.md"
    constraints = target / ".claude" / "rules" / "constraints.md"
    delta_file = Path(args.delta_file).resolve()
    run_id = args.run_id or ""
    expected_delta_hash = args.delta_hash

    if not delta_file.exists():
        return {
            "status": "FAIL",
            "baselineHash": "",
            "stateHash": state_hash(lessons, constraints),
            "deltaHash": "",
            "evidence": [],
            "blockingIssues": [f"Delta file not found: {delta_file}"],
        }

    # Parse and validate delta payload
    parsed = _parse_json_payload(delta_file, "delta payload")
    if parsed.get("_malformed"):
        return {
            "status": "FAIL",
            "baselineHash": "",
            "stateHash": state_hash(lessons, constraints),
            "deltaHash": "",
            "evidence": [],
            "blockingIssues": [parsed["error"]],
        }

    delta_entries: list[dict[str, str]] = parsed.get("delta", [])
    if not isinstance(delta_entries, list) or not delta_entries:
        return {
            "status": "FAIL",
            "baselineHash": "",
            "stateHash": state_hash(lessons, constraints),
            "deltaHash": "",
            "evidence": [],
            "blockingIssues": ["Delta payload has no valid entries."],
        }

    # Compute deltaHash from structured entries
    delta_text = json.dumps(delta_entries, sort_keys=True, ensure_ascii=False)
    delta_hash = sha256_for_content(delta_text)

    # Reject delta hash mismatch before any write
    if delta_hash != expected_delta_hash:
        return {
            "status": "FAIL",
            "baselineHash": "",
            "stateHash": state_hash(lessons, constraints),
            "deltaHash": delta_hash,
            "evidence": [],
            "blockingIssues": [f"Delta hash mismatch: computed {delta_hash}, expected {expected_delta_hash}. Re-run validate-delta."],
        }

    baseline_hash = state_hash(lessons, constraints)
    existing = lessons.read_text(encoding="utf-8") if lessons.exists() else ""

    # Idempotent: already applied (same runId + same deltaHash, regardless of baselineHash drift)
    idempotent_pattern = re.compile(rf"<!-- WFPM-ITERATE runId={re.escape(run_id)} .*?deltaHash={re.escape(delta_hash)} -->")
    idempotent_match = idempotent_pattern.search(existing)
    if idempotent_match:
        marker_text = idempotent_match.group(0)
        stored_bh = baseline_hash
        bh_match = re.search(r'baselineHash=([^\s]+)', marker_text)
        if bh_match:
            stored_bh = bh_match.group(1)
        return {
            "status": "PASS",
            "baselineHash": stored_bh,
            "stateHash": state_hash(lessons, constraints),
            "deltaHash": delta_hash,
            "evidence": [str(lessons.resolve())],
            "blockingIssues": [],
            "receipt": {"runId": run_id, "idempotent": True, "reason": "Mark already present; append already applied."},
        }

    # Baseline drift check (only after confirming no idempotent marker)
    expected_hash = args.state_hash or ""
    if expected_hash and baseline_hash != expected_hash:
        return {
            "status": "FAIL",
            "baselineHash": baseline_hash,
            "stateHash": baseline_hash,
            "deltaHash": delta_hash,
            "evidence": [],
            "blockingIssues": [f"Baseline drift before append: expected {expected_hash}, got {baseline_hash}. Re-run readback."],
        }

    # Reject same runId with different delta content
    run_mark_pattern = re.compile(rf"<!-- WFPM-ITERATE runId={re.escape(run_id)} ")
    if run_mark_pattern.search(existing):
        return {
            "status": "FAIL",
            "baselineHash": baseline_hash,
            "stateHash": baseline_hash,
            "deltaHash": delta_hash,
            "evidence": [],
            "blockingIssues": [f"Idempotency conflict: runId {run_id} already has a different delta applied."],
        }

    body = _append_delta_body(delta_entries)
    if not body.strip():
        return {
            "status": "FAIL",
            "baselineHash": baseline_hash,
            "stateHash": baseline_hash,
            "deltaHash": delta_hash,
            "evidence": [],
            "blockingIssues": ["Rendered delta body is empty."],
        }

    ensure_parent(lessons)
    mark = f"\n<!-- WFPM-ITERATE runId={run_id} baselineHash={baseline_hash} deltaHash={delta_hash} -->\n"
    lessons.write_text(existing + mark + body, encoding="utf-8")
    post_write_hash = state_hash(lessons, constraints)
    return {
        "status": "PASS",
        "baselineHash": baseline_hash,
        "stateHash": post_write_hash,
        "deltaHash": delta_hash,
        "evidence": [str(lessons.resolve())],
        "blockingIssues": [],
        "receipt": {"runId": run_id, "idempotent": False, "appendedBytes": len(body.encode("utf-8"))},
    }


def cmd_apply_constraints(args: argparse.Namespace) -> dict[str, Any]:
    target = Path(args.target_root).resolve()
    lessons = target / "lessons.md"
    constraints = target / ".claude" / "rules" / "constraints.md"
    proposal_file = Path(args.proposal_file).resolve()
    run_id = args.run_id or ""

    if not proposal_file.exists():
        return {
            "status": "FAIL",
            "baselineHash": "",
            "stateHash": state_hash(lessons, constraints),
            "proposalHash": "",
            "evidence": [],
            "blockingIssues": [f"Proposal file not found: {proposal_file}"],
        }

    # Parse and validate proposal payload (need proposal_hash before idempotent check)
    parsed = _parse_json_payload(proposal_file, "proposal payload")
    if parsed.get("_malformed"):
        return {
            "status": "FAIL",
            "baselineHash": "",
            "stateHash": state_hash(lessons, constraints),
            "proposalHash": "",
            "evidence": [],
            "blockingIssues": [parsed["error"]],
        }

    candidates: list[dict[str, str]] = parsed.get("approvedCandidates", [])
    if not isinstance(candidates, list) or not candidates:
        return {
            "status": "FAIL",
            "baselineHash": "",
            "stateHash": state_hash(lessons, constraints),
            "proposalHash": "",
            "evidence": [],
            "blockingIssues": ["Proposal payload has no approvedCandidates to apply."],
        }

    # Compute proposalHash from approved candidates
    proposal_text = json.dumps(candidates, sort_keys=True, ensure_ascii=False)
    proposal_hash = sha256_for_content(proposal_text)

    baseline_hash = state_hash(lessons, constraints)
    existing_text = constraints.read_text(encoding="utf-8") if constraints.exists() else ""

    # Idempotent check BEFORE baseline drift
    idempotent_pattern = re.compile(rf"<!-- WFPM-ITERATE-CONSTRAINTS runId={re.escape(run_id)} .*?proposalHash={re.escape(proposal_hash)} -->")
    idempotent_match = idempotent_pattern.search(existing_text)
    if idempotent_match:
        marker_text = idempotent_match.group(0)
        stored_bh = baseline_hash
        bh_match = re.search(r'baselineHash=([^\s]+)', marker_text)
        if bh_match:
            stored_bh = bh_match.group(1)
        return {
            "status": "PASS",
            "baselineHash": stored_bh,
            "stateHash": state_hash(lessons, constraints),
            "proposalHash": proposal_hash,
            "evidence": [str(constraints.resolve())],
            "blockingIssues": [],
            "receipt": {"runId": run_id, "idempotent": True, "reason": "Mark already present; constraints already applied."},
        }

    # Baseline drift check
    expected_hash = args.state_hash or ""
    if expected_hash and baseline_hash != expected_hash:
        return {
            "status": "FAIL",
            "baselineHash": baseline_hash,
            "stateHash": baseline_hash,
            "proposalHash": proposal_hash,
            "evidence": [],
            "blockingIssues": [f"Baseline drift before constraints apply: expected {expected_hash}, got {baseline_hash}. Re-run readback."],
        }

    # Reject same runId with different proposal
    run_mark_pattern = re.compile(rf"<!-- WFPM-ITERATE-CONSTRAINTS runId={re.escape(run_id)} ")
    if run_mark_pattern.search(existing_text):
        return {
            "status": "FAIL",
            "baselineHash": baseline_hash,
            "stateHash": baseline_hash,
            "proposalHash": proposal_hash,
            "evidence": [],
            "blockingIssues": [f"Idempotency conflict: runId {run_id} already has a different proposal applied."],
        }

    new_content, added_rules = _deduplicate_constraints(existing_text, candidates)
    if not added_rules:
        return {
            "status": "PASS",
            "baselineHash": baseline_hash,
            "stateHash": baseline_hash,
            "proposalHash": proposal_hash,
            "evidence": [str(constraints.resolve())],
            "blockingIssues": [],
            "receipt": {"runId": run_id, "idempotent": True, "reason": "All candidates already present; nothing added."},
        }

    ensure_parent(constraints)
    mark = f"<!-- WFPM-ITERATE-CONSTRAINTS runId={run_id} baselineHash={baseline_hash} proposalHash={proposal_hash} -->\n"
    constraints.write_text(mark + new_content, encoding="utf-8")
    post_write_hash = state_hash(lessons, constraints)
    return {
        "status": "PASS",
        "baselineHash": baseline_hash,
        "stateHash": post_write_hash,
        "proposalHash": proposal_hash,
        "evidence": [str(constraints.resolve())],
        "blockingIssues": [],
        "receipt": {"runId": run_id, "idempotent": False, "addedRules": added_rules},
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build WorkflowProgram Native iterate evidence")
    subparsers = parser.add_subparsers(dest="stage", required=True)

    rb = subparsers.add_parser("readback")
    rb.add_argument("--target-root", required=True)
    rb.add_argument("--run-id", default="")
    rb.add_argument("--json", action="store_true")

    vd = subparsers.add_parser("validate-delta")
    vd.add_argument("--target-root", required=True)
    vd.add_argument("--state-hash", default="")
    vd.add_argument("--delta-file", required=True)
    vd.add_argument("--run-id", default="")
    vd.add_argument("--run-root", required=True)
    vd.add_argument("--failure-kind", required=True)
    vd.add_argument("--json", action="store_true")

    al = subparsers.add_parser("append-lessons")
    al.add_argument("--target-root", required=True)
    al.add_argument("--delta-file", required=True)
    al.add_argument("--delta-hash", required=True)
    al.add_argument("--state-hash", default="")
    al.add_argument("--run-id", required=True)
    al.add_argument("--json", action="store_true")

    ac = subparsers.add_parser("apply-constraints")
    ac.add_argument("--target-root", required=True)
    ac.add_argument("--proposal-file", required=True)
    ac.add_argument("--state-hash", default="")
    ac.add_argument("--run-id", required=True)
    ac.add_argument("--json", action="store_true")

    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.stage == "readback":
            payload = cmd_readback(args)
        elif args.stage == "validate-delta":
            payload = cmd_validate_delta(args)
        elif args.stage == "append-lessons":
            payload = cmd_append_lessons(args)
        elif args.stage == "apply-constraints":
            payload = cmd_apply_constraints(args)
        else:
            raise ValueError(f"Unknown stage: {args.stage}")
    except Exception as exc:
        payload = {
            "status": "FAIL",
            "baselineHash": "",
            "stateHash": "",
            "deltaHash": "",
            "evidence": [],
            "blockingIssues": [str(exc)],
        }

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"{payload['status']}: {payload.get('stateHash', '')}")
        for item in payload.get("blockingIssues", []):
            print(f"  BLOCKED: {item}")

    return 0 if payload["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
