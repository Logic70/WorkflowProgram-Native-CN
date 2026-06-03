#!/usr/bin/env python3
"""
根据 workflow-spec.yaml 生成人类可读的 workflow 视图。

这个脚本刻意保持确定性：
- 输入：workflow-spec.yaml
- 输出：workflow-view.md
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

SCRIPT_ROOT = Path(__file__).resolve().parents[1] / ".claude" / "scripts"
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

from lib.io_utils import utc_now
from lib.yaml_utils import load_yaml_mapping


REQUIRED_TOP_KEYS = [
    "meta",
    "stages",
    "intent_flows",
    "agent_refs",
    "skills",
    "registry",
    "constraints",
    "resource_limits",
    "runtime_contract",
    "test_contract",
]


def parse_args() -> argparse.Namespace:
    """解析仓库侧视图生成器的输入输出路径。"""
    parser = argparse.ArgumentParser(description="Generate workflow-view.md from workflow-spec.yaml")
    parser.add_argument("--spec", default="workflow-spec.yaml", help="Path to workflow-spec.yaml")
    parser.add_argument("--out", default="workflow-view.md", help="Path to generated workflow-view.md")
    parser.add_argument("--json", action="store_true", help="Print structured result")
    return parser.parse_args()


def load_spec(path: Path) -> Dict[str, Any]:
    """加载 workflow spec，并要求根节点必须是映射。"""
    return load_yaml_mapping(path)


def ensure_spec_shape(spec: Dict[str, Any]) -> List[str]:
    """收集缺失的顶层键，同时强制 `stages` 为列表形态。"""
    missing = [key for key in REQUIRED_TOP_KEYS if key not in spec]
    stages = spec.get("stages")
    if stages is None or not isinstance(stages, list):
        raise ValueError("workflow-spec.yaml field 'stages' must be a list")
    return missing


def format_value(value: Any) -> str:
    """把 YAML 值渲染成紧凑、适合 Markdown 的展示形式。"""
    if isinstance(value, list):
        return ", ".join(str(item) for item in value) if value else "-"
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)
    if value in (None, ""):
        return "-"
    return str(value)


def render_meta(meta: Dict[str, Any]) -> List[str]:
    """渲染标识工作流身份的顶层元数据。"""
    return [
        "## Meta",
        "",
        f"- name: `{format_value(meta.get('name'))}`",
        f"- version: `{format_value(meta.get('version'))}`",
        f"- target_platform: `{format_value(meta.get('target_platform'))}`",
        f"- source_design: `{format_value(meta.get('source_design'))}`",
        f"- complexity: `{format_value(meta.get('complexity'))}`",
        "",
    ]


def render_stage_flow(stages: List[Dict[str, Any]]) -> List[str]:
    """把声明的阶段顺序渲染成单行 ASCII 流程。"""
    parts = []
    for stage in stages:
        stage_id = str(stage.get("id", "unknown"))
        stage_name = str(stage.get("name", stage_id))
        parts.append(f"{stage_id}({stage_name})")

    flow = " -> ".join(parts) if parts else "(no stages)"
    return [
        "## Stage Flow (ASCII)",
        "",
        f"`{flow}`",
        "",
    ]


def render_intent_flows(spec: Dict[str, Any]) -> List[str]:
    """根据机器可读 flow 模型渲染 intent 到 stage 的映射。"""
    lines: List[str] = ["## Intent Flows", ""]
    intent_flows = spec.get("intent_flows", {})
    if not isinstance(intent_flows, dict) or not intent_flows:
        lines.append("- None")
        lines.append("")
        return lines

    for intent in ("develop", "audit", "iterate", "validate"):
        flow = intent_flows.get(intent, {})
        if not isinstance(flow, dict):
            lines.append(f"- {intent}: invalid")
            continue
        required_slots = flow.get("required_stage_slots", [])
        optional_slots = flow.get("optional_stage_slots", [])
        lines.append(
            f"- {intent}: required=`{format_value(required_slots)}` optional=`{format_value(optional_slots)}`"
        )
    lines.append("")
    return lines


def render_stages(stages: List[Dict[str, Any]]) -> List[str]:
    """渲染详细的阶段配置，供人工审阅。"""
    lines: List[str] = ["## Stage Details", ""]
    for index, stage in enumerate(stages, start=1):
        stage_id = format_value(stage.get("id"))
        stage_name = format_value(stage.get("name"))
        lines.extend(
            [
                f"### {index}. `{stage_id}` · {stage_name}",
                "",
                f"- pattern: `{format_value(stage.get('pattern'))}`",
                f"- agent_ref: `{format_value(stage.get('agent_ref'))}`",
                f"- gate: `{format_value(stage.get('gate'))}`",
                f"- max_retries: `{format_value(stage.get('max_retries'))}`",
                f"- input: `{format_value(stage.get('input'))}`",
                f"- output: `{format_value(stage.get('output'))}`",
                f"- transitions: `on_approve={format_value(stage.get('on_approve'))}, on_reject={format_value(stage.get('on_reject'))}`",
            ]
        )

        if isinstance(stage.get("feedback"), dict):
            lines.append(f"- feedback: `{format_value(stage.get('feedback'))}`")
        if isinstance(stage.get("resources"), dict):
            lines.append(f"- resources: `{format_value(stage.get('resources'))}`")

        steps = stage.get("steps")
        if isinstance(steps, list) and steps:
            # 保持嵌套数组的人类可读性，避免审阅者必须回到原始 YAML。
            lines.append("- steps:")
            for item in steps:
                lines.append(f"  - `{format_value(item)}`")

        actions = stage.get("actions")
        if isinstance(actions, list) and actions:
            lines.append("- actions:")
            for item in actions:
                lines.append(f"  - `{format_value(item)}`")

        lines.append("")
    return lines


def render_refs_and_constraints(spec: Dict[str, Any]) -> List[str]:
    """渲染辅助 registry、约束和 contract 摘要。"""
    lines: List[str] = [
        "## Agent Refs",
        "",
    ]
    agent_refs = spec.get("agent_refs", [])
    if isinstance(agent_refs, list) and agent_refs:
        lines.extend(f"- `{item}`" for item in agent_refs)
    else:
        lines.append("- None")

    lines.extend(["", "## Skills", ""])
    skills = spec.get("skills", [])
    if isinstance(skills, list) and skills:
        for item in skills:
            if isinstance(item, dict):
                lines.append(f"- `{item.get('name', 'unknown')}` (internal={item.get('internal', False)})")
            else:
                lines.append(f"- `{item}`")
    else:
        lines.append("- None")

    registry = spec.get("registry", {})
    commands = registry.get("commands", []) if isinstance(registry, dict) else []
    reg_skills = registry.get("skills", []) if isinstance(registry, dict) else []
    lines.extend(
        [
            "",
            "## Registry Summary",
            "",
            f"- commands: `{len(commands) if isinstance(commands, list) else 0}`",
            f"- skills: `{len(reg_skills) if isinstance(reg_skills, list) else 0}`",
            "",
            "## Constraints",
            "",
        ]
    )

    constraints = spec.get("constraints", {})
    always = constraints.get("always", []) if isinstance(constraints, dict) else []
    never = constraints.get("never", []) if isinstance(constraints, dict) else []
    lines.append("- ALWAYS:")
    if isinstance(always, list) and always:
        lines.extend(f"  - {item}" for item in always)
    else:
        lines.append("  - None")

    lines.append("- NEVER:")
    if isinstance(never, list) and never:
        lines.extend(f"  - {item}" for item in never)
    else:
        lines.append("  - None")

    lines.extend(["", "## Resource Limits", ""])
    resource_limits = spec.get("resource_limits", {})
    if isinstance(resource_limits, dict) and resource_limits:
        for key, value in resource_limits.items():
            lines.append(f"- {key}: `{format_value(value)}`")
    else:
        lines.append("- None")

    lines.extend(["", "## Runtime Contract", ""])
    runtime_contract = spec.get("runtime_contract", {})
    if isinstance(runtime_contract, dict) and runtime_contract:
        for key in ("write_boundaries", "required_evidence", "failure_kinds", "environment_skip"):
            lines.append(f"- {key}: `{format_value(runtime_contract.get(key))}`")
    else:
        lines.append("- None")

    lines.extend(["", "## Test Contract (Judgment Only)", "", "> This section is for test verdict derivation only. Runner semantics remain owned by runtime_contract.", ""])
    test_contract = spec.get("test_contract", {})
    if isinstance(test_contract, dict) and test_contract:
        for section in ("entry", "boundary", "flow", "artifacts", "failure"):
            lines.append(f"- {section}: `{format_value(test_contract.get(section))}`")
    else:
        lines.append("- None")

    lines.append("")
    return lines


def render_view(spec: Dict[str, Any], spec_path: Path, missing_top_keys: List[str]) -> str:
    """根据已校验的 spec 片段组装最终 Markdown 视图。"""
    meta = spec.get("meta", {})
    stages = spec.get("stages", [])
    if not isinstance(meta, dict):
        meta = {}
    if not isinstance(stages, list):
        stages = []

    lines: List[str] = [
        "# Workflow View",
        "",
        "> AUTO-GENERATED FROM workflow-spec.yaml. DO NOT EDIT DIRECTLY.",
        "",
        f"- source: `{spec_path}`",
        f"- generated_at: `{utc_now()}`",
        "",
    ]

    if missing_top_keys:
        # 缺失键只渲染为 warning，而不是直接失败，这样草案编写阶段也能继续使用视图生成器。
        lines.extend(
            [
                "## Schema Warnings",
                "",
                "- Missing top-level keys:",
                *[f"  - `{key}`" for key in missing_top_keys],
                "",
            ]
        )

    lines.extend(render_meta(meta))
    lines.extend(render_stage_flow(stages))
    lines.extend(render_intent_flows(spec))
    lines.extend(render_stages([stage for stage in stages if isinstance(stage, dict)]))
    lines.extend(render_refs_and_constraints(spec))
    return "\n".join(lines)


def main() -> int:
    """生成确定性的 workflow 视图，并报告输出路径。"""
    args = parse_args()
    spec_path = Path(args.spec).resolve()
    out_path = Path(args.out).resolve()
    try:
        spec = load_spec(spec_path)
        missing_top_keys = ensure_spec_shape(spec)
        rendered = render_view(spec, spec_path, missing_top_keys)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(rendered, encoding="utf-8", newline="\n")
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    result = {
        "spec": str(spec_path),
        "out": str(out_path),
    }
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"Generated view: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
