#!/usr/bin/env python3
"""
根据 workflow-spec.yaml 生成便于阅读的 workflow 视图。

该副本放在 .claude/scripts 下，保证 dist/plugin 自包含，
产品入口 wrapper 不依赖仓库专用的 tools/ 脚本。
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List

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
    "generated_runtime_contract",
    "test_contract",
]


def parse_args() -> argparse.Namespace:
    """解析生成 Markdown 视图所需的输入输出路径。"""
    parser = argparse.ArgumentParser(description="Generate workflow-view.md from workflow-spec.yaml")
    parser.add_argument("--spec", default="workflow-spec.yaml", help="Path to workflow-spec.yaml")
    parser.add_argument("--out", default="workflow-view.md", help="Path to generated workflow-view.md")
    parser.add_argument("--json", action="store_true", help="Print structured result")
    return parser.parse_args()


def load_spec(path: Path) -> Dict[str, Any]:
    """加载 workflow spec；若根节点不是映射则直接失败。"""
    return load_yaml_mapping(path)


def ensure_spec_shape(spec: Dict[str, Any]) -> List[str]:
    """返回缺失的顶层键，同时强制 `stages` 必须保持为列表。"""
    missing = [key for key in REQUIRED_TOP_KEYS if key not in spec]
    stages = spec.get("stages")
    if stages is None or not isinstance(stages, list):
        raise ValueError("workflow-spec.yaml field 'stages' must be a list")
    return missing


def format_value(value: Any) -> str:
    """把值渲染成紧凑、适合 Markdown 展示的形式。"""
    if isinstance(value, list):
        return ", ".join(str(item) for item in value) if value else "-"
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)
    if value in (None, ""):
        return "-"
    return str(value)


def render_meta(meta: Dict[str, Any]) -> List[str]:
    """渲染工作流的高层元数据。"""
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
    """用简单的 ASCII 形式渲染阶段顺序概览。"""
    parts: List[str] = []
    for stage in stages:
        stage_id = str(stage.get("id", "unknown"))
        stage_name = str(stage.get("name", stage_id))
        parts.append(f"{stage_id}({stage_name})")
    flow = " -> ".join(parts) if parts else "(no stages)"
    return ["## Stage Flow (ASCII)", "", f"`{flow}`", ""]


def render_intent_flows(spec: Dict[str, Any]) -> List[str]:
    """把机器可读的 intent flow 声明转换成人类可读文本。"""
    lines: List[str] = ["## Intent Flows", ""]
    intent_flows = spec.get("intent_flows", {})
    if not isinstance(intent_flows, dict) or not intent_flows:
        return lines + ["- None", ""]
    for intent in ("develop", "audit", "iterate", "validate"):
        flow = intent_flows.get(intent, {})
        if not isinstance(flow, dict):
            lines.append(f"- {intent}: invalid")
            continue
        lines.append(
            f"- {intent}: required=`{format_value(flow.get('required_stage_slots', []))}` "
            f"optional=`{format_value(flow.get('optional_stage_slots', []))}`"
        )
    lines.append("")
    return lines


def render_workflow_graph(spec: Dict[str, Any]) -> List[str]:
    """渲染目标工作流自身的业务图。

    这里与 WorkflowProgram 自身 S0-S6 控制面分开展示，避免误以为生成的目标
    工作流也必须套用固定阶段模板。
    """

    graph = spec.get("workflow_graph", {})
    lines: List[str] = ["## Target Workflow Graph", ""]
    if not isinstance(graph, dict) or not graph:
        return lines + ["- None", ""]
    entrypoints = graph.get("entrypoints", [])
    nodes = graph.get("nodes", [])
    transitions = graph.get("transitions", [])
    lines.extend(
        [
            f"- schema_version: `{format_value(graph.get('schema_version'))}`",
            f"- templates_used: `{format_value(graph.get('templates_used', []))}`",
            f"- entrypoints: `{len(entrypoints) if isinstance(entrypoints, list) else 0}`",
            f"- nodes: `{len(nodes) if isinstance(nodes, list) else 0}`",
            f"- transitions: `{len(transitions) if isinstance(transitions, list) else 0}`",
            f"- loop_enabled_nodes: `{len([item for item in nodes if isinstance(item, dict) and isinstance(item.get('loop_policy'), dict) and item.get('loop_policy', {}).get('enabled') is True]) if isinstance(nodes, list) else 0}`",
            "",
        ]
    )
    if isinstance(entrypoints, list) and entrypoints:
        lines.append("### Graph Entrypoints")
        lines.append("")
        for item in entrypoints:
            if isinstance(item, dict):
                lines.append(f"- `{format_value(item.get('name'))}` -> `{format_value(item.get('node'))}`")
        lines.append("")
    if isinstance(nodes, list) and nodes:
        lines.append("### Graph Nodes")
        lines.append("")
        for item in nodes:
            if not isinstance(item, dict):
                continue
            lines.append(
                f"- `{format_value(item.get('id'))}` role=`{format_value(item.get('role'))}` "
                f"template=`{format_value(item.get('template'))}` gate=`{format_value(item.get('gate'))}` "
                f"loop=`{format_value(item.get('loop_policy', {}).get('mode')) if isinstance(item.get('loop_policy'), dict) and item.get('loop_policy', {}).get('enabled') is True else 'disabled'}` "
                f"outputs=`{format_value(item.get('output_refs', []))}`"
            )
        lines.append("")
    return lines


def render_stages(stages: List[Dict[str, Any]]) -> List[str]:
    """渲染逐阶段的细节，便于人工检查和审阅。"""
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
            # steps/actions 保持平铺 bullet，避免读者必须回到原始 YAML 才能理解结构。
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
    """渲染辅助 registry 和全局约束。"""
    lines: List[str] = ["## Target Design Source", ""]
    design_refs = spec.get("design_refs", {})
    if isinstance(design_refs, dict) and design_refs:
        lines.append(f"- schema_version: `{format_value(design_refs.get('schema_version'))}`")
        lines.append(f"- naming: `{format_value(design_refs.get('naming'))}`")
        lines.append(f"- design_overview: `{format_value(design_refs.get('design_overview', design_refs.get('design_highlevel')))}`")
        lines.append(f"- design_detail: `{format_value(design_refs.get('design_detail', design_refs.get('design_lowlevel')))}`")
        persistent = design_refs.get("persistent", {})
        lines.append(f"- persistent_source_archive: `{'yes' if isinstance(persistent, dict) and persistent else 'no'}`")
    else:
        lines.append("- None")
    lines.extend(["", "## Agent Refs", ""])
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
    agents = registry.get("agents", []) if isinstance(registry, dict) else []
    hooks = registry.get("hooks", []) if isinstance(registry, dict) else []
    runtime_assets = registry.get("runtime_assets", []) if isinstance(registry, dict) else []
    lines.extend(
        [
            "",
            "## Registry Summary",
            "",
            f"- commands: `{len(commands) if isinstance(commands, list) else 0}`",
            f"- skills: `{len(reg_skills) if isinstance(reg_skills, list) else 0}`",
            f"- agents: `{len(agents) if isinstance(agents, list) else 0}`",
            f"- hooks: `{len(hooks) if isinstance(hooks, list) else 0}`",
            f"- runtime_assets: `{len(runtime_assets) if isinstance(runtime_assets, list) else 0}`",
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
    lines.append("")
    return lines


def render_contracts(spec: Dict[str, Any]) -> List[str]:
    """原样嵌入 runtime/test contract，方便审计时直接比对。"""
    runtime_contract = spec.get("runtime_contract", {})
    generated_runtime_contract = spec.get("generated_runtime_contract", {})
    target_publish_policy = spec.get("target_publish_policy", {})
    test_contract = spec.get("test_contract", {})
    return [
        "## Runtime Contract",
        "",
        f"```json\n{json.dumps(runtime_contract, ensure_ascii=False, indent=2)}\n```",
        "",
        "## Generated Runtime Contract",
        "",
        f"```json\n{json.dumps(generated_runtime_contract, ensure_ascii=False, indent=2)}\n```",
        "",
        "## Target Publish Policy",
        "",
        f"```json\n{json.dumps(target_publish_policy, ensure_ascii=False, indent=2)}\n```",
        "",
        "## Test Contract (Judgment Only)",
        "",
        f"```json\n{json.dumps(test_contract, ensure_ascii=False, indent=2)}\n```",
        "",
    ]


def render_host_capabilities(spec: Dict[str, Any]) -> List[str]:
    host_capabilities = spec.get("host_capabilities", [])
    lines = ["## Host Capabilities", ""]
    if not isinstance(host_capabilities, list) or not host_capabilities:
        return lines + ["- None", ""]
    for item in host_capabilities:
        if not isinstance(item, dict):
            continue
        bootstrap = item.get("bootstrap", {}) if isinstance(item.get("bootstrap"), dict) else {}
        outputs = bootstrap.get("project_local_outputs", []) if isinstance(bootstrap.get("project_local_outputs"), list) else []
        assets = bootstrap.get("assets", []) if isinstance(bootstrap.get("assets"), list) else []
        lines.append(
            f"- `{item.get('id', 'unknown')}` kind=`{item.get('kind', '-')}` required=`{item.get('required', False)}` "
            f"approval_required=`{item.get('approval_required', False)}` scope=`{bootstrap.get('scope', '-')}` "
            f"project_local_outputs=`{format_value(outputs)}` assets=`{len(assets)}`"
        )
    lines.append("")
    return lines


def render_agent_team_contract(spec: Dict[str, Any]) -> List[str]:
    contract = spec.get("agent_team_contract", {})
    lines = ["## Agent Team Contract", ""]
    if not isinstance(contract, dict) or not contract:
        return lines + ["- None", ""]
    lines.append(
        f"- enabled=`{format_value(contract.get('enabled'))}` "
        f"max_fan_out=`{format_value(contract.get('max_fan_out'))}` "
        f"join_policy=`{format_value(contract.get('join_policy'))}`"
    )
    roles = contract.get("roles", [])
    if isinstance(roles, list) and roles:
        lines.append("- roles:")
        for role in roles:
            if not isinstance(role, dict):
                continue
            lines.append(
                f"  - `{role.get('id', 'unknown')}` stages=`{format_value(role.get('ownership_stage_slots', []))}` "
                f"outputs=`{format_value(role.get('output_patterns', []))}`"
            )
    lines.append("")
    return lines


def render_view(spec: Dict[str, Any]) -> str:
    """组装 workflow spec 的完整 Markdown 视图。"""
    lines: List[str] = [
        "# Workflow View",
        "",
        f"_Generated at {utc_now()} from workflow-spec.yaml_",
        "",
    ]
    lines.extend(render_meta(spec.get("meta", {})))
    lines.extend(render_stage_flow(spec.get("stages", [])))
    lines.extend(render_intent_flows(spec))
    lines.extend(render_workflow_graph(spec))
    lines.extend(render_stages(spec.get("stages", [])))
    lines.extend(render_refs_and_constraints(spec))
    lines.extend(render_host_capabilities(spec))
    lines.extend(render_agent_team_contract(spec))
    lines.extend(render_contracts(spec))
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    """生成 Markdown 视图，并在需要时输出结构化结果。"""
    args = parse_args()
    spec_path = Path(args.spec).resolve()
    out_path = Path(args.out).resolve()
    payload = {"status": "PASS", "spec": str(spec_path), "out": str(out_path), "missing_top_keys": []}
    try:
        spec = load_spec(spec_path)
        payload["missing_top_keys"] = ensure_spec_shape(spec)
        render = render_view(spec)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(render, encoding="utf-8", newline="\n")
    except Exception as exc:
        payload["status"] = "FAIL"
        payload["error"] = str(exc)
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(f"Error: {exc}")
        return 1

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"Generated {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
