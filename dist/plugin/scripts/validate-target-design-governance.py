#!/usr/bin/env python3
# AUTO-GENERATED FROM .claude/ - DO NOT EDIT DIRECTLY
"""Validate target workflow design-source governance evidence."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List

from lib.diagnostics import DiagnosticCollector
from lib.io_utils import write_json
from lib.target_design_refs import iter_existing_node_design_refs, resolve_existing_run_refs, resolve_target_design_refs
from lib.yaml_utils import try_load_yaml_mapping


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate target design governance evidence")
    parser.add_argument("--run-root", required=True, help="RUN_ROOT that owns outputs/stages evidence")
    parser.add_argument("--spec", default="", help="workflow-spec.yaml path")
    parser.add_argument("--out", default="", help="Optional report output path")
    parser.add_argument("--json", action="store_true", help="Print JSON report")
    return parser.parse_args()


def load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def requirement_ids(path: Path) -> List[str]:
    payload = try_load_yaml_mapping(path)
    raw = payload.get("requirements", []) if isinstance(payload, dict) else []
    if isinstance(raw, dict):
        items = raw.values()
    elif isinstance(raw, list):
        items = raw
    else:
        items = []
    ids: List[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        req_id = str(item.get("id", "")).strip()
        if req_id and req_id not in ids:
            ids.append(req_id)
    return ids


def graph_node_ids(spec: Dict[str, Any]) -> List[str]:
    graph = spec.get("workflow_graph", {}) if isinstance(spec, dict) else {}
    nodes = graph.get("nodes", []) if isinstance(graph, dict) else []
    if not isinstance(nodes, list):
        return []
    return [
        str(node.get("id", "")).strip()
        for node in nodes
        if isinstance(node, dict) and str(node.get("id", "")).strip()
    ]


def acceptance_test_records(path: Path) -> List[Dict[str, Any]]:
    payload = try_load_yaml_mapping(path)
    raw = payload.get("tests", payload.get("acceptance_tests", [])) if isinstance(payload, dict) else []
    return [item for item in raw if isinstance(item, dict)] if isinstance(raw, list) else []


def test_requirement_refs(test: Dict[str, Any]) -> List[str]:
    raw = test.get("requirement_ids", test.get("covers", test.get("requirement", [])))
    if isinstance(raw, str):
        return [raw] if raw.strip() else []
    if isinstance(raw, list):
        return [str(item).strip() for item in raw if str(item).strip()]
    return []


def node_requires_design(node: Dict[str, Any]) -> bool:
    loop_policy = node.get("loop_policy", {})
    return (
        node.get("node_design_required") is True
        or str(node.get("complexity", "")).strip() == "complex"
        or str(node.get("design_intensity", "")).strip() == "detailed"
        or (isinstance(loop_policy, dict) and loop_policy.get("enabled") is True)
    )


def node_has_exemption(node: Dict[str, Any]) -> bool:
    exemption = node.get("node_design_exemption")
    return (
        isinstance(exemption, dict)
        and bool(str(exemption.get("reason", "")).strip())
        and str(exemption.get("accepted_by", "")).strip() in {"user", "design_review"}
    )


def run_node_design_validator(run_root: Path, spec_path: Path, node_id: str, rel_path: str) -> Dict[str, Any]:
    script_path = Path(__file__).resolve().parent / "validate-target-node-design.py"
    cmd = [
        sys.executable,
        str(script_path),
        "--node-design",
        str(run_root / rel_path),
        "--spec",
        str(spec_path),
        "--node-id",
        node_id,
        "--json",
    ]
    completed = subprocess.run(cmd, capture_output=True, text=True, check=False)
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        payload = {
            "status": "FAIL",
            "errors": [completed.stderr.strip() or completed.stdout.strip() or "validate-target-node-design.py returned invalid JSON"],
            "warnings": [],
        }
    if completed.returncode != 0 and payload.get("status") == "PASS":
        payload["status"] = "FAIL"
        payload.setdefault("errors", []).append(f"validate-target-node-design.py exited with code {completed.returncode}")
    return payload if isinstance(payload, dict) else {"status": "FAIL", "errors": ["validate-target-node-design.py returned non-object payload"], "warnings": []}


def validate(run_root: Path, spec_path: Path) -> Dict[str, Any]:
    diagnostics = DiagnosticCollector()
    spec = try_load_yaml_mapping(spec_path)
    resolved = resolve_target_design_refs(spec)
    for error in resolved.errors:
        diagnostics.error(error)
    for warning in resolved.warnings:
        diagnostics.warn(warning)

    refs = resolve_existing_run_refs(run_root, spec)
    for key in ("requirements", "design_overview", "design_detail", "acceptance_tests", "traceability_matrix"):
        rel_path = refs.get(key, resolved.run_refs.get(key, ""))
        if not rel_path:
            if resolved.canonical:
                diagnostics.error(f"missing target design ref: {key}")
            continue
        if not (run_root / rel_path).exists():
            diagnostics.error(f"target design artifact missing: {rel_path}")

    req_path = run_root / refs["requirements"] if "requirements" in refs else None
    trace_path = run_root / refs["traceability_matrix"] if "traceability_matrix" in refs else None
    acceptance_path = run_root / refs["acceptance_tests"] if "acceptance_tests" in refs else None
    req_ids = requirement_ids(req_path) if req_path and req_path.exists() else []
    trace_text = trace_path.read_text(encoding="utf-8") if trace_path and trace_path.exists() else ""
    missing_req_trace = [req_id for req_id in req_ids if req_id not in trace_text]
    if req_ids and missing_req_trace:
        diagnostics.error(f"traceability missing requirements: {missing_req_trace}")
    elif not req_ids and resolved.canonical:
        diagnostics.error("target requirements must include at least one requirement id")

    tests = acceptance_test_records(acceptance_path) if acceptance_path and acceptance_path.exists() else []
    covered_req_ids: set[str] = set()
    malformed_tests: List[str] = []
    for idx, test in enumerate(tests):
        test_id = str(test.get("id", f"index:{idx}")).strip()
        refs_for_test = test_requirement_refs(test)
        if not refs_for_test:
            malformed_tests.append(test_id)
        covered_req_ids.update(refs_for_test)
    if malformed_tests:
        diagnostics.error(f"acceptance tests missing requirement refs: {malformed_tests}")
    missing_req_acceptance = [req_id for req_id in req_ids if req_id not in covered_req_ids]
    if req_ids and missing_req_acceptance:
        diagnostics.error(f"acceptance tests missing requirements: {missing_req_acceptance}")
    if resolved.canonical and not tests:
        diagnostics.error("target acceptance tests must include at least one test")

    node_designs = iter_existing_node_design_refs(run_root, spec)
    graph = spec.get("workflow_graph", {}) if isinstance(spec, dict) else {}
    nodes = graph.get("nodes", []) if isinstance(graph, dict) else []
    missing_node_trace = [node_id for node_id in graph_node_ids(spec) if trace_text and node_id not in trace_text]
    if missing_node_trace and resolved.canonical:
        diagnostics.error(f"traceability missing workflow_graph nodes: {missing_node_trace}")
    missing_node_designs: List[str] = []
    if isinstance(nodes, list):
        for node in nodes:
            if not isinstance(node, dict):
                continue
            node_id = str(node.get("id", "")).strip()
            if node_id and node_requires_design(node) and node_id not in node_designs and not node_has_exemption(node):
                missing_node_designs.append(node_id)
    if missing_node_designs:
        diagnostics.error(f"complex nodes missing node design or exemption: {missing_node_designs}")

    node_design_validation_results: Dict[str, Any] = {}
    for node_id, rel_path in sorted(node_designs.items()):
        payload = run_node_design_validator(run_root, spec_path, node_id, rel_path)
        node_design_validation_results[node_id] = {
            "path": rel_path,
            "status": payload.get("status", "FAIL"),
            "errors": payload.get("errors", []),
            "warnings": payload.get("warnings", []),
        }
        for error in payload.get("errors", []):
            diagnostics.error(f"node design validation failed for {node_id}: {error}")
        for warning in payload.get("warnings", []):
            diagnostics.warn(f"node design validation warning for {node_id}: {warning}")

    payload = diagnostics.payload(
        run_root=str(run_root),
        spec=str(spec_path),
        compatibility_mode=resolved.compatibility_mode,
        refs=refs,
        requirement_ids=req_ids,
        acceptance_test_count=len(tests),
        graph_node_ids=graph_node_ids(spec),
        node_design_ids=sorted(node_designs),
        node_design_validation_results=node_design_validation_results,
    )
    return payload


def main() -> int:
    args = parse_args()
    run_root = Path(args.run_root).resolve()
    spec_path = Path(args.spec).resolve() if args.spec.strip() else run_root / "workflow-spec.yaml"
    payload = validate(run_root, spec_path)
    out_path = Path(args.out).resolve() if args.out.strip() else run_root / "outputs" / "stages" / "target-design-governance-validation.json"
    write_json(out_path, payload)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"[{payload['status']}] target design governance")
        for error in payload["errors"]:
            print(f"[ERROR] {error}")
        for warning in payload["warnings"]:
            print(f"[WARN] {warning}")
    return 0 if payload["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
