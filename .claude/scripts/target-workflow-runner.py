#!/usr/bin/env python3
"""Execute a generated target workflow graph under managed-runtime control."""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from lib.io_utils import write_json
from lib.yaml_utils import load_yaml_mapping


TERMINALS = {"abort", "end", "done", "complete", "stop", "finish", "success", "failure"}
AUTO_EXECUTOR_PROVIDERS = {"fixture_host", "command_adapter"}
MANUAL_EXECUTOR_PROVIDERS = {"current_agent", "manual"}
SUPPORTED_EXECUTOR_PROVIDERS = AUTO_EXECUTOR_PROVIDERS | MANUAL_EXECUTOR_PROVIDERS
PROVIDER_ALIASES = {
    "current-agent": "current_agent",
    "current_agent_manual": "current_agent",
}
DEFAULT_EXECUTOR_POLICY = {
    "default_provider": "current_agent",
    "allowed_providers": ["fixture_host", "command_adapter", "current_agent", "manual"],
    "evidence_dir": "outputs/stages/executor-evidence",
    "unsupported_provider_verdict": "FAIL",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a generated target workflow graph")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="Run target workflow graph")
    run.add_argument("--spec", required=True)
    run.add_argument("--run-root", required=True)
    run.add_argument("--target-root", required=True)
    run.add_argument("--plugin-root", default="")
    run.add_argument("--request", default="")
    run.add_argument("--intent", default="develop")
    run.add_argument("--entry-skill", required=True)
    run.add_argument("--runtime-provider", default="")
    run.add_argument("--provider-command", default="")
    run.add_argument("--claude-bin", default="", help="Deprecated no-op; target runtime does not invoke Claude CLI")
    run.add_argument("--auto-approve", action="store_true")
    run.add_argument("--approval-status", default="")
    run.add_argument("--json", action="store_true")

    status = sub.add_parser("status", help="Read target workflow status")
    status.add_argument("--run-root", required=True)
    status.add_argument("--json", action="store_true")
    return parser.parse_args()


def append_event(run_root: Path, event_type: str, **fields: Any) -> None:
    path = run_root / "target-events.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"ts": utc_now(), "event": event_type, **fields}
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_rel(path_text: str) -> str:
    cleaned = path_text.strip().replace("\\", "/")
    while cleaned.startswith("./"):
        cleaned = cleaned[2:]
    return cleaned


def is_logical_ref(ref: str) -> bool:
    text = ref.strip()
    if not text or text.startswith("$"):
        return True
    if "/" not in text and not text.startswith("."):
        return True
    return False


def existing_file_snapshot(target_root: Path, patterns: List[str]) -> Dict[str, str]:
    snapshot: Dict[str, str] = {}
    if not patterns or not target_root.exists():
        return snapshot
    for path in target_root.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(target_root).as_posix()
        if any(fnmatch.fnmatch(rel, pattern) for pattern in patterns):
            snapshot[rel] = sha256_file(path)
    return snapshot


def immutable_changes(before: Dict[str, str], after: Dict[str, str]) -> List[str]:
    changes: List[str] = []
    for rel, digest in sorted(before.items()):
        if rel not in after:
            changes.append(f"deleted:{rel}")
        elif after[rel] != digest:
            changes.append(f"modified:{rel}")
    for rel in sorted(set(after) - set(before)):
        changes.append(f"created:{rel}")
    return changes


def collect_registry(spec: Dict[str, Any]) -> Dict[str, Dict[str, str]]:
    registry = spec.get("registry", {})
    result: Dict[str, Dict[str, str]] = {}
    if not isinstance(registry, dict):
        return result
    for section, kind in (("commands", "command"), ("skills", "skill"), ("agents", "agent"), ("runtime_assets", "runtime_asset")):
        items = registry.get(section, [])
        if not isinstance(items, list):
            continue
        for raw in items:
            if not isinstance(raw, dict):
                continue
            name = str(raw.get("name", "")).strip()
            file_path = str(raw.get("file", "")).strip()
            if name:
                result[name] = {"kind": kind, "file": file_path}
    return result


def resolve_owner(owner: str, registry: Dict[str, Dict[str, str]], target_root: Path) -> Tuple[bool, Dict[str, str]]:
    owner = owner.strip()
    if owner.startswith("script:"):
        rel = safe_rel(owner[len("script:"):])
        path = target_root / rel
        return path.exists(), {"kind": "script", "file": rel, "name": owner}
    if owner in registry:
        record = dict(registry[owner])
        rel = safe_rel(record.get("file", ""))
        if rel:
            return (target_root / rel).exists(), {"name": owner, **record}
        return True, {"name": owner, **record}
    fallback_paths = [
        (f".claude/skills/{owner}/SKILL.md", "skill"),
        (f".claude/agents/{owner}.md", "agent"),
        (f".claude/commands/{owner}.md", "command"),
    ]
    for rel, kind in fallback_paths:
        if (target_root / rel).exists():
            return True, {"name": owner, "kind": kind, "file": rel}
    return False, {"name": owner, "kind": "unknown", "file": ""}


def materialize_output(output_root: Path, run_root: Path, node: Dict[str, Any], output_ref: str, owner: Dict[str, str], attempt: int) -> Dict[str, Any]:
    rel = safe_rel(output_ref)
    path = output_root / rel
    if output_ref.endswith("/"):
        path.mkdir(parents=True, exist_ok=True)
        marker = path / ".workflowprogram-output"
        marker.write_text(f"node={node['id']}\nowner={owner.get('name', '')}\n", encoding="utf-8", newline="\n")
        digest: Optional[str] = sha256_file(marker)
        kind = "dir"
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        if rel.endswith(".json"):
            path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "node_id": node["id"],
                        "owner": owner.get("name", ""),
                        "generated_at": utc_now(),
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
                newline="\n",
            )
        elif rel.endswith((".yaml", ".yml")):
            path.write_text(f"schema_version: 1\nnode_id: {node['id']}\nowner: {owner.get('name', '')}\n", encoding="utf-8", newline="\n")
        elif rel.endswith(".md"):
            path.write_text(f"# {node['id']}\n\nGenerated by `{owner.get('name', '')}`.\n", encoding="utf-8", newline="\n")
        else:
            path.write_text(f"node={node['id']}\nowner={owner.get('name', '')}\n", encoding="utf-8", newline="\n")
        digest = sha256_file(path)
        kind = "file"
    return {
        "path": rel,
        "kind": kind,
        "node_id": node["id"],
        "owner": owner.get("name", ""),
        "owner_kind": owner.get("kind", ""),
        "attempt": attempt,
        "sha256": digest,
        "generated_at": utc_now(),
        "producer": "target-workflow-runner.py",
    }


def load_json_object(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def executor_policy(spec: Dict[str, Any]) -> Dict[str, Any]:
    policy = dict(DEFAULT_EXECUTOR_POLICY)
    declared = spec.get("target_executor_policy", {})
    if isinstance(declared, dict):
        policy.update(declared)
    allowed = policy.get("allowed_providers", DEFAULT_EXECUTOR_POLICY["allowed_providers"])
    if not isinstance(allowed, list) or not allowed:
        allowed = DEFAULT_EXECUTOR_POLICY["allowed_providers"]
    policy["allowed_providers"] = [normalize_provider_name(str(item)) for item in allowed if str(item).strip()]
    policy["default_provider"] = normalize_provider_name(str(policy.get("default_provider", "current_agent")))
    policy["evidence_dir"] = safe_rel(str(policy.get("evidence_dir", DEFAULT_EXECUTOR_POLICY["evidence_dir"])))
    return policy


def normalize_provider_name(provider: str) -> str:
    value = provider.strip()
    return PROVIDER_ALIASES.get(value, value)


def resolve_executor_provider(args: argparse.Namespace, spec: Dict[str, Any]) -> Tuple[str, str]:
    policy = executor_policy(spec)
    raw_provider = str(args.runtime_provider or os.environ.get("WORKFLOWPROGRAM_TARGET_EXECUTOR_PROVIDER", "")).strip()
    provider = normalize_provider_name(raw_provider or str(policy.get("default_provider", "current_agent")))
    if provider not in SUPPORTED_EXECUTOR_PROVIDERS:
        return provider, f"unsupported executor provider: {provider or '<empty>'}"
    allowed = set(policy.get("allowed_providers", []))
    if allowed and provider not in allowed:
        return provider, f"executor provider not allowed by target_executor_policy: {provider}"
    return provider, ""


def executor_evidence_path(run_root: Path, spec: Dict[str, Any], node_id: str) -> Path:
    policy = executor_policy(spec)
    return run_root / safe_rel(str(policy.get("evidence_dir", DEFAULT_EXECUTOR_POLICY["evidence_dir"]))) / f"{safe_rel(node_id)}.json"


def normalize_evidence_output(raw_output: Any) -> Dict[str, str]:
    if isinstance(raw_output, dict):
        return {
            "path": safe_rel(str(raw_output.get("path", ""))),
            "sha256": str(raw_output.get("sha256", "")).strip(),
        }
    return {"path": safe_rel(str(raw_output)), "sha256": ""}


def validate_manual_executor_evidence(
    run_root: Path,
    output_root: Path,
    spec: Dict[str, Any],
    node: Dict[str, Any],
    owner: Dict[str, str],
    provider: str,
    attempt: int,
) -> Tuple[bool, str, List[Dict[str, Any]], str]:
    """Validate evidence produced by the current ClaudeCode session or a manual operator."""

    node_id = str(node.get("id", "")).strip()
    evidence_path = executor_evidence_path(run_root, spec, node_id)
    evidence = load_json_object(evidence_path)
    if not evidence:
        return False, f"manual/current-agent executor evidence missing: {evidence_path}", [], evidence_path.relative_to(run_root).as_posix()
    errors: List[str] = []
    if int(evidence.get("schema_version", 0) or 0) != 1:
        errors.append("schema_version must be 1")
    if str(evidence.get("node_id", "")).strip() != node_id:
        errors.append("node_id mismatch")
    evidence_provider = normalize_provider_name(str(evidence.get("provider", provider)))
    if evidence_provider != provider:
        errors.append(f"provider mismatch: expected {provider}, got {evidence_provider}")
    if str(evidence.get("status", "")).strip() != "PASS":
        errors.append("status must be PASS")
    for field in ("operator", "started_at", "completed_at"):
        if not str(evidence.get(field, "")).strip():
            errors.append(f"{field} is required")
    input_refs = evidence.get("input_refs", [])
    output_refs = evidence.get("output_refs", [])
    if not isinstance(input_refs, list):
        errors.append("input_refs must be a list")
        input_refs = []
    if not isinstance(output_refs, list):
        errors.append("output_refs must be a list")
        output_refs = []
    declared_inputs = [str(item).strip() for item in node.get("input_refs", []) if str(item).strip()]
    declared_outputs = [safe_rel(str(item)) for item in node.get("output_refs", []) if str(item).strip() and not is_logical_ref(str(item))]
    if [str(item).strip() for item in input_refs if str(item).strip()] != declared_inputs:
        errors.append("input_refs must exactly match workflow_graph node input_refs")
    if [safe_rel(str(item)) for item in output_refs if str(item).strip() and not is_logical_ref(str(item))] != declared_outputs:
        errors.append("output_refs must exactly match workflow_graph node output_refs")
    raw_outputs = evidence.get("outputs", [])
    if not isinstance(raw_outputs, list) or not raw_outputs:
        errors.append("outputs must be a non-empty list")
        raw_outputs = []
    output_records = [normalize_evidence_output(item) for item in raw_outputs]
    output_paths = {item["path"] for item in output_records if item.get("path")}
    missing_declared = sorted(path for path in declared_outputs if path not in output_paths)
    if missing_declared:
        errors.append(f"outputs missing declared refs: {missing_declared}")
    provenance: List[Dict[str, Any]] = []
    for output in output_records:
        rel = output.get("path", "")
        if not rel:
            errors.append("outputs[].path is required")
            continue
        if rel not in declared_outputs:
            errors.append(f"outputs[].path is not declared by node output_refs: {rel}")
            continue
        path = output_root / rel
        if not path.exists():
            errors.append(f"declared output file missing: {rel}")
            continue
        digest = sha256_file(path) if path.is_file() else ""
        expected_digest = output.get("sha256", "")
        if expected_digest and digest and digest != expected_digest:
            errors.append(f"output sha256 mismatch: {rel}")
        provenance.append(
            {
                "path": rel,
                "kind": "file" if path.is_file() else "dir",
                "node_id": node_id,
                "owner": owner.get("name", ""),
                "owner_kind": owner.get("kind", ""),
                "attempt": attempt,
                "sha256": digest,
                "generated_at": str(evidence.get("completed_at", "")).strip(),
                "producer": f"target-workflow-runner.py:{provider}",
                "executor_evidence_path": evidence_path.relative_to(run_root).as_posix(),
                "operator": str(evidence.get("operator", "")).strip(),
            }
        )
    if errors:
        return False, "; ".join(errors), [], evidence_path.relative_to(run_root).as_posix()
    return True, f"{provider} executor evidence accepted: {evidence_path}", provenance, evidence_path.relative_to(run_root).as_posix()


def execute_script_owner(target_root: Path, run_root: Path, output_root: Path, owner: Dict[str, str], node: Dict[str, Any], request: str) -> Tuple[bool, str]:
    rel = safe_rel(owner.get("file", ""))
    path = target_root / rel
    completed = subprocess.run(
        [sys.executable, str(path), "--node-id", str(node["id"]), "--request", request],
        cwd=target_root,
        env={
            **dict(os.environ),
            "WORKFLOWPROGRAM_TARGET_ROOT": str(target_root),
            "WORKFLOWPROGRAM_RUN_ROOT": str(run_root),
            "WORKFLOWPROGRAM_OUTPUT_ROOT": str(output_root),
        },
        capture_output=True,
        text=True,
        check=False,
    )
    text = completed.stdout.strip() or completed.stderr.strip()
    return completed.returncode == 0, text


def check_inputs(search_roots: List[Path], node: Dict[str, Any]) -> List[str]:
    missing: List[str] = []
    for raw_ref in node.get("input_refs", []):
        ref = str(raw_ref).strip()
        if is_logical_ref(ref):
            continue
        rel = safe_rel(ref)
        if not any((root / rel).exists() for root in search_roots):
            missing.append(ref)
    return missing


def check_outputs(output_root: Path, node: Dict[str, Any]) -> List[str]:
    missing: List[str] = []
    for raw_ref in node.get("output_refs", []):
        ref = str(raw_ref).strip()
        if is_logical_ref(ref):
            continue
        if not (output_root / safe_rel(ref)).exists():
            missing.append(ref)
    return missing


def target_publish_policy(spec: Dict[str, Any]) -> Dict[str, Any]:
    value = spec.get("target_publish_policy", {})
    return value if isinstance(value, dict) else {}


def target_publish_enabled(policy: Dict[str, Any]) -> bool:
    return bool(policy.get("enabled", False)) and bool(policy.get("run_scoped_outputs_required", False))


def output_base_root(target_root: Path, run_root: Path, spec: Dict[str, Any]) -> Path:
    return run_root if target_publish_enabled(target_publish_policy(spec)) else target_root


def transition_map(graph: Dict[str, Any]) -> Dict[str, str]:
    result: Dict[str, str] = {}
    transitions = graph.get("transitions", [])
    if not isinstance(transitions, list):
        return result
    for raw in transitions:
        if not isinstance(raw, dict):
            continue
        source = str(raw.get("from", "")).strip()
        target = str(raw.get("to", "")).strip()
        if source and target and source not in result:
            result[source] = target
    return result


def ordered_nodes(graph: Dict[str, Any], entry_skill: str) -> List[Dict[str, Any]]:
    nodes = [node for node in graph.get("nodes", []) if isinstance(node, dict)]
    node_map = {str(node.get("id", "")).strip(): node for node in nodes}
    entrypoints = graph.get("entrypoints", [])
    entry_node = ""
    if isinstance(entrypoints, list):
        for raw in entrypoints:
            if not isinstance(raw, dict):
                continue
            if str(raw.get("name", "")).strip() == entry_skill:
                entry_node = str(raw.get("node", "")).strip()
                break
        if not entry_node and entrypoints and isinstance(entrypoints[0], dict):
            entry_node = str(entrypoints[0].get("node", "")).strip()
    if not entry_node and nodes:
        entry_node = str(nodes[0].get("id", "")).strip()
    transitions = transition_map(graph)
    if not transitions:
        if entry_node in node_map:
            start_index = next((idx for idx, node in enumerate(nodes) if str(node.get("id", "")).strip() == entry_node), 0)
            return nodes[start_index:]
        return nodes
    result: List[Dict[str, Any]] = []
    current = entry_node
    seen: set[str] = set()
    while current and current not in TERMINALS and current not in seen:
        seen.add(current)
        node = node_map.get(current)
        if node is None:
            break
        result.append(node)
        current = transitions.get(current, "")
    return result


def run_graph(args: argparse.Namespace) -> Dict[str, Any]:
    spec_path = Path(args.spec).resolve()
    run_root = Path(args.run_root).resolve()
    target_root = Path(args.target_root).resolve()
    run_root.mkdir(parents=True, exist_ok=True)
    (run_root / "outputs" / "stages").mkdir(parents=True, exist_ok=True)

    spec = load_yaml_mapping(spec_path)
    graph = spec.get("workflow_graph", {})
    if not isinstance(graph, dict) or not graph.get("nodes"):
        raise RuntimeError("workflow_graph.nodes is required for target managed runtime")
    policy = spec.get("target_runtime_policy", {})
    if not isinstance(policy, dict):
        policy = {}
    max_retries = policy.get("max_retries_per_node", 0)
    if not isinstance(max_retries, int) or max_retries < 0:
        max_retries = 0
    immutable_patterns = [safe_rel(str(item)) for item in policy.get("immutable_during_run", []) if str(item).strip()] if isinstance(policy.get("immutable_during_run", []), list) else []
    provider, provider_error = resolve_executor_provider(args, spec)
    if provider_error:
        raise RuntimeError(provider_error)
    output_root = output_base_root(target_root, run_root, spec)
    input_search_roots = [output_root]
    if target_root not in input_search_roots:
        input_search_roots.append(target_root)

    registry = collect_registry(spec)
    node_results: List[Dict[str, Any]] = []
    provenance: List[Dict[str, Any]] = []
    status = "PASS"
    failure_kind = "none"
    failure_reason = ""
    blocked_context: Dict[str, Any] = {}
    manual_finalizer_required = provider in MANUAL_EXECUTOR_PROVIDERS

    append_event(run_root, "TargetRuntimeStarted", status="running", entry_skill=args.entry_skill, provider=provider)
    for node in ordered_nodes(graph, args.entry_skill):
        node_id = str(node.get("id", "")).strip()
        owner_name = str(node.get("owner", "")).strip()
        attempts: List[Dict[str, Any]] = []
        node_status = "FAIL"
        for attempt in range(1, max_retries + 2):
            append_event(run_root, "NodeStarted", node_id=node_id, owner=owner_name, attempt=attempt)
            missing_inputs = check_inputs(input_search_roots, node)
            if missing_inputs:
                attempts.append({"attempt": attempt, "status": "FAIL", "reason": "missing_inputs", "missing_inputs": missing_inputs})
                failure_reason = f"node {node_id} missing inputs: {missing_inputs}"
                break

            owner_ok, owner = resolve_owner(owner_name, registry, target_root)
            if not owner_ok:
                append_event(run_root, "OwnerFailed", node_id=node_id, owner=owner_name, attempt=attempt, reason="owner_not_found")
                attempts.append({"attempt": attempt, "status": "FAIL", "reason": "owner_not_found"})
                failure_reason = f"node {node_id} owner not found: {owner_name}"
                break
            append_event(run_root, "OwnerResolved", node_id=node_id, owner=owner_name, owner_kind=owner.get("kind", ""), attempt=attempt)

            before = existing_file_snapshot(target_root, immutable_patterns)
            executor_evidence_rel = ""
            if provider in MANUAL_EXECUTOR_PROVIDERS:
                owner_success, owner_message, manual_provenance, executor_evidence_rel = validate_manual_executor_evidence(
                    run_root,
                    output_root,
                    spec,
                    node,
                    owner,
                    provider,
                    attempt,
                )
                if owner_success:
                    provenance.extend(manual_provenance)
                    append_event(
                        run_root,
                        "ExecutorEvidenceAccepted",
                        node_id=node_id,
                        provider=provider,
                        evidence_path=executor_evidence_rel,
                        attempt=attempt,
                    )
                else:
                    append_event(
                        run_root,
                        "ExecutorEvidenceRejected",
                        node_id=node_id,
                        provider=provider,
                        evidence_path=executor_evidence_rel,
                        reason=owner_message,
                        attempt=attempt,
                    )
            elif owner.get("kind") == "script":
                owner_success, owner_message = execute_script_owner(target_root, run_root, output_root, owner, node, args.request)
            elif provider in AUTO_EXECUTOR_PROVIDERS:
                owner_success, owner_message = True, "deterministic provider materialized declared outputs"
                for output_ref in node.get("output_refs", []):
                    ref = str(output_ref).strip()
                    if not is_logical_ref(ref):
                        provenance.append(materialize_output(output_root, run_root, node, ref, owner, attempt))
            else:
                owner_success, owner_message = False, f"executor provider is not executable: {provider}"
            after = existing_file_snapshot(target_root, immutable_patterns)
            changes = immutable_changes(before, after)
            missing_outputs = check_outputs(output_root, node)
            if not owner_success:
                if provider in MANUAL_EXECUTOR_PROVIDERS:
                    node_status = "BLOCKED"
                    failure_reason = f"awaiting manual/current-agent executor evidence for node {node_id}: {owner_message}"
                    attempts.append(
                        {
                            "attempt": attempt,
                            "status": "BLOCKED",
                            "reason": "executor_evidence_required",
                            "message": owner_message,
                            "executor_evidence_path": executor_evidence_rel,
                        }
                    )
                    blocked_context = {
                        "phase": "executor_evidence",
                        "node_id": node_id,
                        "owner": owner_name,
                        "owner_kind": owner.get("kind", ""),
                        "attempt": attempt,
                        "reason": owner_message,
                        "executor_evidence_path": executor_evidence_rel,
                        "input_refs": [str(item).strip() for item in node.get("input_refs", []) if str(item).strip()],
                        "output_refs": [str(item).strip() for item in node.get("output_refs", []) if str(item).strip()],
                    }
                    append_event(
                        run_root,
                        "ManualExecutorEvidenceRequired",
                        node_id=node_id,
                        owner=owner_name,
                        provider=provider,
                        evidence_path=executor_evidence_rel,
                        reason=owner_message,
                        attempt=attempt,
                    )
                    break
                attempts.append({"attempt": attempt, "status": "FAIL", "reason": "owner_failed", "message": owner_message})
                failure_reason = owner_message
            elif changes:
                attempts.append({"attempt": attempt, "status": "FAIL", "reason": "immutable_changed", "changes": changes})
                failure_reason = f"node {node_id} modified immutable paths: {changes}"
            elif missing_outputs:
                attempts.append({"attempt": attempt, "status": "FAIL", "reason": "missing_outputs", "missing_outputs": missing_outputs})
                failure_reason = f"node {node_id} missing outputs: {missing_outputs}"
            else:
                node_status = "PASS"
                attempt_record = {"attempt": attempt, "status": "PASS", "message": owner_message}
                if executor_evidence_rel:
                    attempt_record["executor_evidence_path"] = executor_evidence_rel
                attempts.append(attempt_record)
                append_event(run_root, "OwnerCompleted", node_id=node_id, owner=owner_name, attempt=attempt, status="PASS")
                append_event(run_root, "NodeGatePassed", node_id=node_id, gate=str(node.get("gate", "none")).strip() or "none")
                break
            if attempt <= max_retries:
                append_event(run_root, "NodeRetried", node_id=node_id, owner=owner_name, attempt=attempt)

        node_result = {
            "node_id": node_id,
            "owner": owner_name,
            "status": node_status,
            "attempts": attempts,
            "outputs": [safe_rel(str(item)) for item in node.get("output_refs", []) if str(item).strip()],
        }
        if attempts and attempts[-1].get("executor_evidence_path"):
            node_result["executor_evidence_path"] = attempts[-1]["executor_evidence_path"]
            node_result["executor_provider"] = provider
        node_results.append(node_result)
        if node_status != "PASS":
            if node_status == "BLOCKED":
                status = "BLOCKED"
                failure_kind = "none"
                append_event(
                    run_root,
                    "NodeGateBlocked",
                    node_id=node_id,
                    owner=owner_name,
                    reason=failure_reason or "executor_evidence_required",
                )
            else:
                status = "FAIL"
                failure_kind = "implementation"
                if not failure_reason and attempts:
                    failure_reason = str(attempts[-1].get("reason", "node_failed"))
                append_event(run_root, "NodeGateFailed", node_id=node_id, owner=owner_name, reason=failure_reason or "node_failed")
            break

    if status == "PASS" and manual_finalizer_required:
        status = "BLOCKED"
        failure_kind = "none"
        failure_reason = "current-agent/manual executor evidence requires finalizer verification"
        blocked_context = {
            "phase": "finalizer_verification",
            "reason": failure_reason,
        }
        append_event(run_root, "ManualExecutorAwaitingFinalizer", status=status, provider=provider)
    append_event(run_root, "TargetRuntimeCompleted", status=status, failure_kind=failure_kind, reason=failure_reason)
    state = {
        "schema_version": 1,
        "schema_name": "target-workflow-runtime-state",
        "run_id": run_root.name,
        "status": status,
        "failure_kind": failure_kind,
        "failure_reason": failure_reason,
        "target_root": str(target_root),
        "spec": str(spec_path),
        "entry_skill": args.entry_skill,
        "provider": provider,
        "executor_provider": provider,
        "executor_mode": "manual_evidence" if manual_finalizer_required else "automatic",
        "manual_finalizer_required": manual_finalizer_required,
        "node_results_path": "node-results.json",
        "events_path": "target-events.jsonl",
        "artifact_provenance_path": "artifact-provenance.json",
        "updated_at": utc_now(),
    }
    if blocked_context:
        state["blocked_phase"] = blocked_context.get("phase", "")
        state["current_node"] = blocked_context
    write_json(run_root / "node-results.json", {"schema_version": 1, "nodes": node_results})
    write_json(run_root / "artifact-provenance.json", {"schema_version": 1, "artifacts": provenance})
    write_json(run_root / "target-state.json", state)
    summary = {
        "schema_version": 1,
        "status": status,
        "failure_kind": failure_kind,
        "failure_reason": failure_reason,
        "run_root": str(run_root),
        "target_root": str(target_root),
        "output_root": str(output_root),
        "executor_provider": provider,
        "executor_mode": "manual_evidence" if manual_finalizer_required else "automatic",
        "manual_finalizer_required": manual_finalizer_required,
        "node_count": len(node_results),
        "artifact_count": len(provenance),
    }
    if blocked_context:
        summary["blocked_phase"] = blocked_context.get("phase", "")
        summary["current_node"] = blocked_context
    write_json(run_root / "outputs" / "stages" / "target-runtime-summary.json", summary)
    return summary


def write_failure_evidence(args: argparse.Namespace, error: str) -> Dict[str, Any]:
    """Persist a target-runtime failure with the same evidence shape as normal runs."""

    run_root = Path(getattr(args, "run_root", ".")).resolve()
    target_root = Path(getattr(args, "target_root", ".")).resolve()
    spec_path = Path(getattr(args, "spec", "") or ".").resolve()
    failure_kind = "environment" if "executor provider" in error else "implementation"
    run_root.mkdir(parents=True, exist_ok=True)
    (run_root / "outputs" / "stages").mkdir(parents=True, exist_ok=True)
    if not (run_root / "target-events.jsonl").exists():
        append_event(
            run_root,
            "TargetRuntimeStarted",
            status="failed",
            entry_skill=str(getattr(args, "entry_skill", "")),
            provider=str(getattr(args, "runtime_provider", "") or "unknown"),
        )
    append_event(run_root, "TargetRuntimeCompleted", status="FAIL", failure_kind=failure_kind, reason=error)
    write_json(run_root / "node-results.json", {"schema_version": 1, "nodes": []})
    write_json(run_root / "artifact-provenance.json", {"schema_version": 1, "artifacts": []})
    state = {
        "schema_version": 1,
        "schema_name": "target-workflow-runtime-state",
        "run_id": run_root.name,
        "status": "FAIL",
        "failure_kind": failure_kind,
        "failure_reason": error,
        "target_root": str(target_root),
        "spec": str(spec_path),
        "entry_skill": str(getattr(args, "entry_skill", "")),
        "provider": str(getattr(args, "runtime_provider", "") or "unknown"),
        "executor_provider": str(getattr(args, "runtime_provider", "") or "unknown"),
        "executor_mode": "unavailable",
        "manual_finalizer_required": False,
        "node_results_path": "node-results.json",
        "events_path": "target-events.jsonl",
        "artifact_provenance_path": "artifact-provenance.json",
        "updated_at": utc_now(),
    }
    write_json(run_root / "target-state.json", state)
    summary = {
        "schema_version": 1,
        "status": "FAIL",
        "failure_kind": failure_kind,
        "failure_reason": error,
        "run_root": str(run_root),
        "target_root": str(target_root),
        "node_count": 0,
        "artifact_count": 0,
    }
    write_json(run_root / "outputs" / "stages" / "target-runtime-summary.json", summary)
    return summary


def command_status(args: argparse.Namespace) -> int:
    run_root = Path(args.run_root).resolve()
    state_path = run_root / "target-state.json"
    if not state_path.exists():
        print(json.dumps({"status": "FAIL", "error": f"target-state.json not found: {state_path}"}, ensure_ascii=False, indent=2))
        return 1
    payload = json.loads(state_path.read_text(encoding="utf-8"))
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"[{payload.get('status', 'UNKNOWN')}] {state_path}")
    if payload.get("status") == "PASS":
        return 0
    if payload.get("status") == "BLOCKED":
        return 2
    if payload.get("status") == "ENVIRONMENT-SKIP":
        return 3
    return 1


def main() -> int:
    args = parse_args()
    if args.command == "status":
        return command_status(args)
    try:
        summary = run_graph(args)
    except Exception as exc:
        payload = write_failure_evidence(args, str(exc))
        payload["error"] = str(exc)
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(f"Error: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(f"[{summary['status']}] target runtime run_root={summary['run_root']}")
    if summary["status"] == "PASS":
        return 0
    if summary["status"] == "BLOCKED":
        return 2
    if summary["status"] == "ENVIRONMENT-SKIP":
        return 3
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
