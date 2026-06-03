#!/usr/bin/env python3
# AUTO-GENERATED FROM .claude/ - DO NOT EDIT DIRECTLY
"""Validate one target workflow node-design document against workflow-spec.yaml."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

from lib.diagnostics import DiagnosticCollector
from lib.io_utils import write_json
from lib.yaml_utils import try_load_yaml_mapping


REQUIRED_SECTIONS: Dict[str, Sequence[str]] = {
    "node_metadata": ("Node Metadata", "节点元信息"),
    "purpose_boundary": ("Purpose And Boundary", "设计目的与职责边界"),
    "input_contract": ("Input Contract", "输入契约"),
    "output_contract": ("Output Contract And Consumers", "输出契约与消费者"),
    "context_rules": ("Context Read/Write Rules", "上下文读写规则"),
    "execution_plan": ("Internal Execution Plan", "内部执行编排"),
    "calls": ("Agent / Skill / Script / Tool Calls", "Agent", "Skill", "Script", "Tool", "调用关系"),
    "data_fields": ("Data Field Contract", "数据字段契约"),
    "exit_gate": ("Exit Gate", "准出目标"),
    "failure_strategy": ("Failure, Retry, And Degrade Strategy", "失败、重试与降级策略"),
    "verification": ("Verification And Tests", "验证与测试要求"),
    "observability": ("Observability And Debug Artifacts", "观测与调试产物"),
    "safety": ("Safety And Execution Constraints", "安全与执行约束"),
    "open_tasks": ("Open Tasks And Extension Points", "遗留任务与扩展点"),
}

PLACEHOLDER_PATTERN = re.compile(r"\b(TBD|TODO|FIXME|REPLACE_ME)\b|待补|待确认|未定")
STATUS_PATTERN = re.compile(r"\b(FAIL|WARN|BLOCKED|ENVIRONMENT-SKIP|HARD_FAIL)\b|降级|重试|失败")
VERIFICATION_PATTERN = re.compile(r"test|pytest|fixture|verifier|acceptance|evidence|state\.json|events\.jsonl|验证|测试|证据", re.I)
LOOP_ALLOWED_PATTERN = re.compile(r"loop(_policy)?|loop-plan|iteration-summary|循环|迭代", re.I)
LOOP_DISALLOWED_PATTERN = re.compile(r"loop\s+allowed\s*[:：]\s*false|loop\s*[:：]\s*disallowed|循环\s*[:：]\s*不允许|不允许循环", re.I)


Heading = Tuple[int, str, int, int]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate a target node-design Markdown file")
    parser.add_argument("--node-design", required=True, help="Path to target-node-design Markdown")
    parser.add_argument("--spec", required=True, help="Path to workflow-spec.yaml")
    parser.add_argument("--node-id", default="", help="Expected workflow_graph node id")
    parser.add_argument("--out", default="", help="Optional JSON report output path")
    parser.add_argument("--json", action="store_true", help="Print JSON report")
    return parser.parse_args()


def normalize_value(value: str) -> str:
    return value.strip().strip("`").strip().strip('"').strip("'")


def field_value(text: str, names: Sequence[str]) -> str:
    for name in names:
        pattern = re.compile(rf"(?im)^\s*(?:[-*]\s*)?{re.escape(name)}\s*[:：]\s*(.+?)\s*$")
        match = pattern.search(text)
        if match:
            return normalize_value(match.group(1))
    return ""


def headings(text: str) -> List[Heading]:
    items: List[Heading] = []
    for match in re.finditer(r"(?m)^(#{1,6})\s+(.+?)\s*$", text):
        level = len(match.group(1))
        title = normalize_heading(match.group(2))
        items.append((level, title, match.start(), match.end()))
    return items


def normalize_heading(title: str) -> str:
    cleaned = re.sub(r"`([^`]+)`", r"\1", title.strip())
    cleaned = re.sub(r"^\d+[\.\)、)]\s*", "", cleaned)
    return cleaned.strip()


def find_heading(parsed: Sequence[Heading], aliases: Sequence[str]) -> Heading | None:
    lowered_aliases = [alias.lower() for alias in aliases]
    for item in parsed:
        title_lower = item[1].lower()
        if any(alias in title_lower for alias in lowered_aliases):
            return item
    return None


def section_body(text: str, parsed: Sequence[Heading], aliases: Sequence[str]) -> str:
    target = find_heading(parsed, aliases)
    if target is None:
        return ""
    start_idx = parsed.index(target)
    level, _, _, body_start = target
    body_end = len(text)
    for next_level, _, next_start, _ in parsed[start_idx + 1 :]:
        if next_level <= level:
            body_end = next_start
            break
    return text[body_start:body_end].strip()


def workflow_nodes(spec: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    graph = spec.get("workflow_graph", {}) if isinstance(spec, dict) else {}
    nodes = graph.get("nodes", []) if isinstance(graph, dict) else []
    result: Dict[str, Dict[str, Any]] = {}
    if not isinstance(nodes, list):
        return result
    for node in nodes:
        if not isinstance(node, dict):
            continue
        node_id = str(node.get("id", "")).strip()
        if node_id:
            result[node_id] = node
    return result


def list_values(node: Dict[str, Any], key: str) -> List[str]:
    raw = node.get(key, [])
    if isinstance(raw, str):
        return [raw] if raw.strip() else []
    if isinstance(raw, list):
        return [str(item).strip() for item in raw if str(item).strip()]
    return []


def validate(node_design_path: Path, spec_path: Path, expected_node_id: str = "") -> Dict[str, Any]:
    diagnostics = DiagnosticCollector()
    checks: List[str] = []
    if not node_design_path.exists():
        diagnostics.error(f"node design file missing: {node_design_path}")
        return diagnostics.payload(
            node_design=str(node_design_path),
            spec=str(spec_path),
            node_id=expected_node_id,
            checks=checks,
        )
    if not spec_path.exists():
        diagnostics.error(f"workflow spec missing: {spec_path}")
        return diagnostics.payload(
            node_design=str(node_design_path),
            spec=str(spec_path),
            node_id=expected_node_id,
            checks=checks,
        )

    try:
        text = node_design_path.read_text(encoding="utf-8")
    except Exception as exc:
        diagnostics.error(f"cannot read node design file: {exc}")
        text = ""
    spec = try_load_yaml_mapping(spec_path)
    graph_nodes = workflow_nodes(spec)
    parsed_headings = headings(text)

    for key, aliases in REQUIRED_SECTIONS.items():
        if find_heading(parsed_headings, aliases) is None:
            diagnostics.error(f"missing required node-design section: {aliases[0]}")
        else:
            checks.append(f"section:{key}")

    placeholder = PLACEHOLDER_PATTERN.search(text)
    if placeholder:
        diagnostics.error(f"unresolved placeholder found: {placeholder.group(0)}")

    declared_node_id = field_value(text, ("Node ID", "node_id", "Node", "节点 ID", "节点标识"))
    node_id = expected_node_id.strip() or declared_node_id or node_design_path.stem
    if not declared_node_id:
        diagnostics.error("node design must declare Node ID")
    elif declared_node_id != node_id:
        diagnostics.error(f"node design Node ID mismatch: declared={declared_node_id}; expected={node_id}")

    node = graph_nodes.get(node_id, {})
    if not node:
        diagnostics.error(f"node design references unknown workflow_graph node: {node_id}")
    else:
        checks.append("projection:node_id")

    graph_path = f"workflow_graph.nodes[id={node_id}]"
    if graph_path not in text:
        diagnostics.error(f"node design must reference `{graph_path}`")
    else:
        checks.append("projection:graph_path")

    for label, key, names in (
        ("Owner", "owner", ("Owner", "owner", "负责人")),
        ("Template", "template", ("Template", "template", "模板")),
        ("Gate", "gate", ("Gate", "gate", "准出", "审批")),
    ):
        expected = str(node.get(key, "")).strip() if isinstance(node, dict) else ""
        if not expected:
            continue
        declared = field_value(text, names)
        if not declared:
            diagnostics.error(f"node design must declare {label} matching workflow_graph.nodes[{node_id}].{key}")
        elif declared != expected:
            diagnostics.error(f"node design {label} mismatch: declared={declared}; expected={expected}")
        else:
            checks.append(f"projection:{key}")

    for ref_kind, key in (("input", "input_refs"), ("output", "output_refs")):
        for ref in list_values(node, key):
            if ref not in text:
                diagnostics.error(f"node design missing {ref_kind} ref from workflow_graph.nodes[{node_id}].{key}: {ref}")
            else:
                checks.append(f"projection:{key}:{ref}")

    loop_policy = node.get("loop_policy", {}) if isinstance(node, dict) else {}
    if isinstance(loop_policy, dict) and loop_policy.get("enabled") is True:
        if LOOP_DISALLOWED_PATTERN.search(text):
            diagnostics.error("loop-enabled node design must not claim loop execution is disallowed")
        if not LOOP_ALLOWED_PATTERN.search(text):
            diagnostics.error("loop-enabled node design must describe loop_policy or loop evidence")
        else:
            checks.append("projection:loop_policy")

    failure_body = section_body(text, parsed_headings, REQUIRED_SECTIONS["failure_strategy"])
    if not STATUS_PATTERN.search(failure_body):
        diagnostics.error("failure strategy must include explicit FAIL/WARN/BLOCKED/ENVIRONMENT-SKIP or degrade/retry semantics")
    else:
        checks.append("section:failure_strategy_semantics")

    verification_body = section_body(text, parsed_headings, REQUIRED_SECTIONS["verification"])
    if not VERIFICATION_PATTERN.search(verification_body):
        diagnostics.error("verification section must include test, verifier, acceptance, evidence, or runtime-state checks")
    else:
        checks.append("section:verification_semantics")

    return diagnostics.payload(
        node_design=str(node_design_path),
        spec=str(spec_path),
        node_id=node_id,
        checks=checks,
    )


def main() -> int:
    args = parse_args()
    payload = validate(
        Path(args.node_design).resolve(),
        Path(args.spec).resolve(),
        args.node_id,
    )
    if args.out:
        write_json(Path(args.out).resolve(), payload)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"[{payload['status']}] target node design {payload.get('node_id') or '<unknown>'}")
        for error in payload["errors"]:
            print(f"[ERROR] {error}")
        for warning in payload["warnings"]:
            print(f"[WARN] {warning}")
    return 0 if payload["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
